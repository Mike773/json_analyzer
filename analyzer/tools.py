"""Типизированные инструменты агента.

Агент НИКОГДА не пишет SQL — он только вызывает эти инструменты с параметрами.
Каждый инструмент внутри выполняет параметрический запрос к in-memory SQLite
(метрики + производная аналитика) либо семантический поиск в pgvector-кэше.

Выдача намеренно компактная: пустые поля убираются, числа округляются —
контекст чат-модели ограничен.
"""
import json
from typing import Any

from langchain_core.tools import StructuredTool

from analyzer import analytics, embeddings
from analyzer.pg_cache import PgCache
from analyzer.sqlite_store import SqliteStore

# Поля строки метрики, отдаваемые модели (остальное скрываем для экономии токенов).
_ROW_KEYS = (
    "person_fio",
    "metric_name",
    "metric_type",
    "date",
    "element",
    "fact",
    "plan",
    "benchmark",
    "plan_status",
    "plan_dev_pct",
    "benchmark_status",
    "wow_change_pct",
    "trend",
    "peer_rank",
    "peer_count",
    "zscore",
    "is_anomaly",
)


def _clean(value: Any) -> Any:
    return round(value, 2) if isinstance(value, float) else value


def _compact_row(row: dict[str, Any]) -> dict[str, Any]:
    """Оставляет только значимые поля строки метрики без пустых значений."""
    return {k: _clean(row[k]) for k in _ROW_KEYS if row.get(k) is not None}


def _strip(row: dict[str, Any]) -> dict[str, Any]:
    """Убирает пустые значения и округляет числа, сохраняя все ключи."""
    return {k: _clean(v) for k, v in row.items() if v is not None}


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _pack(result: dict[str, Any], curated: bool = True) -> str:
    """Сериализует результат со списком строк, ужимая строки."""
    packed = {k: v for k, v in result.items() if k != "rows"}
    transform = _compact_row if curated else _strip
    packed["rows"] = [transform(r) for r in result.get("rows", [])]
    return _dump(packed)


