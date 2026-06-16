"""
test_assets.py — Integration tests for asset upload + listing.

These tests run inside the docker compose context where:
  - DB and Redis are live
  - ffmpeg/ffprobe are installed in the image
  - STORAGE_ROOT is /storage

Media fixtures are generated at test time via ffmpeg lavfi sources.
"""
import io
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _create_project(name: str = "Upload Test Project") -> str:
    resp = client.post("/api/projects", json={"name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


def _make_wav(duration: float = 1.0) -> bytes:
    """Generate a real WAV file (silence) using ffmpeg lavfi source."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out_path = f.name
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"anullsrc=r=16000:cl=mono",
                "-t", str(duration),
                out_path,
            ],
            capture_output=True,
            check=True,
            shell=False,
        )
        return Path(out_path).read_bytes()
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass


def _make_mp4(duration: float = 1.0) -> bytes:
    """Generate a real MP4 file (test pattern + silence) using ffmpeg lavfi source."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        out_path = f.name
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=64x64:rate=10",
                "-f", "lavfi", "-i", f"anullsrc=r=16000:cl=mono",
                "-t", str(duration),
                "-c:v", "libx264",
                "-c:a", "aac",
                "-shortest",
                out_path,
            ],
            capture_output=True,
            check=True,
            shell=False,
        )
        return Path(out_path).read_bytes()
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------

class TestUploadWav:
    def test_upload_wav_returns_201(self):
        project_id = _create_project("WAV Upload")
        wav_bytes = _make_wav()
        resp = client.post(
            f"/api/projects/{project_id}/assets/upload",
            files={"file": ("test_audio.wav", io.BytesIO(wav_bytes), "audio/wav")},
        )
        assert resp.status_code == 201, resp.text

    def test_upload_wav_asset_schema(self):
        project_id = _create_project("WAV Schema")
        wav_bytes = _make_wav()
        resp = client.post(
            f"/api/projects/{project_id}/assets/upload",
            files={"file": ("test_audio.wav", io.BytesIO(wav_bytes), "audio/wav")},
        )
        data = resp.json()
        assert data["media_type"] == "audio"
        assert data["ext"] == ".wav"
        assert data["status"] == "uploaded"
        assert data["project_id"] == project_id
        assert data["size_bytes"] > 0
        assert "id" in data

    def test_upload_wav_job_enqueued(self):
        """Job must be enqueued — assert by checking mock was called."""
        project_id = _create_project("WAV Enqueue")
        wav_bytes = _make_wav()
        with patch("app.services.asset_service.get_queue") as mock_gq:
            mock_queue = MagicMock()
            mock_gq.return_value = mock_queue
            resp = client.post(
                f"/api/projects/{project_id}/assets/upload",
                files={"file": ("test_audio.wav", io.BytesIO(wav_bytes), "audio/wav")},
            )
            assert resp.status_code == 201
            mock_queue.enqueue.assert_called_once()
            call_args = mock_queue.enqueue.call_args
            assert call_args[0][0] == "app.workers.tasks.process_asset"


class TestUploadMp4:
    def test_upload_mp4_returns_201(self):
        project_id = _create_project("MP4 Upload")
        mp4_bytes = _make_mp4()
        resp = client.post(
            f"/api/projects/{project_id}/assets/upload",
            files={"file": ("test_video.mp4", io.BytesIO(mp4_bytes), "video/mp4")},
        )
        assert resp.status_code == 201, resp.text

    def test_upload_mp4_media_type_video(self):
        project_id = _create_project("MP4 Type")
        mp4_bytes = _make_mp4()
        resp = client.post(
            f"/api/projects/{project_id}/assets/upload",
            files={"file": ("test_video.mp4", io.BytesIO(mp4_bytes), "video/mp4")},
        )
        data = resp.json()
        assert data["media_type"] == "video"
        assert data["ext"] == ".mp4"
        assert data["status"] == "uploaded"


# ---------------------------------------------------------------------------
# Rejection tests
# ---------------------------------------------------------------------------

