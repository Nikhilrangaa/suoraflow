"""
test_visual_search.py — Tests for Phase 6 visual indexing and CLIP search.

Frame extraction runs real ffmpeg on generated fixtures; CLIP embedding is
mocked with synthetic 512-dim vectors so no model weights are needed.
"""
import io
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.database import get_engine
from app.main import app
from app.models.frame_embedding import FrameEmbedding
from app.services import pipeline_service
from app.workers.tasks import process_asset

client = TestClient(app)


def make_mp4(duration: float = 6.0, with_audio: bool = False) -> Path:
    out = Path(tempfile.mkstemp(suffix=".mp4")[1])
    args = ["ffmpeg", "-y", "-f", "lavfi",
            "-i", f"testsrc=duration={duration}:size=128x72:rate=10"]
    if with_audio:
        args += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000"]
    args += ["-t", str(duration), "-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if with_audio:
        args += ["-c:a", "aac"]
    args += ["-shortest", str(out)]
    subprocess.run(args, capture_output=True, check=True, shell=False)
    return out


def _upload(project_name: str, path: Path) -> dict:
    resp = client.post("/api/projects", json={"name": project_name})
    project_id = resp.json()["id"]
    with patch("app.services.asset_service.get_queue"):
        up = client.post(
            f"/api/projects/{project_id}/assets/upload",
            files={"file": ("clip.mp4", io.BytesIO(path.read_bytes()), "video/mp4")},
        )
    assert up.status_code == 201, up.text
    return up.json()


def _fake_image_vectors(paths):
    """One-hot 512-dim vector per frame, hot index = frame order."""
    return [[1.0 if j == i else 0.0 for j in range(512)] for i in range(len(paths))]


# ---------------------------------------------------------------------------
# Frame sampling
# ---------------------------------------------------------------------------

class TestFrameSampling:
    def test_extract_frames_produces_jpegs_with_timestamps(self):
        mp4 = make_mp4(duration=6.0)
        out_dir = Path(tempfile.mkdtemp()) / "frames"
        try:
            frames = pipeline_service.sample_frames(mp4, out_dir, duration=6.0)
            assert len(frames) >= 2  # 6s at one frame per 2.5s
            assert all(f.path.suffix == ".jpg" and f.path.exists() for f in frames)
            # Timestamps increase and stay within the clip
            ts = [f.timestamp for f in frames]
            assert ts == sorted(ts)
            assert all(0 <= t <= 6.0 for t in ts)
        finally:
            os.unlink(mp4)

    def test_interval_caps_long_footage(self):
        assert pipeline_service.frame_sample_interval(60) == 2.5
        # 2 hours → interval stretches so the cap holds
        interval = pipeline_service.frame_sample_interval(7200)
        assert 7200 / interval <= 240 + 1


# ---------------------------------------------------------------------------
# Pipeline: silent b-roll now gets a visual index
# ---------------------------------------------------------------------------

class TestVisualPipeline:
    def test_silent_video_is_visually_indexed_and_ready(self):
        mp4 = make_mp4(duration=6.0, with_audio=False)
        asset = _upload("Silent Broll", mp4)
        os.unlink(mp4)

        with patch(
            "app.services.pipeline_service.embed_images",
            side_effect=_fake_image_vectors,
        ):
            process_asset(asset["id"])

        got = client.get(f"/api/assets/{asset['id']}").json()
        assert got["status"] == "ready"
        assert got["speech_ratio"] == 0.0

        with Session(get_engine()) as session:
            frames = session.exec(
                select(FrameEmbedding).where(FrameEmbedding.asset_id == asset["id"])
            ).all()
        assert len(frames) >= 2
        assert all(f.frame_path.endswith(".jpg") for f in frames)

    def test_frame_endpoint_serves_jpeg(self):
        mp4 = make_mp4(duration=6.0)
        asset = _upload("Frame Serve", mp4)
        os.unlink(mp4)
        with patch(
            "app.services.pipeline_service.embed_images",
            side_effect=_fake_image_vectors,
        ):
            process_asset(asset["id"])

        resp = client.get(f"/api/assets/{asset['id']}/frames/0")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/jpeg"
        assert resp.content[:2] == b"\xff\xd8"  # JPEG magic

        assert client.get(f"/api/assets/{asset['id']}/frames/9999").status_code == 404

    def test_audio_asset_gets_no_frames(self):
        wav = Path(tempfile.mkstemp(suffix=".wav")[1])
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
             "-t", "1", str(wav)],
            capture_output=True, check=True, shell=False,
        )
        resp = client.post("/api/projects", json={"name": "Audio Only"})
        project_id = resp.json()["id"]
        with patch("app.services.asset_service.get_queue"):
            up = client.post(
                f"/api/projects/{project_id}/assets/upload",
                files={"file": ("a.wav", io.BytesIO(wav.read_bytes()), "audio/wav")},
            )
        os.unlink(wav)
        asset_id = up.json()["id"]

        from app.services.pipeline_service import RawSegment, TranscribeResult

        with patch(
            "app.services.pipeline_service.transcribe",
            return_value=TranscribeResult(segments=[RawSegment(0, 1, "hi.")]),
        ):
            process_asset(asset_id)

        assert client.get(f"/api/assets/{asset_id}").json()["status"] == "ready"
        with Session(get_engine()) as session:
            frames = session.exec(
                select(FrameEmbedding).where(FrameEmbedding.asset_id == asset_id)
            ).all()
        assert frames == []


