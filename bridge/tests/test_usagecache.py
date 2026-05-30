from vibemonitor.usagecache import UsageCache

def test_cache_returns_last_set():
    c = UsageCache()
    assert c.get() == {"claude": {"ok": False}, "codex": {"ok": False}}
    c.set({"claude": {"ok": True, "pct": 0.5}, "codex": {"ok": False}})
    assert c.get()["claude"]["pct"] == 0.5

def test_cache_is_copied():
    c = UsageCache()
    c.set({"claude": {"ok": True}, "codex": {"ok": False}})
    got = c.get()
    got["claude"]["mutated"] = True
    assert "mutated" not in c.get()["claude"]
