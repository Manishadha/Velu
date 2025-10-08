from fastapi.testclient import TestClient

from services.app_server.main import create_app


def test_preview_route_allows_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("RULES_DIR", "data/rules")
    app = create_app()
    c = TestClient(app)
    r = c.post("/route/preview", json={"task": "plan", "payload": {"x": 1}})
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["policy"]["allowed"] is True
    assert "model" in j and j["model"]["name"]


def test_preview_route_denies_deploy(tmp_path, monkeypatch):
    monkeypatch.setenv("RULES_DIR", "data/rules")
    app = create_app()
    c = TestClient(app)
    r = c.post("/route/preview", json={"task": "deploy", "payload": {}})
    assert r.status_code == 200
    assert r.json()["policy"]["allowed"] is False
