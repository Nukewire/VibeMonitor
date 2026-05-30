import threading
import time
from vibemonitor.model import Store, Session
from vibemonitor.config import Config
from vibemonitor import main as main_mod


def test_session_loop_survives_a_scan_exception(monkeypatch):
    store = Store()
    cfg = Config(token="t", poll_sessions_sec=0.01, waiting_ttl_sec=1800,
                 gone_ttl_sec=14400, enable_claude=True, enable_codex=False)
    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        raise OSError("simulated bad file")

    monkeypatch.setattr(main_mod, "scan_claude", boom)
    stop = threading.Event()
    t = threading.Thread(target=main_mod._session_loop, args=(store, cfg, stop), daemon=True)
    t.start()
    time.sleep(0.1)
    stop.set()
    t.join(timeout=1.0)
    assert not t.is_alive()
    assert calls["n"] >= 2          # kept looping despite the exception


def test_session_loop_reaps_gone(monkeypatch):
    store = Store()
    store.upsert(Session(id="old", tool="claude", project="P", last_activity=0.0))
    cfg = Config(token="t", poll_sessions_sec=0.01, waiting_ttl_sec=1800,
                 gone_ttl_sec=100, enable_claude=False, enable_codex=False)
    monkeypatch.setattr(main_mod.time, "time", lambda: 1_000_000.0)
    stop = threading.Event()
    t = threading.Thread(target=main_mod._session_loop, args=(store, cfg, stop), daemon=True)
    t.start()
    time.sleep(0.1)
    stop.set(); t.join(timeout=1.0)
    assert store.get("old") is None
