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


def init_db() -> None:
    """Create the pgvector extension and all SQLModel tables."""
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
