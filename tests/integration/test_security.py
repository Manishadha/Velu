from fastapi.testclient import TestClient

from services.app_server.main import create_app


def client():
    return TestClient(create_app())


def test_cors_headers_present(monkeypatch):
    c = client()
    r = c.options(
        "/tasks",
        headers={
            "Origin": "http://localhost",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.status_code in (200, 204)
    assert "access-control-allow-origin" in {k.lower() for k in r.headers}


def test_payload_too_large(monkeypatch, tmp_path):
    monkeypatch.setenv("MAX_REQUEST_BYTES", "64")
    monkeypatch.setenv("TASK_LOG", str(tmp_path / "tasks.log"))
    c = client()
    payload = {"task": "plan", "payload": {"x": "y" * 200}}
    r = c.post("/tasks", json=payload)
    assert r.status_code == 413
    assert r.json()["detail"] == "payload too large"


def test_rate_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("RATE_REQUESTS", "3")
    monkeypatch.setenv("RATE_WINDOW_SEC", "2")
    monkeypatch.setenv("TASK_LOG", str(tmp_path / "tasks.log"))
    c = client()
    for i in range(3):
        r = c.post("/tasks", json={"task": "plan", "payload": {"i": i}})
        assert r.status_code == 200
    r = c.post("/tasks", json={"task": "plan", "payload": {"i": "boom"}})
    assert r.status_code == 429
    assert r.json()["detail"] == "rate limit exceeded"
