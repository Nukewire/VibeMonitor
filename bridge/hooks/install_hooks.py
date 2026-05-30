from __future__ import annotations
import json
import shutil
import sys
from pathlib import Path

HOOK_EVENTS = ["Notification", "Stop", "UserPromptSubmit", "SessionStart"]


def _our_command(hooks_dir: Path, token: str, url: str) -> str:
    script = hooks_dir / "vibemonitor_hook.py"
    return f'python "{script}" --url "{url}" --token "{token}"'


def merge_hooks(settings: dict, command: str) -> dict:
    settings = json.loads(json.dumps(settings))  # deep copy; never mutate input
    hooks = settings.setdefault("hooks", {})
    for ev in HOOK_EVENTS:
        blocks = hooks.setdefault(ev, [])
        existing = [h.get("command") for blk in blocks for h in blk.get("hooks", [])]
        if command in existing:
            continue
        blocks.append({"matcher": "", "hooks": [{"type": "command", "command": command}]})
    return settings


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8787/hook")
    ap.add_argument("--token", required=True)
    ap.add_argument("--settings", default=str(Path.home() / ".claude" / "settings.json"))
    args = ap.parse_args(argv)

    settings_path = Path(args.settings)
    settings = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}

    if settings_path.exists():
        backup = settings_path.with_suffix(".json.vibemonitor.bak")
        shutil.copy(settings_path, backup)
        print(f"backed up settings to {backup}")

    command = _our_command(Path(__file__).parent, args.token, args.url)
    merged = merge_hooks(settings, command=command)
    settings_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    print(f"installed VibeMonitor hooks into {settings_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
