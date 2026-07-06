"""Clip and Timeline SQLModel tables."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, String, Text
from sqlmodel import Field, SQLModel


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Clip(SQLModel, table=True):
    __tablename__ = "clip"

    id: str = Field(default_factory=_new_id, primary_key=True)
    project_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("project.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )
    asset_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("asset.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )
    start: float = Field(default=0.0)  # seconds
    end: float = Field(default=0.0)  # seconds
    label: str = Field(default="", sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=_utcnow)


class Timeline(SQLModel, table=True):
    __tablename__ = "timeline"

    id: str = Field(default_factory=_new_id, primary_key=True)
    project_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("project.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )
    name: str = Field(default="Rough Cut")
    created_at: datetime = Field(default_factory=_utcnow)


class TimelineItem(SQLModel, table=True):
    __tablename__ = "timeline_item"

    id: str = Field(default_factory=_new_id, primary_key=True)
    timeline_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("timeline.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )
    clip_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("clip.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )
    position: int = Field(default=0)
