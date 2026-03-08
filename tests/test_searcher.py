"""Tests for searcher.py — keyword and regex search."""

from pathlib import Path

import pytest

from shenron.discovery import discover_sessions
from shenron.searcher import SearchResult, search

from conftest import SAMPLE_PROJECT_DIR, SAMPLE_SESSION_ID


class TestSearch:
    def test_finds_keyword(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        results = list(search(["kaioshin"], sessions))
        assert len(results) == 1
        session_meta, hits = results[0]
        assert session_meta.session_id == SAMPLE_SESSION_ID
        assert len(hits) >= 1

    def test_result_contains_match_text(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        results = list(search(["kaioshin"], sessions))
        _, hits = results[0]
        assert hits[0].match_text.lower() == "kaioshin"

    def test_case_insensitive_by_default(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        results_lower = list(search(["kaioshin"], sessions))
        results_upper = list(search(["KAIOSHIN"], sessions))
        assert len(results_lower) == len(results_upper)

    def test_case_sensitive_no_match(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        # fixture has lowercase "kaioshin"
        results = list(search(["KAIOSHIN"], sessions, case_sensitive=True))
        assert results == []

    def test_case_sensitive_match(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        results = list(search(["kaioshin"], sessions, case_sensitive=True))
        assert len(results) == 1

    def test_regex_mode(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        results = list(search([r"kaio\w+"], sessions, regex=True))
        assert len(results) == 1

    def test_no_match_returns_empty(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        results = list(search(["zzz_nonexistent_zzz"], sessions))
        assert results == []

    def test_limit_respected(self, sample_projects_dir: Path, tmp_path: Path):
        # Create a second session that also has the keyword
        project_dir = tmp_path / SAMPLE_PROJECT_DIR
        import json, uuid
        session2_id = str(uuid.uuid4())
        lines = [
            json.dumps({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "kaioshin again"}]}, "uuid": "u2", "timestamp": "2026-01-02T00:00:00.000Z"}),
            json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "kaioshin found"}], "model": "claude-sonnet-4-6", "usage": {"input_tokens": 100, "output_tokens": 10}}, "uuid": "a2", "timestamp": "2026-01-02T00:01:00.000Z"}),
        ]
        (project_dir / f"{session2_id}.jsonl").write_text("\n".join(lines))
        sessions = list(discover_sessions(projects_dir=tmp_path))
        results = list(search(["kaioshin"], sessions, limit=1))
        total_hits = sum(len(hits) for _, hits in results)
        assert total_hits <= 1

    def test_context_included(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        results = list(search(["kaioshin"], sessions, context_chars=20))
        _, hits = results[0]
        result = hits[0]
        # context_before or context_after should have surrounding text
        assert isinstance(result.context_before, str)
        assert isinstance(result.context_after, str)

    def test_message_type_filter_user_only(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        results = list(search(["kaioshin"], sessions, message_types={"user"}))
        for _, hits in results:
            for hit in hits:
                assert hit.message.msg_type == "user"

    def test_message_type_filter_assistant_only(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        # fixture has "kaioshin" in both user and assistant messages
        results = list(search(["kaioshin"], sessions, message_types={"assistant"}))
        for _, hits in results:
            for hit in hits:
                assert hit.message.msg_type == "assistant"

    def test_search_result_has_session_meta(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        results = list(search(["kaioshin"], sessions))
        _, hits = results[0]
        assert hits[0].session_meta.session_id == SAMPLE_SESSION_ID

    def test_search_result_is_frozen(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        results = list(search(["kaioshin"], sessions))
        _, hits = results[0]
        with pytest.raises((AttributeError, TypeError)):
            hits[0].match_text = "mutated"  # type: ignore[misc]

    def test_yields_per_session(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        # Each yielded tuple should be (SessionMeta, list[SearchResult])
        for meta, hits in search(["kaioshin"], sessions):
            assert hasattr(meta, "session_id")
            assert isinstance(hits, list)
            assert all(isinstance(h, SearchResult) for h in hits)
