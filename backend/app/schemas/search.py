"""Search request/response schemas."""
from pydantic import BaseModel, Field, field_validator


class SearchRequest(BaseModel):
    query: str
    limit: int = Field(default=10, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Search query must not be empty")
        return v


class SearchResult(BaseModel):
    asset_id: str
    asset_filename: str
    media_type: str
    chunk_id: str
    text: str
    start: float
    end: float
    score: float  # cosine similarity, higher is better


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total: int
