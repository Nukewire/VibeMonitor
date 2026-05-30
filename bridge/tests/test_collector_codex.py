import os, shutil
from pathlib import Path
from vibemonitor.model import Store
from vibemonitor.collector_codex import parse_rollout, scan_codex

FIX = Path(__file__).parent / "fixtures" / "codex_rollout.jsonl"

def test_parse_rollout_extracts_project_and_waiting():
    info = parse_rollout(FIX)
    assert info["id"] == "019e556b"
    assert info["project"] == "MyProject"
    assert info["waiting"] is True          # ends on task_complete

def test_parse_rollout_working_when_task_started_last(tmp_path):
    p = tmp_path / "r.jsonl"
    p.write_text(
        '{"type":"session_meta","payload":{"id":"z1","cwd":"/a/b/Proj"}}\n'
        '{"type":"event_msg","payload":{"type":"task_started"}}\n',
        encoding="utf-8")
    info = parse_rollout(p)
    assert info["id"] == "z1"
    assert info["project"] == "Proj"
    assert info["waiting"] is False

def test_scan_codex_reads_today_dir(tmp_path):
    # layout: sessions/2026/05/29/<file>
    day = tmp_path / "sessions" / "2026" / "05" / "29"
    day.mkdir(parents=True)
    dest = day / "rollout-019e556b.jsonl"
    shutil.copy(FIX, dest)
    os.utime(dest, (2000.0, 2000.0))

    store = Store()
    # pass an explicit date so the test is deterministic
    scan_codex(store, sessions_root=tmp_path / "sessions",
               today=(2026, 5, 29), now=2001.0)
    s = store.get("019e556b")
    assert s is not None
    assert s.tool == "codex"
    assert s.project == "MyProject"
    assert s.last_activity == 2000.0
    assert s.waiting is True

def test_scan_codex_missing_root_is_safe(tmp_path):
    store = Store()
    scan_codex(store, sessions_root=tmp_path / "nope", today=(2026, 5, 29), now=1.0)
    assert store.snapshot() == []
