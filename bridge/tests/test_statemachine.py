from vibemonitor.config import Config
from vibemonitor.model import Session
from vibemonitor.statemachine import derive_status, GONE

CFG = Config(token="t", working_sec=10, idle_sec=120, gone_ttl_sec=1800)

def mk(**kw):
    base = dict(id="a", tool="claude", project="P", last_activity=1000.0)
    base.update(kw)
    return Session(**base)

def test_working_when_recent():
    assert derive_status(mk(last_activity=1000.0), now=1005.0, cfg=CFG) == "working"

def test_idle_when_quiet():
    assert derive_status(mk(last_activity=1000.0), now=1100.0, cfg=CFG) == "idle"

def test_gone_when_stale():
    assert derive_status(mk(last_activity=1000.0), now=1000.0 + 2000, cfg=CFG) == GONE

def test_waiting_overrides_recency():
    s = mk(last_activity=1000.0, waiting=True, waiting_event="Stop", waiting_since=1001.0)
    assert derive_status(s, now=1002.0, cfg=CFG) == "waiting"

def test_waiting_overrides_even_when_idle():
    s = mk(last_activity=1000.0, waiting=True, waiting_event="Notification", waiting_since=1001.0)
    assert derive_status(s, now=1100.0, cfg=CFG) == "waiting"

def test_waiting_session_never_goes_gone():
    s = mk(last_activity=1000.0, waiting=True, waiting_event="Stop", waiting_since=1001.0)
    assert derive_status(s, now=1000.0 + 99999, cfg=CFG) == "waiting"

def test_boundary_working_inclusive():
    # exactly working_sec old counts as working
    assert derive_status(mk(last_activity=1000.0), now=1010.0, cfg=CFG) == "working"


# ---------------------------------------------------------------------------
# Task 4 – apply_hook_event
# ---------------------------------------------------------------------------

from vibemonitor.model import Store
from vibemonitor.statemachine import apply_hook_event


def test_apply_notification_marks_waiting():
    st = Store()
    st.upsert(mk(id="x", last_activity=1000.0))
    apply_hook_event(st, {"id": "x", "event": "Notification", "ts": 1001.0,
                          "tool": "claude", "project": "P"})
    assert st.get("x").waiting is True
    assert st.get("x").waiting_event == "Notification"


def test_apply_stop_marks_waiting():
    st = Store()
    st.upsert(mk(id="x", last_activity=1000.0))
    apply_hook_event(st, {"id": "x", "event": "Stop", "ts": 1002.0,
                          "tool": "claude", "project": "P"})
    assert st.get("x").waiting is True


def test_apply_userpromptsubmit_clears_waiting_and_touches():
    st = Store()
    st.upsert(mk(id="x", last_activity=1000.0))
    apply_hook_event(st, {"id": "x", "event": "Stop", "ts": 1002.0,
                          "tool": "claude", "project": "P"})
    apply_hook_event(st, {"id": "x", "event": "UserPromptSubmit", "ts": 1010.0,
                          "tool": "claude", "project": "P"})
    s = st.get("x")
    assert s.waiting is False
    assert s.last_activity == 1010.0


def test_apply_event_autocreates_unknown_session():
    st = Store()
    apply_hook_event(st, {"id": "new", "event": "Notification", "ts": 5.0,
                          "tool": "claude", "project": "Z"})
    s = st.get("new")
    assert s is not None and s.waiting is True and s.project == "Z"


def test_apply_unknown_event_is_ignored():
    st = Store()
    st.upsert(mk(id="x", last_activity=1000.0))
    apply_hook_event(st, {"id": "x", "event": "Frobnicate", "ts": 9.0,
                          "tool": "claude", "project": "P"})
    assert st.get("x").waiting is False
