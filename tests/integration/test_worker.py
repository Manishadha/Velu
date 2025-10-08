import threading
import time

from fastapi.testclient import TestClient

from services.app_server.main import create_app
from services.worker.main import main as worker_main


def test_job_roundtrip(monkeypatch, tmp_path):
    # isolated DB for test
    monkeypatch.setenv("TASK_DB", str(tmp_path / "jobs.db"))

    app = create_app()
    c = TestClient(app)

    # start worker in background
    t = threading.Thread(target=worker_main, daemon=True)
    t.start()

    # submit a task
    r = c.post("/tasks", json={"task": "plan", "payload": {"idea": "test"}})
    assert r.status_code == 200
    job_id = r.json()["job_id"]

    # poll result
    for _ in range(40):
        time.sleep(0.1)
        rr = c.get(f"/results/{job_id}")
        assert rr.status_code == 200
        item = rr.json()["item"]
        if item["status"] == "done":
            assert item["result"]["ok"] is True
            return
    raise AssertionError("job not finished in time")
