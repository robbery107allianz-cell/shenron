"""Tests for compiler.py — session compilation, concept tracking, and wiki output."""

import re
from pathlib import Path

import pytest

from shenron.compiler import (
    CompiledSession,
    ConceptNode,
    DailyDigest,
    FileChange,
    _compute_weight,
    _extract_entities,
    _generate_tag,
    build_concept_index,
    compile_session,
    merge_by_day,
    render_concept_md,
    render_daily_md,
    render_index_md,
    render_session_md,
    write_wiki,
    _update_concept_frontmatter,
)
from shenron.discovery import discover_sessions
from shenron.parser import parse_session

from conftest import SAMPLE_PROJECT_DIR, SAMPLE_SESSION_ID


# ─── Entity extraction ─────────────────────────────────────────────────────

class TestExtractEntities:
    def test_finds_known_entity(self):
        result = _extract_entities("我们继续四星球的工作")
        assert "四星球" in result

    def test_finds_multiple_entities(self):
        result = _extract_entities("Kaioshin安全审计发现了Obsidian的问题")
        assert "Kaioshin" in result
        assert "Obsidian" in result

    def test_case_insensitive(self):
        result = _extract_entities("let's check SUNBVE ads")
        assert "SUNBVE" in result

    def test_no_false_positive(self):
        result = _extract_entities("今天天气不错")
        assert result == []

    def test_alias_matching(self):
        result = _extract_entities("择名致远小程序上线了")
        assert "命名阁" in result

    def test_hwa_hsia_alias(self):
        result = _extract_entities("华夏宪法的设计理念")
        assert "Hwa Hsia" in result


# ─── Tag generation ─────────────────────────────────────────────────────────

class TestGenerateTag:
    def test_lowercase_with_dash(self):
        assert _generate_tag("Lucky Tea") == "lucky-tea"

    def test_chinese_preserved(self):
        assert _generate_tag("四星球") == "四星球"

    def test_underscore_to_dash(self):
        assert _generate_tag("CS_Fundamentals") == "cs-fundamentals"


# ─── Weight system ──────────────────────────────────────────────────────────

class TestComputeWeight:
    def _make_session(self, user_texts, assistant_texts=None):
        """Build a minimal Session-like object for weight testing."""
        from shenron.models import Message, SessionMeta, TokenUsage

        user_msgs = tuple(
            Message(
                msg_type="user",
                content_text=t,
                timestamp=None,
                model="",
                usage=None,
                tool_names=(),
                uuid=f"u{i}",
            )
            for i, t in enumerate(user_texts)
        )
        asst_msgs = tuple(
            Message(
                msg_type="assistant",
                content_text=t,
                timestamp=None,
                model="claude-opus-4-6",
                usage=TokenUsage(100, 50, 0, 0),
                tool_names=(),
                uuid=f"a{i}",
            )
            for i, t in enumerate(assistant_texts or ["ok"])
        )

        class FakeSession:
            user_messages = user_msgs
            assistant_messages = asst_msgs
            messages = user_msgs + asst_msgs

        return FakeSession()

    def test_ops_short_session(self):
        session = self._make_session(["早检了", "4stars正常"])
        assert _compute_weight(session, 0) == "ops"

    def test_dev_with_code_signals(self):
        session = self._make_session([
            "实现新功能",
            "开发完成了",
            "部署到生产环境",
            "修复了一个bug",
        ])
        assert _compute_weight(session, 3) == "dev"

    def test_strategy_with_research_signals(self):
        session = self._make_session([
            "我们来讨论一下产品化可行性",
            "商业模式需要研究对比一下",
            "这个愿景的路线图应该怎么规划",
        ])
        assert _compute_weight(session, 0) == "strategy"

    def test_strategy_from_philosophy(self):
        session = self._make_session([
            "哲学层面来说，AI的法理身份",
            "文明的围墙这个概念很有意思",
        ])
        assert _compute_weight(session, 0) == "strategy"


# ─── compile_session ────────────────────────────────────────────────────────

