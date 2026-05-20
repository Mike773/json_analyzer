"""Строит компактный дайджест прогона для ручной верификации."""
import json
import re

DATASETS = [
    "sample_good", "sample_weak", "sample_rising", "sample_declining",
    "sample_stable", "test_metrics", "test_metrics_agile",
]


def fnum(s):
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def decimals_in(text):
    """Десятичные числа из текста (целые игнорируем — слишком шумно)."""
    out = []
    for m in re.findall(r"\d+[.,]\d+", text or ""):
        v = fnum(m)
        if v is not None:
            out.append((m, v))
    return out


def all_nums(text):
    out = []
    for m in re.findall(r"\d+(?:[.,]\d+)?", text or ""):
        v = fnum(m)
        if v is not None:
            out.append(v)
    return out


def matched(v, pool):
    for t in pool:
        if abs(v - t) < 0.5:
            return True
        if v != 0 and abs(v - t) / abs(v) < 0.02:
            return True
    return False


def tool_calls(transcript):
    return re.findall(r"\d+\.\s+(\w+)\((.*?)\)\s*->", transcript or "")


def truth_block(ds):
    snap = json.load(open(f"eval_out/{ds}_snapshot.json"))
    ov = snap["overview"]
    out = [f"### TRUTH: {ds}"]
    emps = [p for p in ov["people"] if not p["person_is_me"]]
    out.append(f"employees={len(emps)} latest={snap['latest_date']} dates={ov['dates']}")
    out.append("metrics(all): " + "; ".join(
        f"{m['metric_name']}[{m['metric_type']}]" for m in ov["metrics"]))
    out.append("level1: " + ", ".join(snap["level1_metrics"]))
    sm = snap["summary"]
    out.append(f"trend_counts_level1={sm['trend_counts_level1']}")
    out.append("by_metric_latest=" + json.dumps(sm["by_metric_latest"], ensure_ascii=False))

    def rows(kind, fields, n=6):
        rs = snap["flags"][kind].get("rows", [])[:n]
        return [{f: r.get(f) for f in fields} for r in rs]

    out.append("FLAGS below_plan top: " + json.dumps(
        rows("below_plan", ["person_fio", "metric_name", "element", "fact",
                            "plan", "plan_dev_pct", "plan_status"]), ensure_ascii=False))
    out.append("FLAGS above_plan top: " + json.dumps(
        rows("above_plan", ["person_fio", "metric_name", "element", "fact",
                            "plan_dev_pct"]), ensure_ascii=False))
    out.append("FLAGS anomaly top: " + json.dumps(
        rows("anomaly", ["person_fio", "metric_name", "element", "fact",
                         "zscore", "peer_count"]), ensure_ascii=False))
    out.append("FLAGS trend(worst wow) top: " + json.dumps(
        rows("trend", ["person_fio", "metric_name", "element", "fact",
                       "wow_change_pct", "trend"]), ensure_ascii=False))
    for m, pm in snap["per_metric"].items():
        desc = pm.get("describe") or {}
        by_date = [(g["grp"], round(g["avg"], 2) if g["avg"] is not None else None)
                   for g in (pm["by_date"].get("groups") or [])]
        rk = pm.get("rank_latest") or {}
        rk_rows = [{"p": r.get("person_fio"), "rank": r.get("peer_rank"),
                    "fact": r.get("fact"), "plan_status": r.get("plan_status")}
                   for r in (rk.get("rows") or [])[:6]]
        out.append(f"  metric «{m}» type={desc.get('metric_type')} "
                   f"calc={desc.get('calc_period')}")
        out.append(f"    avg_by_date={by_date}")
        out.append(f"    rank_latest_top={json.dumps(rk_rows, ensure_ascii=False)}")
    return "\n".join(out)


def main():
    parts = []
    for ds in DATASETS:
        parts.append(truth_block(ds))
        parts.append("")
        cells = json.load(open(f"eval_out/{ds}_run.json"))
        for c in cells:
            ans = c.get("answer") or ""
            tr = c.get("transcript") or ""
            tnums = all_nums(tr)
            unmatched = [m for m, v in decimals_in(ans) if not matched(v, tnums)]
            calls = tool_calls(tr)
            call_str = "; ".join(
                f"{n}({a[:90]})" for n, a in calls) or "(нет вызовов)"
            parts.append(f"## {ds} / {c['id']}  completed={c.get('completed')} "
                         f"tool_calls={c.get('tool_calls')}")
            parts.append(f"Q: {c['question']}")
            if c.get("error"):
                parts.append(f"ERROR: {c['error'].splitlines()[0]}")
            parts.append("ANCHOR: " + json.dumps(c.get("anchor"), ensure_ascii=False))
            parts.append("CALLS: " + call_str)
            if unmatched:
                parts.append("!! числа из ответа без совпадения в транскрипте: "
                             + ", ".join(unmatched))
            parts.append("ANSWER:\n" + ans)
            parts.append("")
    open("eval_out/_digest.txt", "w", encoding="utf-8").write("\n".join(parts))
    print("digest ->", "eval_out/_digest.txt",
          len("\n".join(parts)), "chars")


if __name__ == "__main__":
    main()
