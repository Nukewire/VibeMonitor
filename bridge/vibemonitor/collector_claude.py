from __future__ import annotations
from pathlib import Path
from vibemonitor.model import Session, Store


def project_from_encoded_dir(name: str) -> str:
    """Claude encodes the cwd as path-with-dashes; project = last segment."""
    parts = [p for p in name.split("-") if p]
    return parts[-1] if parts else name


def claude_projects_root() -> Path:
    return Path.home() / ".claude" / "projects"


def scan_claude(store: Store, projects_root: Path | None = None, now: float = 0.0) -> None:
    """Upsert one Session per *.jsonl found under projects_root, using mtime as
    last_activity. Safe to call on a missing root."""
    root = Path(projects_root) if projects_root is not None else claude_projects_root()
    if not root.exists():
        return
    for projdir in root.iterdir():
        if not projdir.is_dir():
            continue
        project = project_from_encoded_dir(projdir.name)
        for f in projdir.glob("*.jsonl"):
            try:
                mtime = f.stat().st_mtime
            except OSError:
                continue
            store.upsert(Session(
                id=f.stem, tool="claude", project=project, last_activity=mtime,
            ))
