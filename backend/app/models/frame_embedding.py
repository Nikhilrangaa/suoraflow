"""FrameEmbedding SQLModel table — sampled video frames + CLIP embeddings."""
import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, ForeignKey, String
from sqlmodel import Field, SQLModel

CLIP_EMBEDDING_DIM = 512  # clip-ViT-B-32


def _new_id() -> str:
    return str(uuid.uuid4())


class FrameEmbedding(SQLModel, table=True):
    __tablename__ = "frame_embedding"

    id: str = Field(default_factory=_new_id, primary_key=True)
    # DB-level ON DELETE CASCADE: deleting an asset removes its frame index.
    asset_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("asset.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )
    frame_index: int = Field(default=0)
    timestamp: float = Field(default=0.0)  # seconds into the asset
    frame_path: str = Field(default="")  # JPEG under STORAGE_ROOT/frames/
    embedding: Any = Field(sa_column=Column(Vector(CLIP_EMBEDDING_DIM), nullable=False))
