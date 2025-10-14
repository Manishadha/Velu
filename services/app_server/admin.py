# services/app_server/admin.py
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Query

from services.queue import sqlite_queue as q

router = APIRouter()


def admin_enabled() -> bool:
    return os.getenv("ADMIN_ROUTES", "0").lower() not in {"0", "", "false", "no"}


@router.get("/jobs")
def list_jobs(limit: int = Query(50, ge=1, le=500)):
    if not admin_enabled():
        raise HTTPException(status_code=404, detail="Not Found")
    return {"items": q.list_recent(limit)}


@router.get("/jobs/{job_id}")
def get_job(job_id: int):
    if not admin_enabled():
        raise HTTPException(status_code=404, detail="Not Found")
    item = q.load(job_id)
    if not item:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"item": item}
