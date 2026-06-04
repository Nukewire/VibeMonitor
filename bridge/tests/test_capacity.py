from vibemonitor.usageanalytics import capacity


def test_throttle_when_provider_will_exhaust():
    usage = {"claude": {"pct": 0.8, "willExhaustBeforeReset": True}, "codex": {}}
    cap = capacity(usage, {}, {"working": 1, "idle": 0, "waiting": 0})
    assert cap["status"] == "throttle"
    assert "claude" in cap["message"]


def test_throttle_reads_analytics_flag():
    cap = capacity({"claude": {"pct": 0.5}, "codex": {}},
                   {"claude": {"willExhaustBeforeReset": True}, "codex": {}},
                   {"working": 0, "idle": 2, "waiting": 0})
    assert cap["status"] == "throttle"


def test_pace_when_moderate_usage():
    usage = {"claude": {"pct": 0.85}, "codex": {"pct": 0.1}}
    cap = capacity(usage, {}, {"working": 1, "idle": 1, "waiting": 0})
    assert cap["status"] == "pace"


def test_go_with_idle_count_in_message():
    usage = {"claude": {"pct": 0.2}, "codex": {"pct": 0.1}}
    cap = capacity(usage, {}, {"working": 1, "idle": 2, "waiting": 0})
    assert cap["status"] == "go"
    assert "2 idle" in cap["message"]


def test_go_with_no_idle():
    cap = capacity({"claude": {"pct": 0.1}, "codex": {}}, {},
                   {"working": 0, "idle": 0, "waiting": 0})
    assert cap["status"] == "go"


def test_empty_inputs_default_go():
    cap = capacity(None, None, None)
    assert cap["status"] == "go"
