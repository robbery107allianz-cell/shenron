"""Fast grep pre-filter via ripgrep — narrows session files before Python parsing."""

import shutil
import subprocess
from pathlib import Path

from shenron.config import PROJECTS_DIR


def _find_rg() -> str | None:
    """Find ripgrep binary, return None if not installed."""
    return shutil.which("rg")


def grep_file_filter(
    pattern: str,
    projects_dir: Path = PROJECTS_DIR,
    case_insensitive: bool = True,
    fixed_strings: bool = False,
) -> set[Path] | None:
    """
    Use ripgrep to quickly find which JSONL files contain the pattern.

    Returns a set of file paths that matched, or None if rg is unavailable
    (caller should fall back to full Python scan).
    """
    rg = _find_rg()
    if not rg:
        return None

    cmd = [
        rg,
        "--files-with-matches",  # only print file names
        "--glob", "*.jsonl",
        "--no-messages",  # suppress permission errors etc.
    ]

    if case_insensitive:
        cmd.append("--ignore-case")
    if fixed_strings:
        cmd.append("--fixed-strings")

    cmd.append(pattern)
    cmd.append(str(projects_dir))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode not in (0, 1):
        return None  # rg error, fall back to Python

    matched_files: set[Path] = set()
    for line in result.stdout.strip().splitlines():
        if line:
            matched_files.add(Path(line))

    return matched_files
