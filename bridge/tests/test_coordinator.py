from vibemonitor.notifier import WaitingCoordinator, WebhookNotifier


class _RecPush:
    def __init__(self):
        self.calls = []
    def send(self, title, message, priority="default"):
        self.calls.append((title, message, priority))
        return True


def test_push_fires_on_enter_default_priority():
    push = _RecPush()
    clk = {"t": 1000.0}
    co = WaitingCoordinator(webhook=None, push=push, escalate_sec=600,
                            clock=lambda: clk["t"])
    co.update({("claude", "WebApp"): "Refactor auth"})
    assert len(push.calls) == 1
    title, msg, prio = push.calls[0]
    assert prio == "default"
    assert "WebApp" in msg and "Refactor auth" in msg
    # steady state -> no new push
    co.update({("claude", "WebApp"): "Refactor auth"})
    assert len(push.calls) == 1


def test_push_escalates_once_at_threshold():
    push = _RecPush()
    clk = {"t": 1000.0}
    co = WaitingCoordinator(webhook=None, push=push, escalate_sec=600,
                            clock=lambda: clk["t"])
    co.update({("claude", "P"): "x"})           # enter @1000 -> default push
    clk["t"] = 1300.0
    co.update({("claude", "P"): "x"})           # 300s < 600 -> no escalation
    assert [c[2] for c in push.calls] == ["default"]
    clk["t"] = 1650.0                           # 650s >= 600 -> escalate once
    co.update({("claude", "P"): "x"})
    assert [c[2] for c in push.calls] == ["default", "high"]
    clk["t"] = 2000.0                           # already escalated -> no re-fire
    co.update({("claude", "P"): "x"})
    assert [c[2] for c in push.calls] == ["default", "high"]


def test_escalation_resets_after_clear():
    push = _RecPush()
    clk = {"t": 1000.0}
    co = WaitingCoordinator(webhook=None, push=push, escalate_sec=600,
                            clock=lambda: clk["t"])
    co.update({("claude", "P"): "x"})
    clk["t"] = 1700.0
    co.update({("claude", "P"): "x"})           # escalates
    co.update({})                                # clears
    clk["t"] = 1800.0
    co.update({("claude", "P"): "x"})           # re-enter -> default push again
    assert [c[2] for c in push.calls] == ["default", "high", "default"]


def test_fans_out_to_webhook():
    webhook_sent = []
    webhook = WebhookNotifier("http://hook",
                              poster=lambda u, p, timeout=5.0: webhook_sent.append(p),
                              clock=lambda: 1000.0)
    push = _RecPush()
    co = WaitingCoordinator(webhook=webhook, push=push, escalate_sec=600,
                            clock=lambda: 1000.0)
    fired = co.update({("codex", "Api"): None})
    assert [e["event"] for e in fired] == ["waiting"]      # HA behavior intact
    assert len(webhook_sent) == 1
    assert len(push.calls) == 1                            # and push fired too
