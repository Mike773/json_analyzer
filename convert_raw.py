"""Конвертер компактного raw-JSON в формат, который читает analyzer/loader.py.

Источник (см. raw_struct_data.jsonc): {"metrics": [<metric>, ...]}, где у метрики
есть поля metric_id/dt/bs/details/history/children_metrics. details — поэлементная
разбивка с тем же metric_id; history — снапшоты того же узла с другой dt/fact/plan/bs.

Цель (см. analyzer/loader.py и samples/test_metrics.json): {"me": <person>, "employees": []},
где у каждой метрики id/date/benchmark, а все элементные срезы и исторические
снапшоты — отдельные сиблинги с одинаковым id (различаются element и/или date).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _pick(detail: dict[str, Any], parent: dict[str, Any], key: str) -> Any:
    """Берёт key из detail, если задано (не None), иначе из parent."""
    if key in detail and detail[key] is not None:
        return detail[key]
    return parent.get(key)


def _history_clones(base: dict[str, Any], history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Возвращает клоны base с подменёнными dt/fact/plan/bs/calc_period из history."""
    clones: list[dict[str, Any]] = []
    for h in history or []:
        clone = dict(base)
        clone["date"] = h.get("dt", base.get("date"))
        clone["calc_period"] = h.get("calc_period", base.get("calc_period"))
        clone["fact"] = h.get("fact")
        clone["plan"] = h.get("plan")
        clone["benchmark"] = h.get("bs")
        clone["child_metrics"] = []
        clones.append(clone)
    return clones


def convert_metric(metric: dict[str, Any]) -> list[dict[str, Any]]:
    """Разворачивает одну raw-метрику в плоский список loader-узлов.

    Возвращает список, который родитель кладёт в child_metrics своего агрегата
    (или, для топ-уровня, в metrics).
    """
    out: list[dict[str, Any]] = []

    converted_children: list[dict[str, Any]] = []
    for child in metric.get("children_metrics") or []:
        converted_children.extend(convert_metric(child))

    has_fact = metric.get("fact") is not None

    if has_fact:
        aggregate = {
            "id": metric.get("metric_id"),
            "metric_name": metric.get("metric_name"),
            "metric_description": metric.get("metric_description"),
            "metric_type": metric.get("metric_type"),
            "measure_type": metric.get("measure_type"),
            "date": metric.get("dt"),
            "calc_period": metric.get("calc_period"),
            "fact": metric.get("fact"),
            "plan": metric.get("plan"),
            "benchmark": metric.get("bs"),
            "element": None,
            "child_metrics": converted_children,
        }
        if metric.get("influence_percent") is not None:
            aggregate["influent_percent"] = metric.get("influence_percent")
        out.append(aggregate)
        out.extend(_history_clones(aggregate, metric.get("history") or []))
    else:
        # Агрегат не эмитим; чтобы не потерять детей, поднимаем их на тот же
        # уровень, что и детали (вариант B из плана).
        out.extend(converted_children)

    for detail in metric.get("details") or []:
        node = {
            "id": detail.get("metric_id") or metric.get("metric_id"),
            "metric_name": metric.get("metric_name"),
            "metric_description": metric.get("metric_description"),
            "metric_type": _pick(detail, metric, "metric_type"),
            "measure_type": _pick(detail, metric, "measure_type"),
            "date": detail.get("dt") if detail.get("dt") is not None else metric.get("dt"),
            "calc_period": _pick(detail, metric, "calc_period"),
            "fact": detail.get("fact"),
            "plan": detail.get("plan") if detail.get("plan") is not None else metric.get("plan"),
            "benchmark": detail.get("bs") if detail.get("bs") is not None else metric.get("bs"),
            "element": detail.get("element_name"),
            "child_metrics": [],
        }
        infl = detail.get("influence_percent")
        if infl is None:
            infl = metric.get("influence_percent")
        if infl is not None:
            node["influent_percent"] = infl
        out.append(node)
        out.extend(_history_clones(node, detail.get("history") or []))

    return out


def convert_dataset(raw: dict[str, Any], person: dict[str, Any]) -> dict[str, Any]:
    """Оборачивает результат convert_metric в envelope {me, employees}."""
    metrics_out: list[dict[str, Any]] = []
    for m in raw.get("metrics") or []:
        metrics_out.extend(convert_metric(m))
    me = dict(person)
    me["metrics"] = metrics_out
    return {"me": me, "employees": []}


def _parse_tabnum(raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="путь к raw-JSON")
    parser.add_argument("--output", type=Path, required=True, help="куда писать развёрнутый JSON")
    parser.add_argument("--fio", default="Объект", help="ФИО для поля me.fio")
    parser.add_argument("--tabnum", default=None, help="табельный номер для me.tabnum")
    parser.add_argument("--post", default=None, help="должность для me.post")
    parser.add_argument("--depart", default=None, help="подразделение для me.depart")
    args = parser.parse_args()

    raw = json.loads(args.input.read_text(encoding="utf-8"))
    person = {
        "tabnum": _parse_tabnum(args.tabnum),
        "fio": args.fio,
        "post": args.post,
        "depart": args.depart,
    }
    result = convert_dataset(raw, person)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Записано: {args.output} ({len(result['me']['metrics'])} верхнеуровневых узлов)")


if __name__ == "__main__":
    main()
