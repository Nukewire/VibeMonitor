import os, shutil
from pathlib import Path
from vibemonitor.model import Store
from vibemonitor.collector_codex import parse_rollout, scan_codex, _uuid_from_stem

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


def test_uuid_from_stem_full_uuid():
    stem = "rollout-2026-05-30T10-29-18-019e7981-030f-7d60-84cd-b2e9a9ca41ef"
    assert _uuid_from_stem(stem) == "019e7981-030f-7d60-84cd-b2e9a9ca41ef"


def test_parse_rollout_id_is_full_uuid_without_session_meta(tmp_path):
    p = tmp_path / "rollout-2026-05-30T10-29-18-019e7981-030f-7d60-84cd-b2e9a9ca41ef.jsonl"
    p.write_text('{"type":"event_msg","payload":{"type":"task_complete"}}\n',
                 encoding="utf-8")
    info = parse_rollout(p)
    assert info["id"] == "019e7981-030f-7d60-84cd-b2e9a9ca41ef"
    assert info["waiting"] is True


def test_parse_rollout_turn_aborted_is_not_waiting(tmp_path):
    p = tmp_path / "rollout-2026-05-30T10-00-00-aaaa.jsonl"
    p.write_text(
        '{"type":"event_msg","payload":{"type":"task_started"}}\n'
        '{"type":"event_msg","payload":{"type":"turn_aborted"}}\n',
        encoding="utf-8")
    assert parse_rollout(p)["waiting"] is False


def test_parse_rollout_version_fallback_agent_message_waiting(tmp_path):
    p = tmp_path / "rollout-2026-05-30T10-00-00-bbbb.jsonl"
    p.write_text(
        '{"type":"event_msg","payload":{"type":"user_message"}}\n'
        '{"type":"event_msg","payload":{"type":"agent_message"}}\n',
        encoding="utf-8")
    assert parse_rollout(p)["waiting"] is True


def test_parse_rollout_version_fallback_user_message_working(tmp_path):
    p = tmp_path / "rollout-2026-05-30T10-00-00-cccc.jsonl"
    p.write_text(
        '{"type":"event_msg","payload":{"type":"agent_message"}}\n'
        '{"type":"event_msg","payload":{"type":"user_message"}}\n',
        encoding="utf-8")
    assert parse_rollout(p)["waiting"] is False


def test_scan_codex_does_not_resurrect_acked_waiting(tmp_path):
    day = tmp_path / "sessions" / "2026" / "05" / "30"
    day.mkdir(parents=True)
    f = day / "rollout-2026-05-30T10-00-00-019e0000-0000-7000-8000-000000000001.jsonl"
    f.write_text('{"type":"event_msg","payload":{"type":"task_complete"}}\n',
                 encoding="utf-8")
    os.utime(f, (1000.0, 1000.0))
    store = Store()
    scan_codex(store, sessions_root=tmp_path / "sessions", today=(2026, 5, 30), now=1001.0)
    sid = "019e0000-0000-7000-8000-000000000001"
    assert store.get(sid).waiting is True
    store.ack(sid, ts=1500.0)            # user acks after the file's mtime
    scan_codex(store, sessions_root=tmp_path / "sessions", today=(2026, 5, 30), now=1600.0)
    assert store.get(sid).waiting is False   # unchanged file must not resurrect alert


def test_scan_codex_reraises_waiting_after_new_activity(tmp_path):
    day = tmp_path / "sessions" / "2026" / "05" / "30"
    day.mkdir(parents=True)
    f = day / "rollout-2026-05-30T10-00-00-019e0000-0000-7000-8000-000000000002.jsonl"
    f.write_text('{"type":"event_msg","payload":{"type":"task_complete"}}\n',
                 encoding="utf-8")
    os.utime(f, (1000.0, 1000.0))
    store = Store()
    sid = "019e0000-0000-7000-8000-000000000002"
    scan_codex(store, sessions_root=tmp_path / "sessions", today=(2026, 5, 30), now=1001.0)
    store.ack(sid, ts=1500.0)
    os.utime(f, (2000.0, 2000.0))        # genuinely new activity (mtime > acked_at)
    scan_codex(store, sessions_root=tmp_path / "sessions", today=(2026, 5, 30), now=2001.0)
    assert store.get(sid).waiting is True
