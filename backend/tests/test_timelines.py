"""
test_timelines.py — Tests for clips, timelines, item ordering, and export.
"""
import csv
import io
import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _project_with_asset() -> tuple[str, str]:
    resp = client.post("/api/projects", json={"name": "Timeline Test"})
    project_id = resp.json()["id"]

    out = Path(tempfile.mkstemp(suffix=".wav")[1])
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
         "-t", "1", str(out)],
        capture_output=True, check=True, shell=False,
    )
    with patch("app.services.asset_service.get_queue"):
        up = client.post(
            f"/api/projects/{project_id}/assets/upload",
            files={"file": ("footage.wav", io.BytesIO(out.read_bytes()), "audio/wav")},
        )
    os.unlink(out)
    return project_id, up.json()["id"]


def _make_clip(project_id: str, asset_id: str, start=0.0, end=5.0, label="a clip") -> dict:
    resp = client.post(
        f"/api/projects/{project_id}/clips",
        json={"asset_id": asset_id, "start": start, "end": end, "label": label},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestClips:
    def test_create_and_list_clips(self):
        project_id, asset_id = _project_with_asset()
        clip = _make_clip(project_id, asset_id, 1.0, 6.5, "sunrise drone shot")
        assert clip["asset_filename"] == "footage.wav"
        assert clip["start"] == 1.0 and clip["end"] == 6.5

        clips = client.get(f"/api/projects/{project_id}/clips").json()
        assert len(clips) == 1
        assert clips[0]["label"] == "sunrise drone shot"

    def test_clip_requires_valid_asset(self):
        project_id, _ = _project_with_asset()
        resp = client.post(
            f"/api/projects/{project_id}/clips",
            json={"asset_id": "nope", "start": 0, "end": 5, "label": ""},
        )
        assert resp.status_code == 404

    def test_clip_asset_must_belong_to_project(self):
        project_a, asset_a = _project_with_asset()
        project_b, _ = _project_with_asset()
        resp = client.post(
            f"/api/projects/{project_b}/clips",
            json={"asset_id": asset_a, "start": 0, "end": 5, "label": ""},
        )
        assert resp.status_code == 404

    def test_clip_end_must_be_after_start(self):
        project_id, asset_id = _project_with_asset()
        resp = client.post(
            f"/api/projects/{project_id}/clips",
            json={"asset_id": asset_id, "start": 5, "end": 5, "label": ""},
        )
        assert resp.status_code == 422


class TestTimelines:
    def test_create_and_list(self):
        project_id, _ = _project_with_asset()
        tl = client.post(
            f"/api/projects/{project_id}/timelines", json={"name": "Cut v1"}
        ).json()
        assert tl["name"] == "Cut v1"
        assert tl["items"] == []

        listed = client.get(f"/api/projects/{project_id}/timelines").json()
        assert len(listed) == 1

    def test_add_move_remove_items(self):
        project_id, asset_id = _project_with_asset()
        tl = client.post(f"/api/projects/{project_id}/timelines", json={}).json()
        c1 = _make_clip(project_id, asset_id, 0, 5, "first")
        c2 = _make_clip(project_id, asset_id, 10, 20, "second")
        c3 = _make_clip(project_id, asset_id, 30, 45, "third")

        for c in (c1, c2, c3):
            resp = client.post(
                f"/api/timelines/{tl['id']}/items", json={"clip_id": c["id"]}
            )
            assert resp.status_code == 201

        timeline = client.get(f"/api/timelines/{tl['id']}").json()
        assert [i["clip"]["label"] for i in timeline["items"]] == [
            "first", "second", "third"
        ]
        assert timeline["total_duration"] == 30.0  # 5 + 10 + 15

        # Move "third" to the top
        third_item = timeline["items"][2]
        moved = client.patch(
            f"/api/timelines/{tl['id']}/items/{third_item['id']}",
            json={"position": 0},
        ).json()
        assert [i["clip"]["label"] for i in moved["items"]] == [
            "third", "first", "second"
        ]
        assert [i["position"] for i in moved["items"]] == [0, 1, 2]

        # Remove the middle item
        first_item = moved["items"][1]
        resp = client.delete(f"/api/timelines/{tl['id']}/items/{first_item['id']}")
        assert resp.status_code == 204
        after = client.get(f"/api/timelines/{tl['id']}").json()
        assert [i["clip"]["label"] for i in after["items"]] == ["third", "second"]
        assert [i["position"] for i in after["items"]] == [0, 1]

    def test_item_clip_must_belong_to_same_project(self):
        project_a, asset_a = _project_with_asset()
        project_b, _ = _project_with_asset()
        clip_a = _make_clip(project_a, asset_a)
        tl_b = client.post(f"/api/projects/{project_b}/timelines", json={}).json()
        resp = client.post(
            f"/api/timelines/{tl_b['id']}/items", json={"clip_id": clip_a["id"]}
        )
        assert resp.status_code == 404


class TestExport:
    def _timeline_with_items(self) -> str:
        project_id, asset_id = _project_with_asset()
        tl = client.post(f"/api/projects/{project_id}/timelines", json={}).json()
        for start, end, label in [(0, 5, "opening"), (10, 22, "the interview")]:
            clip = _make_clip(project_id, asset_id, start, end, label)
            client.post(f"/api/timelines/{tl['id']}/items", json={"clip_id": clip["id"]})
        return tl["id"]

    def test_export_json(self):
        tl_id = self._timeline_with_items()
        resp = client.get(f"/api/timelines/{tl_id}/export?format=json")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        assert "attachment" in resp.headers["content-disposition"]
        data = json.loads(resp.content)
        assert len(data["items"]) == 2
        assert data["items"][0]["clip"]["label"] == "opening"
        assert data["total_duration"] == 17.0

    def test_export_csv(self):
        tl_id = self._timeline_with_items()
        resp = client.get(f"/api/timelines/{tl_id}/export?format=csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        rows = list(csv.reader(io.StringIO(resp.text)))
        assert rows[0] == ["position", "asset_filename", "asset_id", "start_s",
                           "end_s", "duration_s", "label"]
        assert len(rows) == 3
        assert rows[1][6] == "opening"
        assert rows[2][5] == "12.0"

    def test_export_default_is_json(self):
        tl_id = self._timeline_with_items()
        resp = client.get(f"/api/timelines/{tl_id}/export")
        assert resp.headers["content-type"].startswith("application/json")

    def test_export_bad_format_rejected(self):
        tl_id = self._timeline_with_items()
        assert client.get(f"/api/timelines/{tl_id}/export?format=xml").status_code == 422

    def test_export_unknown_timeline_404(self):
        assert client.get("/api/timelines/nope/export").status_code == 404
