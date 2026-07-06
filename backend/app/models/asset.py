"""Asset SQLModel table."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, ForeignKey, String
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Asset(SQLModel, table=True):
    __tablename__ = "asset"

    id: str = Field(primary_key=True)
    # DB-level ON DELETE CASCADE as defense-in-depth: even a direct project
    # delete can't orphan asset rows. The service still removes files from disk.
    project_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("project.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )
    original_filename: str = Field(default="")  # display only, never used in paths
    stored_path: str = Field(default="")
    media_type: str = Field(default="")  # "video" | "audio"
    ext: str = Field(default="")
    size_bytes: int = Field(default=0)
    status: str = Field(default="uploaded")
    error_message: Optional[str] = Field(default=None)

    # Audio fields (filled by Phase 2 pipeline)
    sample_rate: Optional[int] = Field(default=None)
    channels: Optional[int] = Field(default=None)
    audio_codec: Optional[str] = Field(default=None)

    # Video/media fields (filled by Phase 2 pipeline)
    duration: Optional[float] = Field(default=None)
    width: Optional[int] = Field(default=None)
    height: Optional[int] = Field(default=None)
    fps: Optional[float] = Field(default=None)

    # VAD stats (filled by Phase 2 pipeline)
    speech_ratio: Optional[float] = Field(default=None)  # 0..1 fraction of speech
    vad_segment_count: Optional[int] = Field(default=None)

    # Derived artifacts (paths under STORAGE_ROOT, server-generated)
    audio_path: Optional[str] = Field(default=None)  # extracted mono 16k WAV
    waveform_path: Optional[str] = Field(default=None)  # peaks JSON

    created_at: datetime = Field(default_factory=_utcnow)
