"""
rough_cut_service.py — Script-to-footage rough cut generation.

Splits a script into "beats" (paragraphs, long ones split on sentence
boundaries), matches each beat to footage using the existing embedding
indexes (MiniLM over transcript chunks, CLIP over sampled frames), optionally
reranks the candidates with one Claude API call for the whole script, and
assembles the matched beats into a Timeline of Clips.

Graceful degradation is a hard project rule: if ANTHROPIC_API_KEY is absent,
the anthropic package is missing, the API errors, the model refuses, or the
returned JSON does not validate, selection silently falls back to pure
embedding scores — the request never fails because of the LLM.
"""
import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session

from app.config import get_settings
from app.models.asset import Asset
from app.models.project import Project
from app.schemas.rough_cut import BeatMatch, RoughCutRequest, RoughCutResponse
from app.schemas.search import VisualSearchResult
from app.schemas.timeline import ClipCreate, TimelineCreate, TimelineItemCreate
from app.services import timeline_service
from app.services.pipeline_service import embed_texts
from app.services.search_service import rank_chunks_by_vector
from app.services.visual_search_service import search_frames

logger = logging.getLogger(__name__)

MAX_BEATS = 50
MAX_BEAT_CHARS = 300
TRANSCRIPT_MIN_SCORE = 0.25  # MiniLM cosine similarity floor
VISUAL_MIN_SCORE = 0.20  # CLIP cosine similarity floor (scores run lower)
VISUAL_WINDOW_S = 4.0  # clip window around a matched frame: timestamp ± 4 s
CLIP_LABEL_CHARS = 80
LLM_MAX_TOKENS = 4000
LLM_EXCERPT_CHARS = 200

_MISSING = object()  # sentinel: beat index absent from the LLM's choices

