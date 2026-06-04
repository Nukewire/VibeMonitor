from __future__ import annotations
import sqlite3
import threading

_SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    ts             INTEGER NOT NULL,
    provider       TEXT    NOT NULL,
    pct            REAL,
    week_pct       REAL,
    reset_sec      INTEGER,
    week_reset_sec INTEGER
);
CREATE INDEX IF NOT EXISTS idx_samples_provider_ts ON samples(provider, ts);
"""


def _f(v):
    return float(v) if isinstance(v, (int, float)) else None


def _i(v):
    return int(v) if isinstance(v, (int, float)) else None


class UsageHistory:
    """Persistent usage samples in SQLite. One row per provider per poll. Thread-safe via
    a single shared connection + lock (writer rate is ~1/min, reads are occasional)."""

    def __init__(self, db_path: str = "usage_history.db") -> None:
        self._path = str(db_path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def record(self, now: float, usage: dict) -> int:
        """Insert one row per provider that has a real (ok, non-null pct) reading.
        Returns the number of rows written."""
        rows = []
        for provider in ("claude", "codex"):
            u = usage.get(provider) or {}
            if not u.get("ok") or u.get("pct") is None:
                continue
            rows.append((int(now), provider, _f(u.get("pct")), _f(u.get("weekPct")),
                         _i(u.get("resetSec")), _i(u.get("weekResetSec"))))
        if not rows:
            return 0
        with self._lock:
            self._conn.executemany(
                "INSERT INTO samples(ts,provider,pct,week_pct,reset_sec,week_reset_sec) "
                "VALUES(?,?,?,?,?,?)", rows)
            self._conn.commit()
        return len(rows)

    def samples(self, provider: str, since_ts: float = 0) -> list[dict]:
        """Return samples for a provider at/after since_ts, oldest first."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT ts,pct,week_pct,reset_sec,week_reset_sec FROM samples "
                "WHERE provider=? AND ts>=? ORDER BY ts", (provider, int(since_ts)))
            return [{"ts": r[0], "pct": r[1], "week_pct": r[2],
                     "reset_sec": r[3], "week_reset_sec": r[4]} for r in cur.fetchall()]

    def prune(self, before_ts: float) -> int:
        """Delete samples older than before_ts. Returns rows removed."""
        with self._lock:
            cur = self._conn.execute("DELETE FROM samples WHERE ts < ?", (int(before_ts),))
            self._conn.commit()
            return cur.rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()
