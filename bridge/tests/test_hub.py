import json
from vibemonitor.config import Config
from vibemonitor.model import Store, Session
from vibemonitor.hub import create_app

CFG = Config(token="secret", working_sec=10, waiting_ttl_sec=1800, gone_ttl_sec=1800)
H = {"X-VibeMonitor-Token": "secret"}


def make_client(store, usage=None, summary_provider=None):
    app = create_app(store, CFG, usage_provider=lambda: (usage or {"claude": {}, "codex": {}}),
                     clock=lambda: 1005.0, summary_provider=summary_provider)
    app.testing = True
    return app.test_client()


def test_state_includes_summary_when_provider_set():
    st = Store()
    st.upsert(Session(id="a", tool="claude", project="P", last_activity=1000.0))
    c = make_client(st, summary_provider=lambda sid: "Fixing the parser" if sid == "a" else None)
    body = c.get("/state", headers=H).get_json()
    row = next(s for s in body["sessions"] if s["project"] == "P")
    assert row["summary"] == "Fixing the parser"


def test_state_summary_absent_without_provider():
    st = Store()
    st.upsert(Session(id="a", tool="claude", project="P", last_activity=1000.0))
    body = make_client(st).get("/state", headers=H).get_json()
    row = next(s for s in body["sessions"] if s["project"] == "P")
    assert "summary" not in row          # no provider -> field omitted, contract unchanged


def test_ha_requires_token():
    assert make_client(Store()).get("/ha").status_code == 401


def test_ha_flat_fields_and_counts():
    st = Store()
    # a waiting claude session (waiting_since fresh) + an idle codex one
    st.upsert(Session(id="w", tool="claude", project="WebApp", last_activity=1000.0,
                      waiting=True, waiting_event="Notification", waiting_since=1004.0))
    st.upsert(Session(id="i", tool="codex", project="ApiServer", last_activity=200.0))
    usage = {"claude": {"ok": True, "pct": 0.24, "weekPct": 0.06, "resetSec": 8040},
             "codex": {"ok": False, "pct": None, "weekPct": None, "resetSec": None}}
    c = make_client(st, usage=usage,
                    summary_provider=lambda sid: "Refactor auth" if sid == "w" else None)
    body = c.get("/ha", headers=H).get_json()
    assert body["claude_ok"] is True
    assert body["claude_pct"] == 24 and body["claude_week_pct"] == 6
    assert body["claude_reset_min"] == 134          # 8040s -> 134 min
    assert body["codex_ok"] is False and body["codex_pct"] is None
    assert body["waiting_count"] == 1 and body["idle_count"] == 1
    assert body["session_count"] == 2 and body["any_waiting"] is True
    assert body["waiting"] == [{"tool": "claude", "project": "WebApp",
                                "summary": "Refactor auth"}]


def test_ha_handles_missing_usage_gracefully():
    body = make_client(Store()).get("/ha", headers=H).get_json()
    assert body["claude_pct"] is None and body["claude_ok"] is False
    assert body["waiting_count"] == 0 and body["any_waiting"] is False
    assert body["waiting"] == []


def test_state_requires_token():
    c = make_client(Store())
    assert c.get("/state").status_code == 401


def test_state_returns_sessions_with_status():
    st = Store()
    st.upsert(Session(id="a", tool="claude", project="P", last_activity=1000.0))
    st.upsert(Session(id="b", tool="codex", project="Q", last_activity=500.0))  # idle
    c = make_client(st)
    r = c.get("/state", headers=H)
    assert r.status_code == 200
    body = r.get_json()
    by_id = {s["id"]: s for s in body["sessions"]}
    assert by_id["a"]["status"] == "working"
    assert by_id["a"]["ageSec"] == 5
    assert by_id["b"]["status"] == "idle"
    assert "usage" in body and "ts" in body


def test_state_drops_gone_sessions():
    st = Store()
    # clock=1005.0, last_activity=-800.0 -> elapsed=1805 > gone_ttl_sec(1800) -> GONE.
    st.upsert(Session(id="old", tool="claude", project="P", last_activity=-800.0))
    c = make_client(st)
    body = c.get("/state", headers=H).get_json()
    assert body["sessions"] == []


