from __future__ import annotations
import sys
import threading
import time
from pathlib import Path

from vibemonitor.config import load_config
from vibemonitor.model import Store
from vibemonitor.usagecache import UsageCache
from vibemonitor.collector_claude import scan_claude, claude_session_paths
from vibemonitor.collector_codex import scan_codex
from vibemonitor.usage import claude_usage, codex_usage, read_claude_oauth_token
from vibemonitor.hub import create_app
from vibemonitor.statemachine import derive_status
from vibemonitor.summarizer import extract_latest_prompt, summarize
from vibemonitor.summarycache import SummaryCache, hash_text


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


def _summary_loop(store: Store, summaries: SummaryCache, cfg,
                  stop: threading.Event) -> None:
    """Keep a one-line 'what they're working on' summary per active Claude session.
    Calls the model only when a session's latest prompt changes (hash gate), so cost
    is bounded. Disabled unless [summary] enabled and an OpenRouter key is present."""
    while not stop.is_set():
        try:
            if cfg.summary_enabled and cfg.openrouter_api_key:
                now = time.time()
                paths = claude_session_paths()
                live: set[str] = set()
                for s in store.snapshot():
                    if s.tool != "claude":
                        continue
                    if derive_status(s, now=now, cfg=cfg) == "gone":
                        continue
                    path = paths.get(s.id)
                    if path is None:
                        continue
                    live.add(s.id)
                    text = extract_latest_prompt(path, max_chars=cfg.summary_max_chars)
                    if not text:
                        continue
                    h = hash_text(text)
                    if summaries.needs_update(s.id, h):
                        phrase = summarize(text, api_key=cfg.openrouter_api_key,
                                           model=cfg.summary_model)
                        summaries.set(s.id, h, phrase)
                for sid in [k for k in summaries.ids() if k not in live]:
                    summaries.forget(sid)              # drop reaped sessions
        except Exception as e:                          # never die silently
            print(f"[summary_loop] error (continuing): {e!r}", file=sys.stderr)
        stop.wait(cfg.poll_summary_sec)


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
    summaries = SummaryCache()
    stop = threading.Event()
    heartbeat: dict = {"last_scan": 0.0}

    threading.Thread(target=_session_loop, args=(store, cfg, stop, heartbeat),
                     daemon=True).start()
    threading.Thread(target=_usage_loop, args=(cache, cfg, stop),
                     daemon=True).start()
    if cfg.summary_enabled:
        if cfg.openrouter_api_key:
            threading.Thread(target=_summary_loop, args=(store, summaries, cfg, stop),
                             daemon=True).start()
        else:
            print("note: [summary] enabled but no [openrouter] api_key; summaries off",
                  file=sys.stderr)

    app = create_app(store, cfg, usage_provider=cache.get, heartbeat=heartbeat,
                     summary_provider=summaries.get)
    print(f"VibeMonitor hub on http://{cfg.host}:{cfg.port}  (Ctrl+C to stop)")
    try:
        app.run(host=cfg.host, port=cfg.port, threaded=True)
    finally:
        stop.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
