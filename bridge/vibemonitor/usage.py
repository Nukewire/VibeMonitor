from __future__ import annotations
import json
from pathlib import Path
import requests

MESSAGES_ENDPOINT = "https://api.anthropic.com/v1/messages"
PROBE_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_VERSION = "2023-06-01"

_H5U = "anthropic-ratelimit-unified-5h-utilization"
_H5R = "anthropic-ratelimit-unified-5h-reset"
_D7U = "anthropic-ratelimit-unified-7d-utilization"
_D7R = "anthropic-ratelimit-unified-7d-reset"


def parse_claude_headers(h: dict, now: float) -> dict:
    u5 = h.get(_H5U)
    if u5 is None:
        return {"ok": False, "pct": None, "window": "5h", "resetSec": None,
                "weekPct": None, "weekResetSec": None}
    try:
        reset5 = int(h.get(_H5R, "0"))
    except ValueError:
        reset5 = 0
    week = h.get(_D7U)
    week_reset = None
    if h.get(_D7R) is not None:
        try:
            week_reset = max(0, int(h.get(_D7R, "0")) - int(now))
        except ValueError:
            week_reset = None
    return {
        "ok": True,
        "pct": float(u5),
        "window": "5h",
        "resetSec": max(0, reset5 - int(now)),
        "weekPct": float(week) if week is not None else None,
        "weekResetSec": week_reset,
    }


def _default_poster(token: str):
    return requests.post(
        MESSAGES_ENDPOINT,
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-version": ANTHROPIC_VERSION,
            "anthropic-beta": "oauth-2025-04-20",
            "content-type": "application/json",
            "User-Agent": "vibemonitor/0.1",
        },
        json={"model": PROBE_MODEL, "max_tokens": 1,
              "messages": [{"role": "user", "content": "."}]},
        timeout=10,
    )


def claude_usage(token: str | None, now: float, _poster=None) -> dict:
    miss = {"ok": False, "pct": None, "window": "5h", "resetSec": None,
            "weekPct": None, "weekResetSec": None}
    if not token:
        return miss
    try:
        resp = (_poster or _default_poster)(token)
        return parse_claude_headers(dict(resp.headers), now=now)
    except Exception:
        return miss


def _codex_miss() -> dict:
    return {"ok": False, "pct": None, "window": "5h", "resetSec": None,
            "weekPct": None, "weekResetSec": None}


def _window_reset_sec(window: dict, now: float) -> int:
    """Seconds until a rate-limit window resets. Codex logs `resets_at` (epoch);
    some versions log `resets_in_seconds`. Support both, floored at 0."""
    if "resets_in_seconds" in window:
        return max(0, int(window["resets_in_seconds"]))
    if "resets_at" in window:
        return max(0, int(window["resets_at"]) - int(now))
    return 0


def parse_codex_token_count(text: str, now: float = 0.0) -> dict:
    """Read the LAST `token_count` event_msg's rate_limits from a Codex rollout jsonl.
    primary = 5h window, secondary = weekly. Returns a usage dict."""
    last = None
    for line in text.splitlines():
        line = line.strip()
        if not line or "token_count" not in line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = o.get("payload", o)
        if payload.get("type") == "token_count" and "rate_limits" in payload:
            last = payload["rate_limits"]
    if not last or "primary" not in last:
        return _codex_miss()
    prim = last.get("primary") or {}
    sec = last.get("secondary") or {}
    pct = prim.get("used_percent")
    if pct is None:
        return _codex_miss()
    week = sec.get("used_percent")
    return {
        "ok": True,
        "pct": float(pct) / 100.0,
        "window": "5h",
        "resetSec": _window_reset_sec(prim, now),
        "weekPct": float(week) / 100.0 if week is not None else None,
        "weekResetSec": _window_reset_sec(sec, now) if sec else None,
    }


def _codex_sessions_root() -> Path:
    return Path.home() / ".codex" / "sessions"


def codex_usage(now: float, sessions_root: Path | None = None,
                today: tuple[int, int, int] | None = None) -> dict:
    """Real Codex usage from the most-recently-active session's rate_limits.
    Scans today's + yesterday's date dirs; reads the newest file's last token_count."""
    import datetime
    root = Path(sessions_root) if sessions_root is not None else _codex_sessions_root()
    if not root.exists():
        return _codex_miss()
    if today is None:
        t = datetime.date.today()
        today = (t.year, t.month, t.day)
    days = [datetime.date(*today), datetime.date(*today) - datetime.timedelta(days=1)]

    files = []
    for d in days:
        day_dir = root / f"{d.year:04d}" / f"{d.month:02d}" / f"{d.day:02d}"
        if day_dir.exists():
            files.extend(day_dir.glob("*.jsonl"))
    # newest first: the most-recently-active session has the freshest rate-limit snapshot
    for f in sorted(files, key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            res = parse_codex_token_count(f.read_text(encoding="utf-8", errors="ignore"), now=now)
        except OSError:
            continue
        if res["ok"]:
            return res
    return _codex_miss()


def read_claude_oauth_token(credentials_path: Path | None = None) -> str | None:
    """Best-effort read of the Claude Code OAuth access token from
    ~/.claude/.credentials.json (key 'claudeAiOauth'). Returns None on any problem."""
    path = Path(credentials_path) if credentials_path is not None else Path.home() / ".claude" / ".credentials.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        oauth = data.get("claudeAiOauth") or {}
        # the access token key may be 'accessToken' or 'access_token'
        return oauth.get("accessToken") or oauth.get("access_token")
    except Exception:
        return None
