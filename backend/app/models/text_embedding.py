"""TextEmbedding SQLModel table — transcript chunks + their pgvector embeddings."""
import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, ForeignKey, String, Text
from sqlmodel import Field, SQLModel

EMBEDDING_DIM = 384  # all-MiniLM-L6-v2


def _new_id() -> str:
    return str(uuid.uuid4())


class TextEmbedding(SQLModel, table=True):
    __tablename__ = "text_embedding"

    id: str = Field(default_factory=_new_id, primary_key=True)
    # DB-level ON DELETE CASCADE: deleting an asset removes its embeddings.
    asset_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("asset.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )
    chunk_index: int = Field(default=0)
    start: float = Field(default=0.0)  # seconds
    end: float = Field(default=0.0)  # seconds
    text: str = Field(default="", sa_column=Column(Text, nullable=False))
    embedding: Any = Field(sa_column=Column(Vector(EMBEDDING_DIM), nullable=False))
