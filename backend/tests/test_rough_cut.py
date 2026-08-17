"""
test_rough_cut.py — Tests for script-to-footage rough cut generation.

split_script is pure logic. Endpoint tests insert synthetic 384-dim vectors
and mock the beat embedder + visual search (no real ML), and the Claude path
is exercised with a fake `anthropic` module injected into sys.modules — no
real Anthropic API calls, and the tests pass even if the package is absent.
"""
import io
import json
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.database import get_engine
from app.main import app
from app.models.asset import Asset
from app.models.clip import Clip, Timeline
from app.models.text_embedding import TextEmbedding
from app.schemas.search import VisualSearchResult
from app.services.rough_cut_service import split_script

client = TestClient(app)


# ---------------------------------------------------------------------------
# split_script
# ---------------------------------------------------------------------------

class TestSplitScript:
    def test_paragraphs_become_beats(self):
        script = "First beat about the intro.\n\nSecond beat about the ending."
        beats = split_script(script)
        assert beats == [
            "First beat about the intro.",
            "Second beat about the ending.",
        ]

    def test_blank_lines_with_whitespace_still_split(self):
        script = "One.\n   \n\t\nTwo."
        assert split_script(script) == ["One.", "Two."]

    def test_internal_single_newlines_are_collapsed(self):
        script = "A line\nwrapped onto\nthree lines."
        assert split_script(script) == ["A line wrapped onto three lines."]

    def test_long_paragraph_splits_on_sentence_boundaries(self):
        sentence = "This sentence is about one hundred and twenty characters long so that a few of them together exceed the beat limit. "
        script = (sentence * 4).strip()  # ~480 chars, one paragraph
        beats = split_script(script)
        assert len(beats) >= 2
        # Each beat ends on a sentence boundary and respects the cap
        assert all(b.endswith(".") for b in beats)
        assert all(len(b) <= 300 for b in beats)
        # Nothing lost: rejoining recovers all four sentences
        assert " ".join(beats) == script

    def test_empty_script_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            split_script("   \n\n  \n")
        assert exc.value.status_code == 400

    def test_capped_at_50_beats(self):
        script = "\n\n".join(f"Beat number {i}." for i in range(60))
        assert len(split_script(script)) == 50


# ---------------------------------------------------------------------------
# Endpoint fixtures/helpers
# ---------------------------------------------------------------------------

def _make_vec(hot_index: int) -> list[float]:
    """A one-hot 384-dim unit vector."""
    v = [0.0] * 384
    v[hot_index] = 1.0
    return v


def _setup_project_with_chunks(duration: float = 60.0) -> tuple[str, str]:
    """Create a project + asset and insert two synthetic embedded chunks."""
    resp = client.post("/api/projects", json={"name": "Rough Cut Test"})
    project_id = resp.json()["id"]

    import os
    import subprocess
    import tempfile
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
        asset = session.get(Asset, asset_id)
        asset.duration = duration  # needed for visual clip-window clamping
        session.add(asset)
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


def _no_key_settings():
    """Settings stand-in with the Anthropic key absent."""
    return SimpleNamespace(anthropic_api_key="", rerank_model="claude-opus-5")


def _key_settings():
    return SimpleNamespace(
        anthropic_api_key="test-key", rerank_model="claude-opus-5"
    )


def _fake_anthropic(response=None, error=None):
    """Build a fake `anthropic` module + capture the mocked client."""
    module = types.ModuleType("anthropic")
    fake_client = MagicMock()
    if error is not None:
        fake_client.messages.create.side_effect = error
    else:
        fake_client.messages.create.return_value = response
    module.Anthropic = MagicMock(return_value=fake_client)
    return module, fake_client


def _llm_response(choices: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=json.dumps({"choices": choices}))],
    )


TWO_BEAT_SCRIPT = "A beat about the budget.\n\nA beat about something unrelated."


# ---------------------------------------------------------------------------
# Embedding fallback path (no API key)
# ---------------------------------------------------------------------------

