from vibemonitor.model import Session, Store

def test_upsert_and_get():
    s = Store()
    s.upsert(Session(id="a", tool="claude", project="P", last_activity=100.0))
    got = s.get("a")
    assert got.project == "P"
    assert got.waiting is False

def test_upsert_updates_activity_keeps_waiting():
    s = Store()
    s.upsert(Session(id="a", tool="claude", project="P", last_activity=100.0))
    s.mark_waiting("a", event="Stop", ts=150.0)
    s.touch("a", last_activity=160.0)          # new activity arrives
    got = s.get("a")
    assert got.last_activity == 160.0
    assert got.waiting is True                 # touch does not clear waiting
    assert got.waiting_event == "Stop"

def test_ack_clears_waiting():
    s = Store()
    s.upsert(Session(id="a", tool="claude", project="P", last_activity=100.0))
    s.mark_waiting("a", event="Notification", ts=150.0)
    assert s.get("a").waiting is True
    s.ack("a")
    assert s.get("a").waiting is False
    assert s.get("a").waiting_event is None

def test_remove_and_snapshot():
    s = Store()
    s.upsert(Session(id="a", tool="claude", project="P", last_activity=100.0))
    s.upsert(Session(id="b", tool="codex", project="Q", last_activity=100.0))
    s.remove("a")
    snap = s.snapshot()
    assert [x.id for x in snap] == ["b"]

def test_mark_waiting_unknown_id_is_noop():
    s = Store()
    s.mark_waiting("ghost", event="Stop", ts=1.0)   # must not raise
    assert s.get("ghost") is None