def build_tools(store: SqliteStore, pg: PgCache) -> list[StructuredTool]:
    """Собирает набор инструментов, замкнутых на конкретные хранилища."""

    def _unknown_metric(metric: str) -> str | None:
        """JSON-ошибка, если метрики с таким именем нет; иначе None.

        Без этой проверки инструмент молча вернул бы пустой результат, и агент
        мог зациклиться, повторяя неверный вызов (ФИО или мусор вместо метрики).
        """
        if store.metric_type_of(metric) is not None:
            return None
        return _dump(
            {
                "error": f"Метрика '{metric}' не найдена. Здесь нужно ТОЧНОЕ "
                "название метрики — не человек, не продукт, не произвольный текст.",
                "hint": "человека передавай в person, продукт — в element; "
                "точные названия метрик смотри в schema_overview или подбери "
                "через resolve_entity(kind='metric'). Если фильтр по метрике не "
                "нужен — просто не передавай этот аргумент.",
            }
        )

    def schema_overview() -> str:
        """Обзор загруженного датасета: метрики с их типами и единицами, значения
        element (продукты/разрезы), люди и диапазон дат. Семантику метрик не
        предполагай — смотри по факту."""
        return _dump(store.schema_overview())

    def resolve_entity(text: str, kind: str) -> str:
        """Разрешает нечёткую формулировку в каноничное имя сущности.
        kind: 'metric' — название метрики (поиск по названиям и описаниям),
        'element' — значение поля element (продукт/разрез), 'person' — сотрудник.
        Используй, когда метрика/продукт/человек названы неточно или описательно."""
        kind = (kind or "").strip().lower()
        if kind == "person":
            return _dump(
                {"kind": "person", "matches": store.list_people(name_query=text)[:10]}
            )
        if kind == "metric":
            search_kinds = ["metric_name", "metric_description"]
        elif kind == "element":
            search_kinds = ["element"]
        else:
            return _dump({"error": "kind должен быть 'metric', 'element' или 'person'"})
        vector = embeddings.embed_query(text)
        return _dump(
            {"kind": kind, "matches": pg.search(vector, kinds=search_kinds, top_k=5)}
        )

    def describe_metric(metric: str) -> str:
        """Описание метрики, её тип ('прямая' — чем больше, тем лучше; 'обратная' —
        чем меньше, тем лучше), единица измерения и период расчёта. Вызывай перед
        интерпретацией значений: направление метрики критично."""
        result = store.describe_metric(metric)
        if result is None:
            return _dump(
                {"error": f"Метрика '{metric}' не найдена", "hint": "используй resolve_entity"}
            )
        return _dump(result)

    def get_metric(
        metric: str,
        person: str | None = None,
        element: str | None = None,
        date: str | None = None,
    ) -> str:
        """Значения метрики (fact/plan/benchmark) плюс производная аналитика:
        статусы отклонений, динамика, тренд, peer-ранг, флаг аномалии.
        person — ФИО (или часть) либо табельный номер; date — неделя (YYYY-MM-DD).
        element НЕ указан = агрегат по метрике; чтобы получить конкретный
        продукт/разрез — задай element явно."""
        unknown = _unknown_metric(metric)
        if unknown:
            return unknown
        return _pack(store.get_metric(metric, person=person, element=element, date=date))

    def compare(
        metric: str,
        person: str | None = None,
        element: str | None = None,
        dates: list[str] | None = None,
    ) -> str:
        """Динамика метрики по неделям (поля wow_change_pct и trend) для одного
        человека. person ОБЯЗАТЕЛЕН. element не указан = агрегат. Чтобы найти, у
        кого сильнее всего спад/рост по всем сотрудникам, используй find_flags."""
        unknown = _unknown_metric(metric)
        if unknown:
            return unknown
        return _pack(store.compare(metric, person=person, element=element, dates=dates))

    def rank(
        metric: str,
        date: str,
        element: str | None = None,
        post: str | None = None,
    ) -> str:
        """Рейтинг сотрудников по метрике на конкретную неделю. Направление уже
        учтено: peer_rank=1 — лучший. element не указан = агрегат по сотруднику;
        post — фильтр по должности."""
        unknown = _unknown_metric(metric)
        if unknown:
            return unknown
        return _pack(store.rank(metric, date, element=element, post=post))

    def aggregate(
        metric: str,
        group_by: str,
        date: str | None = None,
        element: str | None = None,
    ) -> str:
        """Агрегация значений метрики (avg/min/max/sum/count) по группам.
        group_by: 'person' | 'element' | 'date' | 'post'."""
        unknown = _unknown_metric(metric)
        if unknown:
            return unknown
        result = store.aggregate(metric, group_by, date=date, element=element)
        if "groups" in result:
            result = dict(result)
            result["groups"] = [_strip(g) for g in result["groups"]]
        return _dump(result)

    def metric_tree(
        metric: str | None = None,
        person: str | None = None,
        date: str | None = None,
    ) -> str:
        """Иерархия метрик: метрика metric (или метрики верхнего уровня) со всеми
        дочерними child_metrics И аналитикой по каждому узлу (plan_status,
        plan_dev_pct, benchmark_status, benchmark_dev_pct, trend, wow_change_pct,
        influent_percent). ОДИН вызов раскладывает метрику на компоненты со всеми
        отклонениями — не нужно дёргать get_metric по каждому компоненту. Для
        разбора состава метрики задавай metric и person (и date — иначе строк
        много)."""
        if metric is not None:
            unknown = _unknown_metric(metric)
            if unknown:
                return unknown
        return _pack(
            store.metric_tree(name=metric, person=person, date=date), curated=False
        )

    def list_people(
        role: str | None = None,
        post: str | None = None,
        depart: str | None = None,
        name_query: str | None = None,
    ) -> str:
        """Список людей в датасете. role: 'me' (руководитель) | 'employee'.
        name_query — подстрока ФИО для поиска."""
        return _dump(
            {
                "people": store.list_people(
                    role=role, post=post, depart=depart, name_query=name_query
                )
            }
        )

    def find_flags(
        kind: str,
        date: str | None = None,
        metric: str | None = None,
        element: str | None = None,
    ) -> str:
        """Выборка предрассчитанных проблемных/заметных строк, ОТСОРТИРОВАННАЯ по
        силе: первая строка — самая значимая.
        kind: 'anomaly' — статистические выбросы (|z-score| выше порога);
        'below_plan' — факт хуже плана с учётом направления метрики (проблемные
        места); 'above_plan' — факт лучше плана (сильные стороны), первая строка —
        самое сильное перевыполнение; 'trend' — кто сильнее всего просел или вырос
        в динамике (первая строка — самый сильный спад). Чтобы сфокусировать
        выдачу, задавай metric (и date). Фильтры date/metric/element опциональны."""
        # metric — необязательный фильтр; модель иногда присылает сюда мусор.
        # Неизвестное значение игнорируем и отдаём общий скан, а не пустоту.
        if metric and store.metric_type_of(metric) is None:
            metric = None
        return _pack(store.find_flags(kind, date=date, metric=metric, element=element))

    def analytics_summary() -> str:
        """Стартовая детерминированная сводка: охват датасета, средние по ключевым
        метрикам на последней неделе, топ аномалий, счётчики трендов."""
        return _dump(analytics.build_summary(store))

    specs = [
        (schema_overview, "schema_overview"),
        (resolve_entity, "resolve_entity"),
        (describe_metric, "describe_metric"),
        (get_metric, "get_metric"),
        (compare, "compare"),
        (rank, "rank"),
        (aggregate, "aggregate"),
        (metric_tree, "metric_tree"),
        (list_people, "list_people"),
        (find_flags, "find_flags"),
        (analytics_summary, "analytics_summary"),
    ]
    return [
        StructuredTool.from_function(func=func, name=name, description=func.__doc__)
        for func, name in specs
    ]
