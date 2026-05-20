"""Кэш эмбеддингов в PostgreSQL + pgvector.

Хранит вектора названий/описаний метрик и значений поля element. Ключ кэша —
sha256 от (kind, текст): один и тот же текст эмбеддится ровно один раз, даже
между запусками и между доменами. Кэш персистентный и накапливается.
"""
from __future__ import annotations

import hashlib
from typing import Any

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg import sql

from config import settings


def make_hash(kind: str, content: str) -> str:
    """Ключ кэша: устойчив к совпадению текста между разными kind."""
    return hashlib.sha256(f"{kind}\x00{content}".encode("utf-8")).hexdigest()


class PgCache:
    """Доступ к таблице metric_embeddings в PostgreSQL."""

    def __init__(self, dsn: str | None = None, dim: int | None = None) -> None:
        self.dsn = dsn or settings.postgres_dsn
        self.dim = dim or settings.embedding_dim
        self.schema = settings.postgres_schema or ""
        self.conn = psycopg.connect(self.dsn, autocommit=True)
        self._init_search_path()
        self._init_schema()
        register_vector(self.conn)

    def _init_search_path(self) -> None:
        if not self.schema:
            return
        with self.conn.cursor() as cur:
            cur.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                    sql.Identifier(self.schema)
                )
            )
            cur.execute(
                sql.SQL("SET search_path TO {}, public, ext").format(
                    sql.Identifier(self.schema)
                )
            )

    def _existing_dim(self, cur: Any) -> int | None:
        """Размерность вектора в уже существующей таблице, или None."""
        cur.execute(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid = to_regclass('metric_embeddings') AND attname = 'embedding'"
        )
        row = cur.fetchone()
        if row is None or row[0] is None or row[0] <= 0:
            return None
        return int(row[0])

    def _init_schema(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            # Кэш можно безопасно пересоздать, если поменялась модель эмбеддингов
            # (другая размерность вектора).
            existing = self._existing_dim(cur)
            if existing is not None and existing != self.dim:
                print(
                    f"  размерность эмбеддингов изменилась ({existing} -> {self.dim}), "
                    "кэш metric_embeddings пересоздаётся"
                )
                cur.execute("DROP TABLE metric_embeddings")
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS metric_embeddings (
                    id           BIGSERIAL PRIMARY KEY,
                    kind         TEXT NOT NULL,
                    content      TEXT NOT NULL,
                    content_hash TEXT NOT NULL UNIQUE,
                    canonical    TEXT NOT NULL,
                    embedding    vector({self.dim}) NOT NULL,
                    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_metric_embeddings_kind "
                "ON metric_embeddings(kind)"
            )

    def existing_hashes(self, hashes: list[str]) -> set[str]:
        if not hashes:
            return set()
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT content_hash FROM metric_embeddings "
                "WHERE content_hash = ANY(%s)",
                (list(hashes),),
            )
            return {row[0] for row in cur.fetchall()}

    def upsert(self, items: list[tuple[str, str, str, list[float]]]) -> int:
        """Вставляет новые вектора. items: (kind, content, canonical, embedding)."""
        if not items:
            return 0
        with self.conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO metric_embeddings "
                "(kind, content, content_hash, canonical, embedding) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (content_hash) DO NOTHING",
                [
                    (kind, content, make_hash(kind, content), canonical, Vector(embedding))
                    for kind, content, canonical, embedding in items
                ],
            )
        return len(items)

    def search(
        self,
        query_embedding: list[float],
        kinds: list[str] | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Поиск ближайших по косинусу записей кэша."""
        query_vector = Vector(query_embedding)
        params: list[Any] = [query_vector]
        clause = ""
        if kinds:
            clause = "WHERE kind = ANY(%s)"
            params.append(list(kinds))
        params.append(query_vector)
        params.append(top_k)
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT kind, canonical, content,
                       1 - (embedding <=> %s) AS similarity
                FROM metric_embeddings
                {clause}
                ORDER BY embedding <=> %s
                LIMIT %s
                """,
                params,
            )
            return [
                {
                    "kind": kind,
                    "canonical": canonical,
                    "content": content,
                    "similarity": round(float(similarity), 4),
                }
                for kind, canonical, content, similarity in cur.fetchall()
            ]

    def row_count(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM metric_embeddings")
            return cur.fetchone()[0]

    def close(self) -> None:
        self.conn.close()


def sync_embeddings(store: Any, pg: PgCache) -> dict[str, int]:
    """Досчитывает в кэш эмбеддинги для текстов загруженного датасета.

    Эмбеддятся только те metric_name/metric_description/element, которых ещё
    нет в кэше (проверка по content_hash). Возвращает статистику.
    """
    from analyzer import embeddings as emb_mod

    raw: list[tuple[str, str, str]] = []
    for name in store.distinct_metric_names():
        raw.append(("metric_name", name, name))
    for name, description in store.distinct_descriptions():
        raw.append(("metric_description", description, name))
    for element in store.distinct_elements():
        raw.append(("element", element, element))

    seen: set[tuple[str, str]] = set()
    unique: list[tuple[str, str, str]] = []
    for kind, content, canonical in raw:
        if not content:
            continue
        key = (kind, content)
        if key in seen:
            continue
        seen.add(key)
        unique.append((kind, content, canonical))

    by_hash = {make_hash(k, c): (k, c, ca) for k, c, ca in unique}
    existing = pg.existing_hashes(list(by_hash.keys()))
    missing = [meta for h, meta in by_hash.items() if h not in existing]

    added = 0
    if missing:
        vectors = emb_mod.embed_documents([content for _, content, _ in missing])
        if vectors and len(vectors[0]) != pg.dim:
            raise RuntimeError(
                f"Размерность эмбеддинга {len(vectors[0])} не совпадает с "
                f"таблицей ({pg.dim}). Задайте EMBEDDING_DIM={len(vectors[0])} "
                f"и пересоздайте таблицу metric_embeddings."
            )
        added = pg.upsert(
            [
                (kind, content, canonical, vector)
                for (kind, content, canonical), vector in zip(missing, vectors)
            ]
        )

    return {"total": len(unique), "added": added, "cached": len(unique) - added}
