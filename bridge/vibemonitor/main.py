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
from vibemonitor.statemachine import derive_status, is_junk_project
from vibemonitor.summarizer import extract_latest_prompt, summarize
from vibemonitor.summarycache import SummaryCache, hash_text
from vibemonitor.notifier import WebhookNotifier, WaitingCoordinator
from vibemonitor.usagehistory import UsageHistory
from vibemonitor.analyticscache import AnalyticsCache
from vibemonitor.usageanalytics import build_provider, daily_history
from vibemonitor.push import PushNotifier
from vibemonitor.costs import CostCache, summarize_costs
from vibemonitor.collector_claude import claude_projects_root
from vibemonitor.collector_codex import codex_sessions_root

_HISTORY_RETENTION_SEC = 90 * 86400        # keep ~90 days of usage samples
_SPARK_WINDOW_SEC = 5 * 3600               # samples shown in the sparkline / used for burn
_DAILY_WINDOW_SEC = 14 * 86400             # span for the per-day history


def _downsample(samples: list[dict], n: int = 80) -> list[dict]:
    """Thin a sample list to at most n points (keep ts+pct) for a compact sparkline.
    Always includes the first and last sample so the trend's most-recent point is shown."""
    if len(samples) <= n:
        return [{"ts": s["ts"], "pct": s["pct"]} for s in samples]
    step = (len(samples) - 1) / (n - 1)
    idxs = sorted({round(i * step) for i in range(n)})   # spans 0 .. len-1 inclusive
    return [{"ts": samples[j]["ts"], "pct": samples[j]["pct"]} for j in idxs]


def _build_analytics(history: UsageHistory, usage: dict, now: float) -> dict:
    bundle: dict = {"ts": int(now)}
    for provider in ("claude", "codex"):
        recent = history.samples(provider, since_ts=now - _SPARK_WINDOW_SEC)
        wide = history.samples(provider, since_ts=now - _DAILY_WINDOW_SEC)
        prov = build_provider(recent, usage.get(provider) or {}, now)
        prov["samples"] = _downsample(recent)
        prov["daily"] = daily_history(wide)
        bundle[provider] = prov
    return bundle


def _waiting_groups(store: Store, cfg, now: float,
                    summaries: SummaryCache | None) -> dict[tuple[str, str], str | None]:
    """Map (tool, project) -> summary for groups currently waiting on the user.
    Mirrors the hub's dedupe/junk filtering so webhook events match what's displayed."""
    groups: dict[tuple[str, str], str | None] = {}
    for s in store.snapshot():
        if derive_status(s, now=now, cfg=cfg) != "waiting" or is_junk_project(s.project):
            continue
        key = (s.tool, s.project)
        if key not in groups:                # first waiting session in the group wins
            groups[key] = summaries.get(s.id) if summaries else None
    return groups


def _session_loop(store: Store, cfg, stop: threading.Event,
                  heartbeat: dict | None = None, notifier: WebhookNotifier | None = None,
                  summaries: SummaryCache | None = None,
                  coordinator: WaitingCoordinator | None = None) -> None:
    while not stop.is_set():
        now = time.time()
        try:
            if cfg.enable_claude:
                scan_claude(store, now=now)
            if cfg.enable_codex:
                scan_codex(store, now=now)
            for s in store.snapshot():                       # reap gone atomically here
                store.remove_if_gone(s.id, now=now, cfg=cfg, derive=derive_status)
            # single edge-detector fans out to HA webhook + phone push; falls back to
            # the bare webhook for callers that still pass a notifier directly (tests).
            sink = coordinator if coordinator is not None else notifier
            if sink is not None:
                sink.update(_waiting_groups(store, cfg, now, summaries))
            if heartbeat is not None:
                heartbeat["last_scan"] = now
        except Exception as e:                               # never die silently
            print(f"[session_loop] scan error (continuing): {e!r}", file=sys.stderr)
        stop.wait(cfg.poll_sessions_sec)


