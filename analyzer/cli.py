"""Интерактивный CLI-чат агента-аналитика метрик.

Поток старта: загрузка JSON в SQLite -> детерминированная аналитика ->
синхронизация кэша эмбеддингов в PostgreSQL -> печать сводки -> REPL.

Запуск из корня проекта:
    python -m analyzer.cli [путь_к_json]
"""
from __future__ import annotations

import argparse
from typing import Any

from config import settings

from analyzer.agent import (
    brief_dataset,
    build_agent,
    render_agent_graph,
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

_EXIT_WORDS = {"exit", "quit", "выход", "q"}


def _print_summary(summary: dict[str, Any]) -> None:
    scope = summary["scope"]
    dates = scope["dates"]
    line = "=" * 64
    print(f"\n{line}\nСВОДКА ПО ДАТАСЕТУ\n{line}")
    print(f"Людей: {scope['people']} (сотрудников: {scope['employees']})")
    print(
        f"Типов метрик: {scope['metric_types']} | "
        f"разрезов (element): {scope['elements']} | "
        f"строк метрик: {scope['metric_rows']}"
    )
    if dates:
        print(f"Периоды: {dates[0]} … {dates[-1]} ({len(dates)} нед.)")
    print(f"\nПоследняя неделя: {summary['latest_date']}")
    for bm in summary["by_metric_latest"]:
        print(
            f"  • {bm['metric']} [{bm['metric_type']}]: среднее={bm['avg_fact']}, "
            f"хуже плана={bm['below_plan']}, аномалий={bm['anomalies']}"
        )
    trends = summary["trend_counts_level1"]
    print(
        f"\nТренды (метрики 1-го уровня): рост={trends['рост']}, "
        f"падение={trends['падение']}, стабильно={trends['стабильно']}"
    )
    anomalies = summary["top_anomalies_latest"]
    if anomalies:
        print("\nТоп аномалий на последней неделе:")
        for a in anomalies:
            element = f" / {a['element']}" if a["element"] else ""
            print(
                f"  ! {a['person_fio']} — {a['metric_name']}{element}: "
                f"факт={a['fact']}, z={a['zscore']}"
            )
    print(line)


def _highlight_line(h: dict[str, Any]) -> str:
    """Строка одной находки для блока «На что посмотреть»."""
    kind = h["kind"]
    element = f" / {h['element']}" if h.get("element") else ""
    if kind == "trend":
        wow = h.get("wow_change_pct")
        label = "спад" if (wow is not None and wow < 0) else "рост"
        # Процент недельного изменения у метрик со знаком/около нуля разлетается
        # до абсурдных величин — направление несёт сам ярлык, число опускаем.
        detail = ""
    elif kind == "anomaly":
        label = "аномалия"
        zscore = h.get("zscore")
        detail = f"z={zscore}" if zscore is not None else ""
    else:
        label = "хуже плана" if kind == "below_plan" else "сильная сторона"
        dev = h.get("plan_dev_pct")
        detail = f"отклонение от плана {dev:+.1f}%" if dev is not None else ""
    detail = f": {detail}" if detail else ""
    return f"  • [{label}] {h['person_fio']} — {h['metric_name']}{element}{detail}"


def _print_suggestions(suggestions: list[str]) -> None:
    """Нумерованный список наводящих вопросов (на старте и по команде «?»)."""
    if not suggestions:
        return
    print("\nС чего начать (введите вопрос или «?» — повторить список):")
    for i, question in enumerate(suggestions, 1):
        print(f"  {i}. {question}")


def _print_briefing(
    brief: str | None,
    highlights: list[dict[str, Any]],
    suggestions: list[str],
) -> None:
    """Стартовый экран поверх сводки: абзац «Главное», находки, вопросы."""
    line = "=" * 64
    if brief:
        print(f"\n{line}\nГЛАВНОЕ\n{line}")
        print(brief.strip())
    if highlights:
        print("\nНа что посмотреть:")
        for h in highlights:
            print(_highlight_line(h))
    _print_suggestions(suggestions)
    print(line)


def main() -> int:
    try:
        settings.validate()
    except RuntimeError as exc:
        print(f"Ошибка конфигурации: {exc}")
        return 1

    parser = argparse.ArgumentParser(
        prog="analyzer.cli",
        description="Интерактивный CLI-чат агента-аналитика метрик.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=settings.default_dataset,
        help="путь к JSON-датасету (по умолчанию: %(default)s)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="печатать шаги выполнения агента (вызовы инструментов и результаты)",
    )
    parser.add_argument(
        "--graph",
        action="store_true",
        help="напечатать граф агента (Mermaid) при запуске",
    )
    args = parser.parse_args()
    path = args.path

    print(f"Чат-провайдер: {settings.llm_provider} (модель: {settings.llm_model})")
    print(f"Датасет: {path}")

    try:
        rows = load_dataset(path)
    except FileNotFoundError:
        print(f"Файл не найден: {path}")
        return 1

    store = SqliteStore()
    print(f"Загружено строк метрик: {store.load(rows)}")

    print("Расчёт детерминированной аналитики...")
    compute_analytics(store)

    print("Синхронизация кэша эмбеддингов (PostgreSQL + pgvector)...")
    try:
        from analyzer import embeddings

        embedding_dim = len(embeddings.embed_query("проба размерности"))
        pg = PgCache(dim=embedding_dim)
        stats = sync_embeddings(store, pg)
    except Exception as exc:
        print(f"Ошибка PostgreSQL/эмбеддингов: {exc}")
        print("Проверь, что поднят контейнер: docker compose up -d")
        return 1
    print(
        f"  эмбеддинги: всего {stats['total']}, "
        f"новых {stats['added']}, из кэша {stats['cached']}"
    )

    tools = build_tools(store, pg)
    try:
        # Стадия 1 — агент сбора (с инструментами). Стадия 2 — модель синтеза
        # (без инструментов), вызывается отдельно с полным контекстом.
        agent = build_agent(tools, store.schema_overview())
        synth_model = build_chat_model()
    except Exception as exc:
        print(f"Не удалось создать агента: {exc}")
        pg.close()
        return 1

    if args.graph:
        line = "=" * 64
        print(f"\n{line}\nГРАФ АГЕНТА (Mermaid)\n{line}")
        print(render_agent_graph(agent))
        print(line)

    summary = build_summary(store)
    _print_summary(summary)

    # Стартовый экран: детерминированные находки и наводящие вопросы — всегда;
    # связный LLM-абзац — по возможности, его сбой не критичен.
    highlights = build_highlights(store)
    suggestions = build_suggestions(store, highlights)
    try:
        brief = brief_dataset(synth_model, summary, highlights)
    except Exception as exc:
        brief = None
        print(f"(LLM-обзор недоступен: {exc})")
    _print_briefing(brief, highlights, suggestions)

    print(
        "\nГотов к вопросам. 'exit' или пустая строка — выход, "
        "'?' — список вопросов."
    )
    from langchain_core.messages import AIMessage, HumanMessage

    # История — только пары «вопрос/ответ» без промежуточных вызовов инструментов:
    # контекст чат-модели ограничен, шум прошлых ходов не тащим.
    history: list[Any] = []
    while True:
        try:
            question = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question or question.lower() in _EXIT_WORDS:
            break
        if question == "?":
            _print_suggestions(suggestions)
            continue
        try:
            # Стадия 1: агент собирает данные инструментами.
            gathered, completed = run_gather(
                agent,
                history + [HumanMessage(content=question)],
                verbose=args.verbose,
            )
            # Стадия 2: финальный ответ из собранных данных без инструментов.
            answer = synthesize_answer(synth_model, question, gathered)
        except Exception as exc:
            print(f"Ошибка агента: {exc}")
            continue
        if not completed:
            answer += (
                "\n\n(Примечание: агент не уложился в лимит шагов сбора — "
                "ответ собран по тем данным, что успели получить.)"
            )
        print(f"\n{answer}")
        history += [HumanMessage(content=question), AIMessage(content=answer)]
        history = history[-8:]

    pg.close()
    print("Завершено.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
