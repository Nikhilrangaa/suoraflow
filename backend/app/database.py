"""Database engine, session dependency, and schema initialisation."""
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, SQLModel, create_engine, text

from app.config import get_settings


def _build_engine():  # type: ignore[return]
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        echo=False,
    )


# Lazy singleton — built once on first access
_engine = None


def get_engine():  # type: ignore[return]
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


# Idempotent column additions for existing volumes. SQLModel's create_all only
# creates missing TABLES — it never alters existing ones — so every column added
# after a table first shipped needs a line here to keep single-command boot
# working against old pgdata volumes.
_MIGRATIONS = [
    "ALTER TABLE asset ADD COLUMN IF NOT EXISTS speech_ratio FLOAT",
    "ALTER TABLE asset ADD COLUMN IF NOT EXISTS vad_segment_count INTEGER",
    "ALTER TABLE asset ADD COLUMN IF NOT EXISTS audio_path VARCHAR",
    "ALTER TABLE asset ADD COLUMN IF NOT EXISTS waveform_path VARCHAR",
    # HNSW vector index for cosine search — better than ivfflat for a corpus
    # that grows row by row (no training step, no recall cliff when small).
    "CREATE INDEX IF NOT EXISTS ix_text_embedding_embedding "
    "ON text_embedding USING hnsw (embedding vector_cosine_ops)",
    "CREATE INDEX IF NOT EXISTS ix_frame_embedding_embedding "
    "ON frame_embedding USING hnsw (embedding vector_cosine_ops)",
]


def init_db() -> None:
    """Create the pgvector extension, all SQLModel tables, and run migrations."""
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    SQLModel.metadata.create_all(engine)
    with engine.connect() as conn:
        for stmt in _MIGRATIONS:
            conn.execute(text(stmt))
        conn.commit()


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
