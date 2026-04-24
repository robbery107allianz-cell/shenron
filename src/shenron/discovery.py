"""Session file discovery — find and enumerate Claude Code sessions."""

import json
import re
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from shenron.config import AGENT_PREFIX, PROJECTS_DIR, SESSION_GLOB
from shenron.models import ObservationSummary, SessionMeta

# Regex: 20+ consecutive alphanumeric chars (likely a secret/token)
_SECRET_RE = re.compile(r"[A-Za-z0-9_\-]{20,}")
# Redact flag values that look like secrets (--flag SECRET_VALUE patterns)
_FLAG_SECRET_RE = re.compile(
    r"((?:--?(?:token|key|secret|password|auth|bearer|api[_-]?key)\s+))[^\s]+",
    re.IGNORECASE,
)

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


# ─── Observation discovery ────────────────────────────────────────────────────

#: Tools whose tool_input carries a file_path field.
_FILE_TOOLS = frozenset({"Read", "Edit", "Write", "NotebookEdit"})

#: Max length for a rendered command string (chars).
_CMD_MAX_LEN = 120


def _sanitize_command(cmd: str) -> str:
    """Return a sanitized version of a Bash command for safe wiki storage.

    - Redacts flag values that look like secrets (--token, --key, etc.)
    - Redacts standalone tokens: ≥ 20 consecutive alphanum chars that are
      NOT a plain filesystem path segment (e.g. ghp_xxx, sk-ant-xxx)
    - Truncates the result to _CMD_MAX_LEN chars
    """
    if not cmd:
        return cmd

    # Step 1: redact --flag SECRET patterns
    sanitized = _FLAG_SECRET_RE.sub(lambda m: m.group(1) + "***", cmd)

    # Step 2: redact bare long tokens that are not filesystem paths
    def _maybe_redact(match: re.Match[str]) -> str:
        token = match.group(0)
        # Allow: path-like tokens (contain / or .) — these are file paths or URLs
        if "/" in token or "." in token:
            return token
        # Allow: git SHAs are exactly 40 hex chars — short enough and expected
        if len(token) == 40 and all(c in "0123456789abcdefABCDEF" for c in token):
            return token
        # Redact if > 20 chars (likely API key / PAT / bearer token)
        return "***" if len(token) > 20 else token

    sanitized = _SECRET_RE.sub(_maybe_redact, sanitized)

    # Step 3: truncate
    if len(sanitized) > _CMD_MAX_LEN:
        sanitized = sanitized[:_CMD_MAX_LEN - 3] + "..."

    return sanitized


def discover_observations(
    session_id: str,
    obs_dir: Path,
) -> ObservationSummary | None:
    """Scan obs_dir for PostToolUse events belonging to session_id.

    obs_dir layout: obs_dir/YYYY-MM-DD/<session_id>.jsonl

    Returns an ObservationSummary if any events are found, else None.
    Malformed JSON lines are silently skipped.
    """
    if not obs_dir.exists():
        return None

    tool_counter: Counter[str] = Counter()
    seen_files: dict[str, None] = {}   # ordered set
    seen_cmds: dict[str, None] = {}    # ordered set
    seen_web: dict[str, None] = {}     # ordered set

    # Scan all date subdirectories (YYYY-MM-DD)
    for date_dir in sorted(obs_dir.iterdir()):
        if not date_dir.is_dir():
            continue
        obs_file = date_dir / f"{session_id}.jsonl"
        if not obs_file.is_file():
            continue

        with obs_file.open(encoding="utf-8") as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    event = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                tool_name: str = event.get("tool_name", "")
                if not tool_name:
                    continue

                tool_counter[tool_name] += 1
                tool_input: dict = event.get("tool_input") or {}

                # Files touched (Edit / Write / Read / NotebookEdit)
                if tool_name in _FILE_TOOLS:
                    path = tool_input.get("file_path", "")
                    if path:
                        seen_files[path] = None

                # Commands run (Bash)
                if tool_name == "Bash":
                    raw_cmd = tool_input.get("command", "").strip()
                    if raw_cmd:
                        clean = _sanitize_command(raw_cmd)
                        seen_cmds[clean] = None

                # Web activity (WebFetch / WebSearch)
                if tool_name == "WebFetch":
                    url = tool_input.get("url", "").strip()
                    if url:
                        seen_web[url] = None
                if tool_name == "WebSearch":
                    query = tool_input.get("query", "").strip()
                    if query:
                        seen_web[query] = None

    if not tool_counter:
        return None

    tools_sorted = tuple(
        (name, count)
        for name, count in tool_counter.most_common()
    )

    return ObservationSummary(
        tools_used=tools_sorted,
        files_touched=tuple(seen_files.keys()),
        commands_run=tuple(seen_cmds.keys()),
        web_fetched=tuple(seen_web.keys()),
    )
