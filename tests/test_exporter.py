"""Tests for exporter.py — Markdown, JSON, HTML export."""

import json
from pathlib import Path

import pytest

from shenron.discovery import discover_sessions
from shenron.exporter import export_session, to_html, to_json, to_markdown
from shenron.parser import parse_session


@pytest.fixture
def session(sample_projects_dir: Path):
    meta = list(discover_sessions(projects_dir=sample_projects_dir))[0]
    return parse_session(meta)


# ─── Markdown ─────────────────────────────────────────────────────────────────

class TestToMarkdown:
    def test_returns_string(self, session):
        result = to_markdown(session)
        assert isinstance(result, str)

    def test_contains_session_id(self, session):
        result = to_markdown(session)
        assert session.meta.session_id in result

    def test_contains_user_header(self, session):
        result = to_markdown(session)
        assert "You" in result

    def test_contains_model_header(self, session):
        result = to_markdown(session)
        assert "claude-sonnet-4-6" in result

    def test_contains_user_text(self, session):
        result = to_markdown(session)
        assert "kaioshin" in result

    def test_contains_token_info(self, session):
        result = to_markdown(session)
        assert "in" in result and "out" in result

    def test_contains_cost(self, session):
        result = to_markdown(session)
        assert "$" in result

    def test_contains_table(self, session):
        result = to_markdown(session)
        assert "| Field |" in result

    def test_tool_names_included(self, session):
        result = to_markdown(session)
        assert "Grep" in result


# ─── JSON ─────────────────────────────────────────────────────────────────────

class TestToJson:
    def test_returns_valid_json(self, session):
        result = to_json(session)
        doc = json.loads(result)
        assert isinstance(doc, dict)

    def test_contains_session_id(self, session):
        doc = json.loads(to_json(session))
        assert doc["session_id"] == session.meta.session_id

    def test_contains_messages(self, session):
        doc = json.loads(to_json(session))
        assert "messages" in doc
        assert len(doc["messages"]) > 0

    def test_messages_have_role(self, session):
        doc = json.loads(to_json(session))
        roles = {m["role"] for m in doc["messages"]}
        assert "user" in roles
        assert "assistant" in roles

    def test_messages_have_content(self, session):
        doc = json.loads(to_json(session))
        user_msgs = [m for m in doc["messages"] if m["role"] == "user"]
        assert any("kaioshin" in m["content"] for m in user_msgs)

    def test_assistant_has_usage(self, session):
        doc = json.loads(to_json(session))
        asst_msgs = [m for m in doc["messages"] if m["role"] == "assistant" and "usage" in m]
        assert len(asst_msgs) > 0
        assert "input_tokens" in asst_msgs[0]["usage"]

    def test_contains_models(self, session):
        doc = json.loads(to_json(session))
        assert "claude-sonnet-4-6" in doc["models"]

    def test_tool_names_in_json(self, session):
        doc = json.loads(to_json(session))
        asst_with_tools = [m for m in doc["messages"] if m.get("tools")]
        assert len(asst_with_tools) >= 1
        assert "Grep" in asst_with_tools[0]["tools"]


# ─── HTML ─────────────────────────────────────────────────────────────────────

class TestToHtml:
    def test_returns_string(self, session):
        result = to_html(session)
        assert isinstance(result, str)

    def test_is_valid_html_structure(self, session):
        result = to_html(session)
        assert "<!DOCTYPE html>" in result
        assert "<html" in result
        assert "</html>" in result

    def test_contains_session_id(self, session):
        result = to_html(session)
        assert session.meta.session_id[:8] in result

    def test_contains_user_message(self, session):
        result = to_html(session)
        assert "kaioshin" in result

    def test_contains_model_name(self, session):
        result = to_html(session)
        assert "claude-sonnet-4-6" in result

    def test_contains_cost(self, session):
        result = to_html(session)
        assert "$" in result

    def test_has_dark_theme_css(self, session):
        result = to_html(session)
        assert "background" in result
        assert "#0d1117" in result

    def test_escapes_html_in_content(self, session):
        # Ensure no raw < or > from user content bleeds into HTML structure
        result = to_html(session)
        # The HTML body content areas should have properly escaped chars
        assert "<script" not in result


