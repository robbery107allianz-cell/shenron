"""Integration tests for CLI commands via Typer test runner."""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from shenron.cli import app
from shenron.discovery import discover_sessions

runner = CliRunner()


def _mock_discover(sample_projects_dir: Path):
    """Return a patched _discover_sessions that always uses fixture dir."""
    def _inner(*args, **kwargs):
        kwargs["projects_dir"] = sample_projects_dir  # always override
        return discover_sessions(*args, **kwargs)
    return _inner


# ─── list ─────────────────────────────────────────────────────────────────────

class TestListCommand:
    def test_list_runs(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["list"])
        assert result.exit_code == 0

    def test_list_shows_session_id(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["list"])
        # ID column may be truncated in narrow terminal; check for at least 4 chars
        assert "aaaa" in result.output

    def test_list_no_sessions(self, tmp_path: Path):
        empty_dir = tmp_path / "empty"
        with patch("shenron.cli._discover_sessions", _mock_discover(empty_dir)):
            result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No sessions" in result.output

    def test_list_sort_tokens(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["list", "--sort", "tokens"])
        assert result.exit_code == 0

    def test_list_sort_messages(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["list", "--sort", "messages"])
        assert result.exit_code == 0


# ─── show ─────────────────────────────────────────────────────────────────────

class TestShowCommand:
    def test_show_valid_session(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["show", "aaaaaaaa"])
        assert result.exit_code == 0

    def test_show_not_found(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["show", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_show_raw(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["show", "aaaaaaaa", "--raw"])
        assert result.exit_code == 0
        assert "queue-operation" in result.output

    def test_show_with_thinking_flag(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["show", "aaaaaaaa", "--thinking"])
        assert result.exit_code == 0

    def test_show_with_limit(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["show", "aaaaaaaa", "--limit", "2"])
        assert result.exit_code == 0


# ─── info ─────────────────────────────────────────────────────────────────────

class TestInfoCommand:
    def test_info_runs(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["info"])
        assert result.exit_code == 0
        assert "Sessions" in result.output

    def test_info_shows_disk(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["info"])
        assert "Disk" in result.output

    def test_info_no_sessions(self, tmp_path: Path):
        empty_dir = tmp_path / "empty"
        with patch("shenron.cli._discover_sessions", _mock_discover(empty_dir)):
            result = runner.invoke(app, ["info"])
        assert result.exit_code == 0
        assert "No sessions" in result.output


# ─── search ───────────────────────────────────────────────────────────────────

class TestSearchCommand:
    def test_search_finds_match(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["search", "kaioshin"])
        assert result.exit_code == 0
        assert "kaioshin" in result.output.lower()

    def test_search_no_match(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["search", "zzz_nobody_zzz"])
        assert result.exit_code == 0
        assert "No results" in result.output

    def test_search_regex(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["search", r"kaio\w+", "--regex"])
        assert result.exit_code == 0
        assert "kaioshin" in result.output.lower()

    def test_search_user_only(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["search", "kaioshin", "--type", "user"])
        assert result.exit_code == 0

    def test_search_assistant_only(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["search", "kaioshin", "--type", "assistant"])
        assert result.exit_code == 0

    def test_search_no_sessions(self, tmp_path: Path):
        empty_dir = tmp_path / "empty"
        with patch("shenron.cli._discover_sessions", _mock_discover(empty_dir)):
            result = runner.invoke(app, ["search", "kaioshin"])
        assert result.exit_code == 0
        assert "No sessions" in result.output

    def test_search_with_limit(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["search", "kaioshin", "--limit", "1"])
        assert result.exit_code == 0

    def test_search_case_sensitive(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["search", "KAIOSHIN", "--case-sensitive"])
        assert result.exit_code == 0
        assert "No results" in result.output


# ─── resume ───────────────────────────────────────────────────────────────────

class TestResumeCommand:
    def test_resume_latest(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["resume"])
        assert result.exit_code == 0
        assert "aaaaaaaa" in result.output

    def test_resume_by_prefix(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["resume", "aaaaaaaa"])
        assert result.exit_code == 0
        assert "aaaaaaaa" in result.output

    def test_resume_not_found(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["resume", "nonexistent"])
        assert result.exit_code == 1

    def test_resume_no_sessions(self, tmp_path: Path):
        empty_dir = tmp_path / "empty"
        with patch("shenron.cli._discover_sessions", _mock_discover(empty_dir)):
            result = runner.invoke(app, ["resume"])
        assert result.exit_code == 1


# ─── stats ────────────────────────────────────────────────────────────────────

class TestStatsCommand:
    def test_stats_runs(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "Cost" in result.output

    def test_stats_by_model(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["stats", "--by", "model"])
        assert result.exit_code == 0

    def test_stats_by_date(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["stats", "--by", "date"])
        assert result.exit_code == 0

    def test_stats_invalid_group_by(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["stats", "--by", "invalid"])
        assert result.exit_code == 1

    def test_stats_no_sessions(self, tmp_path: Path):
        empty_dir = tmp_path / "empty"
        with patch("shenron.cli._discover_sessions", _mock_discover(empty_dir)):
            result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "No sessions" in result.output

    def test_stats_shows_multiplier(self, sample_projects_dir: Path):
        with patch("shenron.cli._discover_sessions", _mock_discover(sample_projects_dir)):
            result = runner.invoke(app, ["stats"])
        assert "x value" in result.output


# ─── version ──────────────────────────────────────────────────────────────────

class TestVersion:
    def test_version_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "shenron" in result.output
