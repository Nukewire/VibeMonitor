from __future__ import annotations
import copy
import json
import threading
import time
from pathlib import Path

from vibemonitor.collector_claude import project_from_encoded_dir
from vibemonitor.collector_codex import _project_from_cwd, _uuid_from_stem

# Cost / usage attribution: per-(tool, project) token totals for TODAY (since local
# midnight), with each project's share of today's grand total and an optional $ estimate
# from a [pricing] table. Pure + injectable so it's testable with tmp files.


def _local_midnight(now: float, localize=time.localtime) -> float:
    """Epoch seconds of local midnight for the day containing ``now``."""
    lt = localize(int(now))
    return now - (lt.tm_hour * 3600 + lt.tm_min * 60 + lt.tm_sec)


def _claude_tokens(path: Path) -> tuple[str | None, int, str | None]:
    """Sum assistant message token usage in one Claude jsonl. Returns
    (project, tokens, model). project is None if undiscoverable from the lines."""
    project = None
    model = None
    total = 0
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None, 0, None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        if o.get("cwd") and project is None:
            project = _project_from_cwd(o["cwd"])
        msg = o.get("message")
        if not isinstance(msg, dict):
            continue
        if msg.get("model") and model is None:
            model = msg["model"]
        usage = msg.get("usage")
        if isinstance(usage, dict):
            for k in ("input_tokens", "output_tokens",
                      "cache_creation_input_tokens", "cache_read_input_tokens"):
                v = usage.get(k)
                if isinstance(v, (int, float)):
                    total += int(v)
    return project, total, model


def _codex_tokens(path: Path) -> tuple[str | None, int]:
    """Sum total tokens from token_count events in one Codex rollout jsonl."""
    project = None
    total = 0
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None, 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = o.get("payload", o)
        if o.get("type") == "session_meta" or payload.get("type") == "session_meta":
            cwd = payload.get("cwd")
            if cwd and project is None:
                project = _project_from_cwd(cwd)
        if payload.get("type") == "token_count":
            info = payload.get("info") or payload
            # prefer an explicit total; else sum input+output from total_token_usage
            tu = info.get("total_token_usage") or info.get("last_token_usage") or {}
            if isinstance(tu, dict):
                t = tu.get("total_tokens")
                if isinstance(t, (int, float)):
                    total = int(t)               # token_count is cumulative; take latest
                else:
                    s = sum(int(tu.get(k, 0) or 0) for k in
                            ("input_tokens", "output_tokens",
                             "cached_input_tokens", "reasoning_output_tokens"))
                    if s:
                        total = s
            else:
                t = payload.get("total_tokens")
                if isinstance(t, (int, float)):
                    total = int(t)
    return project, total


def _price_for(model: str | None, pricing: dict | None, tokens: int) -> float | None:
    """USD estimate using a single blended rate per model. ``pricing`` maps a model key
    (substring match) to {"input": $/1M, "output": $/1M}. None if no price found."""
    if not pricing or not model:
        return None
    entry = pricing.get(model)
    if entry is None:
        for key, val in pricing.items():
            if key in model:
                entry = val
                break
    if not isinstance(entry, dict):
        return None
    rate_in = entry.get("input")
    rate_out = entry.get("output")
    rates = [r for r in (rate_in, rate_out) if isinstance(r, (int, float))]
    if not rates:
        return None
    blended = sum(rates) / len(rates)            # blended $/1M for a token total
    return round(tokens / 1_000_000 * blended, 4)


def summarize_costs(claude_paths, codex_paths, now: float,
                    pricing: dict | None = None, localize=time.localtime) -> dict:
    """Aggregate today's token usage per (tool, project).

    ``claude_paths`` / ``codex_paths`` are iterables of file paths. Only files whose
    mtime is at or after local midnight are counted. Returns
    ``{today: [{tool, project, tokens, sharePct, usd?}], totalTokens, totalUsd?}``
    sorted by tokens desc.
    """
    midnight = _local_midnight(now, localize)
    groups: dict[tuple[str, str], dict] = {}      # (tool, project) -> {tokens, usd}

    def _add(tool: str, project: str, tokens: int, usd: float | None) -> None:
        if tokens <= 0:
            return
        g = groups.setdefault((tool, project), {"tokens": 0, "usd": None})
        g["tokens"] += tokens
        if usd is not None:
            g["usd"] = (g["usd"] or 0.0) + usd

    for p in (claude_paths or []):
        p = Path(p)
        try:
            if p.stat().st_mtime < midnight:
                continue
        except OSError:
            continue
        project, tokens, model = _claude_tokens(p)
        if project is None:
            project = project_from_encoded_dir(p.parent.name)
        _add("claude", project, tokens, _price_for(model, pricing, tokens))

    for p in (codex_paths or []):
        p = Path(p)
        try:
            if p.stat().st_mtime < midnight:
                continue
        except OSError:
            continue
        project, tokens = _codex_tokens(p)
        if project is None or project == "?":
            project = _uuid_from_stem(p.stem)
        # Codex pricing keyed on "codex" if present
        _add("codex", project, tokens, _price_for("codex", pricing, tokens))

    total_tokens = sum(g["tokens"] for g in groups.values())
    any_usd = any(g["usd"] is not None for g in groups.values())
    today = []
    for (tool, project), g in groups.items():
        row = {
            "tool": tool,
            "project": project,
            "tokens": g["tokens"],
            "sharePct": round(g["tokens"] / total_tokens * 100, 1) if total_tokens else 0.0,
        }
        row["usd"] = round(g["usd"], 4) if g["usd"] is not None else None
        today.append(row)
    today.sort(key=lambda r: r["tokens"], reverse=True)

    out = {"today": today, "totalTokens": total_tokens}
    if any_usd:
        out["totalUsd"] = round(sum(g["usd"] or 0.0 for g in groups.values()), 4)
    else:
        out["totalUsd"] = None
    return out


class CostCache:
    """Thread-safe cache of the latest cost bundle (mirrors UsageCache)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data = {"today": [], "totalTokens": 0, "totalUsd": None}

    def set(self, data: dict) -> None:
        with self._lock:
            self._data = copy.deepcopy(data)

    def get(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._data)