def test_state_sorts_waiting_first():
    st = Store()
    st.upsert(Session(id="work", tool="claude", project="P", last_activity=1000.0))
    st.upsert(Session(id="wait", tool="claude", project="Q", last_activity=1000.0,
                      waiting=True, waiting_event="Stop", waiting_since=1001.0))
    c = make_client(st)
    body = c.get("/state", headers=H).get_json()
    assert body["sessions"][0]["id"] == "wait"


def test_ack_clears_waiting():
    st = Store()
    st.upsert(Session(id="a", tool="claude", project="P", last_activity=1000.0,
                      waiting=True, waiting_event="Stop", waiting_since=1001.0))
    c = make_client(st)
    r = c.post("/ack", headers=H, json={"id": "a"})
    assert r.status_code == 200
    assert st.get("a").waiting is False


def test_hook_marks_waiting():
    st = Store()
    st.upsert(Session(id="a", tool="claude", project="P", last_activity=1000.0))
    c = make_client(st)
    r = c.post("/hook", headers=H,
               json={"id": "a", "event": "Notification", "ts": 1002.0,
                     "tool": "claude", "project": "P"})
    assert r.status_code == 200
    assert st.get("a").waiting is True


def test_hook_rejects_bad_token():
    c = make_client(Store())
    r = c.post("/hook", headers={"X-VibeMonitor-Token": "nope"}, json={})
    assert r.status_code == 401


def test_state_dedupes_by_project_with_count():
    st = Store()
    # three DemoApp sessions: one waiting, two idle -> collapse to 1 row
    st.upsert(Session(id="ct1", tool="claude", project="DemoApp", last_activity=1000.0))
    st.upsert(Session(id="ct2", tool="claude", project="DemoApp", last_activity=900.0,
                      waiting=True, waiting_event="Stop", waiting_since=1001.0))
    st.upsert(Session(id="ct3", tool="claude", project="DemoApp", last_activity=500.0))
    st.upsert(Session(id="va", tool="claude", project="VibeMonitor", last_activity=1000.0))
    body = make_client(st).get("/state", headers=H).get_json()
    by_proj = {s["project"]: s for s in body["sessions"]}
    # collapsed to a single plain "DemoApp" row (no "(N)" suffix in the label)
    assert "DemoApp" in by_proj
    ct = by_proj["DemoApp"]
    assert ct["count"] == 3             # count still in payload for reference
    assert ct["waiting"] is True and ct["status"] == "waiting"
    assert ct["id"] == "ct2"            # representative = the waiting session (for /ack)
    assert by_proj["VibeMonitor"]["count"] == 1


def test_state_hides_temp_junk():
    st = Store()
    st.upsert(Session(id="t1", tool="claude", project="Temp", last_activity=1000.0))
    st.upsert(Session(id="t2", tool="claude", project="tmp", last_activity=1000.0))
    st.upsert(Session(id="real", tool="claude", project="WebApp", last_activity=1000.0))
    body = make_client(st).get("/state", headers=H).get_json()
    projs = [s["project"] for s in body["sessions"]]
    assert projs == ["WebApp"]        # Temp/tmp filtered out


def test_ack_clears_whole_project_group():
    st = Store()
    st.upsert(Session(id="a", tool="codex", project="P", last_activity=1000.0,
                      waiting=True, waiting_event="task_complete", waiting_since=1001.0))
    st.upsert(Session(id="b", tool="codex", project="P", last_activity=1001.0,
                      waiting=True, waiting_event="task_complete", waiting_since=1001.0))
    c = make_client(st)
    r = c.post("/ack", headers=H, json={"id": "a"})   # ack representative -> both clear
    assert r.status_code == 200
    assert st.get("a").waiting is False
    assert st.get("b").waiting is False


def test_state_does_not_mutate_store():
    st = Store()
    st.upsert(Session(id="x", tool="claude", project="P", last_activity=-800.0))  # gone vs clock 1005
    c = make_client(st)
    body = c.get("/state", headers=H).get_json()
    assert all(s["id"] != "x" for s in body["sessions"])   # filtered from response
    assert st.get("x") is not None                          # but NOT removed (reaper owns removal)


def test_hook_stamps_server_ts():
    st = Store()
    c = make_client(st)
    c.post("/hook", headers=H,
           json={"id": "z", "event": "Notification", "ts": 9_999_999_999.0,
                 "tool": "claude", "project": "P"})
    s = st.get("z")
    assert s is not None
    assert s.waiting_since == 1005.0    # server clock (make_client clock=1005.0), not client ts