# ---------------------------------------------------------------------------
# Visual search endpoint
# ---------------------------------------------------------------------------

class TestVisualSearch:
    def _indexed_project(self) -> tuple[str, str]:
        mp4 = make_mp4(duration=8.0)
        asset = _upload("Visual Search", mp4)
        os.unlink(mp4)
        with patch(
            "app.services.pipeline_service.embed_images",
            side_effect=_fake_image_vectors,
        ):
            process_asset(asset["id"])
        return asset["project_id"], asset["id"]

    def test_visual_results_ranked_by_clip_similarity(self):
        project_id, asset_id = self._indexed_project()

        # Query vector = one-hot at index 1 → frame 1 must rank first
        query_vec = [1.0 if j == 1 else 0.0 for j in range(512)]
        with (
            patch(
                "app.services.visual_search_service.embed_query_clip",
                return_value=query_vec,
            ),
            patch(
                "app.services.search_service.embed_texts",
                return_value=[[0.0] * 384],
            ),
        ):
            resp = client.post(
                f"/api/projects/{project_id}/search",
                json={"query": "a colorful test pattern", "limit": 5},
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["visual_results"], "expected visual matches"
        top = data["visual_results"][0]
        assert top["asset_id"] == asset_id
        assert top["frame_index"] == 1
        assert top["score"] == pytest.approx(1.0, abs=1e-3)

    def test_nearby_frames_are_deduplicated(self):
        project_id, _ = self._indexed_project()
        # Uniform query: every frame matches equally; frames are ~2.5s apart,
        # so the 10s de-dup window keeps only a spread-out subset.
        norm = 1.0 / (512 ** 0.5)
        with (
            patch(
                "app.services.visual_search_service.embed_query_clip",
                return_value=[norm] * 512,
            ),
            patch(
                "app.services.search_service.embed_texts",
                return_value=[[0.0] * 384],
            ),
        ):
            resp = client.post(
                f"/api/projects/{project_id}/search",
                json={"query": "anything", "limit": 5},
            )
        vis = resp.json()["visual_results"]
        for i, a in enumerate(vis):
            for b in vis[i + 1:]:
                if a["asset_id"] == b["asset_id"]:
                    assert abs(a["timestamp"] - b["timestamp"]) >= 10.0
