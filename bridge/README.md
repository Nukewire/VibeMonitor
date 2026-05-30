# VibeMonitor Bridge

Serves local Claude Code + Codex session state and usage to the VibeMonitor CYD display
(ESP32-2432S028R "Cheap Yellow Display").

A single Python process that:
- watches `~/.claude/projects/**/*.jsonl` and today's `~/.codex/sessions/...` to build a
  live list of your coding sessions (working / idle / waiting / gone),
- receives instant "needs you" events from a Claude Code hook (`Notification` = blocked on
  you; `Stop`/`UserPromptSubmit`/`SessionStart` are activity that clears it),
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
- `GET /state` — `{ts, usage:{claude,codex}, sessions:[{id,tool,project,status,ageSec,waiting,count}], staleSec}`.
  Sessions are sorted waiting-first and deduped per (tool, project); GONE sessions are
  dropped from the response. `staleSec` is seconds since the last successful scan (`-1`
  before the first scan) so a stalled bridge is detectable. `/state` is read-only.
- `POST /ack {"id":...}` — clear the waiting highlight for the whole (tool, project) group
  the session belongs to (device tap-to-dismiss).
- `POST /hook` — receives Claude Code hook events (used by `hooks/vibemonitor_hook.py`);
  the hub stamps the event time server-side.

## Status model
- **working** — session log changed within `working_sec` (default 60s).
- **waiting** — blocked on you. Claude: a `Notification` hook (a `Stop`/turn-finished is
  *not* waiting). Codex (no blocked signal in its logs): a finished turn (`task_complete`).
  A waiting session is highlighted for `waiting_ttl_sec` (default 30 min), then decays to
  idle — never pinned forever. Sorted to top.
- **idle** — quiet but newer than `gone_ttl_sec`.
- **gone** — quiet longer than `gone_ttl_sec` (default 4h) → removed from the list (reaped
  by the poll loop, not the `/state` request).

## Architecture
`main.py` runs two daemon threads — a session scan loop (`collector_claude` +
`collector_codex` → `Store`, which also reaps GONE sessions and publishes a `last_scan`
heartbeat) and a usage poll loop (`usage` → `UsageCache`) — and serves the Flask `hub`.
Each loop iteration is wrapped so one bad file can't silently kill the thread. The `Store`
is thread-safe (RLock, copy-on-read). The collector→hub split is a module boundary so a
second machine's collector can POST to one hub later (multi-PC, designed but not shipped in v1).

## Test
`python -m pytest -q`   (79 tests)

## Notes
- The Codex sessions dir is huge; the collector only scans today's + yesterday's date folders.
- Codex usage % is read from the `token_count` rate-limit events in the rollout logs.
- `config.toml` is gitignored (it holds your token). Never commit it.
