"""Search engine — keyword and regex search across Claude Code sessions."""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from shenron.grepper import grep_file_filter
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


def _build_patterns(terms: list[str], regex: bool, case_sensitive: bool) -> list[re.Pattern]:
    """Compile one pattern per search term."""
    flags = 0 if case_sensitive else re.IGNORECASE
    return [
        re.compile(term if regex else re.escape(term), flags)
        for term in terms
    ]


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
    terms: list[str],
    sessions: list[SessionMeta],
    regex: bool = False,
    case_sensitive: bool = False,
    message_types: set[str] | None = None,
    model_filter: str | None = None,
    limit: int = 50,
    context_chars: int = 80,
    projects_dir: Path | None = None,
) -> Iterator[tuple[SessionMeta, list[SearchResult]]]:
    """
    Search across sessions for terms (AND logic), yielding (session_meta, [results]) per session.

    Uses ripgrep as a pre-filter to skip non-matching files (fast path).
    Falls back to full Python scan if rg is unavailable.

    Multiple terms: a message must contain ALL terms to match.
    Results are anchored to the first term's match position for context display.
    Generator — results are yielded as found. Stops after `limit` total matches.
    """
    patterns = _build_patterns(terms, regex, case_sensitive)
    default_types = {"user", "assistant"}
    filter_types = message_types or default_types

    # Infer projects_dir from the first session if not provided
    if projects_dir is None and sessions:
        projects_dir = sessions[0].file_path.parent.parent

    # ── Fast path: use rg to narrow down which files to scan ──
    rg_matched_files: set | None = None
    if not regex and projects_dir is not None:
        rg_matched_files = grep_file_filter(
            pattern=terms[0],
            projects_dir=projects_dir,
            case_insensitive=not case_sensitive,
            fixed_strings=True,
        )

    total_matches = 0

    for meta in sessions:
        if total_matches >= limit:
            break

        # Skip files that rg already confirmed don't contain the pattern
        if rg_matched_files is not None and meta.file_path not in rg_matched_files:
            continue

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

            # AND logic: all patterns must match somewhere in the text
            if not all(p.search(text) for p in patterns):
                continue

            # One match per message — take the first hit for context display
            first_match = patterns[0].search(text)
            if first_match:
                before, matched, after = _extract_context(text, first_match, context_chars)
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

        if session_results:
            yield meta, session_results
