import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
from install_hooks import merge_hooks, HOOK_EVENTS

def test_merge_into_empty():
    out = merge_hooks({}, command="python hook.py")
    assert set(HOOK_EVENTS).issubset(out["hooks"].keys())
    entry = out["hooks"]["Notification"][0]["hooks"][0]
    assert entry["command"] == "python hook.py"

def test_merge_preserves_existing_unrelated_hooks():
    existing = {"hooks": {"PreToolUse": [{"matcher": "Bash",
                "hooks": [{"type": "command", "command": "gsd.js"}]}]}}
    out = merge_hooks(existing, command="python hook.py")
    assert "PreToolUse" in out["hooks"]
    assert out["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "gsd.js"
    assert "Notification" in out["hooks"]

def test_merge_is_idempotent():
    out1 = merge_hooks({}, command="python hook.py")
    out2 = merge_hooks(out1, command="python hook.py")
    for ev in HOOK_EVENTS:
        cmds = [h["command"] for blk in out2["hooks"][ev] for h in blk["hooks"]]
        assert cmds.count("python hook.py") == 1

def test_merge_appends_to_existing_same_event():
    existing = {"hooks": {"Stop": [{"matcher": "",
                "hooks": [{"type": "command", "command": "other.js"}]}]}}
    out = merge_hooks(existing, command="python hook.py")
    cmds = [h["command"] for blk in out["hooks"]["Stop"] for h in blk["hooks"]]
    assert "other.js" in cmds and "python hook.py" in cmds

def test_merge_does_not_mutate_input():
    existing = {"hooks": {"Stop": [{"matcher": "", "hooks": [{"type": "command", "command": "x"}]}]}}
    import copy
    snapshot = copy.deepcopy(existing)
    merge_hooks(existing, command="python hook.py")
    assert existing == snapshot   # input untouched
