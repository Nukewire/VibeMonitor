from __future__ import annotations
import json
from datetime import date, timedelta
from pathlib import Path
from vibemonitor.model import Session, Store

_WORKING = "task_started"
_DONE = "task_complete"


def _project_from_cwd(cwd: str) -> str:
    cwd = cwd.replace("\\", "/").rstrip("/")
    return cwd.split("/")[-1] if cwd else "?"


def parse_rollout(path: Path) -> dict:
    """Read a Codex rollout jsonl; return {id, project, waiting}.

    waiting is True when the last task_started/task_complete seen is a
    task_complete (turn finished, awaiting the user)."""
    sid = path.stem.split("-")[-1]
    project = "?"
    last_turn_state = None
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
            if pt in (_WORKING, _DONE):
                last_turn_state = pt
    return {"id": sid, "project": project, "waiting": last_turn_state == _DONE}


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
            info = parse_rollout(f)
            store.upsert(Session(
                id=info["id"], tool="codex", project=info["project"],
                last_activity=mtime,
            ))
            if info["waiting"]:
                store.mark_waiting(info["id"], event="task_complete", ts=mtime)
            else:
                store.clear_waiting(info["id"])
