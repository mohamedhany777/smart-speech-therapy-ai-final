"""
Central application configuration.

All configuration is loaded from environment variables (or a `.env` file in
local development). Nothing here should ever hard-code secrets, credentials,
or environment-specific values — see section 83 of the project spec
("Never hard-code API keys, passwords, database URLs...").
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    APP_NAME: str = "Smart Speech Therapy AI"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # --- Security ---
    SECRET_KEY: str = "insecure-dev-key-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # --- Database ---
    DATABASE_URL: str = "sqlite:///./dev.db"

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # --- Storage ---
    STORAGE_BACKEND: str = "local"
    STORAGE_LOCAL_PATH: str = "./storage"
    S3_ENDPOINT_URL: str = ""
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_BUCKET_NAME: str = "smart-speech-therapy"

    # --- Vector database (Knowledge Base / RAG) ---
    # "embedded" runs Qdrant in-process against local disk (single-process
    # only — fine for dev/small deployments). Set QDRANT_URL (e.g.
    # http://qdrant:6333) to point at a real standalone Qdrant server
    # instead for production/multi-worker deployments; no other code needs
    # to change, only how the client is constructed.
    QDRANT_MODE: str = "embedded"
    QDRANT_PATH: str = "./qdrant_storage"
    QDRANT_URL: str = ""

    # --- LLM / Embeddings (optional — RAG works without these, using the
    # TF-IDF baseline and extractive-excerpt responses; setting these
    # upgrades to real embeddings + generated answers) ---
    OPENAI_API_KEY: str = ""
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    # --- Web retrieval (optional — Layer 2 knowledge fallback) ---
    TAVILY_API_KEY: str = ""

    # --- Speech-to-text backend ---
    # "pocketsphinx" (default): fully offline, no download, English only,
    # lower accuracy — always works out of the box.
    # "whisper": real neural ASR via Hugging Face Transformers, genuinely
    # multilingual (including Arabic), much higher accuracy — but the
    # model must be downloaded from huggingface.co on first use (a few
    # hundred MB to ~1.5GB depending on WHISPER_MODEL_SIZE), so it needs
    # real internet access and `pip install -r requirements.txt` to have
    # pulled in torch/transformers.
    # --- Speech-to-text backend ---
    # "auto" (default): uses the Hugging Face Inference API (real,
    # multilingual Whisper — including Arabic) automatically when
    # HF_API_TOKEN is set; otherwise falls back to PocketSphinx (fully
    # offline, no setup, English only, lower accuracy).
    # "pocketsphinx": force the offline baseline regardless of HF_API_TOKEN.
    # "hf_inference": force the Hugging Face Inference API (needs HF_API_TOKEN).
    # "whisper": force a LOCAL Whisper download via transformers/torch —
    # real multilingual ASR that needs no external API calls at request
    # time, but needs enough local RAM to hold the model (not recommended
    # on a 512MB-RAM free-tier instance; fine on a larger one). Requires
    # `pip install -r requirements-whisper.txt`.
    ASR_BACKEND: str = "auto"
    WHISPER_MODEL_SIZE: str = "openai/whisper-base"

    # --- Hugging Face Inference API (optional — real trained models,
    # called remotely so they need almost no local RAM/CPU; see
    # app/services/hf_inference.py) ---
    HF_API_TOKEN: str = ""
    HF_ASR_MODEL: str = "openai/whisper-large-v3-turbo"
    HF_EMBEDDING_MODEL: str = "intfloat/multilingual-e5-base"
    HF_STUTTERING_MODEL: str = "vocametrix/wav2vec2-xlsr-53-stuttering-classification"
    # Optional cross-encoder reranking pass over the top RAG candidates
    # (BAAI/bge-reranker-v2-m3 verified live on the HF Inference API — see
    # app/services/model_registry.py). Empty string = disabled (default),
    # since it adds one extra HTTP round-trip per assistant query; the
    # base retrieval (embedding similarity) is used as-is when unset.
    HF_RERANKER_MODEL: str = ""

    # --- Rate limiting ---
    RATE_LIMIT_LOGIN_PER_MINUTE: int = 5
    RATE_LIMIT_AI_PER_MINUTE: int = 20

    # --- Bootstrap admin (seed script only, never used at runtime auth) ---
    FIRST_ADMIN_EMAIL: str = "admin@example.com"
    FIRST_ADMIN_PASSWORD: str = "change-me-strong-password"
    # Optional: seed one SPECIALIST account too, so the therapy-plan review
    # flow (spec section 16 — approval must be SPECIALIST-only, not ADMIN)
    # has a real, usable account out of the box instead of being untestable
    # until someone manually creates one. Empty email = skip seeding it.
    FIRST_SPECIALIST_EMAIL: str = "specialist@example.com"
    FIRST_SPECIALIST_PASSWORD: str = "change-me-strong-password"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — env is read once per process."""
    return Settings()


settings = get_settings()
