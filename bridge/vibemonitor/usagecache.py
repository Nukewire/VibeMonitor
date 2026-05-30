from __future__ import annotations
import copy
import threading


class UsageCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data = {"claude": {"ok": False}, "codex": {"ok": False}}

    def set(self, data: dict) -> None:
        with self._lock:
            self._data = copy.deepcopy(data)

    def get(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._data)
