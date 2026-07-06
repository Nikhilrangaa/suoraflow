"""Clip and timeline request/response schemas."""
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class ClipCreate(BaseModel):
    asset_id: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    label: str = ""

    @model_validator(mode="after")
    def end_after_start(self) -> "ClipCreate":
        if self.end <= self.start:
            raise ValueError("Clip end must be after start")
        return self


class ClipRead(BaseModel):
    id: str
    project_id: str
    asset_id: str
    asset_filename: str
    start: float
    end: float
    label: str
    created_at: datetime


class TimelineCreate(BaseModel):
    name: str = "Rough Cut"


class TimelineItemCreate(BaseModel):
    clip_id: str


class TimelineItemMove(BaseModel):
    position: int = Field(ge=0)


class TimelineItemRead(BaseModel):
    id: str
    position: int
    clip: ClipRead


class TimelineRead(BaseModel):
    id: str
    project_id: str
    name: str
    created_at: datetime
    items: list[TimelineItemRead]
    total_duration: float
