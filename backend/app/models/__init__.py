"""Models package — import all tables so SQLModel.metadata registers them."""
from app.models.project import Project
from app.models.asset import Asset
from app.models.transcript_segment import TranscriptSegment
from app.models.text_embedding import TextEmbedding
from app.models.frame_embedding import FrameEmbedding
from app.models.clip import Clip, Timeline, TimelineItem

__all__ = [
    "Project",
    "Asset",
    "TranscriptSegment",
    "TextEmbedding",
    "FrameEmbedding",
    "Clip",
    "Timeline",
    "TimelineItem",
]
