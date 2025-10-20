import os
import time

import requests

API = "http://127.0.0.1:8010"
HEADERS = {"X-API-Key": os.environ.get("API_KEYS", "dev")}


def wait_ready(timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = requests.get(f"{API}/ready", timeout=2)
            if r.ok and r.json().get("ok"):
                return True
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("/ready never went ok")


def test_pipeline_plan():
    wait_ready()
    # enqueue
    r = requests.post(
        f"{API}/tasks",
        headers={**HEADERS, "Content-Type": "application/json"},
        json={"task": "plan", "payload": {"idea": "demo", "module": "hello_mod"}},
        timeout=5,
    )
    r.raise_for_status()
    job_id = r.json()["job_id"]

    # poll result
    for _ in range(40):
        rr = requests.get(f"{API}/results/{job_id}", headers=HEADERS, timeout=5)
        rr.raise_for_status()
        item = rr.json()["item"]
        if item["status"] in ("done", "error"):
            assert item["status"] == "done", item
            assert item["result"].get("ok") is True, item
            assert "demo via hello_mod" in item["result"].get("plan", "")
            return
        time.sleep(0.5)
    raise RuntimeError("job never completed")
