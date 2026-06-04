from __future__ import annotations
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    token: str
    port: int = 8787
    host: str = "0.0.0.0"
    working_sec: int = 60
    waiting_ttl_sec: int = 1800
    gone_ttl_sec: int = 14400
    poll_sessions_sec: float = 2.0
    poll_usage_sec: float = 60.0
    claude_oauth_token: str | None = None
    enable_claude: bool = True
    enable_codex: bool = True
    summary_enabled: bool = False
    summary_model: str = "google/gemma-4-31b-it:free"
    summary_max_chars: int = 2000
    openrouter_api_key: str | None = None
    poll_summary_sec: float = 15.0
    ha_webhook_url: str | None = None
    # phone push
    push_provider: str = "ntfy"           # "ntfy" | "pushover"
    push_ntfy_url: str | None = None
    push_pushover_token: str | None = None
    push_pushover_user: str | None = None
    push_escalate_sec: int = 600
    # cost attribution
    poll_costs_sec: float = 120.0
    pricing: dict = None                  # model -> {"input": $/1M, "output": $/1M}


def load_config(path: str | Path) -> Config:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    token = data.get("token")
    if not token:
        raise ValueError("config must set a top-level `token` value")
    th = data.get("thresholds", {})
    poll = data.get("poll", {})
    claude = data.get("claude", {})
    providers = data.get("providers", {})
    summary = data.get("summary", {})
    openrouter = data.get("openrouter", {})
    homeassistant = data.get("homeassistant", {})
    push = data.get("push", {})
    pricing = data.get("pricing", {}) or {}
    return Config(
        token=token,
        port=int(data.get("port", 8787)),
        host=data.get("host", "0.0.0.0"),
        working_sec=int(th.get("working_sec", 60)),
        waiting_ttl_sec=int(th.get("waiting_ttl_sec", 1800)),
        gone_ttl_sec=int(th.get("gone_ttl_sec", 14400)),
        poll_sessions_sec=float(poll.get("sessions_sec", 2.0)),
        poll_usage_sec=float(poll.get("usage_sec", 60.0)),
        claude_oauth_token=claude.get("oauth_token"),
        enable_claude=bool(providers.get("claude", True)),
        enable_codex=bool(providers.get("codex", True)),
        summary_enabled=bool(summary.get("enabled", False)),
        summary_model=str(summary.get("model", "google/gemma-4-31b-it:free")),
        summary_max_chars=int(summary.get("max_chars", 2000)),
        openrouter_api_key=openrouter.get("api_key"),
        poll_summary_sec=float(poll.get("summary_sec", 15.0)),
        ha_webhook_url=homeassistant.get("webhook_url"),
        push_provider=str(push.get("provider", "ntfy")),
        push_ntfy_url=push.get("ntfy_url") or None,
        push_pushover_token=push.get("pushover_token") or None,
        push_pushover_user=push.get("pushover_user") or None,
        push_escalate_sec=int(push.get("escalate_sec", 600)),
        poll_costs_sec=float(poll.get("costs_sec", 120.0)),
        pricing={str(k): dict(v) for k, v in pricing.items() if isinstance(v, dict)},
    )
