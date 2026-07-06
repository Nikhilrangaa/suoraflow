"""TranscriptSegment SQLModel table."""
import uuid

from sqlalchemy import Column, ForeignKey, String, Text
from sqlmodel import Field, SQLModel


def _new_id() -> str:
    return str(uuid.uuid4())


class TranscriptSegment(SQLModel, table=True):
    __tablename__ = "transcript_segment"

    id: str = Field(default_factory=_new_id, primary_key=True)
    # DB-level ON DELETE CASCADE: deleting an asset can never orphan segments.
    asset_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("asset.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )
    seg_index: int = Field(default=0)  # ordering within the asset
    start: float = Field(default=0.0)  # seconds
    end: float = Field(default=0.0)  # seconds
    text: str = Field(default="", sa_column=Column(Text, nullable=False))
    speaker: str = Field(default="Speaker 1")
