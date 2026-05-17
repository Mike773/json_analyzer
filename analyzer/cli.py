"""Интерактивный CLI-чат агента-аналитика метрик.

Поток старта: загрузка JSON в SQLite -> детерминированная аналитика ->
синхронизация кэша эмбеддингов в PostgreSQL -> печать сводки -> REPL.

Запуск из корня проекта:
    python -m analyzer.cli [путь_к_json]
"""
from __future__ import annotations

import sys
from typing import Any

from config import settings

from analyzer.agent import build_agent, synthesize_answer
from analyzer.analytics import build_summary, compute_analytics
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


def main() -> int:
    try:
        settings.validate()
    except RuntimeError as exc:
        print(f"Ошибка конфигурации: {exc}")
        return 1

    path = sys.argv[1] if len(sys.argv) > 1 else settings.default_dataset
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

    _print_summary(build_summary(store))

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

    print("\nГотов к вопросам. 'exit' или пустая строка — выход.")
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
        try:
            # Стадия 1: агент собирает данные инструментами.
            result = agent.invoke(
                {"messages": history + [HumanMessage(content=question)]}
            )
            # Стадия 2: финальный ответ из собранных данных без инструментов.
            answer = synthesize_answer(synth_model, question, result["messages"])
        except Exception as exc:
            print(f"Ошибка агента: {exc}")
            continue
        print(f"\n{answer}")
        history += [HumanMessage(content=question), AIMessage(content=answer)]
        history = history[-8:]

    pg.close()
    print("Завершено.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
