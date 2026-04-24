"""Domain models — immutable dataclasses for Shenron."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class TokenUsage:
    """Token usage from a single assistant message."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_creation_input_tokens=self.cache_creation_input_tokens + other.cache_creation_input_tokens,
            cache_read_input_tokens=self.cache_read_input_tokens + other.cache_read_input_tokens,
        )


ZERO_USAGE = TokenUsage()


@dataclass(frozen=True)
class Message:
    """A single message in a session."""

    uuid: str
    msg_type: str                          # user, assistant, system, progress, etc.
    timestamp: datetime
    content_text: str = ""                 # Extracted plain text
    model: str | None = None               # Only for assistant messages
    usage: TokenUsage | None = None        # Only for assistant messages
    tool_names: tuple[str, ...] = field(default_factory=tuple)
    is_sidechain: bool = False
    parent_uuid: str | None = None


@dataclass(frozen=True)
class ObservationSummary:
    """Aggregated PostToolUse observations for a session."""

    tools_used: tuple[tuple[str, int], ...]  # (tool_name, count) sorted desc by count
    files_touched: tuple[str, ...]           # unique file paths (Edit/Write/Read)
    commands_run: tuple[str, ...]            # unique sanitized Bash commands
    web_fetched: tuple[str, ...]             # WebSearch queries + WebFetch URLs


@dataclass(frozen=True)
class SessionMeta:
    """Lightweight session metadata — no full parse needed."""

    session_id: str
    project_dir: str                       # e.g. "-Users-titans-Desktop-crypto-bots-framework"
    project_name: str                      # e.g. "~/Desktop/crypto-bots/framework"
    file_path: Path
    file_size: int                         # bytes
    modified_time: datetime


@dataclass(frozen=True)
class Session:
    """Fully parsed session."""

    meta: SessionMeta
    messages: tuple[Message, ...]
    cwd: str | None = None
    git_branch: str | None = None
    version: str | None = None
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None

    @property
    def user_messages(self) -> tuple[Message, ...]:
        return tuple(m for m in self.messages if m.msg_type == "user")

    @property
    def assistant_messages(self) -> tuple[Message, ...]:
        return tuple(m for m in self.messages if m.msg_type == "assistant")

    @property
    def duration_seconds(self) -> float | None:
        if self.first_timestamp and self.last_timestamp:
            return (self.last_timestamp - self.first_timestamp).total_seconds()
        return None

    @property
    def total_usage(self) -> TokenUsage:
        result = ZERO_USAGE
        for msg in self.assistant_messages:
            if msg.usage:
                result = result + msg.usage
        return result

    @property
    def models_used(self) -> set[str]:
        return {m.model for m in self.assistant_messages if m.model}

    @property
    def first_user_text(self) -> str:
        for msg in self.messages:
            if msg.msg_type == "user" and msg.content_text.strip():
                return msg.content_text
        return ""
