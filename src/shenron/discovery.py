"""Session file discovery — find and enumerate Claude Code sessions."""

import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from shenron.config import AGENT_PREFIX, PROJECTS_DIR, SESSION_GLOB
from shenron.models import SessionMeta

# UUID pattern: 8-4-4-4-12 hex chars
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _is_main_session(filename: str) -> bool:
    """True if filename looks like a main session UUID (not an agent file)."""
    stem = Path(filename).stem
    return bool(_UUID_RE.match(stem))


def _is_agent_session(filename: str) -> bool:
    """True if filename is a subagent session."""
    return Path(filename).stem.startswith(AGENT_PREFIX)


def project_dir_to_name(dir_name: str) -> str:
    """Convert '-Users-titans-Desktop-crypto-bots-framework' to '~/Desktop/crypto-bots/framework'."""
    # Strip leading dash
    name = dir_name.lstrip("-")
    # Replace dash-separated path components with slashes
    # Heuristic: split on '-' and try to reconstruct a path
    # Use cwd field when available (more accurate); this is fallback
    parts = name.split("-")
    # Look for 'Users' as anchor
    try:
        idx = next(i for i, p in enumerate(parts) if p.lower() == "users")
        # Skip 'Users/<username>'
        path_parts = parts[idx + 2 :]
        if path_parts:
            return "~/" + "/".join(path_parts)
        return "~/"
    except StopIteration:
        return "/" + "/".join(parts)


def _mtime_to_datetime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def discover_sessions(
    projects_dir: Path = PROJECTS_DIR,
    project_filter: str | None = None,
    after: datetime | None = None,
    before: datetime | None = None,
    include_agents: bool = False,
) -> Iterator[SessionMeta]:
    """
    Yield SessionMeta for each session file found under projects_dir.

    Filters:
    - project_filter: substring match against project directory name
    - after / before: filter by file modification time
    - include_agents: include subagent .jsonl files (default False)
    """
    if not projects_dir.exists():
        return

    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue

        dir_name = project_dir.name

        # Apply project filter
        if project_filter and project_filter.lower() not in dir_name.lower():
            continue

        project_name = project_dir_to_name(dir_name)

        # Scan main session files in project root
        for jsonl in project_dir.glob(SESSION_GLOB):
            if not jsonl.is_file():
                continue

            filename = jsonl.name

            # Determine if this is a main session or agent file
            if _is_main_session(filename):
                is_agent = False
            elif _is_agent_session(filename):
                if not include_agents:
                    continue
                is_agent = True
            else:
                continue  # Unknown file pattern, skip

            _ = is_agent  # reserved for future use

            stat = jsonl.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)

            # Apply date filters (using mtime as proxy for session time)
            if after and mtime < after:
                continue
            if before and mtime > before:
                continue

            session_id = jsonl.stem

            yield SessionMeta(
                session_id=session_id,
                project_dir=dir_name,
                project_name=project_name,
                file_path=jsonl,
                file_size=stat.st_size,
                modified_time=mtime,
            )

        # Scan subagent files in subdirectory (named after session UUID)
        if include_agents:
            for sub_dir in project_dir.iterdir():
                if not sub_dir.is_dir():
                    continue
                agents_dir = sub_dir / "subagents"
                if not agents_dir.exists():
                    continue
                for jsonl in agents_dir.glob(SESSION_GLOB):
                    if not jsonl.is_file():
                        continue
                    stat = jsonl.stat()
                    mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
                    if after and mtime < after:
                        continue
                    if before and mtime > before:
                        continue
                    yield SessionMeta(
                        session_id=jsonl.stem,
                        project_dir=dir_name,
                        project_name=project_name,
                        file_path=jsonl,
                        file_size=stat.st_size,
                        modified_time=mtime,
                    )
