"""Token usage and equivalent API cost aggregation."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

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
    if group_by == "week":
        ts = session.meta.modified_time
        if ts:
            iso_year, iso_week, _ = ts.isocalendar()
            return f"{iso_year}-W{iso_week:02d}"
        return "unknown"
    # default: project
    return session.meta.project_name


def compute_stats(
    sessions: list[SessionMeta],
    group_by: str = "project",
    top_n: int | None = None,
) -> StatsReport:
    """
    Aggregate token usage and cost across sessions.

    group_by: "project" | "model" | "date" | "week"
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


# ─── Weekly Model Breakdown ──────────────────────────────────────────────────


def _week_label(iso_year: int, iso_week: int) -> str:
    """Return 'YYYY-W##' label for an ISO week."""
    return f"{iso_year}-W{iso_week:02d}"


def _week_date_range(iso_year: int, iso_week: int) -> tuple[str, str]:
    """Return (Mon date, Sun date) strings for an ISO week."""
    jan4 = datetime(iso_year, 1, 4, tzinfo=UTC)
    start_of_w1 = jan4 - timedelta(days=jan4.weekday())
    mon = start_of_w1 + timedelta(weeks=iso_week - 1)
    sun = mon + timedelta(days=6)
    return mon.strftime("%m/%d"), sun.strftime("%m/%d")


@dataclass
class WeekModelRow:
    """One row in the weekly breakdown: one week's data."""

    week: str  # "2026-W12"
    date_range: str  # "03/17–03/23"
    opus_sessions: int = 0
    opus_output: int = 0
    opus_cost: float = 0.0
    sonnet_sessions: int = 0
    sonnet_output: int = 0
    sonnet_cost: float = 0.0
    other_sessions: int = 0
    other_output: int = 0
    other_cost: float = 0.0

    @property
    def total_sessions(self) -> int:
        return self.opus_sessions + self.sonnet_sessions + self.other_sessions

    @property
    def total_output(self) -> int:
        return self.opus_output + self.sonnet_output + self.other_output

    @property
    def total_cost(self) -> float:
        return self.opus_cost + self.sonnet_cost + self.other_cost

    @property
    def opus_output_pct(self) -> float:
        return (self.opus_output / self.total_output * 100) if self.total_output else 0.0

    @property
    def opus_cost_pct(self) -> float:
        return (self.opus_cost / self.total_cost * 100) if self.total_cost else 0.0


@dataclass
class WeeklyReport:
    """Full weekly breakdown report."""

    rows: list[WeekModelRow]
    total: WeekModelRow


def compute_weekly_breakdown(sessions: list[SessionMeta]) -> WeeklyReport:
    """Compute per-week model breakdown (Opus / Sonnet / Other)."""
    weeks: dict[str, WeekModelRow] = {}

    for meta in sessions:
        ss = _session_stats(meta)
        ts = meta.modified_time
        if not ts:
            continue

        iso_year, iso_week, _ = ts.isocalendar()
        key = _week_label(iso_year, iso_week)

        if key not in weeks:
            mon, sun = _week_date_range(iso_year, iso_week)
            weeks[key] = WeekModelRow(week=key, date_range=f"{mon}-{sun}")

        row = weeks[key]
        model = (ss.model or "").lower()

        if "opus" in model:
            row.opus_sessions += 1
            row.opus_output += ss.usage.output_tokens
            row.opus_cost += ss.cost_usd
        elif "sonnet" in model:
            row.sonnet_sessions += 1
            row.sonnet_output += ss.usage.output_tokens
            row.sonnet_cost += ss.cost_usd
        else:
            row.other_sessions += 1
            row.other_output += ss.usage.output_tokens
            row.other_cost += ss.cost_usd

    sorted_rows = sorted(weeks.values(), key=lambda r: r.week)

    total = WeekModelRow(week="TOTAL", date_range="")
    for r in sorted_rows:
        total.opus_sessions += r.opus_sessions
        total.opus_output += r.opus_output
        total.opus_cost += r.opus_cost
        total.sonnet_sessions += r.sonnet_sessions
        total.sonnet_output += r.sonnet_output
        total.sonnet_cost += r.sonnet_cost
        total.other_sessions += r.other_sessions
        total.other_output += r.other_output
        total.other_cost += r.other_cost

    return WeeklyReport(rows=sorted_rows, total=total)