def _usage_loop(cache: UsageCache, cfg, stop: threading.Event,
                history: UsageHistory | None = None,
                analytics: AnalyticsCache | None = None) -> None:
    while not stop.is_set():
        now = time.time()
        try:
            # Re-resolve the token every poll: the config value wins, otherwise the
            # local Claude OAuth token is auto-read fresh. Claude Code rotates the
            # access token every few hours, so capturing it once at startup would
            # leave the usage gauge stuck on a stale (expired) token -> ok:false.
            claude_token = cfg.claude_oauth_token or read_claude_oauth_token()
            usage = {
                "claude": claude_usage(claude_token, now=now) if cfg.enable_claude
                          else {"ok": False},
                "codex": codex_usage(now=now) if cfg.enable_codex else {"ok": False},
            }
            cache.set(usage)
            if history is not None:
                history.record(now, usage)
                history.prune(now - _HISTORY_RETENTION_SEC)
                if analytics is not None:
                    analytics.set(_build_analytics(history, usage, now))
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


def _claude_cost_paths() -> list[Path]:
    root = claude_projects_root()
    if not root.exists():
        return []
    return [f for projdir in root.iterdir() if projdir.is_dir()
            for f in projdir.glob("*.jsonl")]


def _codex_cost_paths(now: float) -> list[Path]:
    import datetime
    root = codex_sessions_root()
    if not root.exists():
        return []
    t = datetime.date.fromtimestamp(now)
    out: list[Path] = []
    for d in (t, t - datetime.timedelta(days=1)):
        day = root / f"{d.year:04d}" / f"{d.month:02d}" / f"{d.day:02d}"
        if day.exists():
            out.extend(day.glob("*.jsonl"))
    return out


def _costs_loop(cache: CostCache, cfg, stop: threading.Event) -> None:
    """Slow loop: re-scan today's session logs and cache per-project token attribution."""
    while not stop.is_set():
        now = time.time()
        try:
            claude_paths = _claude_cost_paths() if cfg.enable_claude else []
            codex_paths = _codex_cost_paths(now) if cfg.enable_codex else []
            cache.set(summarize_costs(claude_paths, codex_paths, now,
                                      pricing=cfg.pricing))
        except Exception as e:                          # never die silently
            print(f"[costs_loop] error (continuing): {e!r}", file=sys.stderr)
        stop.wait(cfg.poll_costs_sec)


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
    history = UsageHistory(str(cfg_path.parent / "usage_history.db"))
    analytics = AnalyticsCache()
    costs = CostCache()
    notifier = WebhookNotifier(cfg.ha_webhook_url) if cfg.ha_webhook_url else None
    if notifier:
        print("Home Assistant webhook enabled", file=sys.stderr)  # URL holds a secret id
    push = PushNotifier(provider=cfg.push_provider, ntfy_url=cfg.push_ntfy_url,
                        pushover_token=cfg.push_pushover_token,
                        pushover_user=cfg.push_pushover_user)
    if push.configured():
        print(f"Phone push enabled (provider={cfg.push_provider})", file=sys.stderr)
    coordinator = WaitingCoordinator(webhook=notifier,
                                     push=push if push.configured() else None,
                                     escalate_sec=cfg.push_escalate_sec)
    stop = threading.Event()
    heartbeat: dict = {"last_scan": 0.0}

    threading.Thread(target=_session_loop,
                     args=(store, cfg, stop, heartbeat, notifier, summaries, coordinator),
                     daemon=True).start()
    threading.Thread(target=_usage_loop, args=(cache, cfg, stop, history, analytics),
                     daemon=True).start()
    threading.Thread(target=_costs_loop, args=(costs, cfg, stop), daemon=True).start()
    if cfg.summary_enabled:
        if cfg.openrouter_api_key:
            threading.Thread(target=_summary_loop, args=(store, summaries, cfg, stop),
                             daemon=True).start()
        else:
            print("note: [summary] enabled but no [openrouter] api_key; summaries off",
                  file=sys.stderr)

    app = create_app(store, cfg, usage_provider=cache.get, heartbeat=heartbeat,
                     summary_provider=summaries.get, analytics_provider=analytics.get,
                     costs_provider=costs.get)
    print(f"VibeMonitor hub on http://{cfg.host}:{cfg.port}  (Ctrl+C to stop)")
    try:
        app.run(host=cfg.host, port=cfg.port, threaded=True)
    finally:
        stop.set()
        history.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