# ─── Dispatch ─────────────────────────────────────────────────────────────────

class TestExportSession:
    def test_markdown_dispatch(self, session):
        result = export_session(session, fmt="markdown")
        assert "# Session:" in result

    def test_json_dispatch(self, session):
        result = export_session(session, fmt="json")
        doc = json.loads(result)
        assert "session_id" in doc

    def test_html_dispatch(self, session):
        result = export_session(session, fmt="html")
        assert "<!DOCTYPE html>" in result

    def test_unknown_fmt_falls_back_to_markdown(self, session):
        result = export_session(session, fmt="unknown")
        assert "# Session:" in result


# ─── CLI export command ───────────────────────────────────────────────────────

class TestExportCommand:
    def test_export_markdown(self, sample_projects_dir: Path):
        from unittest.mock import patch
        from typer.testing import CliRunner
        from shenron.cli import app
        from shenron.discovery import discover_sessions as _ds

        def _mock(projects_dir=None, **kw):
            return _ds(projects_dir=sample_projects_dir, **kw)

        runner = CliRunner()
        with patch("shenron.cli._discover_sessions", _mock):
            result = runner.invoke(app, ["export", "aaaaaaaa", "--format", "markdown"])
        assert result.exit_code == 0
        assert "# Session:" in result.output

    def test_export_json(self, sample_projects_dir: Path):
        from unittest.mock import patch
        from typer.testing import CliRunner
        from shenron.cli import app
        from shenron.discovery import discover_sessions as _ds

        def _mock(projects_dir=None, **kw):
            return _ds(projects_dir=sample_projects_dir, **kw)

        runner = CliRunner()
        with patch("shenron.cli._discover_sessions", _mock):
            result = runner.invoke(app, ["export", "aaaaaaaa", "--format", "json"])
        assert result.exit_code == 0
        doc = json.loads(result.output)
        assert "session_id" in doc

    def test_export_html(self, sample_projects_dir: Path):
        from unittest.mock import patch
        from typer.testing import CliRunner
        from shenron.cli import app
        from shenron.discovery import discover_sessions as _ds

        def _mock(projects_dir=None, **kw):
            return _ds(projects_dir=sample_projects_dir, **kw)

        runner = CliRunner()
        with patch("shenron.cli._discover_sessions", _mock):
            result = runner.invoke(app, ["export", "aaaaaaaa", "--format", "html"])
        assert result.exit_code == 0
        assert "<!DOCTYPE html>" in result.output

    def test_export_invalid_format(self, sample_projects_dir: Path):
        from unittest.mock import patch
        from typer.testing import CliRunner
        from shenron.cli import app
        from shenron.discovery import discover_sessions as _ds

        def _mock(projects_dir=None, **kw):
            return _ds(projects_dir=sample_projects_dir, **kw)

        runner = CliRunner()
        with patch("shenron.cli._discover_sessions", _mock):
            result = runner.invoke(app, ["export", "aaaaaaaa", "--format", "pdf"])
        assert result.exit_code == 1

    def test_export_not_found(self, sample_projects_dir: Path):
        from unittest.mock import patch
        from typer.testing import CliRunner
        from shenron.cli import app
        from shenron.discovery import discover_sessions as _ds

        def _mock(projects_dir=None, **kw):
            return _ds(projects_dir=sample_projects_dir, **kw)

        runner = CliRunner()
        with patch("shenron.cli._discover_sessions", _mock):
            result = runner.invoke(app, ["export", "nonexistent"])
        assert result.exit_code == 1

    def test_export_to_file(self, sample_projects_dir: Path, tmp_path: Path):
        from unittest.mock import patch
        from typer.testing import CliRunner
        from shenron.cli import app
        from shenron.discovery import discover_sessions as _ds

        def _mock(projects_dir=None, **kw):
            return _ds(projects_dir=sample_projects_dir, **kw)

        out_file = tmp_path / "export.md"
        runner = CliRunner()
        with patch("shenron.cli._discover_sessions", _mock):
            result = runner.invoke(app, ["export", "aaaaaaaa", "-o", str(out_file)])
        assert result.exit_code == 0
        assert out_file.exists()
        assert "# Session:" in out_file.read_text()
