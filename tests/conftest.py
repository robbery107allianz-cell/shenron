"""Shared pytest fixtures for Shenron tests."""

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_SESSION_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
SAMPLE_PROJECT_DIR = "-Users-test-myproject"


@pytest.fixture
def sample_jsonl() -> Path:
    """Path to sample session JSONL fixture."""
    return FIXTURES_DIR / "sample_session.jsonl"


@pytest.fixture
def sample_projects_dir(tmp_path: Path, sample_jsonl: Path) -> Path:
    """
    Temporary projects directory with one sample session.
    Mirrors the real ~/.claude/projects/ structure.
    """
    project_dir = tmp_path / SAMPLE_PROJECT_DIR
    project_dir.mkdir()
    dest = project_dir / f"{SAMPLE_SESSION_ID}.jsonl"
    dest.write_bytes(sample_jsonl.read_bytes())
    return tmp_path
