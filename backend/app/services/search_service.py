"""
search_service.py — Semantic search over transcript chunk embeddings.

The query is embedded with the same MiniLM model used by the pipeline, then
ranked by pgvector cosine distance (`<=>` via cosine_distance) against all
chunks belonging to the project's assets. The HNSW index on the embedding
column keeps this fast as the corpus grows.
"""
from fastapi import HTTPException
from sqlmodel import Session, select

from app.models.asset import Asset
from app.models.project import Project
from app.models.text_embedding import TextEmbedding
from app.schemas.search import SearchRequest, SearchResponse, SearchResult
from app.services.pipeline_service import embed_texts


def rank_chunks_by_vector(
    session: Session, project_id: str, query_vec: list[float], limit: int
) -> list[SearchResult]:
    """Rank a project's transcript chunks by cosine similarity to a query vector.

    Shared by text search (which embeds the query first) and rough-cut
    generation (which embeds all script beats in one batch).
    """
    distance = TextEmbedding.embedding.cosine_distance(query_vec)  # type: ignore[attr-defined]
    rows = session.exec(
        select(TextEmbedding, Asset, distance.label("distance"))
        .join(Asset, Asset.id == TextEmbedding.asset_id)  # type: ignore[arg-type]
        .where(Asset.project_id == project_id)
        .order_by(distance)
        .limit(limit)
    ).all()

    return [
        SearchResult(
            asset_id=asset.id,
            asset_filename=asset.original_filename,
            media_type=asset.media_type,
            chunk_id=chunk.id,
            text=chunk.text,
            start=chunk.start,
            end=chunk.end,
            score=round(1.0 - float(dist), 4),
        )
        for chunk, asset, dist in rows
    ]


def search_project(
    session: Session, project_id: str, request: SearchRequest
) -> SearchResponse:
    """Rank the project's transcript chunks by similarity to the query."""
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    query_vec = embed_texts([request.query])[0]
    results = rank_chunks_by_vector(session, project_id, query_vec, request.limit)

    # Visual matches (CLIP over sampled frames) are a separate ranked section:
    # CLIP and MiniLM scores live in different spaces, so they are not fused.
    from app.services import visual_search_service

    visual_results = visual_search_service.search_frames(
        session, project_id, request.query, request.limit
    )

    return SearchResponse(
        query=request.query,
        results=results,
        visual_results=visual_results,
        total=len(results) + len(visual_results),
    )
