from vibemonitor.usagehistory import UsageHistory


def _usage(claude_pct=0.2, codex_ok=True):
    return {
        "claude": {"ok": True, "pct": claude_pct, "weekPct": 0.1,
                   "resetSec": 3600, "weekResetSec": 200000},
        "codex": {"ok": codex_ok, "pct": 0.5 if codex_ok else None,
                  "weekPct": 0.3, "resetSec": 1800, "weekResetSec": None},
    }


def test_record_and_samples(tmp_path):
    h = UsageHistory(tmp_path / "u.db")
    assert h.record(1000.0, _usage(0.2)) == 2          # claude + codex
    assert h.record(1060.0, _usage(0.25)) == 2
    cl = h.samples("claude")
    assert [s["pct"] for s in cl] == [0.2, 0.25]
    assert cl[0]["ts"] == 1000 and cl[0]["week_reset_sec"] == 200000
    assert [s["ts"] for s in h.samples("codex")] == [1000, 1060]


def test_record_skips_not_ok_or_null(tmp_path):
    h = UsageHistory(tmp_path / "u.db")
    assert h.record(1000.0, _usage(0.2, codex_ok=False)) == 1   # only claude
    assert h.samples("codex") == []


def test_samples_since_filter(tmp_path):
    h = UsageHistory(tmp_path / "u.db")
    h.record(1000.0, _usage()); h.record(2000.0, _usage()); h.record(3000.0, _usage())
    assert [s["ts"] for s in h.samples("claude", since_ts=2000)] == [2000, 3000]


def test_prune(tmp_path):
    h = UsageHistory(tmp_path / "u.db")
    h.record(1000.0, _usage()); h.record(5000.0, _usage())
    assert h.prune(before_ts=3000) == 2                  # both claude+codex at ts=1000
    assert [s["ts"] for s in h.samples("claude")] == [5000]


def test_persists_across_reopen(tmp_path):
    p = tmp_path / "u.db"
    h = UsageHistory(p); h.record(1000.0, _usage(0.4)); h.close()
    h2 = UsageHistory(p)
    assert [s["pct"] for s in h2.samples("claude")] == [0.4]
