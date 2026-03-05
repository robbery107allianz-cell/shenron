"""Token usage and equivalent API cost aggregation."""

from collections import defaultdict
from dataclasses import dataclass

from shenron.models import SessionMeta, TokenUsage
from shenron.parser import stream_messages
from shenron.pricing import compute_cost


@dataclass
class SessionStats:
    """Aggregated stats for one session."""
    meta: SessionMeta
    usage: TokenUsage
    cost_usd: float
    model: str | None
    msg_count: int


@dataclass
class GroupStats:
    """Aggregated stats for a group (project / model / date)."""
    label: str
    sessions: int = 0
    messages: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def add(self, session: SessionStats) -> None:
        self.sessions += 1
        self.messages += session.msg_count
        self.input_tokens += session.usage.input_tokens
        self.output_tokens += session.usage.output_tokens
        self.cache_write_tokens += session.usage.cache_creation_input_tokens
        self.cache_read_tokens += session.usage.cache_read_input_tokens
        self.cost_usd += session.cost_usd


@dataclass
class StatsReport:
    """Full stats report."""
    groups: list[GroupStats]
    totals: GroupStats
    group_by: str


def _session_stats(meta: SessionMeta) -> SessionStats:
    """Compute per-session stats by streaming messages."""
    total_input = total_output = total_cache_write = total_cache_read = 0
    msg_count = 0
    model: str | None = None
    total_cost = 0.0

    for msg in stream_messages(meta.file_path):
        msg_count += 1
        if msg.model:
            model = msg.model
        if msg.usage:
            u = msg.usage
            total_input += u.input_tokens
            total_output += u.output_tokens
            total_cache_write += u.cache_creation_input_tokens
            total_cache_read += u.cache_read_input_tokens
            total_cost += compute_cost(
                model=msg.model or model,
                input_tokens=u.input_tokens,
                output_tokens=u.output_tokens,
                cache_write_tokens=u.cache_creation_input_tokens,
                cache_read_tokens=u.cache_read_input_tokens,
            )

    usage = TokenUsage(
        input_tokens=total_input,
        output_tokens=total_output,
        cache_creation_input_tokens=total_cache_write,
        cache_read_input_tokens=total_cache_read,
    )
    return SessionStats(
        meta=meta,
        usage=usage,
        cost_usd=total_cost,
        model=model,
        msg_count=msg_count,
    )


def _group_key(session: SessionStats, group_by: str) -> str:
    """Return the grouping key for a session."""
    if group_by == "model":
        return session.model or "unknown"
    if group_by == "date":
        ts = session.meta.modified_time
        return ts.strftime("%Y-%m-%d") if ts else "unknown"
    # default: project
    return session.meta.project_name


def compute_stats(
    sessions: list[SessionMeta],
    group_by: str = "project",
    top_n: int | None = None,
) -> StatsReport:
    """
    Aggregate token usage and cost across sessions.

    group_by: "project" | "model" | "date"
    top_n: if set, only return the top N groups by cost
    """
    groups: dict[str, GroupStats] = defaultdict(lambda: GroupStats(label=""))
    totals = GroupStats(label="TOTAL")

    for meta in sessions:
        ss = _session_stats(meta)
        key = _group_key(ss, group_by)

        if key not in groups:
            groups[key] = GroupStats(label=key)
        groups[key].add(ss)
        totals.add(ss)

    sorted_groups = sorted(groups.values(), key=lambda g: g.cost_usd, reverse=True)

    if top_n is not None:
        sorted_groups = sorted_groups[:top_n]

    return StatsReport(
        groups=sorted_groups,
        totals=totals,
        group_by=group_by,
    )
