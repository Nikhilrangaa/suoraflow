"""Rough-cut generation request/response schemas."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.timeline import TimelineRead


class RoughCutRequest(BaseModel):
    script: str
    name: str = "Rough Cut"
    candidates_per_beat: int = Field(default=5, ge=1, le=10)


class BeatMatch(BaseModel):
    """Per-beat report entry: what (if anything) a script beat matched."""

    index: int
    beat_text: str
    matched: bool
    source: Optional[Literal["transcript", "visual"]] = None
    asset_id: Optional[str] = None
    asset_filename: Optional[str] = None
    start: Optional[float] = None
    end: Optional[float] = None
    score: Optional[float] = None
    method: Literal["llm", "embedding"]


class RoughCutResponse(BaseModel):
    timeline: TimelineRead
    beats: list[BeatMatch]
    method: Literal["llm", "embedding"]  # how selection was decided overall
