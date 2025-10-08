# scripts/sqlite_backup.py
from __future__ import annotations

import contextlib
import datetime as dt
import glob
import os
import pathlib
import shutil
import sqlite3
import sys
import tempfile
import time

SRC = os.getenv("TASK_DB", "/data/jobs.db")
DST_DIR = "/data/backups"
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "14"))
INTERVAL = int(os.getenv("BACKUP_INTERVAL_SECONDS", str(24 * 60 * 60)))  # 24h default

pathlib.Path(DST_DIR).mkdir(parents=True, exist_ok=True)


def _timestamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def backup_once() -> str:
    """Online-safe snapshot using sqlite backup + atomic rename."""
    ts = _timestamp()
    final_path = os.path.join(DST_DIR, f"jobs-{ts}.db")

    with tempfile.NamedTemporaryFile(dir=DST_DIR, delete=False) as tmp:
        tmp_path = tmp.name

    try:
        with sqlite3.connect(SRC) as src, sqlite3.connect(tmp_path) as dst:
            dst.execute("PRAGMA journal_mode=WAL;")
            dst.execute("PRAGMA synchronous=NORMAL;")
            src.backup(dst)

        # preserve metadata (mtime will reflect source)
        with contextlib.suppress(Exception):
            shutil.copystat(SRC, tmp_path, follow_symlinks=True)

        os.replace(tmp_path, final_path)  # atomic on same fs
        return final_path
    except Exception:
        with contextlib.suppress(Exception):
            os.remove(tmp_path)
        raise


def prune_old() -> None:
    """Delete snapshots older than RETENTION_DAYS by mtime."""
    cutoff = time.time() - (RETENTION_DAYS * 86400)
    for f in glob.glob(os.path.join(DST_DIR, "jobs-*.db")):
        with contextlib.suppress(Exception):
            if os.path.getmtime(f) < cutoff:
                pathlib.Path(f).unlink(missing_ok=True)


def main() -> None:
    while True:
        try:
            path = backup_once()
            print(f"backup: ok -> {path}", flush=True)
            prune_old()
        except Exception as e:
            print(f"backup: failed: {e}", file=sys.stderr, flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
