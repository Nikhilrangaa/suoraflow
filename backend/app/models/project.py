"""Project SQLModel table."""
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(SQLModel, table=True):
    __tablename__ = "project"

    id: str = Field(default_factory=lambda: __import__("uuid").uuid4().__str__(), primary_key=True)
    name: str = Field(index=False, nullable=False)
    description: str = Field(default="")
    created_at: datetime = Field(default_factory=_utcnow)