class TestUploadRejections:
    def test_disallowed_extension_returns_400(self):
        project_id = _create_project("Bad Ext")
        resp = client.post(
            f"/api/projects/{project_id}/assets/upload",
            files={"file": ("document.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
        )
        assert resp.status_code == 400

    def test_disallowed_extension_txt_returns_400(self):
        project_id = _create_project("Bad Ext TXT")
        resp = client.post(
            f"/api/projects/{project_id}/assets/upload",
            files={"file": ("readme.txt", io.BytesIO(b"hello"), "text/plain")},
        )
        assert resp.status_code == 400

    def test_oversized_upload_returns_413(self, monkeypatch):
        """Monkeypatch max_upload_mb to 0 so any upload exceeds it."""
        from app.config import get_settings
        original = get_settings()

        class TinySettings:
            max_upload_mb = 0  # effectively 0 bytes
            storage_root = original.storage_root

        with patch("app.services.asset_service.get_settings", return_value=TinySettings()):
            project_id = _create_project("Oversized")
            wav_bytes = _make_wav()
            resp = client.post(
                f"/api/projects/{project_id}/assets/upload",
                files={"file": ("test.wav", io.BytesIO(wav_bytes), "audio/wav")},
            )
            assert resp.status_code == 413

    def test_fake_mp4_rejected_by_ffprobe(self):
        """A .mp4 file containing plain text must be rejected with 400."""
        project_id = _create_project("Fake MP4")
        fake_bytes = b"This is not a video file, just plain text content."
        resp = client.post(
            f"/api/projects/{project_id}/assets/upload",
            files={"file": ("fake.mp4", io.BytesIO(fake_bytes), "video/mp4")},
        )
        assert resp.status_code == 400

    def test_upload_to_nonexistent_project_returns_404(self):
        wav_bytes = _make_wav()
        resp = client.post(
            "/api/projects/nonexistent-project-id/assets/upload",
            files={"file": ("test.wav", io.BytesIO(wav_bytes), "audio/wav")},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Asset CRUD tests
# ---------------------------------------------------------------------------

class TestAssetCrud:
    def _upload_wav(self, project_id: str) -> dict:
        wav_bytes = _make_wav()
        resp = client.post(
            f"/api/projects/{project_id}/assets/upload",
            files={"file": ("test_audio.wav", io.BytesIO(wav_bytes), "audio/wav")},
        )
        assert resp.status_code == 201
        return resp.json()

    def test_list_assets(self):
        project_id = _create_project("List Assets")
        self._upload_wav(project_id)
        resp = client.get(f"/api/projects/{project_id}/assets")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_asset(self):
        project_id = _create_project("Get Asset")
        asset = self._upload_wav(project_id)
        resp = client.get(f"/api/assets/{asset['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == asset["id"]

    def test_get_asset_not_found(self):
        resp = client.get("/api/assets/nonexistent-asset-id")
        assert resp.status_code == 404

    def test_get_asset_status(self):
        project_id = _create_project("Asset Status")
        asset = self._upload_wav(project_id)
        resp = client.get(f"/api/assets/{asset['id']}/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == asset["id"]
        assert data["status"] == "uploaded"

    def test_delete_asset(self):
        project_id = _create_project("Delete Asset")
        asset = self._upload_wav(project_id)
        del_resp = client.delete(f"/api/assets/{asset['id']}")
        assert del_resp.status_code == 204

        get_resp = client.get(f"/api/assets/{asset['id']}")
        assert get_resp.status_code == 404

    def test_delete_project_cascades_assets(self):
        project_id = _create_project("Cascade Delete")
        asset = self._upload_wav(project_id)

        del_resp = client.delete(f"/api/projects/{project_id}")
        assert del_resp.status_code == 204

        get_resp = client.get(f"/api/assets/{asset['id']}")
        assert get_resp.status_code == 404

    def test_project_asset_count(self):
        project_id = _create_project("Asset Count")
        self._upload_wav(project_id)
        self._upload_wav(project_id)

        resp = client.get(f"/api/projects/{project_id}")
        assert resp.status_code == 200
        assert resp.json()["asset_count"] == 2
