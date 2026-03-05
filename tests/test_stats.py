"""Tests for pricing.py and stats.py."""

from pathlib import Path

import pytest

from shenron.discovery import discover_sessions
from shenron.pricing import ModelPrice, compute_cost, get_price
from shenron.stats import GroupStats, StatsReport, compute_stats


# ─── Pricing ──────────────────────────────────────────────────────────────────

class TestGetPrice:
    def test_known_model_exact(self):
        price = get_price("claude-sonnet-4-6")
        assert price.input_mtok == 3.00
        assert price.output_mtok == 15.00

    def test_known_model_opus(self):
        price = get_price("claude-opus-4-6")
        assert price.input_mtok == 15.00

    def test_known_model_haiku(self):
        price = get_price("claude-haiku-4-5-20251001")
        assert price.input_mtok == 0.80

    def test_unknown_model_falls_back_to_sonnet(self):
        price = get_price("claude-unknown-9-9")
        sonnet = get_price("claude-sonnet-4-6")
        assert price == sonnet

    def test_none_falls_back_to_sonnet(self):
        price = get_price(None)
        sonnet = get_price("claude-sonnet-4-6")
        assert price == sonnet

    def test_returns_model_price(self):
        assert isinstance(get_price("claude-sonnet-4-6"), ModelPrice)


class TestComputeCost:
    def test_zero_tokens_is_zero_cost(self):
        assert compute_cost("claude-sonnet-4-6") == 0.0

    def test_input_tokens_only(self):
        # 1M input tokens at $3/MTok = $3.00
        cost = compute_cost("claude-sonnet-4-6", input_tokens=1_000_000)
        assert abs(cost - 3.00) < 0.001

    def test_output_tokens_only(self):
        # 1M output tokens at $15/MTok = $15.00
        cost = compute_cost("claude-sonnet-4-6", output_tokens=1_000_000)
        assert abs(cost - 15.00) < 0.001

    def test_cache_write(self):
        # 1M cache write at $3.75/MTok = $3.75
        cost = compute_cost("claude-sonnet-4-6", cache_write_tokens=1_000_000)
        assert abs(cost - 3.75) < 0.001

    def test_cache_read(self):
        # 1M cache read at $0.30/MTok = $0.30
        cost = compute_cost("claude-sonnet-4-6", cache_read_tokens=1_000_000)
        assert abs(cost - 0.30) < 0.001

    def test_opus_is_more_expensive_than_sonnet(self):
        cost_opus = compute_cost("claude-opus-4-6", input_tokens=1_000_000)
        cost_sonnet = compute_cost("claude-sonnet-4-6", input_tokens=1_000_000)
        assert cost_opus > cost_sonnet

    def test_haiku_is_cheapest(self):
        cost_haiku = compute_cost("claude-haiku-4-5", input_tokens=1_000_000)
        cost_sonnet = compute_cost("claude-sonnet-4-6", input_tokens=1_000_000)
        assert cost_haiku < cost_sonnet

    def test_combined_tokens(self):
        cost = compute_cost(
            "claude-sonnet-4-6",
            input_tokens=100_000,
            output_tokens=10_000,
        )
        expected = 100_000 * 3.00 / 1_000_000 + 10_000 * 15.00 / 1_000_000
        assert abs(cost - expected) < 1e-9

    def test_none_model_returns_nonzero_for_tokens(self):
        cost = compute_cost(None, input_tokens=1_000_000)
        assert cost > 0


# ─── Stats ────────────────────────────────────────────────────────────────────

class TestComputeStats:
    def test_returns_stats_report(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        report = compute_stats(sessions)
        assert isinstance(report, StatsReport)

    def test_totals_sessions_count(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        report = compute_stats(sessions)
        assert report.totals.sessions == 1

    def test_totals_has_tokens(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        report = compute_stats(sessions)
        # fixture: input=1500+1800=3300, output=80+40=120
        assert report.totals.input_tokens == 3300
        assert report.totals.output_tokens == 120

    def test_totals_has_cost(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        report = compute_stats(sessions)
        assert report.totals.cost_usd > 0

    def test_group_by_project(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        report = compute_stats(sessions, group_by="project")
        assert report.group_by == "project"
        assert len(report.groups) == 1

    def test_group_by_model(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        report = compute_stats(sessions, group_by="model")
        assert report.group_by == "model"
        assert len(report.groups) == 1
        assert report.groups[0].label == "claude-sonnet-4-6"

    def test_group_by_date(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        report = compute_stats(sessions, group_by="date")
        assert report.group_by == "date"
        assert len(report.groups) == 1
        assert "2026" in report.groups[0].label

    def test_top_n_limits_groups(self, sample_projects_dir: Path, tmp_path: Path):
        import json, uuid
        # Create 3 sessions in 3 different projects
        for i in range(3):
            proj_dir = tmp_path / f"-Users-test-proj{i}"
            proj_dir.mkdir()
            sid = str(uuid.uuid4())
            lines = [
                json.dumps({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": f"hello {i}"}]}, "uuid": f"u{i}", "timestamp": "2026-01-01T00:00:00.000Z"}),
                json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": f"hi {i}"}], "model": "claude-sonnet-4-6", "usage": {"input_tokens": 100 * (i + 1), "output_tokens": 10}}, "uuid": f"a{i}", "timestamp": "2026-01-01T00:01:00.000Z"}),
            ]
            (proj_dir / f"{sid}.jsonl").write_text("\n".join(lines))
        sessions = list(discover_sessions(projects_dir=tmp_path))
        report = compute_stats(sessions, group_by="project", top_n=2)
        assert len(report.groups) == 2

    def test_groups_sorted_by_cost_desc(self, tmp_path: Path):
        import json, uuid
        # Session A: lots of tokens (more expensive)
        # Session B: fewer tokens (cheaper)
        for name, tokens in [("projA", 10000), ("projB", 100)]:
            proj_dir = tmp_path / f"-Users-test-{name}"
            proj_dir.mkdir()
            sid = str(uuid.uuid4())
            lines = [
                json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}], "model": "claude-sonnet-4-6", "usage": {"input_tokens": tokens, "output_tokens": 10}}, "uuid": "a1", "timestamp": "2026-01-01T00:00:00.000Z"}),
            ]
            (proj_dir / f"{sid}.jsonl").write_text("\n".join(lines))
        sessions = list(discover_sessions(projects_dir=tmp_path))
        report = compute_stats(sessions, group_by="project")
        assert report.groups[0].cost_usd >= report.groups[1].cost_usd

    def test_empty_sessions_returns_empty_groups(self, tmp_path: Path):
        sessions = list(discover_sessions(projects_dir=tmp_path / "empty"))
        report = compute_stats(sessions)
        assert report.totals.sessions == 0
        assert report.groups == []


class TestGroupStats:
    def test_total_tokens_property(self):
        g = GroupStats(label="test", input_tokens=1000, output_tokens=200)
        assert g.total_tokens == 1200
