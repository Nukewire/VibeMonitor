from __future__ import annotations
from vibemonitor.model import Session, Store
from vibemonitor.config import Config

# Sentinel: session has been absent long enough to be considered gone
GONE = "gone"

# project names that are temp/cache dirs, not real projects -> hidden everywhere
JUNK_PROJECTS = {"temp", "tmp", "cache", ".cache", "local", "appdata", "roaming"}


def is_junk_project(project: str) -> bool:
    return project.strip().lower() in JUNK_PROJECTS


def derive_status(session: Session, now: float, cfg: Config) -> str:
    """Return the display status for a session.

    Priority:
      1. waiting – blocked on the user AND the waiting flag is still fresh (set
         within cfg.waiting_ttl_sec). After that it decays naturally.
      2. gone    – inactive longer than cfg.gone_ttl_sec (hidden by the hub).
      3. working – active within cfg.working_sec seconds.
      4. idle    – everything else (still listed).

    Returns one of: "waiting", "gone", "working", "idle"
    """
    # waiting_since=None means the flag was set without a timestamp; treat as not-waiting
    if session.waiting and session.waiting_since is not None:
        if (now - session.waiting_since) <= cfg.waiting_ttl_sec:
            return "waiting"

    elapsed = max(0.0, now - session.last_activity)   # clamp clock skew

    if elapsed > cfg.gone_ttl_sec:
        return GONE
    if elapsed <= cfg.working_sec:
        return "working"
    return "idle"


# Only a true block-on-user prompt counts as waiting for Claude.
WAITING_EVENTS = {"Notification"}
# Turn boundaries / prompts are activity: they clear waiting and refresh recency.
ACTIVITY_EVENTS = {"Stop", "UserPromptSubmit", "SessionStart"}


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
