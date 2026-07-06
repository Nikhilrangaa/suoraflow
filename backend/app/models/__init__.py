"""Models package — import all tables so SQLModel.metadata registers them."""
from app.models.project import Project
from app.models.asset import Asset
from app.models.transcript_segment import TranscriptSegment
from app.models.text_embedding import TextEmbedding

__all__ = ["Project", "Asset", "TranscriptSegment", "TextEmbedding"]
