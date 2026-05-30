from __future__ import annotations
import sys
import threading
import time
from pathlib import Path

from vibemonitor.config import load_config
from vibemonitor.model import Store
from vibemonitor.usagecache import UsageCache
from vibemonitor.collector_claude import scan_claude
from vibemonitor.collector_codex import scan_codex
from vibemonitor.usage import claude_usage, codex_usage, read_claude_oauth_token
from vibemonitor.hub import create_app


def _session_loop(store: Store, cfg, stop: threading.Event) -> None:
    while not stop.is_set():
        now = time.time()
        if cfg.enable_claude:
            scan_claude(store, now=now)
        if cfg.enable_codex:
            scan_codex(store, now=now)
        stop.wait(cfg.poll_sessions_sec)


def _usage_loop(cache: UsageCache, cfg, claude_token: str | None,
                stop: threading.Event) -> None:
    while not stop.is_set():
        now = time.time()
        cache.set({
            "claude": claude_usage(claude_token, now=now) if cfg.enable_claude
                      else {"ok": False},
            "codex": codex_usage(now=now) if cfg.enable_codex else {"ok": False},
        })
        stop.wait(cfg.poll_usage_sec)


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    cfg_path = Path(argv[0]) if argv else Path("config.toml")
    if not cfg_path.exists():
        print(f"config not found: {cfg_path} (copy config.example.toml)", file=sys.stderr)
        return 2
    cfg = load_config(cfg_path)

    # Config value wins; otherwise auto-read the local Claude OAuth token so the
    # usage gauge works without the user pasting a token into config.toml.
    claude_token = cfg.claude_oauth_token or read_claude_oauth_token()
    if cfg.enable_claude and not claude_token:
        print("note: no Claude OAuth token found; usage gauge will show '--'", file=sys.stderr)

    store = Store()
    cache = UsageCache()
    stop = threading.Event()

    threading.Thread(target=_session_loop, args=(store, cfg, stop), daemon=True).start()
    threading.Thread(target=_usage_loop, args=(cache, cfg, claude_token, stop),
                     daemon=True).start()

    app = create_app(store, cfg, usage_provider=cache.get)
    print(f"VibeMonitor hub on http://{cfg.host}:{cfg.port}  (Ctrl+C to stop)")
    try:
        app.run(host=cfg.host, port=cfg.port, threaded=True)
    finally:
        stop.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
