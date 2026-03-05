"""Streaming JSONL parser for Claude Code session files."""

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from shenron.config import META_SCAN_LINES, MSG_TYPE_ASSISTANT, MSG_TYPE_USER
from shenron.models import Message, Session, SessionMeta, TokenUsage

logger = logging.getLogger(__name__)


def _parse_timestamp(ts: str) -> datetime:
    """Parse ISO 8601 timestamp string to datetime."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _extract_text(content: list | str | None) -> str:
    """Extract readable text from message content (handles all block types)."""
    if not content:
        return ""
    if isinstance(content, str):
        return content

    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type", "")
        if btype == "text":
            parts.append(block.get("text", ""))
        elif btype == "thinking":
            # Omit thinking by default — too large, has signature noise
            pass
        elif btype == "tool_use":
            name = block.get("name", "unknown")
            parts.append(f"[tool: {name}]")
        elif btype == "tool_result":
            result = block.get("content", "")
            if isinstance(result, str) and result:
                parts.append(result[:200])  # Truncate long tool outputs
    return " ".join(p for p in parts if p)


def _extract_tool_names(content: list | str | None) -> tuple[str, ...]:
    """Extract names of all tools used in a message."""
    if not isinstance(content, list):
        return ()
    return tuple(
        block.get("name", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "tool_use"
    )


def _parse_usage(usage_dict: dict) -> TokenUsage | None:
    """Parse usage dict from assistant message."""
    if not usage_dict:
        return None
    return TokenUsage(
        input_tokens=usage_dict.get("input_tokens", 0),
        output_tokens=usage_dict.get("output_tokens", 0),
        cache_creation_input_tokens=usage_dict.get("cache_creation_input_tokens", 0),
        cache_read_input_tokens=usage_dict.get("cache_read_input_tokens", 0),
    )


def _line_to_message(data: dict) -> Message | None:
    """Convert a parsed JSON dict to a Message, or None if not a content message."""
    msg_type = data.get("type", "")
    if msg_type not in (MSG_TYPE_USER, MSG_TYPE_ASSISTANT, "system"):
        return None

    uuid = data.get("uuid", "")
    ts_str = data.get("timestamp", "")
    try:
        timestamp = _parse_timestamp(ts_str) if ts_str else datetime.now(tz=UTC)
    except ValueError:
        timestamp = datetime.now(tz=UTC)

    message = data.get("message", {})
    content = message.get("content")
    content_text = _extract_text(content)
    tool_names = _extract_tool_names(content)

    model: str | None = None
    usage: TokenUsage | None = None

    if msg_type == MSG_TYPE_ASSISTANT:
        model = message.get("model")
        usage = _parse_usage(message.get("usage", {}))

    return Message(
        uuid=uuid,
        msg_type=msg_type,
        timestamp=timestamp,
        content_text=content_text,
        model=model,
        usage=usage,
        tool_names=tool_names,
        is_sidechain=data.get("isSidechain", False),
        parent_uuid=data.get("parentUuid"),
    )


def stream_messages(file_path: Path) -> Iterator[Message]:
    """
    Yield Messages from a session file one at a time.
    Skips malformed lines with a warning.
    Memory: O(1) — only one message in memory at a time.
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed JSON at %s line %d", file_path, lineno)
                    continue
                msg = _line_to_message(data)
                if msg is not None:
                    yield msg
    except (OSError, PermissionError) as e:
        logger.warning("Cannot read %s: %s", file_path, e)


def parse_session_meta_fields(file_path: Path) -> dict:
    """
    Quick parse: read first META_SCAN_LINES lines to extract
    cwd, version, gitBranch, first_timestamp, model.
    Returns a dict with whatever fields were found.
    """
    result: dict = {}
    try:
        with open(file_path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= META_SCAN_LINES:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Capture first timestamp seen
                if "timestamp" not in result and data.get("timestamp"):
                    import contextlib
                    with contextlib.suppress(ValueError):
                        result["first_timestamp"] = _parse_timestamp(data["timestamp"])

                # Capture cwd, version, gitBranch from first user message
                if data.get("type") == MSG_TYPE_USER and "cwd" not in result:
                    result["cwd"] = data.get("cwd")
                    result["version"] = data.get("version")
                    result["git_branch"] = data.get("gitBranch")

                    # Extract first user message text
                    msg = _line_to_message(data)
                    if msg and msg.content_text:
                        result["first_user_text"] = msg.content_text

                # Capture model from first assistant message
                if data.get("type") == MSG_TYPE_ASSISTANT and "model" not in result:
                    message = data.get("message", {})
                    if message.get("model"):
                        result["model"] = message["model"]

    except (OSError, PermissionError) as e:
        logger.warning("Cannot read %s: %s", file_path, e)

    return result


def parse_session(meta: SessionMeta) -> Session:
    """
    Full parse: stream entire file and build a Session object.
    """
    messages: list[Message] = []
    cwd: str | None = None
    git_branch: str | None = None
    version: str | None = None
    first_ts: datetime | None = None
    last_ts: datetime | None = None

    try:
        with open(meta.file_path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed JSON at %s line %d", meta.file_path, lineno)
                    continue

                # Extract context from user messages
                if data.get("type") == MSG_TYPE_USER and cwd is None:
                    cwd = data.get("cwd")
                    git_branch = data.get("gitBranch")
                    version = data.get("version")

                # Track timestamps
                ts_str = data.get("timestamp", "")
                if ts_str:
                    try:
                        ts = _parse_timestamp(ts_str)
                        if first_ts is None or ts < first_ts:
                            first_ts = ts
                        if last_ts is None or ts > last_ts:
                            last_ts = ts
                    except ValueError:
                        pass

                # Parse message
                msg = _line_to_message(data)
                if msg is not None:
                    messages.append(msg)

    except (OSError, PermissionError) as e:
        logger.warning("Cannot read %s: %s", meta.file_path, e)

    return Session(
        meta=meta,
        messages=tuple(messages),
        cwd=cwd,
        git_branch=git_branch,
        version=version,
        first_timestamp=first_ts,
        last_timestamp=last_ts,
    )
