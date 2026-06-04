import json
import os
import time

from vibemonitor.costs import summarize_costs, CostCache

NOW = 1_700_000_000.0       # fixed "now"; tests use a localize that puts midnight well below it


def _midnight_localize(ts):
    # pretend it's 12:00:00 local for `now`, so local-midnight = NOW - 12h. Files stamped
    # at NOW are comfortably after midnight and counted.
    class LT:
        tm_hour, tm_min, tm_sec = 12, 0, 0
    return LT()


def _write(path, lines, mtime=NOW):
    path.write_text("\n".join(json.dumps(o) for o in lines) + "\n", encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def _claude_line(model, inp, out, cache_c=0, cache_r=0, cwd=None):
    o = {"type": "assistant",
         "message": {"role": "assistant", "model": model,
                     "usage": {"input_tokens": inp, "output_tokens": out,
                               "cache_creation_input_tokens": cache_c,
                               "cache_read_input_tokens": cache_r}}}
    if cwd:
        o["cwd"] = cwd
    return o


def _codex_lines(cwd, total):
    return [
        {"type": "session_meta", "payload": {"cwd": cwd}},
        {"type": "event_msg",
         "payload": {"type": "token_count",
                     "info": {"total_token_usage": {"total_tokens": total}}}},
    ]


def test_token_sum_and_share_per_project(tmp_path):
    cdir = tmp_path / "claude-Alpha"
    cdir.mkdir()
    a = _write(cdir / "s1.jsonl",
               [_claude_line("claude-sonnet", 100, 50, cwd="/home/u/Alpha")])
    bdir = tmp_path / "claude-Beta"
    bdir.mkdir()
    b = _write(bdir / "s2.jsonl",
               [_claude_line("claude-sonnet", 200, 100, cwd="/home/u/Beta")])
    out = summarize_costs([a, b], [], NOW, localize=_midnight_localize)
    by = {r["project"]: r for r in out["today"]}
    assert by["Alpha"]["tokens"] == 150
    assert by["Beta"]["tokens"] == 300
    assert out["totalTokens"] == 450
    # sorted by tokens desc
    assert out["today"][0]["project"] == "Beta"
    # share: Beta 300/450 = 66.7
    assert by["Beta"]["sharePct"] == 66.7
    assert by["Alpha"]["sharePct"] == 33.3


def test_codex_tokens_grouped(tmp_path):
    f = _write(tmp_path / "rollout-x.jsonl", _codex_lines("/proj/Gamma", 1234))
    out = summarize_costs([], [f], NOW, localize=_midnight_localize)
    row = out["today"][0]
    assert row["tool"] == "codex" and row["project"] == "Gamma"
    assert row["tokens"] == 1234


def test_usd_calc_and_missing_price(tmp_path):
    cdir = tmp_path / "claude-Alpha"
    cdir.mkdir()
    a = _write(cdir / "s1.jsonl",
               [_claude_line("claude-sonnet-4", 1_000_000, 1_000_000, cwd="/u/Alpha")])
    # priced model
    pricing = {"claude-sonnet": {"input": 3.0, "output": 15.0}}
    out = summarize_costs([a], [], NOW, pricing=pricing, localize=_midnight_localize)
    row = out["today"][0]
    # 2M tokens at blended (3+15)/2 = 9 $/1M -> 18.0
    assert row["usd"] == 18.0
    assert out["totalUsd"] == 18.0

    # no matching price -> usd None
    out2 = summarize_costs([a], [], NOW, pricing={"other": {"input": 1.0}},
                           localize=_midnight_localize)
    assert out2["today"][0]["usd"] is None
    assert out2["totalUsd"] is None


def test_empty_and_missing_files(tmp_path):
    out = summarize_costs([], [], NOW, localize=_midnight_localize)
    assert out == {"today": [], "totalTokens": 0, "totalUsd": None}
    # nonexistent path is skipped, not fatal
    out2 = summarize_costs([tmp_path / "nope.jsonl"], [], NOW, localize=_midnight_localize)
    assert out2["totalTokens"] == 0


def test_files_before_midnight_excluded(tmp_path):
    cdir = tmp_path / "claude-Old"
    cdir.mkdir()
    # mtime well before local midnight (NOW - 12h) -> excluded
    old = _write(cdir / "s.jsonl",
                 [_claude_line("m", 500, 500, cwd="/u/Old")], mtime=NOW - 86400)
    out = summarize_costs([old], [], NOW, localize=_midnight_localize)
    assert out["totalTokens"] == 0


def test_cost_cache_roundtrip_and_isolation():
    c = CostCache()
    assert c.get() == {"today": [], "totalTokens": 0, "totalUsd": None}
    c.set({"today": [{"tool": "claude", "project": "P", "tokens": 10, "sharePct": 100.0}],
           "totalTokens": 10, "totalUsd": None})
    got = c.get()
    got["today"].append("mutate")
    assert len(c.get()["today"]) == 1       # deep-copied; external mutation isolated
