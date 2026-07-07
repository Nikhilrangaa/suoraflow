"""
visual_search_service.py — CLIP-based visual search over sampled video frames.

The query is embedded with CLIP's text encoder and ranked by pgvector cosine
distance against frame embeddings (CLIP's image encoder, same vector space).
This is what makes silent b-roll searchable: "sunset over the ridge" matches
what's *on screen*, not what was said.
"""
from sqlmodel import Session, select

from app.models.asset import Asset
from app.models.frame_embedding import FrameEmbedding
from app.schemas.search import VisualSearchResult
from app.services.pipeline_service import embed_query_clip


def search_frames(
    session: Session, project_id: str, query: str, limit: int
) -> list[VisualSearchResult]:
    """Rank the project's sampled frames by CLIP similarity to the query."""
    # Cheap existence check first: audio-only projects have no frame index,
    # so we skip loading the CLIP model entirely.
    has_frames = session.exec(
        select(FrameEmbedding.id)
        .join(Asset, Asset.id == FrameEmbedding.asset_id)  # type: ignore[arg-type]
        .where(Asset.project_id == project_id)
        .limit(1)
    ).first()
    if has_frames is None:
        return []

    query_vec = embed_query_clip(query)

    distance = FrameEmbedding.embedding.cosine_distance(query_vec)  # type: ignore[attr-defined]
    rows = session.exec(
        select(FrameEmbedding, Asset, distance.label("distance"))
        .join(Asset, Asset.id == FrameEmbedding.asset_id)  # type: ignore[arg-type]
        .where(Asset.project_id == project_id)
        .order_by(distance)
        .limit(limit * 4)  # overfetch, then de-duplicate nearby frames
    ).all()

    # A query often matches a run of consecutive frames from the same shot;
    # collapse hits within 10 s of a better hit on the same asset.
    results: list[VisualSearchResult] = []
    for frame, asset, dist in rows:
        if any(
            r.asset_id == asset.id and abs(r.timestamp - frame.timestamp) < 10.0
            for r in results
        ):
            continue
        results.append(
            VisualSearchResult(
                asset_id=asset.id,
                asset_filename=asset.original_filename,
                frame_id=frame.id,
                frame_index=frame.frame_index,
                timestamp=frame.timestamp,
                score=round(1.0 - float(dist), 4),
            )
        )
        if len(results) >= limit:
            break
    return results
