from vibemonitor.push import PushNotifier


def test_ntfy_payload_and_headers():
    sent = []
    def poster(url, data, headers, timeout=5.0):
        sent.append((url, data, headers))
    p = PushNotifier(provider="ntfy", ntfy_url="https://ntfy.sh/topic", poster=poster)
    assert p.send("Title", "body text", priority="high") is True
    url, data, headers = sent[0]
    assert url == "https://ntfy.sh/topic"
    assert data == b"body text"
    assert headers["Title"] == "Title"
    assert headers["Priority"] == "5"        # high -> 5


def test_pushover_payload():
    sent = []
    def poster(url, payload, timeout=5.0):
        sent.append((url, payload))
    p = PushNotifier(provider="pushover", pushover_token="tok", pushover_user="usr",
                     poster=poster)
    assert p.send("T", "M") is True
    url, payload = sent[0]
    assert url == "https://api.pushover.net/1/messages.json"
    assert payload["token"] == "tok" and payload["user"] == "usr"
    assert payload["title"] == "T" and payload["message"] == "M"
    assert payload["priority"] == "0"        # default -> 0


def test_unconfigured_is_noop():
    sent = []
    p = PushNotifier(provider="ntfy", ntfy_url=None,
                     poster=lambda *a, **k: sent.append(a))
    assert p.configured() is False
    assert p.send("T", "M") is False
    assert sent == []
    # pushover with only one of the two keys is also unconfigured
    p2 = PushNotifier(provider="pushover", pushover_token="tok", pushover_user=None)
    assert p2.configured() is False
    assert p2.send("T", "M") is False


def test_errors_swallowed():
    def boom(*a, **k):
        raise OSError("network down")
    p = PushNotifier(provider="ntfy", ntfy_url="https://ntfy.sh/x", poster=boom)
    assert p.send("T", "M") is False         # swallowed, no raise
