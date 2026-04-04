"""Compile Claude Code sessions into an Obsidian wiki.

Layer 1 (algorithmic):
  - Parse JSONL → extract conversation text
  - Entity matching against seed dictionary
  - Decision-signal detection (reuses digester heuristics)
  - Frequency-based concept ranking across sessions
  - Generate Markdown with frontmatter + wikilinks

Layer 2 (model, future):
  - 小code enriches stub nodes with semantic summaries
  - Detects "unnamed ideas" that algorithms miss
  - Writes evolution narratives for mature concepts
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from shenron.digester import _has_signal, _truncate
from shenron.models import Message, Session
from shenron.pricing import compute_cost

# ─── Entity dictionary ───────────────────────────────────────────────────────
# Seed entities: known projects, tools, people, concepts in the 1984 ecosystem.
# The compiler matches these against session text. New entities discovered
# at high frequency get promoted into this dict on future runs.

SEED_ENTITIES: dict[str, list[str]] = {
    # Projects
    "四星球": ["四星球", "FourStar", "fourstar", "4stars"],
    "SUNBVE": ["SUNBVE", "sunbve", "童袜"],
    "Lucky Tea": ["Lucky Tea", "lucky-tea", "奶茶"],
    "知几策略": ["知几策略", "知几", "公众号"],
    "AgentMesh": ["AgentMesh", "agentmesh", "Agent Mesh"],
    "命名阁": ["命名阁", "NameGen", "namegen", "择名致远"],
    "择业小程序": ["择业小程序", "择业匹配", "career-match", "职业测评"],
    "Hwa Hsia": ["华夏宪法", "nomos", "华夏", "Hwa Hsia"],
    "CS-Fundamentals": ["CS-Fundamentals", "CS50", "CS 基础"],
    "K12教育": ["K12", "Aaron", "Justin", "K12-Math", "K12-Logic"],
    "Dragon Radar": ["Dragon Radar", "龙珠雷达", "认知图谱"],
    "art-gallery": ["art-gallery", "艺术视频", "光的奏鸣", "油画"],
    "智慧物流与供应链": ["供应链", "物流", "仓储", "智慧物流", "smart-logistics"],
    "网店运营教材": ["网店运营", "网店推广", "电商教材", "淘宝运营"],

    # Tools
    "Shenron": ["Shenron", "shenron", "神龙", "神龍"],
    "Kaioshin": ["Kaioshin", "kaioshin", "界王神"],
    "Chromium MCP": ["Chromium", "chromium-mcp", "CDP", "port 9222"],
    "Obsidian": ["Obsidian", "obsidian"],
    "Claude Code": ["Claude Code", "claude code"],

    # People & identities
    "Rob": ["Rob", "洛持"],
    "小code": ["小code", "小Code"],
    "Alita": ["Alita", "alita", "Telegram"],

    # Concepts (evolving)
    "autoresearch": ["autoresearch", "Karpathy"],
    "复合增长循环": ["复合增长", "compound growth", "闭环"],
    "记忆系统": ["MEMORY.md", "memory system", "记忆系统", "持久化"],
    "安全审计": ["安全审计", "security scan", "逆向分析"],
}


def _build_entity_patterns() -> dict[str, re.Pattern[str]]:
    """Pre-compile regex patterns for each entity."""
    patterns: dict[str, re.Pattern[str]] = {}
    for canonical, aliases in SEED_ENTITIES.items():
        escaped = "|".join(re.escape(a) for a in aliases)
        patterns[canonical] = re.compile(escaped, re.IGNORECASE)
    return patterns


_ENTITY_PATTERNS = _build_entity_patterns()


# ─── Data models ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FileChange:
    """A file created or modified during the session."""
    path: str
    action: str  # created, modified, deleted


# ─── Weight system ───────────────────────────────────────────────────────────
# Three layers only. "Issue/问题排查" is a transient state, not a final weight:
#   - Problem found + fixed in-place → still ops
#   - Problem found + triggered big changes → escalates to dev
#
#   ops      → routine check, status confirmation, problem found & fixed in-place
#   dev      → code written, files changed, feature built, bug fixed, significant iteration
#   strategy → research, new idea, architecture decision, product design, philosophical discussion

WEIGHT_LEVELS = ("ops", "dev", "strategy")
WEIGHT_VALUES = {"ops": 1, "dev": 2, "strategy": 3}

_DEV_SIGNALS = re.compile(
    r"实现|开发|重写|重构|新增|创建|部署|迭代|优化|写入|编译|构建|"
    r"修复|报错|失败|崩溃|"
    r"implement|develop|refactor|build|deploy|create|write|migrate|ship|"
    r"error|fail|crash|fix|debug",
    re.IGNORECASE,
)

# Strategy signals: ONLY match on USER messages to avoid false positives
# from 小code's standard language (方案/分析/设计 appear in almost every reply).
_STRATEGY_SIGNALS = re.compile(
    r"可行性|产品化|路线图|愿景|商业模式|付费|变现|盈利|"
    r"哲学|信仰|文明|宪法|法理|"
    r"架构设计|系统设计|顶层设计|整体方案|"
    r"研究.*对比|对比.*研究|深入.*分析|"
    r"vision|roadmap|monetiz|business model|philosophy",
    re.IGNORECASE,
)


def _compute_weight(session: Session, file_change_count: int) -> str:
    """Determine session weight: ops / dev / strategy.

    Logic:
    1. Strategy: user explicitly discusses research, product design, philosophy
    2. Dev: significant code/file changes, or debugging that led to fixes
    3. Ops: everything else (checks, confirmations, short Q&A)
    """
    user_texts = [m.content_text for m in session.user_messages if m.content_text.strip()]
    all_texts = user_texts + [m.content_text for m in session.assistant_messages if m.content_text.strip()]
    all_text = " ".join(all_texts)
    user_text = " ".join(user_texts)

    dev_hits = len(_DEV_SIGNALS.findall(all_text))
    strategy_hits = len(_STRATEGY_SIGNALS.findall(user_text))
    user_msg_count = len(user_texts)

    # Strategy: user is thinking, researching, designing
    if strategy_hits >= 2:
        return "strategy"

    # Dev: significant work happened
    if dev_hits >= 3 or file_change_count >= 3:
        return "dev"

    # Short sessions with no dev signals → ops
    if user_msg_count <= 5 and dev_hits == 0 and strategy_hits == 0:
        return "ops"

    # Check for lighter signals
    if strategy_hits >= 1:
        return "strategy"
    if dev_hits >= 1 or file_change_count >= 1:
        return "dev"

    # Longer sessions with real conversation are likely dev
    if user_msg_count > 10:
        return "dev"

    return "ops"


@dataclass(frozen=True)
class CompiledSession:
    """Algorithmic compilation of a single session."""
    session_id: str
    date: str
    time_range: str
    project: str
    models: tuple[str, ...]
    user_message_count: int
    assistant_message_count: int
    cost_usd: float
    entities: tuple[str, ...]           # canonical entity names found
    topic_sentence: str                  # first meaningful user message
    key_points: tuple[str, ...]         # decision-signal user messages
    tail_context: tuple[str, ...]       # last few user messages
    file_changes: tuple[FileChange, ...]
    tags: tuple[str, ...]
    weight: str = "ops"                  # ops | issue | dev | strategy
    weight_value: int = 1                # 1-4 numeric weight


@dataclass
class ConceptNode:
    """A concept that appears across sessions."""
    name: str
    sessions: list[str] = field(default_factory=list)      # session IDs
    dates: list[str] = field(default_factory=list)          # YYYY-MM-DD
    first_seen: str = ""
    mention_count: int = 0
    status: str = "stub"  # stub | growing | mature


# ─── Core compilation ────────────────────────────────────────────────────────

def _extract_entities(text: str) -> list[str]:
    """Match text against seed dictionary, return canonical entity names."""
    found: list[str] = []
    for canonical, pattern in _ENTITY_PATTERNS.items():
        if pattern.search(text):
            found.append(canonical)
    return found


def _extract_file_changes(messages: tuple[Message, ...]) -> list[FileChange]:
    """Detect file changes from tool usage patterns in assistant messages."""
    changes: list[FileChange] = []
    seen_paths: set[str] = set()

    for msg in messages:
        if msg.msg_type != "assistant":
            continue
        text = msg.content_text
        # Detect Write/Edit tool results mentioning file paths
        for tool_name in msg.tool_names:
            if tool_name in ("Write", "Edit", "NotebookEdit"):
                # Try to extract file path from surrounding text
                path_match = re.search(
                    r"(/Users/[^\s\"']+\.(?:md|py|json|ts|js|html|css|yaml|yml|toml|sh))",
                    text,
                )
                if path_match:
                    path = path_match.group(1)
                    if path not in seen_paths:
                        seen_paths.add(path)
                        action = "created" if tool_name == "Write" else "modified"
                        changes.append(FileChange(path=path, action=action))

    return changes


def _estimate_cost(session: Session) -> float:
    """Estimate API-equivalent cost for the session."""
    return sum(
        compute_cost(
            model=m.model,
            input_tokens=m.usage.input_tokens if m.usage else 0,
            output_tokens=m.usage.output_tokens if m.usage else 0,
            cache_write_tokens=m.usage.cache_creation_input_tokens if m.usage else 0,
            cache_read_tokens=m.usage.cache_read_input_tokens if m.usage else 0,
        )
        for m in session.assistant_messages
    )


def _generate_tag(entity: str) -> str:
    """Convert entity name to a tag-friendly string."""
    tag = entity.lower().replace(" ", "-").replace("_", "-")
    # Remove non-ascii for tag (keep Chinese as-is)
    return tag


def compile_session(session: Session) -> CompiledSession:
    """Compile a parsed Session into a CompiledSession summary (Layer 1)."""
    # Entity extraction: USER messages only.
    # System messages and assistant boilerplate contain MEMORY.md / CLAUDE.md
    # which mention ALL major entities — scanning them creates false links.
    # Also filter out short user messages (greetings, confirmations).
    user_substance = " ".join(
        m.content_text for m in session.user_messages
        if len(m.content_text.strip()) > 20
        and not m.content_text.strip().startswith("<")
    )
    entities = _extract_entities(user_substance)

    # Filter by mention density: a single passing mention ("telegram是不是要重启")
    # should NOT link a session to that entity. Require minimum hits based
    # on how "common" the entity is across all sessions (high-frequency
    # entities need more hits to prove relevance).
    # Tier 1: ubiquitous (appear in greetings/every session) — suppress from graph
    # These are the MEDIUM of communication, not topics of discussion.
    _SUPPRESS_ENTITIES = {"Rob", "小code", "Claude Code"}

    # Tier 2: frequent infra — need strong signal to link
    _HIGH_FREQ_ENTITIES = {"Obsidian", "四星球", "Alita", "记忆系统",
                           "Kaioshin", "Chromium MCP", "K12教育"}
    _MIN_HITS_HIGH = 3   # need 3+ mentions in user text
    _MIN_HITS_LOW = 1    # rare entities: 1 mention is enough

    filtered_entities: list[str] = []
    for e in entities:
        if e in _SUPPRESS_ENTITIES:
            continue  # never link — they're the medium, not the topic
        pattern = _ENTITY_PATTERNS[e]
        hits = len(pattern.findall(user_substance))
        threshold = _MIN_HITS_HIGH if e in _HIGH_FREQ_ENTITIES else _MIN_HITS_LOW
        if hits >= threshold:
            filtered_entities.append(e)
    entities = filtered_entities

    # Topic: first substantial user message (skip noise)
    topic = ""
    _NOISE_PREFIXES = (
        "<local-command", "<command-", "{", "[", "#", "---", "infra:",
        "Exit code", "Web search", "Found ", "File content",
        "Protocol error", "hostkeys_", "Command running",
        "claude-safe", "100%", "70 100%",
    )
    for msg in session.user_messages:
        text = msg.content_text.strip()
        if len(text) < 15:
            continue
        if any(text.startswith(p) for p in _NOISE_PREFIXES):
            continue
        # Skip pure JSON / tool output
        if text.startswith(("{", "[")) or "xfer#" in text:
            continue
        # Skip session handoff headers
        if "Session Handoff" in text or "工作规范" in text:
            continue
        topic = _truncate(text, 120)
        break
    if not topic:
        # Fallback: session ID as topic
        topic = f"session-{session.meta.session_id[:8]}"

    # Key points: user messages with decision signals
    key_points: list[str] = []
    for msg in session.user_messages:
        text = msg.content_text.strip()
        if len(text) > 20 and _has_signal(text):
            key_points.append(_truncate(text, 160))
    key_points = key_points[:10]  # cap

    # Tail context: last 3 user messages
    user_msgs = [m for m in session.user_messages if len(m.content_text.strip()) > 10]
    tail = [_truncate(m.content_text.strip(), 160) for m in user_msgs[-3:]]

    # File changes
    file_changes = _extract_file_changes(session.messages)

    # Time range
    time_range = ""
    if session.first_timestamp and session.last_timestamp:
        t1 = session.first_timestamp.strftime("%H:%M")
        t2 = session.last_timestamp.strftime("%H:%M")
        time_range = f"{t1} - {t2}"

    # Date
    date_str = session.first_timestamp.strftime("%Y-%m-%d") if session.first_timestamp else "unknown"

    # Models
    models = tuple(sorted(session.models_used))

    # Cost
    cost = _estimate_cost(session)

    # Tags from entities
    tags = tuple(_generate_tag(e) for e in entities)

    # Weight: analyze content layers
    weight = _compute_weight(session, len(file_changes))
    weight_val = WEIGHT_VALUES[weight]

    return CompiledSession(
        session_id=session.meta.session_id[:8],
        date=date_str,
        time_range=time_range,
        project=session.cwd or session.meta.project_name,
        models=models,
        user_message_count=len(session.user_messages),
        assistant_message_count=len(session.assistant_messages),
        cost_usd=cost,
        entities=tuple(entities),
        topic_sentence=topic,
        key_points=tuple(key_points),
        tail_context=tuple(tail),
        file_changes=tuple(file_changes),
        tags=tags,
        weight=weight,
        weight_value=weight_val,
    )


# ─── Daily merge ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DailyDigest:
    """Multiple sessions from the same day merged into one node."""
    date: str
    session_count: int
    session_ids: tuple[str, ...]
    total_user_messages: int
    total_assistant_messages: int
    total_cost: float
    weight: str                          # highest weight of the day
    weight_value: int
    entities: tuple[str, ...]            # union of all entities
    key_points: tuple[str, ...]          # combined, deduplicated
    file_changes: tuple[FileChange, ...]
    tags: tuple[str, ...]
    models: tuple[str, ...]


def merge_by_day(compilations: list[CompiledSession]) -> list[DailyDigest]:
    """Merge sessions from the same date into daily digests."""
    from collections import defaultdict as _defaultdict

    by_date: dict[str, list[CompiledSession]] = _defaultdict(list)
    for cs in compilations:
        by_date[cs.date].append(cs)

    digests: list[DailyDigest] = []
    for date in sorted(by_date.keys()):
        sessions = by_date[date]

        # Weight = highest of the day
        best_weight = max(sessions, key=lambda s: s.weight_value)

        # Union of entities (deduplicated, ordered by first appearance)
        seen_entities: dict[str, None] = {}
        for s in sessions:
            for e in s.entities:
                seen_entities[e] = None
        all_entities = tuple(seen_entities.keys())

        # Combine key points (deduplicated)
        seen_points: dict[str, None] = {}
        for s in sessions:
            for kp in s.key_points:
                seen_points[kp] = None
        all_key_points = tuple(list(seen_points.keys())[:15])  # cap at 15

        # Combine file changes (deduplicated by path)
        seen_files: dict[str, FileChange] = {}
        for s in sessions:
            for fc in s.file_changes:
                seen_files[fc.path] = fc
        all_file_changes = tuple(seen_files.values())

        # Tags from entities
        all_tags = tuple(_generate_tag(e) for e in all_entities)

        # Models
        all_models = tuple(sorted({m for s in sessions for m in s.models}))

        digests.append(DailyDigest(
            date=date,
            session_count=len(sessions),
            session_ids=tuple(s.session_id for s in sessions),
            total_user_messages=sum(s.user_message_count for s in sessions),
            total_assistant_messages=sum(s.assistant_message_count for s in sessions),
            total_cost=sum(s.cost_usd for s in sessions),
            weight=best_weight.weight,
            weight_value=best_weight.weight_value,
            entities=all_entities,
            key_points=all_key_points,
            file_changes=all_file_changes,
            tags=all_tags,
            models=all_models,
        ))

    return digests


def render_daily_md(dd: DailyDigest) -> str:
    """Render a DailyDigest to Obsidian Markdown."""
    home = str(Path.home())
    lines: list[str] = []

    wi = {"ops": "○", "dev": "●", "strategy": "★"}[dd.weight]
    models_str = ", ".join(dd.models)
    tags_str = ", ".join(dd.tags[:8])
    sids = ", ".join(dd.session_ids)

    # Frontmatter
    lines.append("---")
    lines.append(f"date: {dd.date}")
    lines.append(f"sessions: {dd.session_count}")
    lines.append(f"session_ids: [{sids}]")
    lines.append(f"models: [{models_str}]")
    lines.append(f"user_messages: {dd.total_user_messages}")
    lines.append(f"cost: ${dd.total_cost:.2f}")
    lines.append(f"tags: [{tags_str}]")
    lines.append(f"weight: {dd.weight}")
    lines.append(f"weight_value: {dd.weight_value}")
    lines.append("type: daily-digest")
    lines.append("---")
    lines.append("")

    # Title
    lines.append(f"# {wi} {dd.date} · {dd.session_count} sessions · {dd.total_user_messages} msgs")
    lines.append("")
    lines.append(f"**权重**: {wi} {dd.weight} · **成本**: ${dd.total_cost:.2f}")
    lines.append("")

    # Entities
    if dd.entities:
        entity_links = " · ".join(f"[[{e}]]" for e in dd.entities)
        lines.append(f"**涉及**: {entity_links}")
        lines.append("")

    # Key points
    if dd.key_points:
        lines.append("## 关键对话")
        for kp in dd.key_points:
            lines.append(f"- {kp}")
        lines.append("")

    # File changes
    if dd.file_changes:
        lines.append("## 文件变更")
        for fc in dd.file_changes:
            short_path = fc.path.replace(home, "~")
            lines.append(f"- `{short_path}` — {fc.action}")
        lines.append("")

    # Meta
    lines.append("## 元数据")
    lines.append(f"- Sessions: {dd.session_count} (`{sids}`)")
    lines.append(f"- 消息数: {dd.total_user_messages} (user) + {dd.total_assistant_messages} (assistant)")
    lines.append(f"- 模型: {models_str}")
    lines.append(f"- 等价成本: ${dd.total_cost:.2f}")
    lines.append("")

    return "\n".join(lines)


# ─── Concept tracker ─────────────────────────────────────────────────────────

def build_concept_index(compilations: list[CompiledSession]) -> dict[str, ConceptNode]:
    """Build concept nodes from a batch of compiled sessions."""
    index: dict[str, ConceptNode] = {}

    for cs in compilations:
        for entity in cs.entities:
            if entity not in index:
                index[entity] = ConceptNode(name=entity, first_seen=cs.date)
            node = index[entity]
            node.sessions.append(cs.session_id)
            node.dates.append(cs.date)
            node.mention_count += 1

    # Set status based on frequency
    for node in index.values():
        if node.mention_count >= 5:
            node.status = "mature"
        elif node.mention_count >= 3:
            node.status = "growing"
        else:
            node.status = "stub"

    return index


# ─── Markdown renderers ──────────────────────────────────────────────────────

def render_session_md(cs: CompiledSession) -> str:
    """Render a CompiledSession to Obsidian Markdown."""
    home = str(Path.home())
    lines: list[str] = []

    # Frontmatter
    models_str = ", ".join(cs.models)
    tags_str = ", ".join(cs.tags[:8])
    lines.append("---")
    lines.append(f"session_id: {cs.session_id}")
    lines.append(f"date: {cs.date}")
    lines.append(f'time_range: "{cs.time_range}"')
    lines.append(f"project: {cs.project.replace(home, '~')}")
    lines.append(f"models: [{models_str}]")
    lines.append(f"user_messages: {cs.user_message_count}")
    lines.append(f"cost: ${cs.cost_usd:.2f}")
    lines.append(f"tags: [{tags_str}]")
    lines.append(f"weight: {cs.weight}")
    lines.append(f"weight_value: {cs.weight_value}")
    lines.append("status: compiled")
    lines.append("---")
    lines.append("")

    # Weight indicator
    weight_icon = {"ops": "○", "dev": "●", "strategy": "★"}[cs.weight]
    title = cs.topic_sentence[:60] if cs.topic_sentence else cs.date
    lines.append(f"# {weight_icon} Session: {title}")
    lines.append("")
    lines.append(
        f"**权重**: {weight_icon} {cs.weight} · "
        f"**消息**: {cs.user_message_count} · **成本**: ${cs.cost_usd:.2f}"
    )
    lines.append("")

    # Entities as wikilinks
    if cs.entities:
        entity_links = " · ".join(f"[[{e}]]" for e in cs.entities)
        lines.append(f"**涉及**: {entity_links}")
        lines.append("")

    # Key points
    if cs.key_points:
        lines.append("## 关键对话")
        for point in cs.key_points:
            lines.append(f"- {point}")
        lines.append("")

    # Tail context
    if cs.tail_context:
        lines.append("## 结尾上下文")
        for tail in cs.tail_context:
            lines.append(f"> {tail}")
        lines.append("")

    # File changes
    if cs.file_changes:
        lines.append("## 文件变更")
        for fc in cs.file_changes:
            short_path = fc.path.replace(home, "~")
            lines.append(f"- `{short_path}` — {fc.action}")
        lines.append("")

    # Meta
    lines.append("## 元数据")
    lines.append(f"- Session: `{cs.session_id}`")
    lines.append(f"- 时间: {cs.time_range}")
    lines.append(f"- 消息数: {cs.user_message_count} (user) + {cs.assistant_message_count} (assistant)")
    lines.append(f"- 模型: {models_str}")
    lines.append(f"- 等价成本: ${cs.cost_usd:.2f}")
    lines.append("")

    return "\n".join(lines)


def render_concept_md(node: ConceptNode) -> str:
    """Render a ConceptNode to Obsidian Markdown."""
    lines: list[str] = []

    sessions_str = ", ".join(node.sessions[:20])
    lines.append("---")
    lines.append(f"name: {node.name}")
    lines.append("type: concept")
    lines.append(f"first_seen: {node.first_seen}")
    lines.append(f"sessions: [{sessions_str}]")
    lines.append(f"mention_count: {node.mention_count}")
    lines.append(f"status: {node.status}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {node.name}")
    lines.append("")
    lines.append("## 定义")
    lines.append(f"*待小code 补充（出现在 {node.mention_count} 个 session 中）*")
    lines.append("")

    # Evolution trail — link to daily digests
    lines.append("## 演化轨迹")
    seen_dates: set[str] = set()
    for date in node.dates:
        if date not in seen_dates:
            lines.append(f"- **{date}** [[{date}]]")
            seen_dates.add(date)
    lines.append("")

    return "\n".join(lines)


def render_index_md(
    compilations: list[CompiledSession],
    concepts: dict[str, ConceptNode],
) -> str:
    """Render the INDEX.md master index."""
    lines: list[str] = []

    lines.append("---")
    lines.append("title: Code & Rob Wiki")
    lines.append("type: index")
    lines.append(f"updated: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("---")
    lines.append("")
    lines.append("# Code & Rob Wiki")
    lines.append("")
    lines.append("> 小code 与 Rob 的对话编译知识库")
    lines.append("> 编译器：Shenron compiler · 设计参考：Karpathy LLM-as-knowledge-editor")
    lines.append("")

    # Stats
    total_cost = sum(cs.cost_usd for cs in compilations)
    total_user_msgs = sum(cs.user_message_count for cs in compilations)
    mature = sum(1 for n in concepts.values() if n.status == "mature")
    growing = sum(1 for n in concepts.values() if n.status == "growing")
    stub = sum(1 for n in concepts.values() if n.status == "stub")

    # Weight distribution
    from collections import Counter as _Counter
    weight_dist = _Counter(cs.weight for cs in compilations)

    lines.append("## 统计")
    lines.append("")
    lines.append("| 指标 | 值 |")
    lines.append("|------|-----|")
    lines.append(f"| 已编译 session | {len(compilations)} |")
    lines.append(f"| 总对话轮数 | {total_user_msgs} |")
    lines.append(f"| 等价 API 成本 | ${total_cost:,.2f} |")
    lines.append(f"| Concept 节点 | {len(concepts)} (mature: {mature}, growing: {growing}, stub: {stub}) |")
    lines.append("")
    lines.append("### 权重分布")
    lines.append("")
    lines.append("| 层级 | 数量 | 占比 | 说明 |")
    lines.append("|------|------|------|------|")
    total = len(compilations)
    for w, label in [("strategy", "★ 策略/研究/新想法"), ("dev", "● 开发/迭代/修复"), ("ops", "○ 运维/检查/确认")]:
        count = weight_dist.get(w, 0)
        pct = count * 100 / total if total else 0
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        lines.append(f"| {label} | {count} | {pct:.0f}% | {bar} |")
    lines.append("")

    # Daily digests (recent first)
    digests = merge_by_day(compilations)
    lines.append("## 日报")
    lines.append("")
    for dd in sorted(digests, key=lambda d: d.date, reverse=True):
        wi = {"ops": "○", "dev": "●", "strategy": "★"}[dd.weight]
        entities_short = ", ".join(dd.entities[:4])
        lines.append(f"- {wi} [[{dd.date}]] · {dd.session_count}s · {dd.total_user_messages}m · {entities_short}")
    lines.append("")

    # Concepts by frequency
    lines.append("## Concepts")
    lines.append("")
    sorted_concepts = sorted(concepts.values(), key=lambda n: n.mention_count, reverse=True)
    for node in sorted_concepts:
        status_icon = {"mature": "●", "growing": "◐", "stub": "○"}[node.status]
        lines.append(f"- {status_icon} [[{node.name}]] — {node.mention_count} sessions · {node.status}")
    lines.append("")

    return "\n".join(lines)


# ─── File I/O ────────────────────────────────────────────────────────────────

def _session_filename_tag(cs: CompiledSession) -> str:
    """Generate a short filename tag from session topic."""
    topic = cs.topic_sentence
    if not topic or topic.startswith("session-"):
        return cs.session_id[:8]

    # Remove Chinese punctuation
    clean = re.sub(r"[，。！？、；：\u201c\u201d\u2018\u2019（）\[\]…\n\r]", " ", topic)
    # Remove non-filename-safe chars
    clean = re.sub(r'[<>:"|?*{}#@&=+$!`~^]', "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()

    # Take first ~40 chars
    tag = clean[:40].strip().replace(" ", "-").replace("/", "-")
    # Remove consecutive dashes and trailing dashes
    tag = re.sub(r"-+", "-", tag).strip("-")

    # Final safety: if tag is empty or too short, use session ID
    return tag if len(tag) >= 4 else cs.session_id[:8]


def write_wiki(
    compilations: list[CompiledSession],
    concepts: dict[str, ConceptNode],
    output_dir: Path,
) -> tuple[int, int, int]:
    """Write all compiled data to the wiki directory.

    Sessions are merged into daily digests (1 file per day).
    Returns (digests_written, concepts_written, index_updated).
    """
    sessions_dir = output_dir / "sessions"
    concepts_dir = output_dir / "concepts"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    concepts_dir.mkdir(parents=True, exist_ok=True)

    # Merge sessions into daily digests
    digests = merge_by_day(compilations)

    sessions_written = 0
    for dd in digests:
        filename = f"{dd.date}.md"
        filepath = sessions_dir / filename
        # Don't overwrite archaeological-recovery or manually enriched sessions
        if filepath.exists():
            existing = filepath.read_text(encoding="utf-8")
            if "source: archaeological-recovery" in existing or "source: merged" in existing:
                sessions_written += 1
                continue
        filepath.write_text(render_daily_md(dd), encoding="utf-8")
        sessions_written += 1

    concepts_written = 0
    for node in concepts.values():
        filename = f"{node.name}.md"
        filename = re.sub(r'[<>:"|?*]', "", filename)
        filepath = concepts_dir / filename
        # Don't overwrite manually enriched concept files
        if filepath.exists():
            existing = filepath.read_text(encoding="utf-8")
            if "待小code 补充" not in existing:
                # File has been manually enriched; only update frontmatter sessions list
                _update_concept_frontmatter(filepath, node)
                concepts_written += 1
                continue
        filepath.write_text(render_concept_md(node), encoding="utf-8")
        concepts_written += 1

    # INDEX.md
    index_path = output_dir / "INDEX.md"
    index_path.write_text(render_index_md(compilations, concepts), encoding="utf-8")

    return sessions_written, concepts_written, 1


def _update_concept_frontmatter(filepath: Path, node: ConceptNode) -> None:
    """Update only the sessions list and mention_count in existing concept files."""
    content = filepath.read_text(encoding="utf-8")

    # Update sessions line
    sessions_str = ", ".join(node.sessions[:20])
    content = re.sub(
        r"^sessions: \[.*?\]$",
        f"sessions: [{sessions_str}]",
        content,
        count=1,
        flags=re.MULTILINE,
    )

    # Update mention_count
    content = re.sub(
        r"^mention_count: \d+$",
        f"mention_count: {node.mention_count}",
        content,
        count=1,
        flags=re.MULTILINE,
    )

    # Update status
    content = re.sub(
        r"^status: \w+$",
        f"status: {node.status}",
        content,
        count=1,
        flags=re.MULTILINE,
    )

    filepath.write_text(content, encoding="utf-8")
