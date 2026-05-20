"""Настройки приложения: читаются из окружения (.env при запуске из корня проекта)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# Дефолтная модель чата под активного провайдера, если LLM_MODEL не задан.
_DEFAULT_CHAT_MODEL = {"gigachat": "GigaChat-2-Max", "openai": "gpt-4o"}


def _bool(raw: str | None, default: bool = False) -> bool:
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    # Активный провайдер чат-модели: "openai" | "gigachat".
    llm_provider: str
    # Имя чат-модели у активного провайдера.
    llm_model: str
    # OpenAI (нужен при llm_provider == "openai").
    openai_api_key: str
    # GigaChat (нужен при llm_provider == "gigachat" И всегда — для эмбеддингов).
    gigachat_credentials: str
    gigachat_scope: str
    gigachat_verify_ssl: bool
    gigachat_embeddings_model: str
    # Кастомный API-эндпоинт GigaChat-совместимого шлюза. Пусто => дефолт библиотеки.
    gigachat_base_url: str
    # PostgreSQL с расширением pgvector.
    postgres_dsn: str
    # Схема для кэша metric_embeddings. Пусто => search_path не трогается.
    postgres_schema: str
    # Порог |z-score| для пометки строки метрики как аномалии.
    anomaly_zscore_threshold: float
    # Размерность вектора эмбеддингов (фиксируется под модель GigaChat).
    embedding_dim: int
    # Путь к датасету по умолчанию.
    default_dataset: str

    def validate(self) -> None:
        if self.llm_provider not in ("openai", "gigachat"):
            raise RuntimeError(
                f"LLM_PROVIDER должен быть 'openai' или 'gigachat', получено: {self.llm_provider!r}"
            )
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise RuntimeError("LLM_PROVIDER=openai, но не задан OPENAI_API_KEY")
        if self.llm_provider == "gigachat" and not self.gigachat_credentials and not self.gigachat_base_url:
            raise RuntimeError(
                "LLM_PROVIDER=gigachat: задайте GIGACHAT_CREDENTIALS "
                "или GIGACHAT_BASE_URL (для no-auth шлюза)"
            )
        # Эмбеддинги всегда считаются через GigaChat-совместимый API.
        if not self.gigachat_credentials and not self.gigachat_base_url:
            raise RuntimeError(
                "Не задан ни GIGACHAT_CREDENTIALS, ни GIGACHAT_BASE_URL — нужен один из них: "
                "эмбеддинги всегда идут через GigaChat-совместимый API"
            )


def load_settings() -> Settings:
    provider = os.getenv("LLM_PROVIDER", "gigachat").strip().lower()
    model = os.getenv("LLM_MODEL", "").strip() or _DEFAULT_CHAT_MODEL.get(provider, "")
    return Settings(
        llm_provider=provider,
        llm_model=model,
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        gigachat_credentials=os.getenv("GIGACHAT_CREDENTIALS", "").strip(),
        gigachat_scope=os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS").strip(),
        gigachat_verify_ssl=_bool(os.getenv("GIGACHAT_VERIFY_SSL"), default=False),
        gigachat_embeddings_model=os.getenv(
            "GIGACHAT_EMBEDDINGS_MODEL", "EmbeddingsGigaR"
        ).strip(),
        gigachat_base_url=os.getenv("GIGACHAT_BASE_URL", "").strip(),
        postgres_dsn=os.getenv(
            "POSTGRES_DSN", "postgresql://analyzer:analyzer@localhost:5432/analyzer"
        ).strip(),
        postgres_schema=os.getenv("POSTGRES_SCHEMA", "").strip(),
        anomaly_zscore_threshold=float(os.getenv("ANOMALY_ZSCORE_THRESHOLD", "2.0")),
        embedding_dim=int(os.getenv("EMBEDDING_DIM", "2560")),
        default_dataset=os.getenv("DEFAULT_DATASET", "test_metrics.json").strip(),
    )


settings = load_settings()
