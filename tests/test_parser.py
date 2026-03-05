"""Tests for parser.py — JSONL streaming parser."""

from pathlib import Path

import pytest

from shenron.models import Session, TokenUsage
from shenron.parser import (
    _extract_text,
    _extract_tool_names,
    _parse_usage,
    parse_session,
    parse_session_meta_fields,
    stream_messages,
)

from conftest import SAMPLE_PROJECT_DIR, SAMPLE_SESSION_ID


class TestExtractText:
    def test_plain_string(self):
        assert _extract_text("hello") == "hello"

    def test_text_block(self):
        content = [{"type": "text", "text": "hello world"}]
        assert _extract_text(content) == "hello world"

    def test_tool_use_block(self):
        content = [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]
        assert _extract_text(content) == "[tool: Bash]"

    def test_thinking_block_excluded(self):
        content = [{"type": "thinking", "thinking": "deep thoughts"}]
        assert _extract_text(content) == ""

    def test_mixed_blocks(self):
        content = [
            {"type": "text", "text": "I will run a command."},
            {"type": "tool_use", "name": "Bash", "input": {}},
        ]
        result = _extract_text(content)
        assert "I will run a command." in result
        assert "[tool: Bash]" in result

    def test_empty_content(self):
        assert _extract_text([]) == ""
        assert _extract_text(None) == ""

    def test_tool_result(self):
        content = [{"type": "tool_result", "tool_use_id": "x", "content": "output here"}]
        assert "output here" in _extract_text(content)


class TestExtractToolNames:
    def test_single_tool(self):
        content = [{"type": "tool_use", "name": "Bash", "input": {}}]
        assert _extract_tool_names(content) == ("Bash",)

    def test_multiple_tools(self):
        content = [
            {"type": "tool_use", "name": "Read", "input": {}},
            {"type": "tool_use", "name": "Write", "input": {}},
        ]
        assert _extract_tool_names(content) == ("Read", "Write")

    def test_no_tools(self):
        content = [{"type": "text", "text": "hello"}]
        assert _extract_tool_names(content) == ()

    def test_string_content(self):
        assert _extract_tool_names("plain string") == ()


class TestParseUsage:
    def test_full_usage(self):
        data = {
            "input_tokens": 1000,
            "output_tokens": 200,
            "cache_creation_input_tokens": 500,
            "cache_read_input_tokens": 100,
        }
        usage = _parse_usage(data)
        assert usage is not None
        assert usage.input_tokens == 1000
        assert usage.output_tokens == 200
        assert usage.cache_creation_input_tokens == 500
        assert usage.cache_read_input_tokens == 100

    def test_partial_usage(self):
        usage = _parse_usage({"input_tokens": 100})
        assert usage is not None
        assert usage.input_tokens == 100
        assert usage.output_tokens == 0

    def test_empty_usage(self):
        assert _parse_usage({}) is None


class TestStreamMessages:
    def test_yields_correct_count(self, sample_jsonl: Path):
        messages = list(stream_messages(sample_jsonl))
        # fixture has 2 user messages + 2 assistant messages = 4 content messages
        assert len(messages) == 4

    def test_message_types(self, sample_jsonl: Path):
        messages = list(stream_messages(sample_jsonl))
        types = [m.msg_type for m in messages]
        assert "user" in types
        assert "assistant" in types

    def test_user_message_text(self, sample_jsonl: Path):
        messages = list(stream_messages(sample_jsonl))
        user_msgs = [m for m in messages if m.msg_type == "user" and m.content_text]
        assert any("kaioshin" in m.content_text for m in user_msgs)

    def test_assistant_has_model(self, sample_jsonl: Path):
        messages = list(stream_messages(sample_jsonl))
        asst_msgs = [m for m in messages if m.msg_type == "assistant"]
        assert all(m.model == "claude-sonnet-4-6" for m in asst_msgs)

    def test_assistant_has_usage(self, sample_jsonl: Path):
        messages = list(stream_messages(sample_jsonl))
        asst_msgs = [m for m in messages if m.msg_type == "assistant"]
        assert all(m.usage is not None for m in asst_msgs)

    def test_tool_names_captured(self, sample_jsonl: Path):
        messages = list(stream_messages(sample_jsonl))
        asst_with_tools = [m for m in messages if m.tool_names]
        assert len(asst_with_tools) >= 1
        assert "Grep" in asst_with_tools[0].tool_names

    def test_malformed_line_skipped(self, tmp_path: Path):
        bad_file = tmp_path / "bad.jsonl"
        bad_file.write_text('{"type":"user","message":{"role":"user","content":[{"type":"text","text":"ok"}]},"uuid":"u1","timestamp":"2026-01-01T00:00:00.000Z"}\nNOT JSON\n')
        messages = list(stream_messages(bad_file))
        assert len(messages) == 1

    def test_nonexistent_file(self, tmp_path: Path):
        messages = list(stream_messages(tmp_path / "ghost.jsonl"))
        assert messages == []


class TestParseSessionMetaFields:
    def test_extracts_cwd(self, sample_jsonl: Path):
        fields = parse_session_meta_fields(sample_jsonl)
        assert fields.get("cwd") == "/Users/test/myproject"

    def test_extracts_version(self, sample_jsonl: Path):
        fields = parse_session_meta_fields(sample_jsonl)
        assert fields.get("version") == "2.1.63"

    def test_extracts_git_branch(self, sample_jsonl: Path):
        fields = parse_session_meta_fields(sample_jsonl)
        assert fields.get("git_branch") == "main"

    def test_extracts_model(self, sample_jsonl: Path):
        fields = parse_session_meta_fields(sample_jsonl)
        assert fields.get("model") == "claude-sonnet-4-6"

    def test_extracts_first_timestamp(self, sample_jsonl: Path):
        fields = parse_session_meta_fields(sample_jsonl)
        assert fields.get("first_timestamp") is not None


class TestParseSession:
    def test_returns_session(self, sample_projects_dir: Path):
        from shenron.discovery import discover_sessions

        sessions_meta = list(discover_sessions(projects_dir=sample_projects_dir))
        assert len(sessions_meta) == 1
        session = parse_session(sessions_meta[0])
        assert isinstance(session, Session)

    def test_session_has_messages(self, sample_projects_dir: Path):
        from shenron.discovery import discover_sessions

        meta = list(discover_sessions(projects_dir=sample_projects_dir))[0]
        session = parse_session(meta)
        assert len(session.messages) == 4

    def test_session_total_usage(self, sample_projects_dir: Path):
        from shenron.discovery import discover_sessions

        meta = list(discover_sessions(projects_dir=sample_projects_dir))[0]
        session = parse_session(meta)
        usage = session.total_usage
        # fixture: msg1 input=1500, output=80; msg2 input=1800, output=40
        assert usage.input_tokens == 3300
        assert usage.output_tokens == 120

    def test_session_cwd(self, sample_projects_dir: Path):
        from shenron.discovery import discover_sessions

        meta = list(discover_sessions(projects_dir=sample_projects_dir))[0]
        session = parse_session(meta)
        assert session.cwd == "/Users/test/myproject"

    def test_session_duration(self, sample_projects_dir: Path):
        from shenron.discovery import discover_sessions

        meta = list(discover_sessions(projects_dir=sample_projects_dir))[0]
        session = parse_session(meta)
        assert session.duration_seconds is not None
        assert session.duration_seconds > 0

    def test_session_models_used(self, sample_projects_dir: Path):
        from shenron.discovery import discover_sessions

        meta = list(discover_sessions(projects_dir=sample_projects_dir))[0]
        session = parse_session(meta)
        assert "claude-sonnet-4-6" in session.models_used
