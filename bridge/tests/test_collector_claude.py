import os
from vibemonitor.model import Store
from vibemonitor.collector_claude import project_from_encoded_dir, scan_claude

def test_project_from_encoded_dir():
    assert project_from_encoded_dir("C--Projects-VibeMonitor") == "VibeMonitor"
    assert project_from_encoded_dir("C--Projects-MyProject") == "MyProject"
    assert project_from_encoded_dir("solo") == "solo"

def test_scan_picks_up_session_files(tmp_path):
    projdir = tmp_path / "projects" / "C--Projects-Demo"
    projdir.mkdir(parents=True)
    f = projdir / "abc123.jsonl"
    f.write_text('{"type":"user"}\n', encoding="utf-8")
    os.utime(f, (1000.0, 1000.0))   # set mtime

    store = Store()
    scan_claude(store, projects_root=tmp_path / "projects", now=1005.0)
    s = store.get("abc123")
    assert s is not None
    assert s.tool == "claude"
    assert s.project == "Demo"
    assert s.last_activity == 1000.0

def test_scan_skips_non_jsonl(tmp_path):
    projdir = tmp_path / "projects" / "C--x-Demo"
    projdir.mkdir(parents=True)
    (projdir / "notes.txt").write_text("x", encoding="utf-8")
    store = Store()
    scan_claude(store, projects_root=tmp_path / "projects", now=1.0)
    assert store.snapshot() == []

def test_scan_missing_root_is_safe(tmp_path):
    store = Store()
    scan_claude(store, projects_root=tmp_path / "nope", now=1.0)  # must not raise
    assert store.snapshot() == []

def test_scan_claude_clamps_future_mtime(tmp_path):
    import os
    from vibemonitor.model import Store
    from vibemonitor.collector_claude import scan_claude
    root = tmp_path / "projects"
    proj = root / "-c-Projects-MyApp"
    proj.mkdir(parents=True)
    f = proj / "abc123.jsonl"
    f.write_text("{}\n", encoding="utf-8")
    os.utime(f, (5000.0, 5000.0))          # mtime in the future relative to now
    store = Store()
    scan_claude(store, projects_root=root, now=1000.0)
    s = store.get("abc123")
    assert s is not None
    assert s.last_activity <= 1000.0       # clamped, not 5000
