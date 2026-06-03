from __future__ import annotations
import hashlib
import threading


def hash_text(text: str) -> str:
    """Short stable hex digest of `text` (sha1 of utf-8, first 16 chars)."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


class SummaryCache:
    """Thread-safe map of session_id -> (input_hash, summary)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, tuple[str, str | None]] = {}

    def needs_update(self, sid: str, input_hash: str) -> bool:
        with self._lock:
            entry = self._data.get(sid)
            return entry is None or entry[0] != input_hash

    def set(self, sid: str, input_hash: str, summary: str | None) -> None:
        with self._lock:
            self._data[sid] = (input_hash, summary)

    def get(self, sid: str) -> str | None:
        with self._lock:
            entry = self._data.get(sid)
            return entry[1] if entry is not None else None

    def forget(self, sid: str) -> None:
        with self._lock:
            self._data.pop(sid, None)

    def ids(self) -> list[str]:
        with self._lock:
            return list(self._data.keys())
