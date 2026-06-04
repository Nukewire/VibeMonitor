from __future__ import annotations
import copy
import threading


class AnalyticsCache:
    """Thread-safe holder for the computed usage-analytics bundle. The usage loop refreshes
    it once per poll so request handlers never touch SQLite or recompute per request."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict = {"claude": {}, "codex": {}}

    def set(self, data: dict) -> None:
        with self._lock:
            self._data = copy.deepcopy(data)

    def get(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._data)
