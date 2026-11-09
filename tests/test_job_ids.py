import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import server  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "JOBS_ROOT", str(tmp_path / "jobs"))
    os.makedirs(server.JOBS_ROOT)
    # never start a real render
    monkeypatch.setattr(server, "_render_worker", lambda *a, **k: None)
    return TestClient(server.app)


@pytest.mark.parametrize("bad", ["../escape", "..", "a/b", "x" * 65, "has space"])
def test_render_rejects_unsafe_job_id(client, tmp_path, bad):
    r = client.post("/api/render", json={"script": {}, "job_id": bad})
    assert r.status_code == 400
    assert not (tmp_path / "escape").exists()


def test_render_accepts_issued_job_id(client):
    r = client.post("/api/render", json={"script": {}, "job_id": "abc123DEF456"})
    assert r.status_code == 200
    assert r.json() == {"job_id": "abc123DEF456"}


@pytest.mark.parametrize("path", ["/api/jobs/..%2F..%2Fsecret/video"])
def test_video_rejects_unsafe_job_id(client, path):
    assert client.get(path).status_code in (400, 404)
