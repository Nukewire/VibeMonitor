from __future__ import annotations
import requests

_PUSHOVER_ENDPOINT = "https://api.pushover.net/1/messages.json"

# ntfy priority header takes 1..5; pushover -2..2. Map our vocabulary onto both.
_NTFY_PRIORITY = {"low": "2", "default": "3", "high": "5"}
_PUSHOVER_PRIORITY = {"low": "-1", "default": "0", "high": "1"}


def _default_ntfy_poster(url: str, data: bytes, headers: dict, timeout: float = 5.0):
    return requests.post(url, data=data, headers=headers, timeout=timeout)


def _default_pushover_poster(url: str, payload: dict, timeout: float = 5.0):
    return requests.post(url, data=payload, timeout=timeout)


class PushNotifier:
    """Best-effort phone push via ntfy or pushover.

    A no-op (``.send`` returns False) when the selected provider is unconfigured.
    All network errors are swallowed — pushing must never disrupt the caller.
    The ``poster`` is injectable for tests:
      - ntfy:     poster(url, data: bytes, headers: dict)
      - pushover: poster(url, payload: dict)
    """

    def __init__(self, provider: str = "ntfy", ntfy_url: str | None = None,
                 pushover_token: str | None = None, pushover_user: str | None = None,
                 poster=None) -> None:
        self._provider = (provider or "ntfy").lower()
        self._ntfy_url = ntfy_url or None
        self._pushover_token = pushover_token or None
        self._pushover_user = pushover_user or None
        self._poster = poster

    def configured(self) -> bool:
        if self._provider == "ntfy":
            return bool(self._ntfy_url)
        if self._provider == "pushover":
            return bool(self._pushover_token and self._pushover_user)
        return False

    def send(self, title: str, message: str, priority: str = "default") -> bool:
        """Send one push. Returns True if a POST was attempted, False if unconfigured
        or on any error."""
        if not self.configured():
            return False
        try:
            if self._provider == "ntfy":
                poster = self._poster or _default_ntfy_poster
                headers = {
                    "Title": title,
                    "Priority": _NTFY_PRIORITY.get(priority, "3"),
                }
                poster(self._ntfy_url, message.encode("utf-8"), headers)
                return True
            if self._provider == "pushover":
                poster = self._poster or _default_pushover_poster
                payload = {
                    "token": self._pushover_token,
                    "user": self._pushover_user,
                    "title": title,
                    "message": message,
                    "priority": _PUSHOVER_PRIORITY.get(priority, "0"),
                }
                poster(_PUSHOVER_ENDPOINT, payload)
                return True
        except Exception:
            return False
        return False