# Structured-output schema for the single rerank call: one choice per beat,
# candidate_id is a candidate key like "t0"/"v1" or null for "nothing fits".
_RERANK_SCHEMA = {
    "type": "object",
    "properties": {
        "choices": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "beat_index": {"type": "integer"},
                    "candidate_id": {"type": ["string", "null"]},
                },
                "required": ["beat_index", "candidate_id"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["choices"],
    "additionalProperties": False,
}


@dataclass
class _Candidate:
    """A footage candidate for one beat, with its clip window pre-resolved."""

    cid: str  # presentation id: "t0", "t1" (transcript) / "v0", "v1" (visual)
    source: str  # "transcript" | "visual"
    asset_id: str
    asset_filename: str
    start: float
    end: float
    score: float
    text: str = ""  # transcript excerpt (empty for visual candidates)
    timestamp: Optional[float] = None  # frame timestamp (visual only)


# ---------------------------------------------------------------------------
# Script splitting
# ---------------------------------------------------------------------------

def split_script(script: str) -> list[str]:
    """Split a script into beats.

    Blank lines separate paragraphs; paragraphs longer than ~300 characters
    are further split on sentence boundaries. Empty beats are dropped and the
    result is capped at 50 beats. Raises 400 if the script is empty.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", script) if p.strip()]

    beats: list[str] = []
    for para in paragraphs:
        para = " ".join(para.split())  # collapse internal whitespace/newlines
        if len(para) <= MAX_BEAT_CHARS:
            beats.append(para)
            continue
        sentences = re.split(r"(?<=[.!?])\s+", para)
        current = ""
        for sentence in sentences:
            if current and len(current) + 1 + len(sentence) > MAX_BEAT_CHARS:
                beats.append(current)
                current = sentence
            else:
                current = f"{current} {sentence}".strip()
        if current:
            beats.append(current)

    beats = [b for b in beats if b]
    if not beats:
        raise HTTPException(status_code=400, detail="Script must not be empty")
    return beats[:MAX_BEATS]


# ---------------------------------------------------------------------------
# Candidate gathering
# ---------------------------------------------------------------------------

def _visual_window(
    session: Session, asset_cache: dict[str, Optional[Asset]], result: VisualSearchResult
) -> Optional[tuple[float, float]]:
    """Frame timestamp ± VISUAL_WINDOW_S, clamped to [0, asset.duration]."""
    if result.asset_id not in asset_cache:
        asset_cache[result.asset_id] = session.get(Asset, result.asset_id)
    asset = asset_cache[result.asset_id]
    duration = asset.duration if asset is not None else None

    start = max(0.0, result.timestamp - VISUAL_WINDOW_S)
    end = result.timestamp + VISUAL_WINDOW_S
    if duration is not None:
        start = min(start, max(0.0, duration))
        end = min(end, duration)
    if end - start <= 0:
        return None
    return round(start, 3), round(end, 3)


def _gather_candidates(
    session: Session,
    project_id: str,
    beats: list[str],
    beat_vecs: list[list[float]],
    per_beat_limit: int,
) -> list[dict[str, _Candidate]]:
    """For each beat, collect transcript + visual candidates keyed by id."""
    asset_cache: dict[str, Optional[Asset]] = {}
    per_beat: list[dict[str, _Candidate]] = []

    for beat, vec in zip(beats, beat_vecs):
        candidates: dict[str, _Candidate] = {}

        for i, r in enumerate(
            rank_chunks_by_vector(session, project_id, vec, per_beat_limit)
        ):
            cid = f"t{i}"
            candidates[cid] = _Candidate(
                cid=cid,
                source="transcript",
                asset_id=r.asset_id,
                asset_filename=r.asset_filename,
                start=r.start,
                end=r.end,
                score=r.score,
                text=r.text,
            )

        vi = 0
        for r in search_frames(session, project_id, beat, per_beat_limit):
            window = _visual_window(session, asset_cache, r)
            if window is None:
                continue
            cid = f"v{vi}"
            candidates[cid] = _Candidate(
                cid=cid,
                source="visual",
                asset_id=r.asset_id,
                asset_filename=r.asset_filename,
                start=window[0],
                end=window[1],
                score=r.score,
                timestamp=r.timestamp,
            )
            vi += 1

        per_beat.append(candidates)

    return per_beat


# ---------------------------------------------------------------------------
# Selection — Claude rerank (optional) with embedding fallback
# ---------------------------------------------------------------------------

def _select_by_embedding(candidates: dict[str, _Candidate]) -> Optional[_Candidate]:
    """Threshold-based selection: best transcript hit, else best visual hit."""
    transcript = [c for c in candidates.values() if c.source == "transcript"]
    if transcript:
        best = max(transcript, key=lambda c: c.score)
        if best.score >= TRANSCRIPT_MIN_SCORE:
            return best
    visual = [c for c in candidates.values() if c.source == "visual"]
    if visual:
        best = max(visual, key=lambda c: c.score)
        if best.score >= VISUAL_MIN_SCORE:
            return best
    return None


def _build_rerank_prompt(
    beats: list[str], per_beat: list[dict[str, _Candidate]]
) -> str:
    lines = [
        "You are matching script beats to footage candidates for a video rough cut.",
        "For each beat, pick the single candidate id whose content best fits the"
        " beat's meaning, or null if no candidate fits.",
        'Candidate ids starting with "t" are transcript excerpts (what was said);'
        ' ids starting with "v" are visual frame matches (what is on screen).',
        "",
    ]
    for idx, (beat, candidates) in enumerate(zip(beats, per_beat)):
        lines.append(f'Beat {idx}: "{beat}"')
        if not candidates:
            lines.append("  (no candidates)")
        for cid, c in candidates.items():
            if c.source == "transcript":
                excerpt = c.text[:LLM_EXCERPT_CHARS]
                lines.append(
                    f'  {cid}: {c.start:.1f}s-{c.end:.1f}s'
                    f' (sim {c.score:.2f}) "{excerpt}"'
                )
            else:
                lines.append(
                    f"  {cid}: frame at {c.timestamp:.1f}s (sim {c.score:.2f})"
                )
        lines.append("")
    lines.append(
        'Return JSON: {"choices": [{"beat_index": <int>, "candidate_id":'
        ' "<id>" or null}, ...]} with exactly one entry per beat.'
    )
    return "\n".join(lines)


def _rerank_with_llm(
    beats: list[str], per_beat: list[dict[str, _Candidate]]
) -> Optional[dict[int, Optional[str]]]:
    """One Claude call for the whole script. Returns beat_index -> candidate id
    (or None for "nothing fits"), or None if the rerank is unavailable/failed —
    the caller then falls back to embedding selection. Never raises.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None

    try:
        import anthropic  # lazy: app must run even if the package is missing
    except Exception:
        logger.info("anthropic package unavailable; using embedding selection")
        return None

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.rerank_model,
            max_tokens=LLM_MAX_TOKENS,
            messages=[
                {"role": "user", "content": _build_rerank_prompt(beats, per_beat)}
            ],
            output_config={
                "format": {"type": "json_schema", "schema": _RERANK_SCHEMA}
            },
        )
    except Exception:
        logger.warning("Claude rerank call failed; using embedding selection")
        return None

    # Check stop_reason before touching content: on a refusal the content is
    # empty/partial and must not be parsed.
    if getattr(response, "stop_reason", None) == "refusal":
        logger.info("Claude rerank refused; using embedding selection")
        return None

    try:
        text = next(
            b.text for b in response.content if getattr(b, "type", "") == "text"
        )
        data = json.loads(text)
        selections: dict[int, Optional[str]] = {}
        for entry in data["choices"]:
            idx = entry["beat_index"]
            cid = entry["candidate_id"]
            if not isinstance(idx, int) or not (cid is None or isinstance(cid, str)):
                raise ValueError("invalid choice entry")
            selections[idx] = cid
        return selections
    except Exception:
        logger.warning("Claude rerank output invalid; using embedding selection")
        return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def generate_rough_cut(
    session: Session, project_id: str, request: RoughCutRequest
) -> RoughCutResponse:
    """Match each script beat to footage and assemble a rough-cut timeline."""
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    beats = split_script(request.script)
    beat_vecs = embed_texts(beats)  # one MiniLM batch for all beats
    per_beat = _gather_candidates(
        session, project_id, beats, beat_vecs, request.candidates_per_beat
    )

    selections = _rerank_with_llm(beats, per_beat)
    llm_used = selections is not None

    # Resolve one candidate (or None) per beat, remembering which method decided.
    chosen: list[tuple[Optional[_Candidate], str]] = []
    for idx, candidates in enumerate(per_beat):
        if llm_used:
            cid = selections.get(idx, _MISSING)  # type: ignore[union-attr]
            if cid is None:
                chosen.append((None, "llm"))
                continue
            if cid is not _MISSING and cid in candidates:
                chosen.append((candidates[cid], "llm"))  # type: ignore[index]
                continue
            # Beat missing from choices, or an id the model invented: fall back
            # to embedding selection for this beat only.
        chosen.append((_select_by_embedding(candidates), "embedding"))

    # Assemble: one Clip + TimelineItem per matched beat, in beat order.
    timeline = timeline_service.create_timeline(
        session, project_id, TimelineCreate(name=request.name)
    )
    beat_reports: list[BeatMatch] = []
    for idx, (beat, (candidate, method)) in enumerate(zip(beats, chosen)):
        if candidate is None:
            beat_reports.append(
                BeatMatch(index=idx, beat_text=beat, matched=False, method=method)
            )
            continue
        try:
            clip = timeline_service.create_clip(
                session,
                project_id,
                ClipCreate(
                    asset_id=candidate.asset_id,
                    start=candidate.start,
                    end=candidate.end,
                    label=beat[:CLIP_LABEL_CHARS],
                ),
            )
            timeline_service.add_item(
                session, timeline.id, TimelineItemCreate(clip_id=clip.id)
            )
        except HTTPException:
            # e.g. clip window rejected against the asset's duration — report
            # the beat as unmatched rather than failing the whole request.
            logger.warning("Rough cut: clip rejected for beat %d; skipping", idx)
            beat_reports.append(
                BeatMatch(index=idx, beat_text=beat, matched=False, method=method)
            )
            continue
        beat_reports.append(
            BeatMatch(
                index=idx,
                beat_text=beat,
                matched=True,
                source=candidate.source,  # type: ignore[arg-type]
                asset_id=candidate.asset_id,
                asset_filename=candidate.asset_filename,
                start=candidate.start,
                end=candidate.end,
                score=candidate.score,
                method=method,  # type: ignore[arg-type]
            )
        )

    final_timeline = timeline_service.get_timeline(session, timeline.id)
    return RoughCutResponse(
        timeline=final_timeline,
        beats=beat_reports,
        method="llm" if llm_used else "embedding",
    )
