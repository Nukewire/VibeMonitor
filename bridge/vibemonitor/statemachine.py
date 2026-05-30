from __future__ import annotations
from vibemonitor.model import Session, Store
from vibemonitor.config import Config

# Sentinel: session has been absent long enough to be considered gone
GONE = "gone"


def derive_status(session: Session, now: float, cfg: Config) -> str:
    """Return the display status for a session.

    Priority order:
      1. waiting – session is waiting for user input (never goes gone while waiting)
      2. gone    – session has been inactive longer than cfg.gone_ttl_sec
      3. working – session was active within cfg.working_sec seconds
      4. idle    – session was active within cfg.idle_sec seconds (but not working)

    Returns one of: "waiting", "gone", "working", "idle"
    """
    # Waiting sessions are pinned – they never flip to gone
    if session.waiting:
        return "waiting"

    elapsed = now - session.last_activity

    if elapsed > cfg.gone_ttl_sec:
        return GONE

    if elapsed <= cfg.working_sec:
        return "working"

    return "idle"


WAITING_EVENTS = {"Notification", "Stop"}
ACTIVITY_EVENTS = {"UserPromptSubmit", "SessionStart"}


def apply_hook_event(store: Store, ev: dict) -> None:
    """Apply a hook payload to the store. Auto-creates the session if unseen."""
    sid = ev.get("id")
    if not sid:
        return
    event = ev.get("event", "")
    ts = float(ev.get("ts", 0.0))
    if store.get(sid) is None:
        store.upsert(Session(
            id=sid, tool=ev.get("tool", "claude"),
            project=ev.get("project", "?"), last_activity=ts,
        ))
    if event in WAITING_EVENTS:
        store.mark_waiting(sid, event=event, ts=ts)
    elif event in ACTIVITY_EVENTS:
        store.clear_waiting(sid)
        store.touch(sid, last_activity=ts)
