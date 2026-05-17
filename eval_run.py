"""Харнесс комплексного тестового прогона агента-аналитика.

Прогоняет полный двухстадийный агент по каждому (датасет × вопрос) и
складывает сырые дампы в eval_out/ для последующей верификации. Сам вердиктов
НЕ выносит — только собирает: ответ, транскрипт инструментов, метаданные и
детерминированный «эталонный снимок» датасета.

Запуск из корня проекта:
    .venv/bin/python -m eval_run [--datasets a,b,...] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import time
import traceback
from pathlib import Path
from typing import Any

from config import settings
from langchain_core.messages import HumanMessage

from analyzer import embeddings
from analyzer.agent import (
    build_agent,
    extract_tool_transcript,
    run_gather,
    synthesize_answer,
)
from analyzer.analytics import _trend, build_summary, compute_analytics
from analyzer.llm import build_chat_model
from analyzer.loader import load_dataset
from analyzer.pg_cache import PgCache, sync_embeddings
from analyzer.sqlite_store import SqliteStore
from analyzer.tools import build_tools

_OUT = Path("eval_out")

# Датасет -> (путь, вид набора вопросов).
_DATASETS: dict[str, tuple[str, str]] = {
    "sample_good": ("samples/sample_good.json", "single"),
    "sample_weak": ("samples/sample_weak.json", "single"),
    "sample_rising": ("samples/sample_rising.json", "single"),
    "sample_declining": ("samples/sample_declining.json", "single"),
    "sample_stable": ("samples/sample_stable.json", "single"),
    "test_metrics": ("samples/test_metrics.json", "manager"),
    "test_metrics_agile": ("samples/test_metrics_agile.json", "agile"),
}

# Наборы вопросов: (id, шаблон). {emp} подставляется ФИО единственного оператора.
_QSETS: dict[str, list[tuple[str, str]]] = {
    "single": [
        ("E1", "{emp}: в чём сейчас главная проблема и насколько это критично?"),
        ("E2", "{emp} за последние недели растёт или падает?"),
        ("E3", "По каким метрикам {emp} выполняет план, а по каким — нет?"),
        ("E4", "Разложи AHT у {emp} по компонентам — где дальше всего от бенчмарка?"),
        ("E5", "У {emp} хорошая доля переводов?"),
        ("E6", "Что конкретно посоветуешь {emp} сделать в первую очередь?"),
        ("E7", "Сравни {emp} с другими операторами сектора."),
    ],
    "manager": [
        ("M1", "На кого обратить внимание в первую очередь и почему?"),
        ("M2", "Кто не выполнил план по производительности на последней неделе?"),
        ("M3", "Топ-5 операторов по производительности за последнюю неделю."),
        ("M4", "У кого самая сильная аномалия и в чём она?"),
        ("M5", "Какая метрика сектора просела сильнее всего и почему? Разложи по факторам."),
        ("M6", "На каких продуктах у сектора худший AHT?"),
        ("M7", "У кого лучшая доля переводов?"),
        ("M8", "Дай 3 точки роста для сектора."),
    ],
    "agile": [
        ("A1", "На кого обратить внимание в первую очередь и почему?"),
        ("A2", "Кто не выполняет план и по каким метрикам?"),
        ("A3", "Составь рейтинг сотрудников по ключевой метрике за последнюю неделю."),
        ("A4", "У кого самая сильная аномалия?"),
        ("A5", "Какая метрика просела сильнее всего и почему?"),
        ("A6", "Разложи самую проблемную составную метрику на компоненты."),
        ("A7", "Дай 3 точки роста для команды."),
        ("A8", "Какая выручка у команды за квартал?"),
    ],
}


def _level1_metrics(store: SqliteStore) -> list[str]:
    return [
        r["metric_name"]
        for r in store.conn.execute(
            "SELECT DISTINCT metric_name FROM metrics WHERE depth = 1 "
            "ORDER BY metric_name"
        )
    ]


def _snapshot(store: SqliteStore) -> dict[str, Any]:
    """Детерминированный эталонный снимок датасета (без LLM)."""
    overview = store.schema_overview()
    dates = overview["dates"]
    latest = dates[-1] if dates else None
    level1 = _level1_metrics(store)
    flags = {
        kind: store.find_flags(kind, date=latest)
        for kind in ("below_plan", "above_plan", "anomaly", "trend")
    }
    flags["trend_all_weeks"] = store.find_flags("trend")
    per_metric: dict[str, Any] = {}
    for m in level1:
        per_metric[m] = {
            "describe": store.describe_metric(m),
            "by_date": store.aggregate(m, "date"),
            "by_person": store.aggregate(m, "person"),
            "rank_latest": store.rank(m, latest) if latest else None,
        }
    return {
        "overview": overview,
        "summary": build_summary(store),
        "level1_metrics": level1,
        "latest_date": latest,
        "flags": flags,
        "per_metric": per_metric,
    }


def _anchor(qid: str, store: SqliteStore, snap: dict[str, Any], emp: str | None) -> Any:
    """Детерминированный эталон для вопросов, где истина вычислима кодом.

    Возвращает компактный dict с ожидаемыми фактами либо None. Анкер
    некритичен — при ошибке фиксируется поле anchor_error.
    """
    latest = snap["latest_date"]
    level1 = snap["level1_metrics"]
    try:
        if qid == "E2":
            main = "Производительность" if "Производительность" in level1 else (
                level1[0] if level1 else None
            )
            if not main:
                return None
            rows = store.compare(main, person=emp).get("rows", [])
            facts = [r.get("fact") for r in rows if r.get("fact") is not None]
            return {
                "metric": main,
                "facts_by_week": facts,
                "expected_trend": _trend(facts),
                "trend_field": rows[0].get("trend") if rows else None,
            }
        if qid == "E3":
            status = {}
            for m in level1:
                rows = store.get_metric(m, person=emp, date=latest).get("rows", [])
                status[m] = rows[0].get("plan_status") if rows else None
            return {"latest": latest, "plan_status_by_metric": status}
        if qid in ("E5", "M7"):
            return {
                "metric": "Доля переводов",
                "metric_type": store.metric_type_of("Доля переводов"),
                "note": "обратная => меньше = лучше",
            }
        if qid == "E7":
            emps = [p for p in snap["overview"]["people"] if not p["person_is_me"]]
            return {
                "operator_count": len(emps),
                "note": "peer-сравнение невозможно при одном операторе",
            }
        if qid == "M2":
            rows = store.find_flags(
                "below_plan", metric="Производительность", date=latest
            ).get("rows", [])
            return {
                "metric": "Производительность",
                "latest": latest,
                "below_plan_people": sorted({r.get("person_fio") for r in rows}),
            }
        if qid == "M3":
            rows = store.rank("Производительность", latest).get("rows", []) if latest else []
            return {
                "metric": "Производительность",
                "latest": latest,
                "top5": [
                    {"person": r.get("person_fio"), "rank": r.get("peer_rank"),
                     "fact": r.get("fact")}
                    for r in rows[:5]
                ],
            }
        if qid in ("M4", "A4"):
            rows = snap["flags"]["anomaly"].get("rows", [])
            top = rows[0] if rows else None
            return {
                "top_anomaly": None if not top else {
                    "person": top.get("person_fio"),
                    "metric": top.get("metric_name"),
                    "element": top.get("element"),
                    "zscore": top.get("zscore"),
                }
            }
        if qid in ("M5", "A5"):
            rows = snap["flags"]["trend"].get("rows", [])
            top = rows[0] if rows else None
            return {
                "worst_trend": None if not top else {
                    "person": top.get("person_fio"),
                    "metric": top.get("metric_name"),
                    "element": top.get("element"),
                    "wow_change_pct": top.get("wow_change_pct"),
                    "trend": top.get("trend"),
                }
            }
        if qid == "A2":
            by_metric = {}
            for m in level1:
                rows = store.find_flags("below_plan", metric=m, date=latest).get(
                    "rows", []
                )
                people = sorted({r.get("person_fio") for r in rows})
                if people:
                    by_metric[m] = people
            return {"latest": latest, "below_plan_by_metric": by_metric}
        if qid == "A3":
            return {
                "level1_metrics": level1,
                "note": "ранг по каждой метрике — в snapshot.per_metric[*].rank_latest",
            }
        if qid == "A8":
            return {
                "all_metric_names": [r["metric_name"] for r in snap["overview"]["metrics"]],
                "note": "проверить, что метрики «выручка»/revenue нет",
            }
    except Exception as exc:  # noqa: BLE001 — анкер некритичен
        return {"anchor_error": repr(exc)}
    return None


def _run_dataset(
    name: str, path: str, kind: str, pg: PgCache, limit: int, qfilter: set[str]
) -> int:
    print(f"\n=== {name} ({path}) ===", flush=True)
    store = SqliteStore()
    store.load(load_dataset(path))
    compute_analytics(store)
    sync_embeddings(store, pg)

    snap = _snapshot(store)
    (_OUT / f"{name}_snapshot.json").write_text(
        json.dumps(snap, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
    )

    people = snap["overview"]["people"]
    emps = [p for p in people if not p["person_is_me"]]
    emp = emps[0]["person_fio"] if emps else None

    tools = build_tools(store, pg)
    agent = build_agent(tools, store.schema_overview())
    synth = build_chat_model()

    qset = _QSETS[kind]
    if qfilter:
        qset = [(qid, t) for qid, t in qset if qid in qfilter]
    elif limit:
        qset = qset[:limit]

    cells: list[dict[str, Any]] = []
    run_path = _OUT / f"{name}_run.json"
    for qid, template in qset:
        question = template.format(emp=emp) if kind == "single" else template
        print(f"  [{qid}] {question}", flush=True)
        t0 = time.time()
        cell: dict[str, Any] = {
            "id": qid,
            "dataset": name,
            "question": question,
            "anchor": _anchor(qid, store, snap, emp),
        }
        try:
            gathered, completed = run_gather(agent, [HumanMessage(content=question)])
            answer = synthesize_answer(synth, question, gathered)
            transcript, n_calls = extract_tool_transcript(gathered)
            cell.update(
                answer=answer,
                transcript=transcript,
                tool_calls=n_calls,
                completed=completed,
                error=None,
            )
        except Exception as exc:  # noqa: BLE001 — сбой ячейки не рушит прогон
            cell.update(
                answer=None,
                transcript=None,
                tool_calls=0,
                completed=False,
                error=f"{exc!r}\n{traceback.format_exc()}",
            )
        cell["elapsed_sec"] = round(time.time() - t0, 1)
        cells.append(cell)
        run_path.write_text(
            json.dumps(cells, ensure_ascii=False, indent=1, default=str),
            encoding="utf-8",
        )
        if cell["error"]:
            status = f"ERROR: {cell['error'].splitlines()[0]}"
        else:
            status = (
                f"{cell['tool_calls']} calls, completed={cell['completed']}, "
                f"{len(cell['answer'] or '')} chars"
            )
        print(f"  [{qid}] -> {status} ({cell['elapsed_sec']}s)", flush=True)

    store.conn.close()
    return len(cells)


def main() -> int:
    parser = argparse.ArgumentParser(description="Тестовый прогон агента-аналитика.")
    parser.add_argument(
        "--datasets", default="", help="список датасетов через запятую (по умолчанию все)"
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="первые N вопросов на датасет (0 = все)"
    )
    parser.add_argument(
        "--questions", default="", help="фильтр id вопросов через запятую (напр. E3,M5)"
    )
    parser.add_argument(
        "--out", default="eval_out", help="каталог для дампов прогона"
    )
    args = parser.parse_args()

    try:
        settings.validate()
    except RuntimeError as exc:
        print(f"Ошибка конфигурации: {exc}")
        return 1

    names = [n.strip() for n in args.datasets.split(",") if n.strip()] or list(_DATASETS)
    unknown = [n for n in names if n not in _DATASETS]
    if unknown:
        print(f"Неизвестные датасеты: {unknown}. Доступно: {list(_DATASETS)}")
        return 1

    global _OUT
    _OUT = Path(args.out)
    _OUT.mkdir(parents=True, exist_ok=True)
    qfilter = {q.strip().upper() for q in args.questions.split(",") if q.strip()}
    print(f"Чат-провайдер: {settings.llm_provider} (модель: {settings.llm_model})")
    print(
        f"Датасеты: {names}; "
        f"вопросы: {sorted(qfilter) if qfilter else (args.limit or 'все')}; "
        f"вывод: {_OUT}/"
    )

    try:
        dim = len(embeddings.embed_query("проба размерности"))
        pg = PgCache(dim=dim)
    except Exception as exc:  # noqa: BLE001
        print(f"Ошибка PostgreSQL/эмбеддингов: {exc}")
        print("Проверь, что поднят контейнер: docker compose up -d")
        return 1

    t0 = time.time()
    total = 0
    try:
        for name in names:
            path, kind = _DATASETS[name]
            total += _run_dataset(name, path, kind, pg, args.limit, qfilter)
    finally:
        pg.close()

    print(
        f"\nГотово: {total} вопросов за {round((time.time() - t0) / 60, 1)} мин. "
        f"Дампы в {_OUT}/"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
