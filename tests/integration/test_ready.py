from fastapi.testclient import TestClient

from services.app_server.main import create_app


def test_ready_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("TASK_DB", str(tmp_path / "jobs.db"))
    app = create_app()
    c = TestClient(app)
    r = c.get("/ready")
    assert r.status_code in (200, 503)  # both acceptable at startup
    assert "ok" in r.json() or "detail" in r.json()
