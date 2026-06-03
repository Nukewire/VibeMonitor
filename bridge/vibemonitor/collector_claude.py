from __future__ import annotations
from pathlib import Path
from vibemonitor.model import Session, Store


def project_from_encoded_dir(name: str) -> str:
    """Claude encodes the cwd as path-with-dashes; project = last segment."""
    parts = [p for p in name.split("-") if p]
    return parts[-1] if parts else name


def claude_projects_root() -> Path:
    return Path.home() / ".claude" / "projects"


def claude_session_paths(projects_root: Path | None = None) -> dict[str, Path]:
    """Map session id (jsonl stem) -> file path, mirroring scan_claude's discovery.
    Used by the summary loop to locate a session's transcript. Safe on missing root."""
    root = Path(projects_root) if projects_root is not None else claude_projects_root()
    out: dict[str, Path] = {}
    if not root.exists():
        return out
    for projdir in root.iterdir():
        if not projdir.is_dir():
            continue
        for f in projdir.glob("*.jsonl"):
            out[f.stem] = f
    return out


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
            if now:
                mtime = min(mtime, now)        # clamp clock skew / future files
            store.upsert(Session(
                id=f.stem, tool="claude", project=project, last_activity=mtime,
            ))
