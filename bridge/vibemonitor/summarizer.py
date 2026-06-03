from __future__ import annotations
import json
from pathlib import Path
import requests

OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = (
    "You label software developer coding sessions. Given the developer's latest "
    "prompt, reply with a SHORT 3-6 word phrase describing what they are working on. "
    "No punctuation, no quotes, no preamble."
)

# Claude Code injects system/tool wrappers as "user" messages; these aren't real prompts.
_INJECTED_PREFIXES = ("<command-", "<local-command", "<system-reminder", "Caveat:")


def _extract_message_text(message: dict) -> str | None:
    """Pull human prompt text out of a message dict, or None if it carries no text.
    A string content is taken verbatim; a list content joins only `text` blocks and
    skips messages that are purely tool_result (tool output fed back, not a prompt)."""
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        if not texts:
            return None
        return "".join(texts)
    return None


def _is_injected(text: str) -> bool:
    return any(text.startswith(p) for p in _INJECTED_PREFIXES)


def extract_latest_prompt(jsonl_path, max_chars: int = 2000) -> str | None:
    """Return the most recent human prompt text from a Claude Code session JSONL file.
    Returns None if the file is missing/unreadable or no qualifying prompt exists.
    Never raises."""
    try:
        path = Path(jsonl_path)
        latest: str | None = None
        with path.open(encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(obj, dict) or obj.get("type") != "user":
                    continue
                text = _extract_message_text(obj.get("message"))
                if text is None:
                    continue
                text = text.strip()
                if not text or _is_injected(text):
                    continue
                latest = text
        if latest is None:
            return None
        return latest[:max_chars]
    except Exception:
        return None


def _default_poster(api_key: str, model: str, text: str, timeout: int):
    body = {
        "model": model,
        "max_tokens": 24,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    }
    return requests.post(
        OPENROUTER_ENDPOINT,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=timeout,
    )


def _clean_phrase(raw: str) -> str:
    phrase = raw.strip()
    # strip surrounding matching quotes
    if len(phrase) >= 2 and phrase[0] == phrase[-1] and phrase[0] in ("'", '"'):
        phrase = phrase[1:-1].strip()
    phrase = phrase.rstrip(".")
    phrase = " ".join(phrase.split())
    return phrase[:60].strip()


def summarize(text, *, api_key, model, poster=None, timeout=15) -> str | None:
    """Turn `text` into a short 3-6 word phrase via OpenRouter. Returns None on any
    failure (no text, no key, non-200, parse error, exception). Never raises."""
    if not text or not api_key:
        return None
    try:
        resp = (poster or _default_poster)(api_key, model, text, timeout)
        if getattr(resp, "status_code", None) != 200:
            return None
        content = resp.json()["choices"][0]["message"]["content"]
        phrase = _clean_phrase(content)
        return phrase or None
    except Exception:
        return None
