"""Фабрика чат-модели: OpenAI или GigaChat — выбор по настройке LLM_PROVIDER."""
from __future__ import annotations

from typing import Any

from config import settings


def build_chat_model() -> Any:
    """Возвращает чат-модель активного провайдера (обе поддерживают tool-calling)."""
    provider = settings.llm_provider

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.openai_api_key,
            temperature=0,
        )

    if provider == "gigachat":
        from langchain_gigachat import GigaChat

        return GigaChat(
            credentials=settings.gigachat_credentials,
            scope=settings.gigachat_scope,
            model=settings.llm_model,
            verify_ssl_certs=settings.gigachat_verify_ssl,
        )

    raise RuntimeError(
        f"Неизвестный LLM_PROVIDER: {provider!r} (ожидается 'openai' или 'gigachat')"
    )
