#!/usr/bin/env python3
import json
import os
import sys
import urllib.request

HOST = os.getenv("HOST", "http://127.0.0.1:8000")
task = sys.argv[1] if len(sys.argv) > 1 else "plan"
payload = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {"demo": 1}

req = urllib.request.Request(
    f"{HOST}/tasks",
    data=json.dumps({"task": task, "payload": payload}).encode(),
    headers={"content-type": "application/json"},
)
with urllib.request.urlopen(req) as r:
    print(r.read().decode())