class TestCompileSession:
    def test_compiles_fixture_session(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        parsed = parse_session(sessions[0])
        compiled = compile_session(parsed)

        assert isinstance(compiled, CompiledSession)
        assert compiled.session_id == SAMPLE_SESSION_ID[:8]
        assert compiled.user_message_count > 0
        assert compiled.weight in ("ops", "dev", "strategy")
        assert compiled.weight_value in (1, 2, 3)

    def test_topic_extracted(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        parsed = parse_session(sessions[0])
        compiled = compile_session(parsed)

        # Topic should not be empty or just session ID fallback
        assert compiled.topic_sentence
        assert len(compiled.topic_sentence) > 5

    def test_entities_filtered(self, sample_projects_dir: Path):
        """Entities like Rob, 小code should be suppressed (they're the medium)."""
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        parsed = parse_session(sessions[0])
        compiled = compile_session(parsed)

        assert "Rob" not in compiled.entities
        assert "小code" not in compiled.entities
        assert "Claude Code" not in compiled.entities

    def test_frozen_dataclass(self, sample_projects_dir: Path):
        sessions = list(discover_sessions(projects_dir=sample_projects_dir))
        parsed = parse_session(sessions[0])
        compiled = compile_session(parsed)

        with pytest.raises((AttributeError, TypeError)):
            compiled.weight = "ops"  # type: ignore[misc]


# ─── Concept index ──────────────────────────────────────────────────────────

class TestBuildConceptIndex:
    def _make_compiled(self, session_id, date, entities):
        return CompiledSession(
            session_id=session_id,
            date=date,
            time_range="10:00 - 11:00",
            project="~/test",
            models=("claude-opus-4-6",),
            user_message_count=10,
            assistant_message_count=8,
            cost_usd=1.0,
            entities=tuple(entities),
            topic_sentence="test topic",
            key_points=(),
            tail_context=(),
            file_changes=(),
            tags=(),
            weight="dev",
            weight_value=2,
        )

    def test_builds_index(self):
        compilations = [
            self._make_compiled("aaa", "2026-03-01", ["四星球", "SUNBVE"]),
            self._make_compiled("bbb", "2026-03-02", ["四星球", "Kaioshin"]),
            self._make_compiled("ccc", "2026-03-03", ["四星球"]),
        ]
        index = build_concept_index(compilations)

        assert "四星球" in index
        assert index["四星球"].mention_count == 3
        assert index["SUNBVE"].mention_count == 1

    def test_status_by_frequency(self):
        compilations = [
            self._make_compiled(f"s{i}", f"2026-03-{i+1:02d}", ["Alpha"])
            for i in range(6)
        ]
        index = build_concept_index(compilations)
        assert index["Alpha"].status == "mature"  # 6 >= 5

    def test_growing_status(self):
        compilations = [
            self._make_compiled(f"s{i}", f"2026-03-{i+1:02d}", ["Beta"])
            for i in range(3)
        ]
        index = build_concept_index(compilations)
        assert index["Beta"].status == "growing"  # 3 >= 3

    def test_stub_status(self):
        compilations = [
            self._make_compiled("s0", "2026-03-01", ["Gamma"]),
        ]
        index = build_concept_index(compilations)
        assert index["Gamma"].status == "stub"  # 1 < 3

    def test_first_seen(self):
        compilations = [
            self._make_compiled("s0", "2026-03-05", ["Delta"]),
            self._make_compiled("s1", "2026-03-10", ["Delta"]),
        ]
        index = build_concept_index(compilations)
        assert index["Delta"].first_seen == "2026-03-05"


# ─── Daily merge ────────────────────────────────────────────────────────────

class TestMergeByDay:
    def _make_compiled(self, session_id, date, weight="dev", entities=("A",)):
        return CompiledSession(
            session_id=session_id,
            date=date,
            time_range="10:00 - 11:00",
            project="~/test",
            models=("claude-opus-4-6",),
            user_message_count=10,
            assistant_message_count=8,
            cost_usd=5.0,
            entities=entities,
            topic_sentence="test",
            key_points=("point 1",),
            tail_context=(),
            file_changes=(),
            tags=(),
            weight=weight,
            weight_value={"ops": 1, "dev": 2, "strategy": 3}[weight],
        )

    def test_merges_same_day(self):
        compilations = [
            self._make_compiled("s1", "2026-03-10"),
            self._make_compiled("s2", "2026-03-10"),
            self._make_compiled("s3", "2026-03-11"),
        ]
        digests = merge_by_day(compilations)
        assert len(digests) == 2
        day10 = [d for d in digests if d.date == "2026-03-10"][0]
        assert day10.session_count == 2
        assert day10.total_user_messages == 20
        assert day10.total_cost == 10.0

    def test_highest_weight_wins(self):
        compilations = [
            self._make_compiled("s1", "2026-03-10", weight="ops"),
            self._make_compiled("s2", "2026-03-10", weight="strategy"),
        ]
        digests = merge_by_day(compilations)
        assert digests[0].weight == "strategy"

    def test_entities_union(self):
        compilations = [
            self._make_compiled("s1", "2026-03-10", entities=("A", "B")),
            self._make_compiled("s2", "2026-03-10", entities=("B", "C")),
        ]
        digests = merge_by_day(compilations)
        assert set(digests[0].entities) == {"A", "B", "C"}

    def test_sorted_by_date(self):
        compilations = [
            self._make_compiled("s1", "2026-03-12"),
            self._make_compiled("s2", "2026-03-10"),
            self._make_compiled("s3", "2026-03-11"),
        ]
        digests = merge_by_day(compilations)
        dates = [d.date for d in digests]
        assert dates == sorted(dates)


# ─── Markdown renderers ─────────────────────────────────────────────────────

class TestRenderers:
    def _make_compiled(self, **overrides):
        defaults = dict(
            session_id="abcd1234",
            date="2026-03-15",
            time_range="10:00 - 11:30",
            project="~/test-project",
            models=("claude-opus-4-6",),
            user_message_count=25,
            assistant_message_count=30,
            cost_usd=12.50,
            entities=("四星球", "SUNBVE"),
            topic_sentence="讨论四星球策略优化",
            key_points=("关键决定1", "关键决定2"),
            tail_context=("最后一句话",),
            file_changes=(FileChange("/Users/titans/test.py", "modified"),),
            tags=("四星球", "sunbve"),
            weight="strategy",
            weight_value=3,
        )
        defaults.update(overrides)
        return CompiledSession(**defaults)

    def test_render_session_md_has_frontmatter(self):
        cs = self._make_compiled()
        md = render_session_md(cs)
        assert md.startswith("---")
        assert "session_id: abcd1234" in md
        assert "weight: strategy" in md

    def test_render_session_md_has_wikilinks(self):
        cs = self._make_compiled()
        md = render_session_md(cs)
        assert "[[四星球]]" in md
        assert "[[SUNBVE]]" in md

    def test_render_session_md_has_weight_icon(self):
        cs = self._make_compiled(weight="strategy")
        md = render_session_md(cs)
        assert "★" in md

    def test_render_concept_md_stub(self):
        node = ConceptNode(
            name="TestConcept",
            sessions=["aaa", "bbb"],
            dates=["2026-03-01", "2026-03-02"],
            first_seen="2026-03-01",
            mention_count=2,
            status="stub",
        )
        md = render_concept_md(node)
        assert "name: TestConcept" in md
        assert "待小code 补充" in md
        assert "**2026-03-01**" in md

    def test_render_concept_md_deduplicates_dates(self):
        node = ConceptNode(
            name="Dedup",
            sessions=["a", "b", "c"],
            dates=["2026-03-01", "2026-03-01", "2026-03-02"],
            first_seen="2026-03-01",
            mention_count=3,
            status="growing",
        )
        md = render_concept_md(node)
        # Should only have 2026-03-01 once
        assert md.count("**2026-03-01**") == 1

    def test_render_daily_md(self):
        dd = DailyDigest(
            date="2026-03-15",
            session_count=3,
            session_ids=("aaa", "bbb", "ccc"),
            total_user_messages=50,
            total_assistant_messages=60,
            total_cost=25.0,
            weight="strategy",
            weight_value=3,
            entities=("四星球", "SUNBVE"),
            key_points=("讨论了策略",),
            file_changes=(),
            tags=("四星球", "sunbve"),
            models=("claude-opus-4-6",),
        )
        md = render_daily_md(dd)
        assert "date: 2026-03-15" in md
        assert "sessions: 3" in md
        assert "[[四星球]]" in md
        assert "★" in md

    def test_render_index_md(self):
        cs = self._make_compiled()
        concepts = {"四星球": ConceptNode(
            name="四星球", sessions=["a"], dates=["2026-03-15"],
            first_seen="2026-03-15", mention_count=1, status="stub",
        )}
        md = render_index_md([cs], concepts)
        assert "Code & Rob Wiki" in md
        assert "Karpathy" in md
        assert "[[四星球]]" in md


# ─── write_wiki ─────────────────────────────────────────────────────────────

class TestWriteWiki:
    def _make_compiled(self, session_id="aaa", date="2026-03-15"):
        return CompiledSession(
            session_id=session_id,
            date=date,
            time_range="10:00 - 11:00",
            project="~/test",
            models=("claude-opus-4-6",),
            user_message_count=10,
            assistant_message_count=8,
            cost_usd=5.0,
            entities=("TestEntity",),
            topic_sentence="test topic",
            key_points=(),
            tail_context=(),
            file_changes=(),
            tags=("testentity",),
            weight="dev",
            weight_value=2,
        )

    def test_creates_directories(self, tmp_path: Path):
        cs = self._make_compiled()
        concepts = build_concept_index([cs])
        write_wiki([cs], concepts, tmp_path)

        assert (tmp_path / "sessions").is_dir()
        assert (tmp_path / "concepts").is_dir()

    def test_writes_session_file(self, tmp_path: Path):
        cs = self._make_compiled()
        concepts = build_concept_index([cs])
        write_wiki([cs], concepts, tmp_path)

        session_file = tmp_path / "sessions" / "2026-03-15.md"
        assert session_file.exists()
        content = session_file.read_text()
        assert "date: 2026-03-15" in content

    def test_writes_concept_file(self, tmp_path: Path):
        cs = self._make_compiled()
        concepts = build_concept_index([cs])
        write_wiki([cs], concepts, tmp_path)

        concept_file = tmp_path / "concepts" / "TestEntity.md"
        assert concept_file.exists()

    def test_writes_index(self, tmp_path: Path):
        cs = self._make_compiled()
        concepts = build_concept_index([cs])
        write_wiki([cs], concepts, tmp_path)

        assert (tmp_path / "INDEX.md").exists()

    def test_does_not_overwrite_enriched_concept(self, tmp_path: Path):
        cs = self._make_compiled()
        concepts = build_concept_index([cs])

        # Pre-create an enriched concept file (no "待小code 补充")
        concepts_dir = tmp_path / "concepts"
        concepts_dir.mkdir(parents=True)
        enriched = concepts_dir / "TestEntity.md"
        enriched.write_text(
            "---\nname: TestEntity\ntype: concept\nfirst_seen: 2026-03-01\n"
            "sessions: [old_id]\nmention_count: 1\nstatus: stub\n---\n\n"
            "# TestEntity\n\n## 定义\n这是手动写的定义\n",
            encoding="utf-8",
        )

        write_wiki([cs], concepts, tmp_path)

        content = enriched.read_text()
        # Content should be preserved (not overwritten with stub)
        assert "这是手动写的定义" in content
        assert "待小code 补充" not in content
        # But frontmatter should be updated
        assert "sessions: [aaa]" in content

    def test_does_not_overwrite_archaeological(self, tmp_path: Path):
        cs = self._make_compiled()
        concepts = build_concept_index([cs])

        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)
        arch_file = sessions_dir / "2026-03-15.md"
        arch_file.write_text(
            "---\nsource: archaeological-recovery\n---\n\nRecovered data.\n",
            encoding="utf-8",
        )

        write_wiki([cs], concepts, tmp_path)

        content = arch_file.read_text()
        assert "archaeological-recovery" in content
        assert "Recovered data" in content

    def test_returns_counts(self, tmp_path: Path):
        cs = self._make_compiled()
        concepts = build_concept_index([cs])
        s, c, idx = write_wiki([cs], concepts, tmp_path)

        assert s >= 1
        assert c >= 1
        assert idx == 1


# ─── Frontmatter update ────────────────────────────────────────────────────

class TestUpdateConceptFrontmatter:
    def test_updates_sessions_and_count(self, tmp_path: Path):
        filepath = tmp_path / "test.md"
        filepath.write_text(
            "---\nname: Test\ntype: concept\nfirst_seen: 2026-03-01\n"
            "sessions: [old1, old2]\nmention_count: 2\nstatus: stub\n---\n\n"
            "# Test\n\nContent here.\n",
            encoding="utf-8",
        )

        node = ConceptNode(
            name="Test",
            sessions=["new1", "new2", "new3"],
            dates=["2026-03-01", "2026-03-05", "2026-03-10"],
            first_seen="2026-03-01",
            mention_count=5,
            status="mature",
        )
        _update_concept_frontmatter(filepath, node)

        content = filepath.read_text()
        assert "sessions: [new1, new2, new3]" in content
        assert "mention_count: 5" in content
        assert "status: mature" in content
        # Body preserved
        assert "Content here." in content
