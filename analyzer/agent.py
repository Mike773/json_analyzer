"""Двухстадийный агент-аналитик.

Стадия 1 (сбор) — `create_agent` из LangChain 1.x вызывает инструменты в цикле.
У GigaChat запрос С ФУНКЦИЯМИ ограничен ~4096 токенами, поэтому выдача инструментов
держится компактной.

Стадия 2 (синтез) — отдельный вызов чат-модели БЕЗ инструментов получает вопрос и
все собранные данные обычным текстом. Без функций доступен полный контекст модели
(у GigaChat-2-Max — 128k), поэтому финальный ответ можно собрать из всех данных
сразу и без шума tool-схем.
"""
from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from analyzer.llm import build_chat_model

_SYSTEM_PROMPT = """\
Ты — универсальный агент-аналитик метрик. Данные о метриках и людях доступны тебе
ТОЛЬКО через инструменты — у тебя нет прямого доступа к базе. Твоя задача на этом
шаге — вызвать нужные инструменты и собрать данные; финальный ответ пользователю
будет составлен отдельно по собранным данным.

Принципы работы:
1. Метрики могут быть из любого домена (колл-центр, разработчики, клиентские
   менеджеры, руководство и т.д.). НЕ предполагай смысл метрики по названию —
   при необходимости вызови describe_metric.
2. В аргументах инструментов используй ТОЧНЫЕ значения из «Состава датасета»
   ниже: точные названия метрик, должностей, значений element и даты периодов.
   Относительные периоды ('первая неделя', 'последняя', 'прошлая') переводи в
   конкретные даты из списка периодов.
3. Если пользователь называет метрику, продукт (element) или человека неточно
   или описательно — разреши это через resolve_entity.
4. Направление метрики критично: metric_type 'прямая' — чем больше, тем лучше;
   'обратная' — чем меньше, тем лучше.
5. Производная аналитика уже посчитана — пользуйся полями результатов
   (plan_status, benchmark_status, wow_change_*, trend, peer_rank, is_anomaly)
   и инструментом find_flags. Не пересчитывай то, что уже готово.
6. Строго tools-only: ты не пишешь SQL. Если вопрос невозможно решить имеющимися
   инструментами — честно скажи об этом и предложи переформулировать.
7. Не выдумывай числа: вызывай инструменты для каждого нужного факта.

Собери все данные, необходимые для полного ответа на вопрос пользователя.
"""

_SYNTHESIS_PROMPT = """\
Ты — аналитик метрик. Тебе дан вопрос пользователя и данные, уже собранные
инструментами из базы. Составь по этим данным точный и полный ответ на русском.

Правила:
- Опирайся ТОЛЬКО на приведённые данные. Ничего не додумывай и не пересчитывай.
- Имена людей, названия метрик, продукты (element) и числа переноси ДОСЛОВНО из
  данных — не склоняй, не сокращай, не округляй сверх данного.
- Учитывай направление метрики: 'прямая' — больше значит лучше; 'обратная' —
  меньше значит лучше.
- Если в данных есть ошибка или их недостаточно для ответа — честно скажи об этом,
  не подставляй похожие значения.
- Отвечай по делу: конкретные числа, имена, периоды.
"""


def _format_facts(overview: dict[str, Any]) -> str:
    """Компактная сводка состава датасета для системного промпта."""
    dates = overview.get("dates") or []
    metric_names = sorted({m["metric_name"] for m in overview.get("metrics", [])})
    people = overview.get("people") or []
    posts = sorted({p["person_post"] for p in people if p.get("person_post")})
    departs = sorted({p["person_depart"] for p in people if p.get("person_depart")})
    elements = overview.get("elements") or []
    managers = sum(1 for p in people if p.get("person_is_me"))

    lines = [
        "СОСТАВ ЗАГРУЖЕННОГО ДАТАСЕТА (используй эти точные значения в аргументах):",
        f"- Периоды по порядку ('первая неделя' = первый): {', '.join(dates)}",
        f"- Метрики: {'; '.join(metric_names)}",
        f"- Должности: {', '.join(posts)}",
        f"- Подразделения: {', '.join(departs)}",
        f"- Значения element (продукты/разрезы): {', '.join(elements)}",
        f"- Людей: {len(people)} ({managers} рук. + {len(people) - managers} сотр.). "
        "Человека по неточному имени ищи через resolve_entity или list_people.",
    ]
    return "\n".join(lines)


def _text(msg: Any) -> str:
    """Извлекает текст из сообщения (content — строка или список блоков)."""
    content = getattr(msg, "content", msg)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return str(content)


def build_agent(tools: list[Any], overview: dict[str, Any]) -> Any:
    """Стадия 1: агент сбора данных поверх чат-модели и инструментов."""
    model = build_chat_model()
    system_prompt = _SYSTEM_PROMPT + "\n\n" + _format_facts(overview)
    return create_agent(model=model, tools=tools, system_prompt=system_prompt)


def extract_tool_transcript(messages: list[Any]) -> tuple[str, int]:
    """Собирает из сообщений стадии 1 транскрипт «вызов инструмента -> результат».

    Возвращает (текст транскрипта, число вызовов инструментов).
    """
    results: dict[str, str] = {}
    for msg in messages:
        if isinstance(msg, ToolMessage):
            results[msg.tool_call_id] = _text(msg)

    blocks: list[str] = []
    for msg in messages:
        for call in getattr(msg, "tool_calls", None) or []:
            args = ", ".join(
                f"{k}={v!r}" for k, v in (call.get("args") or {}).items()
            )
            result = results.get(call.get("id"), "(результат отсутствует)")
            blocks.append(f"{len(blocks) + 1}. {call.get('name')}({args}) ->\n{result}")
    return "\n\n".join(blocks), len(blocks)


def synthesize_answer(model: Any, question: str, messages: list[Any]) -> str:
    """Стадия 2: финальный ответ из собранных данных вызовом модели без инструментов."""
    transcript, tool_calls = extract_tool_transcript(messages)
    if tool_calls == 0:
        # Инструменты не вызывались — стадия 1 уже дала прямой ответ или отказ.
        return _text(messages[-1]) if messages else ""
    user_content = (
        f"Вопрос пользователя: {question}\n\n"
        f"Данные, собранные инструментами из базы:\n{transcript}"
    )
    response = model.invoke(
        [SystemMessage(content=_SYNTHESIS_PROMPT), HumanMessage(content=user_content)]
    )
    return _text(response)
