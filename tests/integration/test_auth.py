from fastapi.testclient import TestClient

from services.app_server.main import create_app


def client(env=None):
    app = create_app()
    return TestClient(app)


def test_post_requires_key_when_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("TASK_LOG", str(tmp_path / "tasks.log"))
    monkeypatch.setenv("API_KEYS", "k1:dev,k2:ops")

    c = client()
    # No key -> 401
    r = c.post("/tasks", json={"task": "plan", "payload": {}})
    assert r.status_code == 401
    assert r.json()["detail"] == "missing or invalid api key"

    # Bad key -> 401
    r = c.post("/tasks", json={"task": "plan", "payload": {}}, headers={"X-API-Key": "nope"})
    assert r.status_code == 401

    # Good key -> 200
    r = c.post(
        "/tasks",
        json={"task": "plan", "payload": {"ok": 1}},
        headers={"X-API-Key": "k1"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_per_key_rate_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("TASK_LOG", str(tmp_path / "tasks.log"))
    monkeypatch.setenv("API_KEYS", "kA:alpha,kB:beta")
    monkeypatch.setenv("RATE_REQUESTS", "2")
    monkeypatch.setenv("RATE_WINDOW_SEC", "10")

    c = client()

    # key A: 2 ok, 3rd 429
    for i in range(2):
        r = c.post(
            "/tasks",
            json={"task": "plan", "payload": {"i": i}},
            headers={"X-API-Key": "kA"},
        )
        assert r.status_code == 200
    r = c.post(
        "/tasks",
        json={"task": "plan", "payload": {"i": "boom"}},
        headers={"X-API-Key": "kA"},
    )
    assert r.status_code == 429

    # key B starts fresh, should pass
    r = c.post(
        "/tasks",
        json={"task": "plan", "payload": {"j": 0}},
        headers={"X-API-Key": "kB"},
    )
    assert r.status_code == 200


def test_get_endpoints_are_open_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("TASK_LOG", str(tmp_path / "tasks.log"))
    monkeypatch.setenv("API_KEYS", "k1:dev")
    c = client()
    assert c.get("/health").status_code == 200
    assert c.get("/tasks").status_code == 200
