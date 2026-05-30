# VibeMonitor Bridge

Serves local Claude Code + Codex session state and usage to the VibeMonitor CYD display
(ESP32-2432S028R "Cheap Yellow Display").

A single Python process that:
- watches `~/.claude/projects/**/*.jsonl` and today's `~/.codex/sessions/...` to build a
  live list of your coding sessions (working / idle / waiting / gone),
- receives instant "needs you" events from a Claude Code hook (`Notification` / `Stop`),
- polls your Claude usage % (and resets) via the Anthropic rate-limit headers,
- serves it all to the ESP32 over HTTP.

## Setup
1. `python -m pip install -e ".[dev]"`
2. `cp config.example.toml config.toml` and set a random `token` (the device sends it as
   the `X-VibeMonitor-Token` header). The Claude OAuth token is auto-read from
   `~/.claude/.credentials.json`; set `[claude] oauth_token` only to override it.
3. Run the hub: `python -m vibemonitor.main config.toml`
4. Install Claude Code hooks (instant "waiting" alerts):
   `python hooks/install_hooks.py --token <same-token> --url http://localhost:8787/hook`
   This backs up and MERGES into `~/.claude/settings.json` (it will not clobber your
   existing hooks). Restart Claude Code so it picks them up.

## Endpoints
All require the `X-VibeMonitor-Token` header.
- `GET /state` — `{ts, usage:{claude,codex}, sessions:[{id,tool,project,status,ageSec,waiting}]}`.
  Sessions are sorted waiting-first; GONE sessions are dropped.
- `POST /ack {"id":...}` — clear a session's waiting highlight (device tap-to-dismiss).
- `POST /hook` — receives Claude Code hook events (used by `hooks/vibemonitor_hook.py`).

## Status model
- **waiting** — a hook `Notification`/`Stop` (Claude), or a trailing `task_complete` (Codex). Sorted to top.
- **working** — session file active within `working_sec` (default 10s).
- **idle** — quiet but newer than `gone_ttl_sec`.
- **gone** — older than `gone_ttl_sec` (default 30m) → removed from the list.

## Architecture
`main.py` runs two daemon threads — a session scan loop (`collector_claude` +
`collector_codex` → `Store`) and a usage poll loop (`usage` → `UsageCache`) — and serves
the Flask `hub`. The `Store` is thread-safe (RLock, copy-on-read). The collector→hub split
is a module boundary so a second machine's collector can POST to one hub later (multi-PC,
designed but not shipped in v1).

## Test
`python -m pytest -q`   (51 tests)

## Notes
- The Codex sessions dir is huge; the collector only scans today's + yesterday's date folders.
- Codex usage % is a placeholder in v1 (`ok:false`); the device shows "—".
- `config.toml` is gitignored (it holds your token). Never commit it.
- The next deliverable is the CYD firmware (Plan 2), built against these endpoints.
