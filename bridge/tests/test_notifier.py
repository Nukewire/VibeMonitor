from vibemonitor.notifier import WebhookNotifier


def _recorder():
    sent = []
    def poster(url, payload, timeout=5.0):
        sent.append((url, payload))
    return sent, poster


def test_no_url_is_noop():
    sent, poster = _recorder()
    n = WebhookNotifier(None, poster=poster, clock=lambda: 100.0)
    assert n.update({("claude", "P"): "x"}) == []
    assert sent == []


def test_fires_waiting_on_enter_only_once():
    sent, poster = _recorder()
    n = WebhookNotifier("http://hook", poster=poster, clock=lambda: 100.0)
    fired1 = n.update({("claude", "WebApp"): "Refactor auth"})
    assert [e["event"] for e in fired1] == ["waiting"]
    assert fired1[0]["tool"] == "claude" and fired1[0]["project"] == "WebApp"
    assert fired1[0]["summary"] == "Refactor auth" and fired1[0]["ts"] == 100
    # steady state -> no new events
    fired2 = n.update({("claude", "WebApp"): "Refactor auth"})
    assert fired2 == []
    assert len(sent) == 1


def test_fires_cleared_on_leave():
    sent, poster = _recorder()
    n = WebhookNotifier("http://hook", poster=poster, clock=lambda: 200.0)
    n.update({("codex", "ApiServer"): None})            # enter
    fired = n.update({})                                # leaves -> cleared
    assert [e["event"] for e in fired] == ["cleared"]
    assert fired[0]["tool"] == "codex" and fired[0]["project"] == "ApiServer"
    assert "summary" not in fired[0]


def test_simultaneous_enter_and_clear():
    sent, poster = _recorder()
    n = WebhookNotifier("http://hook", poster=poster, clock=lambda: 1.0)
    n.update({("claude", "A"): "a"})
    fired = n.update({("claude", "B"): "b"})            # A clears, B enters
    events = {(e["event"], e["project"]) for e in fired}
    assert events == {("cleared", "A"), ("waiting", "B")}


def test_poster_exception_is_swallowed():
    def boom(url, payload, timeout=5.0):
        raise OSError("HA unreachable")
    n = WebhookNotifier("http://hook", poster=boom, clock=lambda: 1.0)
    # must not raise even though the POST fails
    fired = n.update({("claude", "P"): "x"})
    assert [e["event"] for e in fired] == ["waiting"]
