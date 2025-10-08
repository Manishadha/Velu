import datetime as dt
import glob
import os
import pathlib
import sqlite3
import sys
import time

SRC = os.getenv("TASK_DB", "/data/jobs.db")
BACKDIR = "/data/backups"
pathlib.Path(BACKDIR).mkdir(parents=True, exist_ok=True)

KEEP = int(os.getenv("RETENTION_DAYS", "14"))


def do_backup():
    ts = dt.datetime.now().strftime("%Y-%m-%d")
    dst = f"{BACKDIR}/jobs-{ts}.db"
    con = sqlite3.connect(SRC)
    bcon = sqlite3.connect(dst)
    try:
        con.backup(bcon)  # online-safe backup
    finally:
        bcon.close()
        con.close()
    # prune old snapshots
    cutoff = dt.datetime.now() - dt.timedelta(days=KEEP)
    for f in glob.glob(f"{BACKDIR}/jobs-*.db"):
        try:
            d = dt.datetime.strptime(os.path.basename(f)[5:15], "%Y-%m-%d")
            if d < cutoff:
                os.remove(f)
        except Exception:
            pass


if __name__ == "__main__":
    while True:
        try:
            do_backup()
            print("backup: ok", flush=True)
        except Exception as e:
            print("backup: failed:", e, file=sys.stderr, flush=True)
        time.sleep(24 * 60 * 60)
