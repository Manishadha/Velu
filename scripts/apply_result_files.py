#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description="Write files from a job result into the working tree.")
    ap.add_argument("job_id", type=int)
    ap.add_argument("--db", default="data/jobs.db")
    ap.add_argument("--root", default=".")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT result FROM jobs WHERE id=?", (args.job_id,)).fetchone()
    if not row or not row["result"]:
        raise SystemExit(f"No result for job {args.job_id}")

    res = json.loads(row["result"])
    files = (
        res.get("files")
        or res.get("subjobs_detail", {}).get("generate", {}).get("result", {}).get("files")
        or []
    )

    root = Path(args.root).resolve()
    written = []
    for f in files:
        p = root / f["path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        # support optional base64 later; for now plain text
        content = f.get("content", "")
        p.write_text(content, encoding="utf-8")
        written.append(str(p.relative_to(root)))

    print("WROTE:", *written, sep="\n - ")


if __name__ == "__main__":
    main()
