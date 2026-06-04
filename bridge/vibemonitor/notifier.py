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


class WaitingCoordinator:
    """Single edge-detector for waiting groups; fans out to the HA webhook AND phone push.

    Computes the enter/clear diff exactly once, drives the existing ``WebhookNotifier``
    unchanged, and additionally fires a phone push: priority ``default`` on enter, and
    ONE escalation push at priority ``high`` once a group has been waiting
    ``escalate_sec`` seconds. Tracks per-group first-seen time to drive the escalation.
    All errors are swallowed; alerting must never disrupt the poll loop.
    """

    def __init__(self, webhook: WebhookNotifier | None = None, push=None,
                 escalate_sec: int = 600, clock=time.time) -> None:
        self._webhook = webhook
        self._push = push
        self._escalate_sec = escalate_sec
        self._clock = clock
        self._since: dict[tuple[str, str], float] = {}      # group -> first-seen ts
        self._escalated: set[tuple[str, str]] = set()       # groups already re-fired
        self._lock = threading.Lock()

    def update(self, current: dict[tuple[str, str], str | None]) -> list[dict]:
        now = self._clock()
        with self._lock:
            prev_keys = set(self._since)
            cur_keys = set(current)
            entered = sorted(cur_keys - prev_keys)
            cleared = sorted(prev_keys - cur_keys)
            for key in entered:
                self._since[key] = now
            for key in cleared:
                self._since.pop(key, None)
                self._escalated.discard(key)
            # which groups crossed the escalation threshold this tick?
            escalate: list[tuple[str, str]] = []
            for key in cur_keys:
                if key in self._escalated:
                    continue
                if now - self._since.get(key, now) >= self._escalate_sec:
                    self._escalated.add(key)
                    escalate.append(key)

        fired: list[dict] = []
        if self._webhook is not None:
            fired = self._webhook.update(current)        # HA behavior intact

        if self._push is not None:
            for tool, project in entered:
                summary = current.get((tool, project)) or ""
                msg = f"{project} needs you" + (f" — {summary}" if summary else "")
                try:
                    self._push.send(f"🔔 {project}", msg, priority="default")
                except Exception:
                    pass
            for tool, project in sorted(escalate):
                summary = current.get((tool, project)) or ""
                msg = f"{project} still waiting" + (f" — {summary}" if summary else "")
                try:
                    self._push.send(f"⏰ {project} (stale)", msg, priority="high")
                except Exception:
                    pass
        return fired
