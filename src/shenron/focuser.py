"""
Focus analyzer — extract keyword frequency from recent sessions.

Analyzes user messages (what Rob types) to surface hot topics.
Outputs a focus.md showing current attention distribution.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from shenron.models import SessionMeta
from shenron.parser import stream_messages

# ─── Stop words ───────────────────────────────────────────────────────────────

_STOP_ZH_CHARS = set("的了是在我他你这那和也就都而及与着被地得到说要会没有人上下来去对不")

_STOP_ZH_WORDS = {
    "这个", "那个", "一个", "没有", "可以", "什么", "我们", "你们", "他们",
    "因为", "所以", "但是", "如果", "已经", "现在", "时候", "东西", "一下",
    "还是", "还有", "然后", "不是", "就是", "这样", "那样", "一些", "感觉",
    "觉得", "知道", "一起", "所有", "应该", "需要", "这里", "那里", "使用",
    "进行", "通过", "可能", "问题", "方式", "内容", "工作", "发现", "看看",
    "一直", "一个", "两个", "继续", "开始", "完成", "更新", "添加", "设置",
    "文件", "目录", "命令", "运行", "执行", "输出", "输入", "结果", "当前",
}

_STOP_EN = {
    "the", "and", "for", "are", "but", "not", "you", "all", "can",
    "was", "one", "our", "out", "get", "has", "him", "his", "how",
    "its", "new", "now", "she", "use", "way", "who", "did", "let",
    "say", "too", "via", "yes", "yet", "your", "with", "this", "that",
    "they", "have", "from", "been", "will", "more", "when", "than",
    "then", "some", "what", "into", "just", "like", "time", "know",
    "also", "make", "here", "each", "most", "need", "such", "well",
    "file", "files", "line", "path", "text", "true", "false", "none",
    "null", "run", "see", "set", "add", "got", "non", "would", "could",
    "should", "there", "about", "which", "after", "before", "where",
    "these", "those", "their", "them", "were", "had", "does", "doing",
    "done", "every", "only", "will", "been",
    # path noise
    "users", "titans", "home", "local", "library", "desktop", "bots",
    # tool output noise
    "successfully", "updated", "created", "output", "found", "showing",
    "results", "matches", "session", "sessions", "error", "failed",
    "warning", "total", "lines", "bytes", "size",
}


# ─── Token extraction ─────────────────────────────────────────────────────────

def _extract_tokens(text: str) -> list[str]:
    """Extract meaningful tokens from mixed Chinese/English text."""
    tokens: list[str] = []

    # English: words 4+ chars, not in stop list
    for word in re.findall(r'\b[a-zA-Z]{4,}\b', text):
        w = word.lower()
        if w not in _STOP_EN:
            tokens.append(w)

    # Chinese: extract sequences of 2-6 non-stop characters
    # Split on stop chars and punctuation to get natural chunks
    zh_chunks = re.findall(r'[\u4e00-\u9fff]{2,8}', text)
    for chunk in zh_chunks:
        # Skip if chunk is all stop chars
        clean = ''.join(c for c in chunk if c not in _STOP_ZH_CHARS)
        if len(clean) < 2:
            continue
        # Emit 2-char and 3-char substrings as candidate terms
        for length in (2, 3):
            for i in range(len(clean) - length + 1):
                term = clean[i:i + length]
                if term not in _STOP_ZH_WORDS and len(term) >= 2:
                    tokens.append(term)

    return tokens


# ─── Analysis ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FocusEntry:
    term: str
    count: int
    pct: float     # relative to max count


@dataclass(frozen=True)
class FocusReport:
    generated_at: datetime
    hours_window: int
    sessions_scanned: int
    messages_scanned: int
    top_terms: tuple[FocusEntry, ...]


def analyze(
    sessions: list[SessionMeta],
    hours: int = 24,
    top_n: int = 20,
    user_only: bool = True,
) -> FocusReport:
    """
    Scan recent sessions and count keyword frequency.

    user_only=True: only analyze what Rob typed (signal of his attention).
    """
    cutoff = datetime.now(tz=UTC) - timedelta(hours=hours)
    recent = [s for s in sessions if s.modified_time >= cutoff]

    counter: Counter[str] = Counter()
    messages_scanned = 0

    for meta in recent:
        for msg in stream_messages(meta.file_path):
            if user_only and msg.msg_type != "user":
                continue
            if not user_only and msg.msg_type not in ("user", "assistant"):
                continue

            text = msg.content_text
            if not text or len(text) < 5:
                continue

            # Skip tool results and system noise masquerading as user messages
            _noise_prefixes = (
                "<local-command", "<system-reminder", "<task-notification",
                "Updated task", "The file", "File created", "Found ",
                "No files", "Showing ", "Tool loaded", "Usage: ",
                "/Users/", "~/", "---", "```",
            )
            if any(text.startswith(p) for p in _noise_prefixes):
                continue
            # Skip messages that are mostly paths/code (high slash density)
            slash_ratio = text.count("/") / max(len(text), 1)
            if slash_ratio > 0.05:
                continue

            tokens = _extract_tokens(text)
            counter.update(tokens)
            messages_scanned += 1

    max_count = counter.most_common(1)[0][1] if counter else 1
    top = [
        FocusEntry(term=term, count=count, pct=count / max_count)
        for term, count in counter.most_common(top_n)
    ]

    return FocusReport(
        generated_at=datetime.now(tz=UTC),
        hours_window=hours,
        sessions_scanned=len(recent),
        messages_scanned=messages_scanned,
        top_terms=tuple(top),
    )


# ─── Renderer ─────────────────────────────────────────────────────────────────

_BAR_FULL = "█"
_BAR_WIDTH = 16


def _bar(pct: float) -> str:
    filled = round(pct * _BAR_WIDTH)
    return _BAR_FULL * filled + "░" * (_BAR_WIDTH - filled)


def render_markdown(report: FocusReport) -> str:
    ts = report.generated_at.strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"## 当前聚焦 · Focus Weights",
        f"> 更新: {ts} · 扫描窗口: {report.hours_window}h · "
        f"{report.sessions_scanned} sessions · {report.messages_scanned} 条消息",
        "",
        "| # | 关键词 | 频率 | 次数 |",
        "|---|--------|------|------|",
    ]

    for i, entry in enumerate(report.top_terms, 1):
        bar = _bar(entry.pct)
        lines.append(f"| {i:2d} | {entry.term} | {bar} | {entry.count} |")

    lines.append("")
    return "\n".join(lines)
