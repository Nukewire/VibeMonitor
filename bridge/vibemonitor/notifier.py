from __future__ import annotations
import threading
import time
import requests


def _default_poster(url: str, payload: dict, timeout: float = 5.0):
    return requests.post(url, json=payload, timeout=timeout)


class WebhookNotifier:
    """Edge-triggered Home Assistant webhook.

    Tracks which ``(tool, project)`` groups are waiting on the user and POSTs a
    ``{"event": "waiting", ...}`` payload when a group *enters* that state and a
    ``{"event": "cleared", ...}`` payload when it *leaves*. Fires only on transitions,
    so a steady waiting state produces exactly one event. A no-op when no URL is set.
    Network errors are swallowed — alerting must never disrupt the poll loop.
    """

    def __init__(self, url: str | None, poster=None, clock=time.time) -> None:
        self._url = url
        self._poster = poster or _default_poster
        self._clock = clock
        self._prev: dict[tuple[str, str], str | None] = {}
        self._lock = threading.Lock()

    def update(self, current: dict[tuple[str, str], str | None]) -> list[dict]:
        """Reconcile the set of currently-waiting groups against the previous set.

        ``current`` maps ``(tool, project)`` -> latest summary (or None). Returns the
        list of event payloads fired (handy for tests). No-op (returns ``[]``) when no
        webhook URL is configured.
        """
        if not self._url:
            return []
        with self._lock:
            prev_keys = set(self._prev)
            cur_keys = set(current)
            ts = int(self._clock())
            fired: list[dict] = []
            for tool, project in sorted(cur_keys - prev_keys):        # entered waiting
                fired.append({"event": "waiting", "tool": tool, "project": project,
                              "summary": current[(tool, project)], "ts": ts})
            for tool, project in sorted(prev_keys - cur_keys):        # cleared
                fired.append({"event": "cleared", "tool": tool, "project": project,
                              "ts": ts})
            self._prev = dict(current)
        for ev in fired:                          # POST outside the lock
            try:
                self._poster(self._url, ev)
            except Exception:
                pass
        return fired