class TestEmbeddingFallback:
    def test_matched_and_unmatched_beats(self):
        project_id, asset_id = _setup_project_with_chunks()
        # Beat 0 matches chunk 0 exactly (score 1.0); beat 1 is orthogonal to
        # both chunks (score 0.0 < 0.25 threshold) -> unmatched.
        beat_vecs = [_make_vec(0), _make_vec(5)]

        with (
            patch("app.services.rough_cut_service.get_settings", _no_key_settings),
            patch("app.services.rough_cut_service.embed_texts", return_value=beat_vecs),
            patch("app.services.rough_cut_service.search_frames", return_value=[]),
        ):
            resp = client.post(
                f"/api/projects/{project_id}/rough-cut",
                json={"script": TWO_BEAT_SCRIPT, "name": "Script Cut"},
            )

        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["method"] == "embedding"

        beats = data["beats"]
        assert len(beats) == 2
        assert beats[0]["matched"] is True
        assert beats[0]["source"] == "transcript"
        assert beats[0]["asset_id"] == asset_id
        assert beats[0]["start"] == 0.0
        assert beats[0]["end"] == 30.0
        assert beats[0]["score"] == pytest.approx(1.0, abs=1e-3)
        assert beats[0]["method"] == "embedding"
        assert beats[1]["matched"] is False
        assert beats[1]["source"] is None

        # Timeline created with one item, in beat order, named from the request
        timeline = data["timeline"]
        assert timeline["name"] == "Script Cut"
        assert len(timeline["items"]) == 1
        assert timeline["items"][0]["clip"]["start"] == 0.0
        assert "budget" in timeline["items"][0]["clip"]["label"]

        # DB rows really exist
        with Session(get_engine()) as session:
            tl = session.get(Timeline, timeline["id"])
            assert tl is not None
            clips = session.exec(
                select(Clip).where(Clip.project_id == project_id)
            ).all()
        assert len(clips) == 1
        assert len(clips[0].label) <= 80

    def test_visual_fallback_uses_clamped_frame_window(self):
        project_id, asset_id = _setup_project_with_chunks(duration=10.0)
        # Orthogonal beat vector -> no transcript match; visual candidate at
        # t=2.0 s with score above the 0.20 floor -> window [0, 6] after
        # clamping (2-4 -> 0, 2+4 -> 6, within duration 10).
        visual = [
            VisualSearchResult(
                asset_id=asset_id, asset_filename="clip.wav", frame_id="f1",
                frame_index=0, timestamp=2.0, score=0.5,
            )
        ]
        with (
            patch("app.services.rough_cut_service.get_settings", _no_key_settings),
            patch(
                "app.services.rough_cut_service.embed_texts",
                return_value=[_make_vec(7)],
            ),
            patch("app.services.rough_cut_service.search_frames", return_value=visual),
        ):
            resp = client.post(
                f"/api/projects/{project_id}/rough-cut",
                json={"script": "A purely visual beat."},
            )
        assert resp.status_code == 201, resp.text
        beat = resp.json()["beats"][0]
        assert beat["matched"] is True
        assert beat["source"] == "visual"
        assert beat["start"] == 0.0
        assert beat["end"] == 6.0

    def test_low_visual_score_is_unmatched(self):
        project_id, asset_id = _setup_project_with_chunks()
        visual = [
            VisualSearchResult(
                asset_id=asset_id, asset_filename="clip.wav", frame_id="f1",
                frame_index=0, timestamp=5.0, score=0.1,  # below 0.20 floor
            )
        ]
        with (
            patch("app.services.rough_cut_service.get_settings", _no_key_settings),
            patch(
                "app.services.rough_cut_service.embed_texts",
                return_value=[_make_vec(7)],
            ),
            patch("app.services.rough_cut_service.search_frames", return_value=visual),
        ):
            resp = client.post(
                f"/api/projects/{project_id}/rough-cut",
                json={"script": "Nothing matches this."},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["beats"][0]["matched"] is False
        assert data["timeline"]["items"] == []

    def test_empty_script_400(self):
        project_id, _ = _setup_project_with_chunks()
        with patch(
            "app.services.rough_cut_service.get_settings", _no_key_settings
        ):
            resp = client.post(
                f"/api/projects/{project_id}/rough-cut", json={"script": "  \n\n "}
            )
        assert resp.status_code == 400

    def test_unknown_project_404(self):
        resp = client.post(
            "/api/projects/nope/rough-cut", json={"script": "A beat."}
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# LLM rerank path (mocked anthropic client — never the real API)
# ---------------------------------------------------------------------------

class TestLLMPath:
    def test_llm_choices_drive_selection(self):
        project_id, asset_id = _setup_project_with_chunks()
        beat_vecs = [_make_vec(0), _make_vec(1)]
        # The model picks t0 for beat 0 and declines beat 1 (null) even though
        # beat 1's embedding score would have matched.
        fake_module, fake_client = _fake_anthropic(
            response=_llm_response(
                [
                    {"beat_index": 0, "candidate_id": "t0"},
                    {"beat_index": 1, "candidate_id": None},
                ]
            )
        )

        with (
            patch.dict(sys.modules, {"anthropic": fake_module}),
            patch("app.services.rough_cut_service.get_settings", _key_settings),
            patch("app.services.rough_cut_service.embed_texts", return_value=beat_vecs),
            patch("app.services.rough_cut_service.search_frames", return_value=[]),
        ):
            resp = client.post(
                f"/api/projects/{project_id}/rough-cut",
                json={"script": TWO_BEAT_SCRIPT},
            )

        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["method"] == "llm"
        assert data["beats"][0]["matched"] is True
        assert data["beats"][0]["method"] == "llm"
        assert data["beats"][0]["asset_id"] == asset_id
        assert data["beats"][1]["matched"] is False
        assert data["beats"][1]["method"] == "llm"
        assert len(data["timeline"]["items"]) == 1

        # Exactly one Claude call for the whole script
        assert fake_client.messages.create.call_count == 1
        kwargs = fake_client.messages.create.call_args.kwargs
        assert kwargs["model"] == "claude-opus-5"
        assert kwargs["max_tokens"] == 4000
        schema = kwargs["output_config"]["format"]["schema"]
        assert schema["additionalProperties"] is False

    def test_llm_error_falls_back_to_embeddings(self):
        project_id, asset_id = _setup_project_with_chunks()
        fake_module, _ = _fake_anthropic(error=RuntimeError("api down"))

        with (
            patch.dict(sys.modules, {"anthropic": fake_module}),
            patch("app.services.rough_cut_service.get_settings", _key_settings),
            patch(
                "app.services.rough_cut_service.embed_texts",
                return_value=[_make_vec(0), _make_vec(5)],
            ),
            patch("app.services.rough_cut_service.search_frames", return_value=[]),
        ):
            resp = client.post(
                f"/api/projects/{project_id}/rough-cut",
                json={"script": TWO_BEAT_SCRIPT},
            )

        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["method"] == "embedding"
        assert data["beats"][0]["matched"] is True  # embedding threshold path
        assert data["beats"][1]["matched"] is False

    def test_llm_refusal_falls_back(self):
        project_id, _ = _setup_project_with_chunks()
        refusal = SimpleNamespace(stop_reason="refusal", content=[])
        fake_module, _ = _fake_anthropic(response=refusal)

        with (
            patch.dict(sys.modules, {"anthropic": fake_module}),
            patch("app.services.rough_cut_service.get_settings", _key_settings),
            patch(
                "app.services.rough_cut_service.embed_texts",
                return_value=[_make_vec(0), _make_vec(5)],
            ),
            patch("app.services.rough_cut_service.search_frames", return_value=[]),
        ):
            resp = client.post(
                f"/api/projects/{project_id}/rough-cut",
                json={"script": TWO_BEAT_SCRIPT},
            )
        assert resp.status_code == 201
        assert resp.json()["method"] == "embedding"

    def test_llm_invalid_json_falls_back(self):
        project_id, _ = _setup_project_with_chunks()
        bad = SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text="not json at all")],
        )
        fake_module, _ = _fake_anthropic(response=bad)

        with (
            patch.dict(sys.modules, {"anthropic": fake_module}),
            patch("app.services.rough_cut_service.get_settings", _key_settings),
            patch(
                "app.services.rough_cut_service.embed_texts",
                return_value=[_make_vec(0), _make_vec(5)],
            ),
            patch("app.services.rough_cut_service.search_frames", return_value=[]),
        ):
            resp = client.post(
                f"/api/projects/{project_id}/rough-cut",
                json={"script": TWO_BEAT_SCRIPT},
            )
        assert resp.status_code == 201
        assert resp.json()["method"] == "embedding"

    def test_llm_unknown_candidate_id_falls_back_per_beat(self):
        project_id, _ = _setup_project_with_chunks()
        fake_module, _ = _fake_anthropic(
            response=_llm_response(
                [
                    {"beat_index": 0, "candidate_id": "t99"},  # invented id
                    {"beat_index": 1, "candidate_id": None},
                ]
            )
        )
        with (
            patch.dict(sys.modules, {"anthropic": fake_module}),
            patch("app.services.rough_cut_service.get_settings", _key_settings),
            patch(
                "app.services.rough_cut_service.embed_texts",
                return_value=[_make_vec(0), _make_vec(5)],
            ),
            patch("app.services.rough_cut_service.search_frames", return_value=[]),
        ):
            resp = client.post(
                f"/api/projects/{project_id}/rough-cut",
                json={"script": TWO_BEAT_SCRIPT},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["method"] == "llm"  # the call itself succeeded
        # Beat 0 was rescued by the embedding threshold (score 1.0 >= 0.25)
        assert data["beats"][0]["matched"] is True
        assert data["beats"][0]["method"] == "embedding"
