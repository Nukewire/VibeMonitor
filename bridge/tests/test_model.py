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


def test_ack_records_acked_at():
    st = Store()
    st.upsert(Session(id="x", tool="codex", project="P", last_activity=10.0))
    st.mark_waiting("x", event="task_complete", ts=10.0)
    st.ack("x", ts=20.0)
    s = st.get("x")
    assert s.waiting is False
    assert s.acked_at == 20.0


def test_ack_group_clears_all_in_project():
    st = Store()
    st.upsert(Session(id="a", tool="codex", project="P", last_activity=10.0))
    st.upsert(Session(id="b", tool="codex", project="P", last_activity=11.0))
    st.upsert(Session(id="c", tool="codex", project="OTHER", last_activity=12.0))
    for sid in ("a", "b", "c"):
        st.mark_waiting(sid, event="task_complete", ts=10.0)
    st.ack_group("codex", "P", ts=30.0)
    assert st.get("a").waiting is False and st.get("a").acked_at == 30.0
    assert st.get("b").waiting is False and st.get("b").acked_at == 30.0
    assert st.get("c").waiting is True       # different project untouched


def test_remove_if_gone_removes_stale():
    from vibemonitor.config import Config
    from vibemonitor import statemachine
    st = Store()
    st.upsert(Session(id="x", tool="codex", project="P", last_activity=1000.0))
    cfg = Config(token="t", working_sec=10, waiting_ttl_sec=1800, gone_ttl_sec=100)
    assert st.remove_if_gone("x", now=2000.0, cfg=cfg, derive=statemachine.derive_status) is True
    assert st.get("x") is None


def test_remove_if_gone_keeps_fresh_waiting():
    from vibemonitor.config import Config
    from vibemonitor import statemachine
    st = Store()
    st.upsert(Session(id="x", tool="codex", project="P", last_activity=1000.0))
    st.mark_waiting("x", event="task_complete", ts=1000.0)
    cfg = Config(token="t", working_sec=10, waiting_ttl_sec=1800, gone_ttl_sec=100)
    assert st.remove_if_gone("x", now=1100.0, cfg=cfg, derive=statemachine.derive_status) is False
    assert st.get("x") is not None
