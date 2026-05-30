from __future__ import annotations
import json
import re
from datetime import date, timedelta
from pathlib import Path
from vibemonitor.model import Session, Store

_WORKING = "task_started"
_DONE = "task_complete"
_ABORTED = "turn_aborted"

# v7-style uuid 8-4-4-4-12. Codex names files rollout-<ISO ts>-<uuid>.jsonl
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _uuid_from_stem(stem: str) -> str:
    """Full session uuid from a rollout filename stem; fall back to the last
    dash-group only if no uuid is present."""
    m = _UUID_RE.search(stem)
    return m.group(0) if m else stem.split("-")[-1]


def _project_from_cwd(cwd: str) -> str:
    cwd = cwd.replace("\\", "/").rstrip("/")
    return cwd.split("/")[-1] if cwd else "?"


def parse_rollout(path: Path) -> dict:
    """Read a Codex rollout jsonl; return {id, project, waiting}.

    waiting (turn finished, your move) is determined by, in order:
      1. last task_started/task_complete/turn_aborted marker, if any
         (task_complete -> waiting; task_started/turn_aborted -> not waiting)
      2. version fallback when no markers exist: last event_msg of
         agent_message -> waiting; user_message -> not waiting.
    """
    sid = _uuid_from_stem(path.stem)
    project = "?"
    last_turn_state = None
    last_msg_kind = None
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = o.get("type")
        payload = o.get("payload", {})
        if t == "session_meta":
            if payload.get("id"):
                sid = payload["id"]
            if payload.get("cwd"):
                project = _project_from_cwd(payload["cwd"])
        elif t == "event_msg":
            pt = payload.get("type")
            if pt in (_WORKING, _DONE, _ABORTED):
                last_turn_state = pt
            if pt == "agent_message":
                last_msg_kind = "agent"
            elif pt == "user_message":
                last_msg_kind = "user"

    if last_turn_state is not None:
        waiting = last_turn_state == _DONE
    else:
        waiting = last_msg_kind == "agent"     # version-agnostic fallback
    return {"id": sid, "project": project, "waiting": waiting}


def codex_sessions_root() -> Path:
    return Path.home() / ".codex" / "sessions"


def _day_dir(root: Path, d: tuple[int, int, int]) -> Path:
    y, m, day = d
    return root / f"{y:04d}" / f"{m:02d}" / f"{day:02d}"


def scan_codex(store: Store, sessions_root: Path | None = None,
               today: tuple[int, int, int] | None = None, now: float = 0.0) -> None:
    """Scan today's (and yesterday's) Codex date dirs only. Safe on missing root."""
    root = Path(sessions_root) if sessions_root is not None else codex_sessions_root()
    if not root.exists():
        return
    if today is None:
        t = date.today()
        today = (t.year, t.month, t.day)
    days = [today]
    yt = date(*today) - timedelta(days=1)
    days.append((yt.year, yt.month, yt.day))

    for d in days:
        day_dir = _day_dir(root, d)
        if not day_dir.exists():
            continue
        for f in day_dir.glob("*.jsonl"):
            try:
                mtime = f.stat().st_mtime
            except OSError:
                continue
            if now:
                mtime = min(mtime, now)            # clamp clock skew / future files
            info = parse_rollout(f)
            sid = info["id"]
            store.upsert(Session(
                id=sid, tool="codex", project=info["project"], last_activity=mtime,
            ))
            if info["waiting"]:
                cur = store.get(sid)
                # don't resurrect an alert the user already acked unless the file
                # has new activity since the ack
                if cur and cur.acked_at is not None and mtime <= cur.acked_at:
                    continue
                store.mark_waiting(sid, event="task_complete", ts=mtime)
            else:
                store.clear_waiting(sid)
