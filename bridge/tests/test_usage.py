import json as _json

from vibemonitor.usage import (
    parse_claude_headers,
    claude_usage,
    codex_usage,
    parse_codex_token_count,
    read_claude_oauth_token,
)


class FakeResp:
    def __init__(self, headers, status=200):
        self.headers = headers
        self.status_code = status


def test_parse_claude_headers_ok():
    h = {
        "anthropic-ratelimit-unified-5h-utilization": "0.24",
        "anthropic-ratelimit-unified-5h-reset": "1779792000",
        "anthropic-ratelimit-unified-7d-utilization": "0.04",
        "anthropic-ratelimit-unified-7d-reset": "1780322400",
    }
    out = parse_claude_headers(h, now=1779790000)
    assert out["ok"] is True
    assert out["pct"] == 0.24
    assert out["window"] == "5h"
    assert out["resetSec"] == 2000
    assert out["weekPct"] == 0.04


def test_parse_claude_headers_missing():
    out = parse_claude_headers({}, now=0)
    assert out["ok"] is False
    assert out["pct"] is None


def test_claude_usage_uses_injected_poster():
    h = {
        "anthropic-ratelimit-unified-5h-utilization": "0.5",
        "anthropic-ratelimit-unified-5h-reset": "100",
        "anthropic-ratelimit-unified-7d-utilization": "0.1",
        "anthropic-ratelimit-unified-7d-reset": "200",
    }
    out = claude_usage(token="x", now=50, _poster=lambda *a, **k: FakeResp(h))
    assert out["ok"] is True and out["pct"] == 0.5 and out["resetSec"] == 50


def test_claude_usage_no_token():
    out = claude_usage(token=None, now=0)
    assert out["ok"] is False


def test_claude_usage_handles_exception():
    def boom(*a, **k):
        raise RuntimeError("network down")
    out = claude_usage(token="x", now=0, _poster=boom)
    assert out["ok"] is False


# ---- Codex usage (from session rate_limits) ----

def test_codex_usage_miss_when_no_sessions(tmp_path):
    assert codex_usage(now=0, sessions_root=tmp_path)["ok"] is False


def test_parse_codex_token_count_resets_at():
    # real Codex shape: resets_at is an epoch timestamp
    text = (
        '{"type":"event_msg","payload":{"type":"task_started"}}\n'
        '{"type":"event_msg","payload":{"type":"token_count","rate_limits":'
        '{"primary":{"used_percent":2.0,"window_minutes":300,"resets_at":1000600},'
        '"secondary":{"used_percent":18.0,"window_minutes":10080,"resets_at":1099999}}}}'
    )
    out = parse_codex_token_count(text, now=1000000)
    assert out["ok"] is True
    assert abs(out["pct"] - 0.02) < 1e-6
    assert out["resetSec"] == 600          # 1000600 - 1000000
    assert abs(out["weekPct"] - 0.18) < 1e-6


def test_parse_codex_token_count_resets_in_seconds():
    # fallback shape some Codex versions use
    text = (
        '{"type":"event_msg","payload":{"type":"token_count","rate_limits":'
        '{"primary":{"used_percent":5.8,"resets_in_seconds":11645},'
        '"secondary":{"used_percent":16.5,"resets_in_seconds":232729}}}}'
    )
    out = parse_codex_token_count(text, now=0)
    assert out["ok"] is True
    assert out["resetSec"] == 11645


def test_parse_codex_token_count_no_data():
    assert parse_codex_token_count(
        '{"type":"event_msg","payload":{"type":"task_started"}}', now=0)["ok"] is False


def test_codex_usage_reads_newest_session(tmp_path):
    day = tmp_path / "2026" / "05" / "30"
    day.mkdir(parents=True)
    (day / "rollout-test.jsonl").write_text(
        '{"type":"event_msg","payload":{"type":"token_count","rate_limits":'
        '{"primary":{"used_percent":42.0,"window_minutes":300,"resets_at":1000600},'
        '"secondary":{"used_percent":7.0,"window_minutes":10080,"resets_at":1099999}}}}',
        encoding="utf-8")
    out = codex_usage(now=1000000, sessions_root=tmp_path, today=(2026, 5, 30))
    assert out["ok"] is True
    assert abs(out["pct"] - 0.42) < 1e-6
    assert out["resetSec"] == 600


# ---- Claude OAuth token auto-read ----

def test_read_claude_oauth_token(tmp_path):
    p = tmp_path / ".credentials.json"
    p.write_text(_json.dumps({"claudeAiOauth": {"accessToken": "tok-123"}}), encoding="utf-8")
    assert read_claude_oauth_token(p) == "tok-123"


def test_read_claude_oauth_token_missing(tmp_path):
    assert read_claude_oauth_token(tmp_path / "nope.json") is None
