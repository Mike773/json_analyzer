"""Клиент эмбеддингов GigaChat.

Эмбеддинги всегда считаются через GigaChat — независимо от того, какой провайдер
выбран для чат-модели. Это фиксирует размерность вектора в pgvector.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from config import settings


@lru_cache(maxsize=1)
def get_embeddings() -> Any:
    """Ленивая инициализация клиента GigaChatEmbeddings (один на процесс)."""
    from langchain_gigachat import GigaChatEmbeddings

    kwargs: dict[str, Any] = {
        "model": settings.gigachat_embeddings_model,
        "verify_ssl_certs": settings.gigachat_verify_ssl,
    }
    if settings.gigachat_credentials:
        kwargs["credentials"] = settings.gigachat_credentials
        kwargs["scope"] = settings.gigachat_scope
    if settings.gigachat_base_url:
        kwargs["base_url"] = settings.gigachat_base_url
    return GigaChatEmbeddings(**kwargs)


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Считает эмбеддинги для набора текстов (для наполнения кэша)."""
    return get_embeddings().embed_documents(list(texts))


def embed_query(text: str) -> list[float]:
    """Считает эмбеддинг одного поискового запроса."""
    return get_embeddings().embed_query(text)
