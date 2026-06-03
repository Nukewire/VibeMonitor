from __future__ import annotations
import time
from functools import wraps
from pathlib import Path
from flask import Flask, jsonify, request, Response
from vibemonitor.config import Config
from vibemonitor.model import Store
from vibemonitor.statemachine import derive_status, apply_hook_event, GONE

_STATIC_DIR = Path(__file__).parent / "static"

# status sort order: waiting first, then working, then idle
_ORDER = {"waiting": 0, "working": 1, "idle": 2}

# project names that are temp/cache dirs, not real projects -> hidden from the device
_JUNK_PROJECTS = {"temp", "tmp", "cache", ".cache", "local", "appdata", "roaming"}


def _dedupe_and_filter(rows: list[dict]) -> list[dict]:
    """Collapse same (tool, project) sessions into one row and drop temp/junk dirs.

    - Merged status = most important present (waiting > working > idle).
    - Merged ageSec = smallest (most recent activity) in the group.
    - Representative id = a waiting session's id if any (so /ack targets the one
      that's actually waiting), else the most-recent one.
    - count is kept in the payload for reference but NOT shown in the label.
    """
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        if r["project"].strip().lower() in _JUNK_PROJECTS:
            continue
        groups.setdefault((r["tool"], r["project"]), []).append(r)

    merged = []
    for (tool, project), grp in groups.items():
        best = min(grp, key=lambda x: _ORDER.get(x["status"], 9))   # most important status
        waiting_rows = [g for g in grp if g["waiting"]]
        rep_id = (min(waiting_rows, key=lambda x: x["ageSec"])["id"]
                  if waiting_rows else min(grp, key=lambda x: x["ageSec"])["id"])
        count = len(grp)
        merged.append({
            "id": rep_id,
            "tool": tool,
            "project": project,
            "status": best["status"],
            "ageSec": min(g["ageSec"] for g in grp),
            "waiting": any(g["waiting"] for g in grp),
            "count": count,
        })
    return merged


def create_app(store: Store, cfg: Config, usage_provider=None, clock=time.time,
               heartbeat=None, summary_provider=None) -> Flask:
    app = Flask(__name__)

    def require_token(fn):
        @wraps(fn)
        def wrapper(*a, **k):
            if request.headers.get("X-VibeMonitor-Token") != cfg.token:
                return jsonify({"error": "unauthorized"}), 401
            return fn(*a, **k)
        return wrapper

    @app.get("/")
    def dashboard():
        # The dashboard shell is served WITHOUT a token (it carries no data); its JS
        # fetches /state with the token from localStorage. Keeps secret out of the URL.
        html = _STATIC_DIR / "dashboard.html"
        if not html.exists():
            return Response("dashboard.html not found", status=404, mimetype="text/plain")
        return Response(html.read_text(encoding="utf-8"), mimetype="text/html")

    @app.get("/state")
    @require_token
    def state():
        now = clock()
        out = []
        for s in store.snapshot():
            status = derive_status(s, now=now, cfg=cfg)
            if status == GONE:
                continue          # filtered from response; poll-loop reaper owns removal
            out.append({
                "id": s.id, "tool": s.tool, "project": s.project,
                "status": status, "ageSec": int(max(0.0, now - s.last_activity)),
                "waiting": status == "waiting",
            })
        out = _dedupe_and_filter(out)
        if summary_provider:
            for r in out:                       # rep id carries the group's summary
                r["summary"] = summary_provider(r["id"])
        out.sort(key=lambda x: (_ORDER.get(x["status"], 9), x["ageSec"], x["tool"], x["project"]))
        usage = usage_provider() if usage_provider else {"claude": {}, "codex": {}}
        last_scan = (heartbeat or {}).get("last_scan", 0.0)
        stale_sec = int(max(0.0, now - last_scan)) if last_scan else -1
        return jsonify({"ts": int(now), "usage": usage, "sessions": out,
                        "staleSec": stale_sec})

    @app.post("/ack")
    @require_token
    def ack():
        sid = (request.get_json(silent=True) or {}).get("id")
        if sid:
            now = clock()
            cur = store.get(sid)
            if cur is not None:
                store.ack_group(cur.tool, cur.project, ts=now)
            else:
                store.ack(sid, ts=now)
        return jsonify({"ok": True})

    @app.post("/hook")
    @require_token
    def hook():
        ev = request.get_json(silent=True) or {}
        ev["ts"] = clock()      # trust the hub clock, not the hook process clock
        apply_hook_event(store, ev)
        return jsonify({"ok": True})

    return app
