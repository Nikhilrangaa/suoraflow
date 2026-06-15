"""Application configuration — all values from environment variables."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    postgres_user: str = "suoraflow"
    postgres_password: str = "suoraflow_secret"
    postgres_db: str = "suoraflow"
    database_url: str = (
        "postgresql+psycopg://suoraflow:suoraflow_secret@db:5432/suoraflow"
    )

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # CORS — never allow wildcard
    frontend_url: str = "http://localhost:5173"

    # Storage
    storage_root: str = "/storage"
    max_upload_mb: int = 500

    # ASR / Whisper
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"

    # Diarization (optional) — empty string means disabled
    hf_token: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
