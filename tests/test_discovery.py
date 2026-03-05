"""Tests for discovery.py — session file discovery."""

from pathlib import Path

import pytest

from shenron.discovery import discover_sessions, project_dir_to_name
from shenron.models import SessionMeta

from conftest import SAMPLE_PROJECT_DIR, SAMPLE_SESSION_ID


class TestProjectDirToName:
    def test_standard_path(self):
        # Heuristic: all dashes become slashes (known limitation for hyphenated dir names)
        result = project_dir_to_name("-Users-titans-Desktop-crypto-bots-framework")
        assert result.startswith("~/Desktop/")
        assert "framework" in result

    def test_home_root(self):
        result = project_dir_to_name("-Users-titans")
        assert result == "~/"

    def test_nested_path(self):
        # Heuristic: all dashes become slashes
        result = project_dir_to_name("-Users-titans-1984-10-System")
        assert result.startswith("~/1984/")

    def test_no_users(self):
        result = project_dir_to_name("some-dir")
        assert "/" in result  # Falls back to slash-joined


class TestDiscoverSessions:
    def test_finds_sample_session(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        assert len(sessions) == 1
        session = sessions[0]
        assert isinstance(session, SessionMeta)
        assert session.session_id == SAMPLE_SESSION_ID

    def test_session_has_correct_project(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        assert sessions[0].project_dir == SAMPLE_PROJECT_DIR

    def test_project_filter_match(self, sample_projects_dir: Path):
        sessions = list(
            discover_sessions(projects_dir=sample_projects_dir, project_filter="myproject")
        )
        assert len(sessions) == 1

    def test_project_filter_no_match(self, sample_projects_dir: Path):
        sessions = list(
            discover_sessions(projects_dir=sample_projects_dir, project_filter="nonexistent")
        )
        assert len(sessions) == 0

    def test_nonexistent_dir(self, tmp_path: Path):
        sessions = list(discover_sessions(projects_dir=tmp_path / "ghost"))
        assert sessions == []

    def test_file_size_populated(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        assert sessions[0].file_size > 0

    def test_agent_files_excluded_by_default(self, sample_projects_dir: Path, tmp_path: Path):
        # Add an agent file
        project_dir = sample_projects_dir / SAMPLE_PROJECT_DIR
        agent_file = project_dir / "agent-abc123.jsonl"
        agent_file.write_text("{}")
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        ids = [s.session_id for s in sessions]
        assert "agent-abc123" not in ids

    def test_agent_files_included_when_requested(self, sample_projects_dir: Path):
        project_dir = sample_projects_dir / SAMPLE_PROJECT_DIR
        agent_file = project_dir / "agent-abc123.jsonl"
        agent_file.write_text("{}")
        sessions = list(
            discover_sessions(projects_dir=sample_projects_dir, include_agents=True)
        )
        ids = [s.session_id for s in sessions]
        assert "agent-abc123" in ids
