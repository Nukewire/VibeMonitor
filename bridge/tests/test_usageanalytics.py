import time
from vibemonitor import usageanalytics as ua


def _samples(pairs):
    return [{"ts": t, "pct": p} for t, p in pairs]


def test_burn_rate_rising():
    # +0.1 over 600s -> 0.1/600 per sec -> 0.6 per hour
    s = _samples([(0, 0.0), (300, 0.05), (600, 0.10)])
    burn = ua.burn_rate_per_hour(s, now=600)
    assert abs(burn - 0.6) < 1e-6


def test_burn_rate_flat_is_zero():
    s = _samples([(0, 0.3), (300, 0.3), (600, 0.3)])
    assert abs(ua.burn_rate_per_hour(s, now=600)) < 1e-9


def test_burn_rate_uses_segment_after_reset():
    # a reset (0.9 -> 0.1) then a gentle climb; burn should reflect only the new segment
    s = _samples([(0, 0.85), (60, 0.90), (120, 0.10), (180, 0.12), (240, 0.14)])
    burn = ua.burn_rate_per_hour(s, now=240)
    assert burn is not None and 0.1 < burn < 0.2 * 60  # positive, small, from last segment


def test_burn_rate_insufficient():
    assert ua.burn_rate_per_hour([], now=0) is None
    assert ua.burn_rate_per_hour(_samples([(0, 0.5)]), now=0) is None


def test_project_exhaust_before_reset():
    # 50% used, burning 30%/hr, window resets in 2h -> predicted 110% -> caps out first
    p = ua.project(0.5, 0.30, reset_sec=7200, now=1000.0)
    assert p["will_exhaust_before_reset"] is True
    assert p["predicted_at_reset"] > 1.0
    # remaining 0.5 at 0.30/hr -> 1.6667h -> 6000s
    assert abs(p["eta_sec"] - 6000) <= 1
    assert p["eta_ts"] == 1000 + p["eta_sec"]


def test_project_resets_first_with_leftover():
    # 20% used, burning 10%/hr, resets in 3h -> predicted 50% -> 50% to spare
    p = ua.project(0.2, 0.10, reset_sec=10800, now=0.0)
    assert p["will_exhaust_before_reset"] is False
    assert abs(p["leftover_pct"] - 0.5) < 1e-9
    assert p["eta_sec"] is None


def test_project_idle_no_exhaust():
    p = ua.project(0.4, 0.0, reset_sec=3600, now=0.0)
    assert p["will_exhaust_before_reset"] is False
    assert p["leftover_pct"] is not None


def test_project_missing_inputs():
    assert ua.project(None, 0.1, 100, 0.0)["predicted_at_reset"] is None
    assert ua.project(0.5, None, 100, 0.0)["predicted_at_reset"] is None


def _fixed(y, mo, d, h, mi):
    return lambda ts: time.struct_time((y, mo, d, h, mi, 0, 0, 0, -1))


def test_fmt_clock():
    assert ua.fmt_clock(0, localize=_fixed(2026, 6, 3, 15, 40)) == "3:40 PM"
    assert ua.fmt_clock(0, localize=_fixed(2026, 6, 3, 0, 5)) == "12:05 AM"
    assert ua.fmt_clock(0, localize=_fixed(2026, 6, 3, 12, 0)) == "12:00 PM"


def test_daily_history_groups_and_flags_cap():
    # ts<2000 -> day 1, else day 2; day 2 peaks at 0.99 (capped)
    def loc(ts):
        day = 1 if ts < 2000 else 2
        return time.struct_time((2026, 6, day, 14, 0, 0, 0, 0, -1))
    s = _samples([(1000, 0.3), (1500, 0.5), (2500, 0.7), (3000, 0.99)])
    hist = ua.daily_history(s, localize=loc)
    assert [d["date"] for d in hist] == ["2026-06-01", "2026-06-02"]
    assert hist[0]["peak_pct"] == 0.5 and hist[0]["hit_cap"] is False
    assert hist[1]["peak_pct"] == 0.99 and hist[1]["hit_cap"] is True
