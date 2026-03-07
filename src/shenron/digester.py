"""Digest a session into a structured decisions.md entry.

Heuristic extraction — no LLM required.
Identifies: session topic, key decision moments, closing conclusions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from shenron.models import Message, Session

# ─── Signal keywords ──────────────────────────────────────────────────────────

_SIGNALS_ZH = [
    "决定", "决策", "选择", "方案", "结论", "确认", "不要", "改为",
    "换成", "触发条件", "下一步", "建议", "理由", "原因", "架构",
    "设计", "不建议", "放弃", "保留", "新增", "删除",
]
_SIGNALS_EN = [
    "decided", "decision", "because", "reason", "instead",
    "approach", "conclusion", "next step", "recommend", "architecture",
    "design", "abandon", "keep", "add", "remove",
]

_SIGNAL_RE = re.compile(
    "|".join(re.escape(k) for k in _SIGNALS_ZH) +
    "|" +
    "|".join(re.escape(k) for k in _SIGNALS_EN),
    re.IGNORECASE,
)


def _has_signal(text: str) -> bool:
    return bool(_SIGNAL_RE.search(text))


def _truncate(text: str, max_chars: int = 180) -> str:
    text = " ".join(text.split())  # collapse whitespace
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"


# ─── Data model ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class KeyExchange:
    """A user+assistant exchange flagged as decision-relevant."""
    user_text: str
    assistant_text: str


@dataclass(frozen=True)
class DigestEntry:
    """Structured summary of a single session."""
    session_id: str
    date: str                                    # YYYY-MM-DD
    project: str
    duration_min: float | None
    message_count: int
    topic: str                                   # first meaningful user message
    key_exchanges: tuple[KeyExchange, ...]       # decision-signal exchanges
    tail_exchanges: tuple[KeyExchange, ...]      # last N exchanges (closing context)


# ─── Core extraction ──────────────────────────────────────────────────────────

def _pair_messages(messages: tuple[Message, ...]) -> list[tuple[Message, Message | None]]:
    """Pair each user message with the following assistant message."""
    pairs: list[tuple[Message, Message | None]] = []
    msgs = [m for m in messages if m.msg_type in ("user", "assistant")]
    i = 0
    while i < len(msgs):
        if msgs[i].msg_type == "user":
            assistant = msgs[i + 1] if i + 1 < len(msgs) and msgs[i + 1].msg_type == "assistant" else None
            pairs.append((msgs[i], assistant))
            i += 2 if assistant else 1
        else:
            i += 1
    return pairs


def digest_session(session: Session, tail_n: int = 3, max_key: int = 8) -> DigestEntry:
    """Extract a DigestEntry from a fully parsed Session."""
    pairs = _pair_messages(session.messages)

    # Topic: first user message with real content (skip very short ones)
    topic = ""
    for user_msg, _ in pairs:
        text = user_msg.content_text.strip()
        if len(text) > 10:
            topic = _truncate(text, 120)
            break

    # Only work with pairs that have real conversational content on both sides
    def _is_conversational(u_text: str, a_text: str) -> bool:
        # Filter out tool-result user messages and tool-only assistant messages
        if len(u_text) < 15 or len(a_text) < 30:
            return False
        # Tool outputs start with these patterns — skip them
        tool_output_prefixes = (
            "The file ", "File created", "Found ", "No files found",
            "Usage: ", "Error:", "[", "{",
        )
        if any(u_text.startswith(p) for p in tool_output_prefixes):
            return False
        return True

    # Key exchanges: pairs where user OR assistant text contains decision signals
    key_exchanges: list[KeyExchange] = []
    for user_msg, asst_msg in pairs:
        if asst_msg is None:
            continue
        u_text = user_msg.content_text.strip()
        a_text = asst_msg.content_text.strip()
        if not _is_conversational(u_text, a_text):
            continue
        if _has_signal(u_text) or _has_signal(a_text):
            key_exchanges.append(KeyExchange(
                user_text=_truncate(u_text, 160),
                assistant_text=_truncate(a_text, 200),
            ))

    # Tail exchanges: last tail_n conversational pairs
    conv_pairs = [
        (u, a) for u, a in pairs
        if a is not None and _is_conversational(u.content_text.strip(), a.content_text.strip())
    ]
    tail_pairs = conv_pairs[-tail_n:] if len(conv_pairs) >= tail_n else conv_pairs
    tail_exchanges: list[KeyExchange] = []
    for user_msg, asst_msg in tail_pairs:
        tail_exchanges.append(KeyExchange(
            user_text=_truncate(user_msg.content_text.strip(), 160),
            assistant_text=_truncate(asst_msg.content_text.strip(), 200),
        ))

    # Cap key exchanges
    key_exchanges = key_exchanges[:max_key]

    # Deduplicate: remove tail entries already in key_exchanges
    key_set = {(e.user_text, e.assistant_text) for e in key_exchanges}
    tail_unique = [e for e in tail_exchanges if (e.user_text, e.assistant_text) not in key_set]

    # Metadata
    date_str = session.first_timestamp.strftime("%Y-%m-%d") if session.first_timestamp else "unknown"
    duration = session.duration_seconds / 60 if session.duration_seconds else None
    msg_count = len([m for m in session.messages if m.msg_type in ("user", "assistant")])

    return DigestEntry(
        session_id=session.meta.session_id,
        date=date_str,
        project=session.cwd or session.meta.project_name,
        duration_min=duration,
        message_count=msg_count,
        topic=topic,
        key_exchanges=tuple(key_exchanges),
        tail_exchanges=tuple(tail_unique),
    )


# ─── Markdown renderer ────────────────────────────────────────────────────────

def render_markdown(entry: DigestEntry) -> str:
    """Render a DigestEntry as a decisions.md-compatible markdown block."""
    lines: list[str] = []

    duration_str = f"{entry.duration_min:.0f}min" if entry.duration_min else "?"
    lines.append(f"### {entry.date} · `{entry.project}` · {duration_str} · {entry.message_count} msgs")
    lines.append(f"<!-- session: {entry.session_id[:16]} -->")
    lines.append("")

    if entry.topic:
        lines.append(f"**话题**: {entry.topic}")
        lines.append("")

    if entry.key_exchanges:
        lines.append("**关键决策**:")
        lines.append("")
        for ex in entry.key_exchanges:
            lines.append(f"- **Q**: {ex.user_text}")
            lines.append(f"  **A**: {ex.assistant_text}")
            lines.append("")

    if entry.tail_exchanges:
        lines.append("**结尾上下文**:")
        lines.append("")
        for ex in entry.tail_exchanges:
            lines.append(f"> 👤 {ex.user_text}")
            lines.append(f"> 🤖 {ex.assistant_text}")
            lines.append("")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)
