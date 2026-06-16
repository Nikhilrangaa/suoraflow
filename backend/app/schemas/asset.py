"""Asset request/response schemas — separate from the SQLModel table."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AssetRead(BaseModel):
    id: str
    project_id: str
    original_filename: str
    media_type: str
    ext: str
    size_bytes: int
    status: str
    error_message: Optional[str]
    # Audio fields
    sample_rate: Optional[int]
    channels: Optional[int]
    audio_codec: Optional[str]
    # Media fields
    duration: Optional[float]
    width: Optional[int]
    height: Optional[int]
    fps: Optional[float]
    created_at: datetime


class AssetStatus(BaseModel):
    id: str
    status: str
    error_message: Optional[str]
