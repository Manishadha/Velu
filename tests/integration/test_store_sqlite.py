from fastapi.testclient import TestClient

from services.app_server.main import create_app


def test_sqlite_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("TASK_BACKEND", "sqlite")
    monkeypatch.setenv("TASK_DB", str(tmp_path / "tasks.db"))
    app = create_app()
    c = TestClient(app)

    # write two tasks
    for i in range(2):
        r = c.post("/tasks", json={"task": "plan", "payload": {"i": i}})
        assert r.status_code == 200

    # read back
    r = c.get("/tasks?limit=10")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    items = data["items"]
    assert len(items) >= 2
    assert items[0]["payload"] == {"i": 1}
    assert items[1]["payload"] == {"i": 0}
