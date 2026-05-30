from __future__ import annotations
import threading
from dataclasses import dataclass, replace


@dataclass
class Session:
    id: str
    tool: str                       # "claude" | "codex"
    project: str
    last_activity: float            # epoch seconds
    waiting: bool = False
    waiting_event: str | None = None  # "Notification" | "Stop" | "task_complete"
    waiting_since: float | None = None
    acked_at: float | None = None


class Store:
    """Thread-safe in-memory session store. All reads return copies."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, Session] = {}

    def upsert(self, s: Session) -> None:
        with self._lock:
            existing = self._sessions.get(s.id)
            if existing is None:
                self._sessions[s.id] = replace(s)
            else:
                # preserve waiting flags unless the incoming session sets them
                self._sessions[s.id] = replace(
                    existing,
                    project=s.project,
                    tool=s.tool,
                    last_activity=max(existing.last_activity, s.last_activity),
                )

    def touch(self, sid: str, last_activity: float) -> None:
        with self._lock:
            cur = self._sessions.get(sid)
            if cur:
                self._sessions[sid] = replace(cur, last_activity=max(cur.last_activity, last_activity))

    def mark_waiting(self, sid: str, event: str, ts: float) -> None:
        with self._lock:
            cur = self._sessions.get(sid)
            if cur:
                self._sessions[sid] = replace(cur, waiting=True, waiting_event=event, waiting_since=ts)

    def clear_waiting(self, sid: str) -> None:
        with self._lock:
            cur = self._sessions.get(sid)
            if cur and cur.waiting:
                self._sessions[sid] = replace(cur, waiting=False, waiting_event=None, waiting_since=None)

    def ack(self, sid: str, ts: float) -> None:
        with self._lock:
            cur = self._sessions.get(sid)
            if cur:
                self._sessions[sid] = replace(cur, waiting=False, waiting_event=None,
                                              waiting_since=None, acked_at=ts)

    def ack_group(self, tool: str, project: str, ts: float) -> None:
        with self._lock:
            for sid, cur in list(self._sessions.items()):
                if cur.tool == tool and cur.project == project:
                    self._sessions[sid] = replace(cur, waiting=False, waiting_event=None,
                                                  waiting_since=None, acked_at=ts)

    def remove_if_gone(self, sid: str, now: float, cfg, derive) -> bool:
        """Atomically remove the session iff its derived status is gone. Returns
        True if removed. Run from the single poll thread to avoid TOCTOU races."""
        with self._lock:
            cur = self._sessions.get(sid)
            if cur is None:
                return False
            if derive(cur, now=now, cfg=cfg) == "gone":
                del self._sessions[sid]
                return True
            return False

    def remove(self, sid: str) -> None:
        with self._lock:
            self._sessions.pop(sid, None)

    def get(self, sid: str) -> Session | None:
        with self._lock:
            cur = self._sessions.get(sid)
            return replace(cur) if cur else None

    def snapshot(self) -> list[Session]:
        with self._lock:
            return [replace(s) for s in self._sessions.values()]
