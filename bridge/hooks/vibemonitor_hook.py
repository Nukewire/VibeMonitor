#!/usr/bin/env python3
"""Invoked by Claude Code hooks. Reads hook JSON on stdin, POSTs to the VibeMonitor hub.
Must never block Claude Code: short timeout, swallow all errors, always exit 0."""
from __future__ import annotations
import argparse
import json
import sys
import time
import urllib.request


def project_from_cwd(cwd: str) -> str:
    cwd = (cwd or "").replace("\\", "/").rstrip("/")
    return cwd.split("/")[-1] if cwd else "?"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--token", required=True)
    args, _ = ap.parse_known_args()

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}

    event = payload.get("hook_event_name") or payload.get("hookEventName") or "Stop"
    body = {
        "id": payload.get("session_id") or payload.get("sessionId") or "unknown",
        "project": project_from_cwd(payload.get("cwd", "")),
        "tool": "claude",
        "event": event,
        "ts": time.time(),
    }
    try:
        req = urllib.request.Request(
            args.url, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "X-VibeMonitor-Token": args.token},
            method="POST")
        urllib.request.urlopen(req, timeout=1.5).read()
    except Exception:
        pass  # never disrupt Claude Code
    return 0


if __name__ == "__main__":
    sys.exit(main())
