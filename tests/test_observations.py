"""Tests for PostToolUse observation ingestion.

Covers:
- _sanitize_command: token/secret redaction
- discover_observations: JSONL scanning + aggregation
- compile_session: observation field pass-through
- render_daily_md: 工具履历 section rendering
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shenron.discovery import _sanitize_command, discover_observations
from shenron.models import ObservationSummary


# ─── Fixtures ──────────────────────────────────────────────────────────────────

def _write_obs(
    obs_dir: Path,
    date: str,
    session_id: str,
    events: list[dict],
) -> None:
    """Write a fake observations JSONL file."""
    day_dir = obs_dir / date
    day_dir.mkdir(parents=True, exist_ok=True)
    out = day_dir / f"{session_id}.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def _obs_event(
    session_id: str,
    tool_name: str,
    tool_input: dict,
    observed_at: str = "2026-04-17T10:00:00+08:00",
) -> dict:
    return {
        "session_id": session_id,
        "hook_event_name": "PostToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_response": {},  # not used in aggregation
        "observed_at": observed_at,
    }


# ─── _sanitize_command ─────────────────────────────────────────────────────────

class TestSanitizeCommand:
    def test_short_command_unchanged(self):
        assert _sanitize_command("ls /tmp") == "ls /tmp"

    def test_redacts_long_token_arg(self):
        cmd = "curl -H 'Authorization: Bearer sk-ant-abcdefghijklmnopqrstuvwxyz1234567890' https://api.example.com"
        result = _sanitize_command(cmd)
        assert "sk-ant-" not in result
        assert "***" in result

    def test_redacts_long_alphanumeric_string(self):
        # Anything > 20 consecutive alphanumeric chars looks like a secret
        cmd = "git clone https://user:ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcd@github.com/org/repo"
        result = _sanitize_command(cmd)
        assert "ghp_" not in result
        assert "***" in result

    def test_normal_git_command_preserved(self):
        result = _sanitize_command("git commit -m 'fix: update deps'")
        assert result == "git commit -m 'fix: update deps'"

    def test_truncates_very_long_command(self):
        long_cmd = "echo " + "x" * 200
        result = _sanitize_command(long_cmd)
        assert len(result) <= 120

    def test_empty_command(self):
        assert _sanitize_command("") == ""

    def test_npm_build_preserved(self):
        result = _sanitize_command("npm run build --prefix /Users/titans/Desktop/sunbve")
        assert "npm run build" in result


# ─── discover_observations ────────────────────────────────────────────────────

SESSION_A = "aaaaaaaa-1111-2222-3333-444444444444"


class TestDiscoverObservations:
    def test_returns_none_when_no_files(self, tmp_path: Path):
        result = discover_observations(SESSION_A, tmp_path)
        assert result is None

    def test_counts_tools_used(self, tmp_path: Path):
        _write_obs(tmp_path, "2026-04-17", SESSION_A, [
            _obs_event(SESSION_A, "Read", {"file_path": "/a.py"}),
            _obs_event(SESSION_A, "Read", {"file_path": "/b.py"}),
            _obs_event(SESSION_A, "Edit", {"file_path": "/a.py"}),
        ])
        result = discover_observations(SESSION_A, tmp_path)
        assert result is not None
        tools = dict(result.tools_used)
        assert tools["Read"] == 2
        assert tools["Edit"] == 1

    def test_files_touched_deduped(self, tmp_path: Path):
        _write_obs(tmp_path, "2026-04-17", SESSION_A, [
            _obs_event(SESSION_A, "Read", {"file_path": "/a.py"}),
            _obs_event(SESSION_A, "Read", {"file_path": "/a.py"}),  # duplicate
            _obs_event(SESSION_A, "Edit", {"file_path": "/b.md"}),
        ])
        result = discover_observations(SESSION_A, tmp_path)
        assert result is not None
        assert len(result.files_touched) == 2
        assert "/a.py" in result.files_touched
        assert "/b.md" in result.files_touched

    def test_commands_run_deduped(self, tmp_path: Path):
        _write_obs(tmp_path, "2026-04-17", SESSION_A, [
            _obs_event(SESSION_A, "Bash", {"command": "git status", "description": ""}),
            _obs_event(SESSION_A, "Bash", {"command": "git status", "description": ""}),  # dup
            _obs_event(SESSION_A, "Bash", {"command": "npm install", "description": ""}),
        ])
        result = discover_observations(SESSION_A, tmp_path)
        assert result is not None
        assert len(result.commands_run) == 2

    def test_web_fetched_collected(self, tmp_path: Path):
        _write_obs(tmp_path, "2026-04-17", SESSION_A, [
            _obs_event(SESSION_A, "WebSearch", {"query": "cloudflare workers tutorial"}),
            _obs_event(SESSION_A, "WebFetch", {"url": "https://docs.cloudflare.com/workers/"}),
        ])
        result = discover_observations(SESSION_A, tmp_path)
        assert result is not None
        assert "cloudflare workers tutorial" in result.web_fetched
        assert "https://docs.cloudflare.com/workers/" in result.web_fetched

    def test_scans_multiple_date_dirs(self, tmp_path: Path):
        """Session spans two calendar days (rare but possible)."""
        _write_obs(tmp_path, "2026-04-17", SESSION_A, [
            _obs_event(SESSION_A, "Read", {"file_path": "/a.py"}),
        ])
        _write_obs(tmp_path, "2026-04-18", SESSION_A, [
            _obs_event(SESSION_A, "Edit", {"file_path": "/b.py"}),
        ])
        result = discover_observations(SESSION_A, tmp_path)
        assert result is not None
        tools = dict(result.tools_used)
        assert tools["Read"] == 1
        assert tools["Edit"] == 1

    def test_ignores_other_sessions(self, tmp_path: Path):
        OTHER = "bbbbbbbb-1111-2222-3333-444444444444"
        _write_obs(tmp_path, "2026-04-17", SESSION_A, [
            _obs_event(SESSION_A, "Read", {"file_path": "/a.py"}),
        ])
        _write_obs(tmp_path, "2026-04-17", OTHER, [
            _obs_event(OTHER, "Bash", {"command": "rm -rf /", "description": ""}),
        ])
        result = discover_observations(SESSION_A, tmp_path)
        assert result is not None
        tools = dict(result.tools_used)
        assert "Bash" not in tools  # OTHER session's Bash not included

    def test_returns_immutable_summary(self, tmp_path: Path):
        _write_obs(tmp_path, "2026-04-17", SESSION_A, [
            _obs_event(SESSION_A, "Read", {"file_path": "/a.py"}),
        ])
        result = discover_observations(SESSION_A, tmp_path)
        assert result is not None
        with pytest.raises((AttributeError, TypeError)):
            result.tools_used = ()  # type: ignore[misc]

    def test_skips_malformed_json_lines(self, tmp_path: Path):
        """Partial writes or corruption should be silently skipped."""
        day_dir = tmp_path / "2026-04-17"
        day_dir.mkdir(parents=True)
        out = day_dir / f"{SESSION_A}.jsonl"
        out.write_text(
            json.dumps(_obs_event(SESSION_A, "Read", {"file_path": "/a.py"})) + "\n"
            "{ this is not valid json \n"
            + json.dumps(_obs_event(SESSION_A, "Edit", {"file_path": "/b.py"})) + "\n",
            encoding="utf-8",
        )
        result = discover_observations(SESSION_A, tmp_path)
        assert result is not None
        tools = dict(result.tools_used)
        assert tools["Read"] == 1
        assert tools["Edit"] == 1

    def test_tools_used_sorted_by_count_desc(self, tmp_path: Path):
        _write_obs(tmp_path, "2026-04-17", SESSION_A, [
            _obs_event(SESSION_A, "Bash", {"command": "ls", "description": ""}),
            _obs_event(SESSION_A, "Read", {"file_path": "/a.py"}),
            _obs_event(SESSION_A, "Read", {"file_path": "/b.py"}),
            _obs_event(SESSION_A, "Read", {"file_path": "/c.py"}),
        ])
        result = discover_observations(SESSION_A, tmp_path)
        assert result is not None
        # Most used tool should be first
        assert result.tools_used[0][0] == "Read"
        assert result.tools_used[0][1] == 3


# ─── ObservationSummary model ────────────────────────────────────────────────

class TestObservationSummary:
    def test_can_construct(self):
        obs = ObservationSummary(
            tools_used=(("Read", 5), ("Bash", 3)),
            files_touched=("/a.py", "/b.md"),
            commands_run=("git status",),
            web_fetched=("https://example.com",),
        )
        assert obs.tools_used[0] == ("Read", 5)

    def test_is_frozen(self):
        obs = ObservationSummary(
            tools_used=(("Read", 1),),
            files_touched=(),
            commands_run=(),
            web_fetched=(),
        )
        with pytest.raises((AttributeError, TypeError)):
            obs.files_touched = ("/new.py",)  # type: ignore[misc]


# ─── compile_session with observations ───────────────────────────────────────

class TestCompileSessionWithObservations:
    def test_observation_field_stored(self):
        """compile_session should store the observation when provided."""
        from shenron.compiler import compile_session
        from shenron.discovery import discover_sessions
        from shenron.parser import parse_session

        from conftest import FIXTURES_DIR, SAMPLE_PROJECT_DIR, SAMPLE_SESSION_ID

        tmp = Path(__file__).parent / "fixtures"
        # Use the sample session fixture
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            proj_dir = Path(td) / SAMPLE_PROJECT_DIR
            proj_dir.mkdir()
            import shutil
            shutil.copy(
                FIXTURES_DIR / "sample_session.jsonl",
                proj_dir / f"{SAMPLE_SESSION_ID}.jsonl",
            )
            sessions = list(discover_sessions(projects_dir=Path(td)))
            parsed = parse_session(sessions[0])

        obs = ObservationSummary(
            tools_used=(("Read", 5), ("Bash", 2)),
            files_touched=("/tmp/a.py",),
            commands_run=("git status",),
            web_fetched=(),
        )
        compiled = compile_session(parsed, observation=obs)
        assert compiled.observation is obs

    def test_observation_none_by_default(self):
        """compile_session without observation param → None."""
        from shenron.compiler import compile_session
        from shenron.discovery import discover_sessions
        from shenron.parser import parse_session

        from conftest import FIXTURES_DIR, SAMPLE_PROJECT_DIR, SAMPLE_SESSION_ID

        import tempfile, shutil
        with tempfile.TemporaryDirectory() as td:
            proj_dir = Path(td) / SAMPLE_PROJECT_DIR
            proj_dir.mkdir()
            shutil.copy(
                FIXTURES_DIR / "sample_session.jsonl",
                proj_dir / f"{SAMPLE_SESSION_ID}.jsonl",
            )
            sessions = list(discover_sessions(projects_dir=Path(td)))
            parsed = parse_session(sessions[0])

        compiled = compile_session(parsed)
        assert compiled.observation is None


# ─── render_daily_md with 工具履历 ────────────────────────────────────────────

class TestRenderDailyMdWithObservations:
    def _make_digest(self, tool_summary: "ObservationSummary | None" = None):
        from shenron.compiler import DailyDigest
        return DailyDigest(
            date="2026-04-17",
            session_count=2,
            session_ids=("aaa", "bbb"),
            total_user_messages=20,
            total_assistant_messages=18,
            total_cost=5.0,
            weight="dev",
            weight_value=2,
            entities=("SUNBVE",),
            key_points=("做了 SEO 优化",),
            file_changes=(),
            tags=("sunbve",),
            models=("claude-sonnet-4-6",),
            tool_summary=tool_summary,
        )

    def test_no_tool_summary_no_section(self):
        from shenron.compiler import render_daily_md
        dd = self._make_digest(tool_summary=None)
        md = render_daily_md(dd)
        assert "工具履历" not in md

    def test_tool_summary_renders_section(self):
        from shenron.compiler import render_daily_md
        obs = ObservationSummary(
            tools_used=(("Read", 8), ("Bash", 3)),
            files_touched=("/Users/titans/Desktop/sunbve/src/main.py",),
            commands_run=("git commit",),
            web_fetched=("https://docs.aws.com",),
        )
        dd = self._make_digest(tool_summary=obs)
        md = render_daily_md(dd)
        assert "工具履历" in md
        assert "Read" in md
        assert "Bash" in md

    def test_files_touched_uses_tilde(self):
        from shenron.compiler import render_daily_md
        obs = ObservationSummary(
            tools_used=(("Edit", 1),),
            files_touched=("/Users/titans/Desktop/sunbve/src/main.py",),
            commands_run=(),
            web_fetched=(),
        )
        dd = self._make_digest(tool_summary=obs)
        md = render_daily_md(dd)
        assert "~/Desktop/sunbve/src/main.py" in md

    def test_commands_shown(self):
        from shenron.compiler import render_daily_md
        obs = ObservationSummary(
            tools_used=(("Bash", 2),),
            files_touched=(),
            commands_run=("git status", "npm run build"),
            web_fetched=(),
        )
        dd = self._make_digest(tool_summary=obs)
        md = render_daily_md(dd)
        assert "git status" in md
        assert "npm run build" in md

    def test_web_fetched_shown(self):
        from shenron.compiler import render_daily_md
        obs = ObservationSummary(
            tools_used=(("WebSearch", 1),),
            files_touched=(),
            commands_run=(),
            web_fetched=("cloudflare workers docs",),
        )
        dd = self._make_digest(tool_summary=obs)
        md = render_daily_md(dd)
        assert "cloudflare workers docs" in md
