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


def test_downsample_includes_first_and_last():
    samples = [{"ts": i, "pct": i / 1000.0} for i in range(1000)]
    out = main_mod._downsample(samples, n=80)
    assert len(out) <= 80
    assert out[0]["ts"] == 0            # oldest kept
    assert out[-1]["ts"] == 999        # most-recent kept (the bug was dropping the tail)
    assert all(a["ts"] < b["ts"] for a, b in zip(out, out[1:]))   # strictly increasing


def test_downsample_passthrough_when_small():
    samples = [{"ts": 1, "pct": 0.1}, {"ts": 2, "pct": 0.2}]
    assert main_mod._downsample(samples, n=80) == samples


def _summary_cfg(**kw):
    base = dict(token="t", poll_summary_sec=0.01, working_sec=60,
                waiting_ttl_sec=1800, gone_ttl_sec=14400,
                summary_enabled=True, openrouter_api_key="k", summary_model="m")
    base.update(kw)
    return Config(**base)


def test_summary_loop_populates_cache_and_only_calls_on_change(monkeypatch, tmp_path):
    from vibemonitor.summarycache import SummaryCache, hash_text
    # one active claude session with a transcript file
    f = tmp_path / "sess1.jsonl"
    f.write_text('{"type":"user","message":{"role":"user","content":"fix the parser"}}\n',
                 encoding="utf-8")
    store = Store()
    store.upsert(Session(id="sess1", tool="claude", project="P", last_activity=1_000_000.0))
    summaries = SummaryCache()
    cfg = _summary_cfg()
    monkeypatch.setattr(main_mod.time, "time", lambda: 1_000_000.0)
    monkeypatch.setattr(main_mod, "claude_session_paths", lambda: {"sess1": f})
    calls = {"n": 0}

    def fake_summarize(text, *, api_key, model):
        calls["n"] += 1
        return "Fixing the parser"

    monkeypatch.setattr(main_mod, "summarize", fake_summarize)
    stop = threading.Event()
    t = threading.Thread(target=main_mod._summary_loop,
                         args=(store, summaries, cfg, stop), daemon=True)
    t.start()
    time.sleep(0.1)
    stop.set(); t.join(timeout=1.0)
    assert summaries.get("sess1") == "Fixing the parser"
    assert calls["n"] == 1          # unchanged prompt -> model called once, not every tick


def test_summary_loop_disabled_without_key(monkeypatch, tmp_path):
    from vibemonitor.summarycache import SummaryCache
    f = tmp_path / "s.jsonl"
    f.write_text('{"type":"user","message":{"role":"user","content":"hi"}}\n', encoding="utf-8")
    store = Store()
    store.upsert(Session(id="s", tool="claude", project="P", last_activity=1_000_000.0))
    summaries = SummaryCache()
    cfg = _summary_cfg(openrouter_api_key=None)
    monkeypatch.setattr(main_mod.time, "time", lambda: 1_000_000.0)
    monkeypatch.setattr(main_mod, "claude_session_paths", lambda: {"s": f})
    monkeypatch.setattr(main_mod, "summarize", lambda *a, **k: "nope")
    stop = threading.Event()
    t = threading.Thread(target=main_mod._summary_loop,
                         args=(store, summaries, cfg, stop), daemon=True)
    t.start()
    time.sleep(0.05)
    stop.set(); t.join(timeout=1.0)
    assert summaries.get("s") is None      # no key -> never summarizes


def test_session_loop_fires_waiting_webhook(monkeypatch):
    from vibemonitor.notifier import WebhookNotifier
    store = Store()
    store.upsert(Session(id="w", tool="claude", project="WebApp", last_activity=1_000_000.0,
                         waiting=True, waiting_event="Notification", waiting_since=1_000_000.0))
    cfg = Config(token="t", poll_sessions_sec=0.01, working_sec=60,
                 waiting_ttl_sec=1800, gone_ttl_sec=14400,
                 enable_claude=False, enable_codex=False)
    monkeypatch.setattr(main_mod.time, "time", lambda: 1_000_000.0)
    sent = []
    notifier = WebhookNotifier("http://hook", poster=lambda u, p, timeout=5.0: sent.append(p),
                               clock=lambda: 1_000_000.0)
    stop = threading.Event()
    t = threading.Thread(target=main_mod._session_loop,
                         args=(store, cfg, stop, None, notifier, None), daemon=True)
    t.start()
    time.sleep(0.1)
    stop.set(); t.join(timeout=1.0)
    assert any(e["event"] == "waiting" and e["project"] == "WebApp" for e in sent)


def test_summary_loop_forgets_reaped_sessions(monkeypatch, tmp_path):
    from vibemonitor.summarycache import SummaryCache, hash_text
    summaries = SummaryCache()
    summaries.set("ghost", hash_text("old"), "stale summary")   # not in store anymore
    store = Store()                                              # empty store
    cfg = _summary_cfg()
    monkeypatch.setattr(main_mod.time, "time", lambda: 1_000_000.0)
    monkeypatch.setattr(main_mod, "claude_session_paths", lambda: {})
    stop = threading.Event()
    t = threading.Thread(target=main_mod._summary_loop,
                         args=(store, summaries, cfg, stop), daemon=True)
    t.start()
    time.sleep(0.05)
    stop.set(); t.join(timeout=1.0)
    assert summaries.get("ghost") is None      # reaped session dropped from cache
