"""Search engine — keyword and regex search across Claude Code sessions."""

import re
from collections.abc import Iterator
from dataclasses import dataclass

from shenron.models import Message, SessionMeta
from shenron.parser import stream_messages


@dataclass(frozen=True)
class SearchResult:
    """A single match within a session."""

    session_meta: SessionMeta
    message: Message
    context_before: str   # text before the match
    match_text: str       # the matched portion
    context_after: str    # text after the match


def _build_pattern(query: str, regex: bool, case_sensitive: bool) -> re.Pattern:
    """Compile search pattern."""
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = query if regex else re.escape(query)
    return re.compile(pattern, flags)


def _extract_context(text: str, match: re.Match, context_chars: int) -> tuple[str, str, str]:
    """Return (before, matched, after) with context_chars on each side."""
    start, end = match.start(), match.end()
    before = text[max(0, start - context_chars) : start]
    matched = text[start:end]
    after = text[end : end + context_chars]

    # Trim to word boundaries for cleaner output
    if start - context_chars > 0 and before:
        before = "…" + before.lstrip()
    if end + context_chars < len(text) and after:
        after = after.rstrip() + "…"

    return before, matched, after


def search(
    query: str,
    sessions: list[SessionMeta],
    regex: bool = False,
    case_sensitive: bool = False,
    message_types: set[str] | None = None,
    model_filter: str | None = None,
    limit: int = 50,
    context_chars: int = 80,
) -> Iterator[tuple[SessionMeta, list[SearchResult]]]:
    """
    Search across sessions for query, yielding (session_meta, [results]) per session.

    Generator — results are yielded as found, no need to wait for full scan.
    Stops after `limit` total matches.
    """
    pattern = _build_pattern(query, regex, case_sensitive)
    default_types = {"user", "assistant"}
    filter_types = message_types or default_types

    total_matches = 0

    for meta in sessions:
        if total_matches >= limit:
            break

        session_results: list[SearchResult] = []

        for msg in stream_messages(meta.file_path):
            if total_matches >= limit:
                break

            # Filter by message type
            if msg.msg_type not in filter_types:
                continue

            # Filter by model
            if model_filter and msg.model and model_filter.lower() not in msg.model.lower():
                continue

            text = msg.content_text
            if not text:
                continue

            for match in pattern.finditer(text):
                before, matched, after = _extract_context(text, match, context_chars)
                session_results.append(
                    SearchResult(
                        session_meta=meta,
                        message=msg,
                        context_before=before,
                        match_text=matched,
                        context_after=after,
                    )
                )
                total_matches += 1
                if total_matches >= limit:
                    break

        if session_results:
            yield meta, session_results
