import time

from orchestrator.router_client import route
from services.queue import sqlite_queue as q


def main():
    q.init()
    print("worker: online")
    while True:
        job_id = q.dequeue()
        if job_id is None:
            time.sleep(0.5)
            continue
        rec = q.load(job_id)
        try:
            result = route(rec["task"])
            q.finish(job_id, result)
            print(f"worker: done {job_id}")
        except Exception as e:
            q.fail(job_id, f"{type(e).__name__}: {e}")
            print(f"worker: error {job_id}: {e}")


if __name__ == "__main__":
    main()
