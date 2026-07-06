"""
test_search.py — Tests for transcript chunking and semantic search.

Chunking is pure logic. Search tests insert synthetic 384-dim vectors and
mock the query embedder, so no model weights are needed.
"""
import io
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.database import get_engine
from app.main import app
from app.models.text_embedding import TextEmbedding
from app.services.pipeline_service import RawSegment, chunk_segments

client = TestClient(app)


# ---------------------------------------------------------------------------
# chunk_segments
# ---------------------------------------------------------------------------

def _seg(start: float, end: float, text: str) -> RawSegment:
    return RawSegment(start=start, end=end, text=text)


class TestChunking:
    def test_empty_input_gives_no_chunks(self):
        assert chunk_segments([]) == []

    def test_short_transcript_is_one_chunk(self):
        segs = [_seg(0, 3, "Hello there."), _seg(3, 6, "Short clip.")]
        chunks = chunk_segments(segs)
        assert len(chunks) == 1
        assert chunks[0].start == 0
        assert chunks[0].end == 6
        assert chunks[0].text == "Hello there. Short clip."

    def test_closes_on_sentence_boundary_after_min_duration(self):
        # 5 segments of 6s each; sentence end on every segment.
        # Chunk should close at >= 20s → after the 4th segment (24s).
        segs = [_seg(i * 6, (i + 1) * 6, f"Sentence number {i}.") for i in range(5)]
        chunks = chunk_segments(segs)
        assert len(chunks) == 2
        assert chunks[0].end - chunks[0].start >= 20
        assert chunks[1].text == "Sentence number 4."

    def test_force_close_at_max_duration_without_sentence_end(self):
        # No sentence-ending punctuation at all; 10s segments
        segs = [_seg(i * 10, (i + 1) * 10, f"clause {i} and") for i in range(8)]
        chunks = chunk_segments(segs)
        assert all((c.end - c.start) <= 70 for c in chunks)  # 60s cap + one segment
        assert len(chunks) >= 2

    def test_chunk_times_cover_segments(self):
        segs = [_seg(2.5, 8.0, "One."), _seg(8.5, 12.0, "Two.")]
        chunks = chunk_segments(segs)
        assert chunks[0].start == 2.5
        assert chunks[-1].end == 12.0


# ---------------------------------------------------------------------------
# search endpoint
# ---------------------------------------------------------------------------

def _make_vec(hot_index: int) -> list[float]:
    """A one-hot 384-dim unit vector."""
    v = [0.0] * 384
    v[hot_index] = 1.0
    return v


def _blend(a: list[float], b: list[float], wa: float, wb: float) -> list[float]:
    import math

    v = [wa * x + wb * y for x, y in zip(a, b)]
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def _setup_project_with_chunks() -> tuple[str, str]:
    """Create a project + asset and insert two synthetic embedded chunks."""
    resp = client.post("/api/projects", json={"name": "Search Test"})
    project_id = resp.json()["id"]

    import subprocess, tempfile, os
    from pathlib import Path

    out = Path(tempfile.mkstemp(suffix=".wav")[1])
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
         "-t", "1", str(out)],
        capture_output=True, check=True, shell=False,
    )
    with patch("app.services.asset_service.get_queue"):
        up = client.post(
            f"/api/projects/{project_id}/assets/upload",
            files={"file": ("clip.wav", io.BytesIO(out.read_bytes()), "audio/wav")},
        )
    os.unlink(out)
    asset_id = up.json()["id"]

    with Session(get_engine()) as session:
        session.add(
            TextEmbedding(
                asset_id=asset_id, chunk_index=0, start=0.0, end=30.0,
                text="The team discussed the budget for supplies.",
                embedding=_make_vec(0),
            )
        )
        session.add(
            TextEmbedding(
                asset_id=asset_id, chunk_index=1, start=30.0, end=60.0,
                text="Drone footage of the sunrise over the ridge.",
                embedding=_make_vec(1),
            )
        )
        session.commit()
    return project_id, asset_id


class TestSearchEndpoint:
    def test_search_ranks_by_similarity(self):
        project_id, asset_id = _setup_project_with_chunks()
        # Query vector close to chunk 1 (drone footage)
        query_vec = _blend(_make_vec(1), _make_vec(0), 0.9, 0.1)

        with patch(
            "app.services.search_service.embed_texts", return_value=[query_vec]
        ):
            resp = client.post(
                f"/api/projects/{project_id}/search",
                json={"query": "drone shots of mountains", "limit": 10},
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total"] == 2
        first, second = data["results"]
        assert "Drone footage" in first["text"]
        assert first["score"] > second["score"]
        assert first["asset_id"] == asset_id
        assert first["start"] == 30.0

    def test_search_respects_limit(self):
        project_id, _ = _setup_project_with_chunks()
        with patch(
            "app.services.search_service.embed_texts", return_value=[_make_vec(0)]
        ):
            resp = client.post(
                f"/api/projects/{project_id}/search",
                json={"query": "budget", "limit": 1},
            )
        assert resp.status_code == 200
        assert len(resp.json()["results"]) == 1

    def test_search_scoped_to_project(self):
        project_id, _ = _setup_project_with_chunks()
        other = client.post("/api/projects", json={"name": "Empty Project"}).json()
        with patch(
            "app.services.search_service.embed_texts", return_value=[_make_vec(0)]
        ):
            resp = client.post(
                f"/api/projects/{other['id']}/search",
                json={"query": "budget"},
            )
        assert resp.status_code == 200
        assert resp.json()["results"] == []

    def test_empty_query_rejected(self):
        project_id, _ = _setup_project_with_chunks()
        resp = client.post(
            f"/api/projects/{project_id}/search", json={"query": "   "}
        )
        assert resp.status_code == 422

    def test_unknown_project_404(self):
        with patch(
            "app.services.search_service.embed_texts", return_value=[_make_vec(0)]
        ):
            resp = client.post("/api/projects/nope/search", json={"query": "x"})
        assert resp.status_code == 404
