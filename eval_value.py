"""Харнесс теста «польза для непонимающего руководителя».

Прогоняет 6 типовых ситуаций растерянного руководителя по каждому датасету и
складывает сырые исходы в eval_value_out/ для качественной оценки полезности.
Фактическую корректность проверяет отдельный eval_run.py — здесь оценивается,
получает ли пользу пользователь, который не разбирается в метриках.

Запуск из корня проекта:
    .venv/bin/python -m eval_value [--datasets ...] [--situations ...] [--out ...]
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
    brief_dataset,
    build_agent,
    extract_tool_transcript,
    run_gather,
    synthesize_answer,
)
from analyzer.analytics import (
    build_highlights,
    build_suggestions,
    build_summary,
    compute_analytics,
)
from analyzer.llm import build_chat_model
from analyzer.loader import load_dataset
from analyzer.pg_cache import PgCache, sync_embeddings
from analyzer.sqlite_store import SqliteStore
from analyzer.tools import build_tools

_OUT = Path("eval_value_out")

_DATASETS: dict[str, tuple[str, str]] = {
    "sample_good": ("samples/sample_good.json", "single"),
    "sample_weak": ("samples/sample_weak.json", "single"),
    "sample_rising": ("samples/sample_rising.json", "single"),
    "sample_declining": ("samples/sample_declining.json", "single"),
    "sample_stable": ("samples/sample_stable.json", "single"),
    "test_metrics": ("samples/test_metrics.json", "manager"),
    "test_metrics_agile": ("samples/test_metrics_agile.json", "agile"),
}

_SITUATION_IDS = ["S1", "S2", "S3", "S4", "S5", "S6"]


def _render_briefing(
    brief: str | None,
    highlights: list[dict[str, Any]],
    suggestions: list[str],
) -> str:
    """Текстовое представление стартового экрана (ситуация S1)."""
    parts: list[str] = []
    if brief:
        parts.append("ГЛАВНОЕ:\n" + brief.strip())
    if highlights:
        lines = ["На что посмотреть:"]
        for h in highlights:
            element = f" / {h['element']}" if h.get("element") else ""
            lines.append(
                f"  • [{h.get('kind')}] {h.get('person_fio')} — "
                f"{h.get('metric_name')}{element}"
            )
        parts.append("\n".join(lines))
    if suggestions:
        lines = ["С чего начать:"]
        for i, question in enumerate(suggestions, 1):
            lines.append(f"  {i}. {question}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts) if parts else "(пустой стартовый экран)"


def _term_metric(store: SqliteStore) -> str:
    """Метрика для ситуации S4 — самая проблемная (топ below_plan)."""
    rows = store.find_flags("below_plan").get("rows", [])
    if rows:
        return rows[0]["metric_name"]
    metrics = store.schema_overview()["metrics"]
    return metrics[0]["metric_name"] if metrics else "—"


def _situations(
    multi: bool, emp: str | None, term_metric: str, suggestions: list[str]
) -> dict[str, tuple[str, str | None]]:
    """Карта ситуаций: id -> (название, вопрос). S1 без вопроса (стартовый экран)."""
    if multi:
        s2 = "Как у нас в команде дела — всё нормально или есть проблемы?"
        s3 = "На что обратить внимание в команде в первую очередь и что мне предпринять?"
    else:
        s2 = f"Как дела у {emp} — всё нормально или есть проблемы?"
        s3 = f"{emp}: на что обратить внимание в первую очередь и что мне предпринять?"
    s6 = suggestions[1] if len(suggestions) > 1 else (suggestions[0] if suggestions else "")
    return {
        "S1": ("Холодный старт", None),
        "S2": ("Размытый вопрос о состоянии", s2),
        "S3": ("«Что мне делать»", s3),
        "S4": (
            "Непонятный термин",
            f"Что значит «{term_metric}» простыми словами и почему мне как "
            "руководителю это важно?",
        ),
        "S5": (
            "Запрос вне возможностей",
            "Дай прогноз: какие будут результаты в следующем месяце?",
        ),
        "S6": ("Переход по подсказке", s6),
    }


def _run_dataset(
    name: str, path: str, kind: str, pg: PgCache, situations: list[str]
) -> int:
    print(f"\n=== {name} ({path}) ===", flush=True)
    store = SqliteStore()
    store.load(load_dataset(path))
    compute_analytics(store)
    sync_embeddings(store, pg)

    summary = build_summary(store)
    highlights = build_highlights(store)
    suggestions = build_suggestions(store, highlights)
    people = store.schema_overview()["people"]
    emps = [p for p in people if not p["person_is_me"]]
    emp = emps[0]["person_fio"] if emps else None
    specs = _situations(len(emps) > 1, emp, _term_metric(store), suggestions)

    tools = build_tools(store, pg)
    agent = build_agent(tools, store.schema_overview())
    synth = build_chat_model()

    cells: list[dict[str, Any]] = []
    out_path = _OUT / f"{name}.json"
    for sid in situations:
        label, question = specs[sid]
        print(f"  [{sid}] {label}", flush=True)
        t0 = time.time()
        cell: dict[str, Any] = {
            "dataset": name,
            "situation": sid,
            "label": label,
            "question": question,
        }
        try:
            if sid == "S1":
                try:
                    brief = brief_dataset(synth, summary, highlights)
                except Exception as exc:  # noqa: BLE001 — бриф необязателен
                    brief = None
                    cell["brief_error"] = repr(exc)
                cell.update(
                    input="(нет вопроса — стартовый экран инструмента)",
                    output=_render_briefing(brief, highlights, suggestions),
                    transcript=None,
                    tool_calls=0,
                    completed=True,
                    error=None,
                )
            else:
                gathered, completed = run_gather(
                    agent, [HumanMessage(content=question)]
                )
                answer = synthesize_answer(synth, question, gathered)
                transcript, n_calls = extract_tool_transcript(gathered)
                cell.update(
                    input=question,
                    output=answer,
                    transcript=transcript,
                    tool_calls=n_calls,
                    completed=completed,
                    error=None,
                )
        except Exception as exc:  # noqa: BLE001 — сбой ситуации не рушит прогон
            cell.update(
                input=question,
                output=None,
                transcript=None,
                tool_calls=0,
                completed=False,
                error=f"{exc!r}\n{traceback.format_exc()}",
            )
        cell["elapsed_sec"] = round(time.time() - t0, 1)
        cells.append(cell)
        out_path.write_text(
            json.dumps(cells, ensure_ascii=False, indent=1, default=str),
            encoding="utf-8",
        )
        if cell["error"]:
            status = f"ERROR: {cell['error'].splitlines()[0]}"
        else:
            status = (
                f"{len(cell['output'] or '')} символов, "
                f"tool_calls={cell['tool_calls']}, completed={cell['completed']}"
            )
        print(f"  [{sid}] -> {status} ({cell['elapsed_sec']}s)", flush=True)

    store.conn.close()
    return len(cells)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Тест полезности агента для непонимающего руководителя."
    )
    parser.add_argument(
        "--datasets", default="", help="список датасетов через запятую (по умолчанию все)"
    )
    parser.add_argument(
        "--situations", default="", help="список id ситуаций через запятую (S1..S6)"
    )
    parser.add_argument(
        "--out", default="eval_value_out", help="каталог для дампов прогона"
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

    situations = [
        s.strip().upper() for s in args.situations.split(",") if s.strip()
    ] or list(_SITUATION_IDS)
    bad = [s for s in situations if s not in _SITUATION_IDS]
    if bad:
        print(f"Неизвестные ситуации: {bad}. Доступно: {_SITUATION_IDS}")
        return 1

    global _OUT
    _OUT = Path(args.out)
    _OUT.mkdir(parents=True, exist_ok=True)
    print(f"Чат-провайдер: {settings.llm_provider} (модель: {settings.llm_model})")
    print(f"Датасеты: {names}; ситуации: {situations}; вывод: {_OUT}/")

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
            total += _run_dataset(name, path, kind, pg, situations)
    finally:
        pg.close()

    print(
        f"\nГотово: {total} ситуаций за {round((time.time() - t0) / 60, 1)} мин. "
        f"Дампы в {_OUT}/"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
