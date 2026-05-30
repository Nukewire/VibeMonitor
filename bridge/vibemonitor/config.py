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


def load_config(path: str | Path) -> Config:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    token = data.get("token")
    if not token:
        raise ValueError("config must set a top-level `token` value")
    th = data.get("thresholds", {})
    poll = data.get("poll", {})
    claude = data.get("claude", {})
    providers = data.get("providers", {})
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
    )
