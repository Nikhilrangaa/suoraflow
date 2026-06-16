"""
test_projects.py — Integration tests for Project CRUD.

Runs in the docker compose context where DB + Redis are live.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_create_project():
    resp = client.post("/api/projects", json={"name": "Test Project", "description": "desc"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Project"
    assert data["description"] == "desc"
    assert "id" in data
    assert "created_at" in data
    assert data["asset_count"] == 0


def test_create_project_empty_name():
    resp = client.post("/api/projects", json={"name": "  "})
    assert resp.status_code == 422


def test_list_projects():
    # Create a project first
    client.post("/api/projects", json={"name": "List Test"})
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert "projects" in data
    assert "total" in data
    assert isinstance(data["projects"], list)
    assert data["total"] == len(data["projects"])


def test_get_project():
    create_resp = client.post("/api/projects", json={"name": "Get Test"})
    project_id = create_resp.json()["id"]

    resp = client.get(f"/api/projects/{project_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == project_id


def test_get_project_not_found():
    resp = client.get("/api/projects/nonexistent-id-12345")
    assert resp.status_code == 404


def test_delete_project():
    create_resp = client.post("/api/projects", json={"name": "Delete Test"})
    project_id = create_resp.json()["id"]

    del_resp = client.delete(f"/api/projects/{project_id}")
    assert del_resp.status_code == 204

    get_resp = client.get(f"/api/projects/{project_id}")
    assert get_resp.status_code == 404


def test_delete_project_not_found():
    resp = client.delete("/api/projects/nonexistent-id-99999")
    assert resp.status_code == 404
