"""
test_pipeline.py — Tests for the Phase 2 processing pipeline.

Real ffprobe/ffmpeg/VAD run against tiny generated fixtures (fast, no model
downloads — Silero VAD weights ship inside the faster-whisper package).
Whisper transcription and diarization are mocked so the suite never pulls
model weights.
"""
import io
import json
import math
import os
import struct
import subprocess
import tempfile
import wave
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import pipeline_service
from app.services.pipeline_service import RawSegment, TranscribeResult
from app.utils.waveform import compute_waveform_peaks
from app.workers.tasks import process_asset

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixture generators (ffmpeg lavfi — no external files needed)
# ---------------------------------------------------------------------------

def _gen_media(args: list[str], suffix: str) -> Path:
    out = Path(tempfile.mkstemp(suffix=suffix)[1])
    subprocess.run(
        ["ffmpeg", "-y", *args, str(out)],
        capture_output=True, check=True, shell=False,
    )
    return out


def make_sine_wav(duration: float = 2.0) -> Path:
    return _gen_media(
        ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=16000",
         "-t", str(duration), "-ac", "1"],
        ".wav",
    )


def make_silent_wav(duration: float = 1.0) -> Path:
    return _gen_media(
        ["-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", str(duration)],
        ".wav",
    )


def make_mp4(duration: float = 1.0, with_audio: bool = True) -> Path:
    args = ["-f", "lavfi", "-i", f"testsrc=duration={duration}:size=64x64:rate=10"]
    if with_audio:
        args += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100"]
    args += ["-t", str(duration), "-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if with_audio:
        args += ["-c:a", "aac"]
    args += ["-shortest"]
    return _gen_media(args, ".mp4")


def _cleanup(*paths: Path) -> None:
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# probe
# ---------------------------------------------------------------------------

class TestProbe:
    def test_probe_mp4_has_video_and_audio_metadata(self):
        mp4 = make_mp4()
        try:
            r = pipeline_service.probe_asset(mp4)
            assert r.has_audio is True
            assert r.width == 64 and r.height == 64
            assert r.fps == pytest.approx(10, abs=0.5)
            assert r.duration == pytest.approx(1.0, abs=0.3)
            assert r.sample_rate == 44100
            assert r.channels in (1, 2)
            assert r.audio_codec == "aac"
        finally:
            _cleanup(mp4)

    def test_probe_wav_audio_fields(self):
        wav = make_sine_wav()
        try:
            r = pipeline_service.probe_asset(wav)
            assert r.has_audio is True
            assert r.sample_rate == 16000
            assert r.channels == 1
            assert r.audio_codec == "pcm_s16le"
            assert r.width is None and r.fps is None
        finally:
            _cleanup(wav)

    def test_probe_video_without_audio(self):
        mp4 = make_mp4(with_audio=False)
        try:
            r = pipeline_service.probe_asset(mp4)
            assert r.has_audio is False
            assert r.width == 64
        finally:
            _cleanup(mp4)


# ---------------------------------------------------------------------------
# extract_audio + waveform
# ---------------------------------------------------------------------------

class TestExtractAudio:
    def test_extract_produces_mono_16k_wav_and_peaks(self):
        mp4 = make_mp4(duration=2.0)
        out_wav = Path(tempfile.mkstemp(suffix=".wav")[1])
        out_json = Path(tempfile.mkstemp(suffix=".json")[1])
        try:
            pipeline_service.extract_audio(mp4, out_wav, out_json)
            with wave.open(str(out_wav), "rb") as wf:
                assert wf.getnchannels() == 1
                assert wf.getframerate() == 16000
                assert wf.getsampwidth() == 2
            data = json.loads(out_json.read_text())
            assert data["duration"] == pytest.approx(2.0, abs=0.3)
            assert len(data["peaks"]) > 100
            # lavfi sine defaults to 1/8 amplitude (~0.125) — clearly non-silent
            assert max(data["peaks"]) > 0.05
        finally:
            _cleanup(mp4, out_wav, out_json)

    def test_waveform_of_silence_is_near_zero(self):
        wav = make_silent_wav()
        try:
            data = compute_waveform_peaks(wav)
            assert data["peaks"]
            assert max(data["peaks"]) < 0.01
        finally:
            _cleanup(wav)


# ---------------------------------------------------------------------------
# VAD
# ---------------------------------------------------------------------------

class TestVad:
    def test_vad_on_silence_reports_no_speech(self):
        wav = make_silent_wav(duration=2.0)
        try:
            r = pipeline_service.run_vad(wav)
            assert r.speech_ratio == 0.0
            assert r.segment_count == 0
        finally:
            _cleanup(wav)


# ---------------------------------------------------------------------------
# diarize fallback
# ---------------------------------------------------------------------------

class TestDiarizeFallback:
    def test_no_token_keeps_speaker_1(self):
        segs = [RawSegment(start=0.0, end=1.0, text="hello")]
        wav = make_silent_wav()
        try:
            # HF_TOKEN is empty in the test env → pipeline returns None
            out = pipeline_service.diarize(wav, segs)
            assert out[0].speaker == "Speaker 1"
        finally:
            _cleanup(wav)


# ---------------------------------------------------------------------------
# process_asset orchestration (transcription mocked)
# ---------------------------------------------------------------------------

def _upload_asset(project_name: str, filename: str, content: bytes) -> dict:
    resp = client.post("/api/projects", json={"name": project_name})
    assert resp.status_code == 201
    project_id = resp.json()["id"]
    with patch("app.services.asset_service.get_queue"):  # don't enqueue for real
        up = client.post(
            f"/api/projects/{project_id}/assets/upload",
            files={"file": (filename, io.BytesIO(content), "application/octet-stream")},
        )
    assert up.status_code == 201, up.text
    return up.json()


FAKE_TRANSCRIPT = TranscribeResult(
    segments=[
        RawSegment(start=0.1, end=1.2, text="Hello there."),
        RawSegment(start=1.4, end=2.0, text="This is a test."),
    ],
    language="en",
)


class TestProcessAsset:
    def test_full_pipeline_reaches_ready(self):
        mp4 = make_mp4(duration=2.0)
        asset = _upload_asset("Pipeline Ready", "clip.mp4", mp4.read_bytes())
        _cleanup(mp4)

        with patch(
            "app.services.pipeline_service.transcribe", return_value=FAKE_TRANSCRIPT
        ):
            process_asset(asset["id"])

        got = client.get(f"/api/assets/{asset['id']}").json()
        assert got["status"] == "ready"
        assert got["sample_rate"] == 44100
        assert got["audio_codec"] == "aac"
        assert got["duration"] == pytest.approx(2.0, abs=0.4)
        assert got["width"] == 64
        assert got["speech_ratio"] is not None

        tr = client.get(f"/api/assets/{asset['id']}/transcript").json()
        assert len(tr["segments"]) == 2
        assert tr["segments"][0]["text"] == "Hello there."
        assert tr["segments"][0]["speaker"] == "Speaker 1"
        assert tr["segments"][0]["start"] == pytest.approx(0.1)

        wf = client.get(f"/api/assets/{asset['id']}/waveform").json()
        assert len(wf["peaks"]) > 100
        assert wf["duration"] == pytest.approx(2.0, abs=0.3)

    def test_video_without_audio_marks_ready_gracefully(self):
        mp4 = make_mp4(duration=1.0, with_audio=False)
        asset = _upload_asset("No Audio", "broll.mp4", mp4.read_bytes())
        _cleanup(mp4)

        process_asset(asset["id"])  # no transcription mock needed — skips audio path

        got = client.get(f"/api/assets/{asset['id']}").json()
        assert got["status"] == "ready"
        assert got["speech_ratio"] == 0.0
        tr = client.get(f"/api/assets/{asset['id']}/transcript").json()
        assert tr["segments"] == []

    def test_missing_file_marks_failed_with_safe_message(self):
        wav = make_sine_wav(duration=1.0)
        asset = _upload_asset("Missing File", "gone.wav", wav.read_bytes())
        _cleanup(wav)

        # Remove the stored file to simulate disk loss
        stored = client.get(f"/api/assets/{asset['id']}").json()
        # stored_path isn't exposed via API — delete via the DB row
        from sqlmodel import Session
        from app.database import get_engine
        from app.models.asset import Asset

        with Session(get_engine()) as session:
            row = session.get(Asset, asset["id"])
            Path(row.stored_path).unlink()

        process_asset(asset["id"])

        got = client.get(f"/api/assets/{asset['id']}").json()
        assert got["status"] == "failed"
        assert "probing" in got["error_message"] or "media" in got["error_message"]
        # Never leak stack traces
        assert "Traceback" not in (got["error_message"] or "")

    def test_transcription_failure_is_safe(self):
        wav = make_sine_wav(duration=1.0)
        asset = _upload_asset("ASR Fails", "boom.wav", wav.read_bytes())
        _cleanup(wav)

        with patch(
            "app.services.pipeline_service.transcribe",
            side_effect=RuntimeError("model exploded with secret internals"),
        ):
            process_asset(asset["id"])

        got = client.get(f"/api/assets/{asset['id']}").json()
        assert got["status"] == "failed"
        assert got["error_message"] == "Processing failed during transcription."
        assert "secret" not in got["error_message"]


# ---------------------------------------------------------------------------
# API endpoints for transcript / waveform / media
# ---------------------------------------------------------------------------

class TestPhase2Endpoints:
    def test_transcript_404_for_unknown_asset(self):
        assert client.get("/api/assets/nope/transcript").status_code == 404

    def test_waveform_404_before_pipeline(self):
        wav = make_sine_wav(duration=1.0)
        asset = _upload_asset("WF Pending", "w.wav", wav.read_bytes())
        _cleanup(wav)
        assert client.get(f"/api/assets/{asset['id']}/waveform").status_code == 404

    def test_media_served_with_content_type_and_range(self):
        wav = make_sine_wav(duration=1.0)
        content = wav.read_bytes()
        asset = _upload_asset("Media Serve", "tone.wav", content)
        _cleanup(wav)

        resp = client.get(f"/api/assets/{asset['id']}/media")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/wav"
        assert len(resp.content) == len(content)

        # Range requests are what make browser seeking work
        ranged = client.get(
            f"/api/assets/{asset['id']}/media", headers={"Range": "bytes=0-99"}
        )
        assert ranged.status_code == 206
        assert len(ranged.content) == 100
