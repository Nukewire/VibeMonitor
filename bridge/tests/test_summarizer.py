import json

from vibemonitor.summarizer import extract_latest_prompt, summarize


def _write_jsonl(path, objs):
    path.write_text(
        "\n".join(json.dumps(o) for o in objs) + "\n",
        encoding="utf-8",
    )


# ---- extract_latest_prompt ----

def test_extract_string_content(tmp_path):
    p = tmp_path / "session.jsonl"
    _write_jsonl(p, [
        {"type": "user", "message": {"content": "hello world"}},
    ])
    assert extract_latest_prompt(p) == "hello world"


def test_extract_text_block_list(tmp_path):
    p = tmp_path / "session.jsonl"
    _write_jsonl(p, [
        {"type": "user", "message": {"content": [
            {"type": "text", "text": "fix the bug"},
        ]}},
    ])
    assert extract_latest_prompt(p) == "fix the bug"


def test_tool_result_only_message_skipped(tmp_path):
    # earlier text user message should win over a later tool_result-only message
    p = tmp_path / "session.jsonl"
    _write_jsonl(p, [
        {"type": "user", "message": {"content": "real prompt"}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "content": "command output here"},
        ]}},
    ])
    assert extract_latest_prompt(p) == "real prompt"


def test_injected_command_message_skipped(tmp_path):
    p = tmp_path / "session.jsonl"
    _write_jsonl(p, [
        {"type": "user", "message": {"content": "actual question"}},
        {"type": "user", "message": {"content": "<command-name>/clear</command-name>"}},
    ])
    assert extract_latest_prompt(p) == "actual question"


def test_picks_most_recent_qualifying(tmp_path):
    p = tmp_path / "session.jsonl"
    _write_jsonl(p, [
        {"type": "user", "message": {"content": "first"}},
        {"type": "assistant", "message": {"content": "reply"}},
        {"type": "user", "message": {"content": "second"}},
    ])
    assert extract_latest_prompt(p) == "second"


def test_missing_file_returns_none(tmp_path):
    assert extract_latest_prompt(tmp_path / "nope.jsonl") is None


def test_no_qualifying_prompt_returns_none(tmp_path):
    p = tmp_path / "session.jsonl"
    _write_jsonl(p, [
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "content": "out"},
        ]}},
        {"type": "user", "message": {"content": "<system-reminder>nope</system-reminder>"}},
    ])
    assert extract_latest_prompt(p) is None


def test_truncation_to_max_chars(tmp_path):
    p = tmp_path / "session.jsonl"
    long = "x" * 5000
    _write_jsonl(p, [
        {"type": "user", "message": {"content": long}},
    ])
    out = extract_latest_prompt(p, max_chars=100)
    assert out == "x" * 100


def test_skips_unparseable_lines(tmp_path):
    p = tmp_path / "session.jsonl"
    p.write_text(
        "not json at all\n"
        + json.dumps({"type": "user", "message": {"content": "good"}}) + "\n",
        encoding="utf-8",
    )
    assert extract_latest_prompt(p) == "good"


# ---- summarize ----

class FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


def _ok_payload(content):
    return {"choices": [{"message": {"content": content}}]}


def test_summarize_returns_cleaned_phrase():
    def poster(api_key, model, text, timeout):
        return FakeResp(_ok_payload('"Building a Flask bridge."'))

    out = summarize("some prompt", api_key="k", model="m", poster=poster)
    assert out == "Building a Flask bridge"


def test_summarize_collapses_whitespace():
    def poster(api_key, model, text, timeout):
        return FakeResp(_ok_payload("adding   summary\n cache"))

    out = summarize("p", api_key="k", model="m", poster=poster)
    assert out == "adding summary cache"


def test_summarize_status_500_returns_none():
    def poster(api_key, model, text, timeout):
        return FakeResp(_ok_payload("x"), status=500)

    assert summarize("p", api_key="k", model="m", poster=poster) is None


def test_summarize_poster_raises_returns_none():
    def poster(api_key, model, text, timeout):
        raise RuntimeError("network down")

    assert summarize("p", api_key="k", model="m", poster=poster) is None


def test_summarize_empty_text_no_poster_call():
    called = []

    def poster(api_key, model, text, timeout):
        called.append(True)
        return FakeResp(_ok_payload("x"))

    assert summarize("", api_key="k", model="m", poster=poster) is None
    assert called == []


def test_summarize_missing_api_key_no_poster_call():
    called = []

    def poster(api_key, model, text, timeout):
        called.append(True)
        return FakeResp(_ok_payload("x"))

    assert summarize("p", api_key="", model="m", poster=poster) is None
    assert called == []
