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
from vibemonitor.statemachine import derive_status


def _session_loop(store: Store, cfg, stop: threading.Event,
                  heartbeat: dict | None = None) -> None:
    while not stop.is_set():
        now = time.time()
        try:
            if cfg.enable_claude:
                scan_claude(store, now=now)
            if cfg.enable_codex:
                scan_codex(store, now=now)
            for s in store.snapshot():                       # reap gone atomically here
                store.remove_if_gone(s.id, now=now, cfg=cfg, derive=derive_status)
            if heartbeat is not None:
                heartbeat["last_scan"] = now
        except Exception as e:                               # never die silently
            print(f"[session_loop] scan error (continuing): {e!r}", file=sys.stderr)
        stop.wait(cfg.poll_sessions_sec)


def _usage_loop(cache: UsageCache, cfg, stop: threading.Event) -> None:
    while not stop.is_set():
        now = time.time()
        try:
            # Re-resolve the token every poll: the config value wins, otherwise the
            # local Claude OAuth token is auto-read fresh. Claude Code rotates the
            # access token every few hours, so capturing it once at startup would
            # leave the usage gauge stuck on a stale (expired) token -> ok:false.
            claude_token = cfg.claude_oauth_token or read_claude_oauth_token()
            cache.set({
                "claude": claude_usage(claude_token, now=now) if cfg.enable_claude
                          else {"ok": False},
                "codex": codex_usage(now=now) if cfg.enable_codex else {"ok": False},
            })
        except Exception as e:
            print(f"[usage_loop] error (continuing): {e!r}", file=sys.stderr)
        stop.wait(cfg.poll_usage_sec)


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    cfg_path = Path(argv[0]) if argv else Path("config.toml")
    if not cfg_path.exists():
        print(f"config not found: {cfg_path} (copy config.example.toml)", file=sys.stderr)
        return 2
    cfg = load_config(cfg_path)

    # The usage loop re-reads the Claude OAuth token each poll (see _usage_loop);
    # this startup check just warns once if neither a config override nor a local
    # credentials token is available.
    if cfg.enable_claude and not (cfg.claude_oauth_token or read_claude_oauth_token()):
        print("note: no Claude OAuth token found; usage gauge will show '--'", file=sys.stderr)

    store = Store()
    cache = UsageCache()
    stop = threading.Event()
    heartbeat: dict = {"last_scan": 0.0}

    threading.Thread(target=_session_loop, args=(store, cfg, stop, heartbeat),
                     daemon=True).start()
    threading.Thread(target=_usage_loop, args=(cache, cfg, stop),
                     daemon=True).start()

    app = create_app(store, cfg, usage_provider=cache.get, heartbeat=heartbeat)
    print(f"VibeMonitor hub on http://{cfg.host}:{cfg.port}  (Ctrl+C to stop)")
    try:
        app.run(host=cfg.host, port=cfg.port, threaded=True)
    finally:
        stop.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
