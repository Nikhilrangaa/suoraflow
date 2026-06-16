"""Project request/response schemas — separate from the SQLModel table."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class ProjectCreate(BaseModel):
    name: str
    description: str = ""

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Project name must not be empty")
        return v


class ProjectRead(BaseModel):
    id: str
    name: str
    description: str
    created_at: datetime
    asset_count: int = 0


class ProjectList(BaseModel):
    projects: list[ProjectRead]
    total: int
