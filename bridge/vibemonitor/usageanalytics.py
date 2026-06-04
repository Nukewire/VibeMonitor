from __future__ import annotations
import time

# Pure analytics over usage samples. A "sample" is a dict with at least {ts, pct}; the
# history store also provides week_pct / reset_sec / week_reset_sec.


def _segments(samples: list[dict], key: str, drop: float = 0.1) -> list[list[tuple]]:
    """Split into contiguous segments, breaking where the value drops by >`drop`
    (a rolling-window reset or sharp drain — not part of the current burn)."""
    segs: list[list[tuple]] = []
    cur: list[tuple] = []
    prev = None
    for s in samples:
        v = s.get(key)
        if v is None:
            continue
        if prev is not None and v < prev - drop:
            if cur:
                segs.append(cur)
            cur = []
        cur.append((s["ts"], v))
        prev = v
    if cur:
        segs.append(cur)
    return segs


def _slope_per_sec(points: list[tuple]) -> float | None:
    """Least-squares slope of value vs time (per second)."""
    n = len(points)
    if n < 2:
        return None
    sx = sum(t for t, _ in points)
    sy = sum(v for _, v in points)
    sxx = sum(t * t for t, _ in points)
    sxy = sum(t * v for t, v in points)
    denom = n * sxx - sx * sx
    if denom == 0:
        return None
    return (n * sxy - sx * sy) / denom


def burn_rate_per_hour(samples: list[dict], window_sec: int = 1800,
                       now: float | None = None, key: str = "pct") -> float | None:
    """Rate of `key` increase (fraction per hour) over the most recent rising segment
    within the last `window_sec`. None if not enough data. May be <=0 (idle/draining)."""
    if not samples:
        return None
    latest = now if now is not None else samples[-1]["ts"]
    recent = [s for s in samples if s["ts"] >= latest - window_sec]
    segs = _segments(recent, key)
    if not segs:
        return None
    slope = _slope_per_sec(segs[-1])
    if slope is None:
        return None
    return slope * 3600.0


def project(current_pct: float | None, burn_per_hr: float | None,
            reset_sec: int | None, now: float) -> dict:
    """Project the window outcome.

    Returns will_exhaust_before_reset + eta (if you'll cap out before the window resets),
    or leftover_pct (the headroom you'll reset with if you won't). predicted_at_reset is
    the utilization you're on track to reach when the window resets.
    """
    out = {"eta_sec": None, "eta_ts": None, "will_exhaust_before_reset": False,
           "predicted_at_reset": None, "leftover_pct": None}
    if current_pct is None or burn_per_hr is None or reset_sec is None:
        return out
    current_pct = min(max(current_pct, 0.0), 1.0)        # clamp odd/over-100% readings
    predicted = current_pct + burn_per_hr * (reset_sec / 3600.0)
    out["predicted_at_reset"] = predicted
    if burn_per_hr > 0 and predicted >= 1.0:
        remaining = max(0.0, 1.0 - current_pct)
        eta_sec = int((remaining / burn_per_hr) * 3600)
        out["will_exhaust_before_reset"] = True
        out["eta_sec"] = eta_sec
        out["eta_ts"] = int(now + eta_sec)
    else:
        out["leftover_pct"] = max(0.0, 1.0 - predicted)
    return out


def fmt_clock(ts: float, localize=time.localtime) -> str:
    """Local 12-hour clock string, e.g. '3:40 PM' (manual format — no platform %-I quirks)."""
    lt = localize(int(ts))
    h = lt.tm_hour
    ampm = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{lt.tm_min:02d} {ampm}"


def daily_history(samples: list[dict], days: int = 14, localize=time.localtime,
                  cap: float = 0.98) -> list[dict]:
    """Per local day: peak pct, whether it hit the cap, and when the peak happened.
    Most recent `days` days, oldest first."""
    by_day: dict[tuple, dict] = {}
    for s in samples:
        v = s.get("pct")
        if v is None:
            continue
        lt = localize(s["ts"])
        key = (lt.tm_year, lt.tm_mon, lt.tm_mday)
        d = by_day.get(key)
        if d is None or v > d["peak"]:
            by_day[key] = {"peak": v, "peak_ts": s["ts"]}
    out = []
    for (y, m, dd), info in sorted(by_day.items()):
        out.append({
            "date": f"{y:04d}-{m:02d}-{dd:02d}",
            "peak_pct": info["peak"],
            "hit_cap": info["peak"] >= cap,
            "peak_clock": fmt_clock(info["peak_ts"], localize),
        })
    return out[-days:]


def build_provider(samples: list[dict], usage: dict, now: float) -> dict:
    """Projection scalars for one provider from its recent samples + current usage.
    Sparkline samples and multi-day `daily` history are attached by the caller (they use
    different query windows)."""
    pct = usage.get("pct")
    reset_sec = usage.get("resetSec")
    burn = burn_rate_per_hour(samples, now=now)
    proj = project(pct, burn, reset_sec, now)
    return {
        "burnPerHr": round(burn, 4) if burn is not None else None,
        "etaSec": proj["eta_sec"],
        "etaClock": fmt_clock(proj["eta_ts"]) if proj["eta_ts"] else None,
        "willExhaustBeforeReset": proj["will_exhaust_before_reset"],
        "leftoverPct": round(proj["leftover_pct"], 4) if proj["leftover_pct"] is not None else None,
        "predictedAtReset": round(proj["predicted_at_reset"], 4) if proj["predicted_at_reset"] is not None else None,
        "weekResetSec": usage.get("weekResetSec"),
    }
