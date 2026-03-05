"""Shenron configuration — paths, constants, defaults."""

from pathlib import Path

# Claude Code data directory
CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"

# File patterns
SESSION_GLOB = "*.jsonl"
AGENT_PREFIX = "agent-"

# Message types
MSG_TYPE_USER = "user"
MSG_TYPE_ASSISTANT = "assistant"
MSG_TYPE_SYSTEM = "system"
MSG_TYPE_PROGRESS = "progress"
MSG_TYPE_QUEUE = "queue-operation"
MSG_TYPE_SNAPSHOT = "file-history-snapshot"

CONTENT_TYPES = {MSG_TYPE_USER, MSG_TYPE_ASSISTANT}

# Parser
META_SCAN_LINES = 20  # Lines to read in meta-only mode

# Display
DEFAULT_LIMIT = 20
DEFAULT_CONTEXT_CHARS = 80
DEFAULT_TOP_N = 10
MAX_PREVIEW_LEN = 80
