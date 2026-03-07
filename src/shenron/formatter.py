"""Rich terminal rendering for Shenron — all display logic lives here."""

from typing import TYPE_CHECKING

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from shenron.config import MAX_PREVIEW_LEN
from shenron.models import Session, SessionMeta

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from shenron.searcher import SearchResult
    from shenron.stats import StatsReport

console = Console(highlight=False)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _truncate(text: str, max_len: int = MAX_PREVIEW_LEN) -> str:
    # Strip markup-like chars that confuse Rich, collapse whitespace
    text = text.replace("\n", " ").replace("\r", "").replace("[", "❲").replace("]", "❳").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}h{m:02d}m"


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def _fmt_size(n: int) -> str:
    if n >= 1_048_576:
        return f"{n / 1_048_576:.1f} MB"
    if n >= 1_024:
        return f"{n / 1_024:.0f} KB"
    return f"{n} B"


def _short_model(model: str | None) -> str:
    if not model:
        return "—"
    return (
        model.replace("claude-opus-4-6", "Opus")
             .replace("claude-sonnet-4-6", "Sonnet")
             .replace("claude-haiku-4-5-20251001", "Haiku")
             .replace("claude-haiku-4-5", "Haiku")
    )


def _short_id(session_id: str) -> str:
    return session_id[:8]


# ─── Session List ─────────────────────────────────────────────────────────────

def print_session_list(
    sessions: "Iterable[tuple[SessionMeta, dict]]",
    total: int,
    shown: int,
) -> None:
    """Render a compact table of sessions."""
    table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold cyan",
        expand=False,
        pad_edge=True,
    )
    table.add_column("Date", width=10, no_wrap=True, style="cyan")
    table.add_column("ID", width=8, no_wrap=True, style="dim")
    table.add_column("Model", width=6, no_wrap=True)
    table.add_column("Msgs", width=4, justify="right")
    table.add_column("Tokens", width=6, justify="right")
    table.add_column("Project", width=22, no_wrap=True)
    table.add_column("First Message", no_wrap=True, max_width=45)

    for _, (meta, fields) in enumerate(sessions, 1):
        date = ""
        if fields.get("first_timestamp"):
            date = fields["first_timestamp"].strftime("%Y-%m-%d")
        elif meta.modified_time:
            date = meta.modified_time.strftime("%Y-%m-%d")

        model = _short_model(fields.get("model"))
        msg_count = str(fields.get("msg_count", "—"))
        tokens = _fmt_tokens(fields.get("total_tokens", 0))
        preview = _truncate(fields.get("first_user_text", ""), 45)
        project = _truncate(fields.get("display_project", meta.project_name), 22)

        table.add_row(
            date,
            _short_id(meta.session_id),
            model,
            msg_count,
            tokens,
            project,
            preview,
        )

    console.print()
    console.print(table)
    if total > shown:
        console.print(
            f"  [dim]Showing {shown}/{total}. Use [bold]-n {total}[/bold] to show all.[/dim]"
        )
    console.print()


# ─── Session Detail ───────────────────────────────────────────────────────────

def print_session_detail(session: Session, include_thinking: bool = False, limit: int | None = None) -> None:
    """Render a full session in readable conversation format."""
    meta = session.meta
    usage = session.total_usage
    models = ", ".join(sorted(session.models_used)) or "—"

    date_str = session.first_timestamp.strftime("%Y-%m-%d %H:%M") if session.first_timestamp else "—"
    duration_str = _fmt_duration(session.duration_seconds)
    token_str = f"{_fmt_tokens(usage.input_tokens)} in / {_fmt_tokens(usage.output_tokens)} out"

    header_lines = [
        f"[bold cyan]{session.cwd or meta.project_name}[/bold cyan]",
        f"[dim]Session:[/dim] {meta.session_id}",
        f"[dim]Date:[/dim]    {date_str}   [dim]Duration:[/dim] {duration_str}",
        f"[dim]Model:[/dim]   {models}",
        f"[dim]Tokens:[/dim]  {token_str}",
    ]
    if session.git_branch:
        header_lines.append(f"[dim]Branch:[/dim]  {session.git_branch}")

    console.print()
    console.print(Panel("\n".join(header_lines), title="[bold]Shenron 神龍[/bold]", border_style="cyan"))
    console.print()

    messages = session.messages
    if limit:
        messages = messages[:limit]

    for msg in messages:
        if msg.msg_type == "user":
            _print_user_message(msg)
        elif msg.msg_type == "assistant":
            _print_assistant_message(msg, include_thinking)

    console.print()


def _print_user_message(msg) -> None:
    text = msg.content_text.strip()
    if not text:
        return
    label = Text("  YOU  ", style="bold white on blue")
    console.print(label, end=" ")
    console.print(f"[dim]{msg.timestamp.strftime('%H:%M:%S')}[/dim]")
    console.print(f"  {text}\n")


def _print_assistant_message(msg, include_thinking: bool = False) -> None:
    model_label = _short_model(msg.model)
    label = Text(f"  {model_label.upper()}  ", style="bold white on magenta")
    console.print(label, end=" ")
    if msg.usage:
        tok = f"[dim]+{msg.usage.input_tokens:,}in {msg.usage.output_tokens:,}out[/dim]"
        console.print(tok, end="  ")
    console.print(f"[dim]{msg.timestamp.strftime('%H:%M:%S')}[/dim]")

    text = msg.content_text.strip()
    if text:
        console.print(f"  {text}")

    if msg.tool_names:
        for tool in msg.tool_names:
            console.print(f"  [yellow]⚙ {tool}[/yellow]")

    console.print()


# ─── Info Panel ───────────────────────────────────────────────────────────────

def print_info(
    total_sessions: int,
    total_size: int,
    projects: list[str],
    date_range: tuple[str, str] | None,
) -> None:
    lines = [
        "[bold cyan]Claude Code Session Data[/bold cyan]",
        "",
        f"  Sessions:  [bold]{total_sessions}[/bold]",
        f"  Disk:      [bold]{_fmt_size(total_size)}[/bold]",
        f"  Projects:  [bold]{len(projects)}[/bold]",
    ]
    if date_range:
        lines.append(f"  Range:     [bold]{date_range[0]}[/bold] → [bold]{date_range[1]}[/bold]")
    lines += ["", "  Projects:"]
    for p in sorted(set(projects)):
        lines.append(f"    [dim]•[/dim] {p}")

    console.print()
    console.print(Panel("\n".join(lines), border_style="cyan", title="[bold]shenron info[/bold]"))
    console.print()


# ─── Search Results ───────────────────────────────────────────────────────────

def _escape(text: str) -> str:
    """Escape Rich markup chars in user text."""
    return text.replace("[", "❲").replace("]", "❳")


def print_search_results(
    results_iter: "Iterator[tuple[SessionMeta, list[SearchResult]]]",
    query: str,
    total_limit: int,
) -> tuple[list[SessionMeta], int]:
    """Render search results with highlighted matches.

    Returns (matched_sessions, total_matches) for interactive follow-up.
    """
    total_matches = 0
    matched_sessions: list[SessionMeta] = []

    console.print()

    for meta, session_results in results_iter:
        matched_sessions.append(meta)
        n = len(matched_sessions)

        # Session header with index number
        date_str = meta.modified_time.strftime("%Y-%m-%d") if meta.modified_time else "—"
        sid = _short_id(meta.session_id)
        console.print(
            f"[bold cyan]▶ [{n}] {meta.project_name}[/bold cyan]  "
            f"[dim]{sid}  {date_str}[/dim]"
        )

        for result in session_results:
            total_matches += 1
            msg = result.message
            role = "YOU" if msg.msg_type == "user" else _short_model(msg.model).upper()
            ts = msg.timestamp.strftime("%H:%M") if msg.timestamp else ""

            before = _escape(result.context_before)
            matched = _escape(result.match_text)
            after = _escape(result.context_after)

            line = Text()
            line.append(f"  [{role} {ts}] ", style="dim")
            line.append(before)
            line.append(matched, style="bold yellow on black")
            line.append(after)

            console.print(line)

        console.print()

    if total_matches == 0:
        console.print(f"  [yellow]No results found for:[/yellow] [bold]{query}[/bold]\n")
    else:
        console.print(
            f"  [dim]Found [bold]{total_matches}[/bold] match{'es' if total_matches != 1 else ''} "
            f"across [bold]{len(matched_sessions)}[/bold] session{'s' if len(matched_sessions) != 1 else ''}.[/dim]"
        )

    return matched_sessions, total_matches


# ─── Stats Dashboard ──────────────────────────────────────────────────────────

def _fmt_cost(usd: float) -> str:
    if usd >= 1.0:
        return f"${usd:.2f}"
    if usd >= 0.001:
        return f"${usd:.4f}"
    return f"${usd:.6f}"


def _bar(fraction: float, width: int = 12) -> str:
    """Simple ASCII progress bar."""
    filled = int(round(fraction * width))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def print_stats(report: "StatsReport", subscription_usd: float = 100.0) -> None:
    """Render the token usage and equivalent cost dashboard."""
    t = report.totals
    group_label = report.group_by.capitalize()

    # ── Header panel ──
    multiplier = t.cost_usd / subscription_usd if subscription_usd > 0 else 0
    header_lines = [
        "[bold cyan]Claude Code — Equivalent API Cost[/bold cyan]",
        "[dim](Claude Max subscribers are billed a flat fee — these figures",
        "show what the same usage would cost at pay-as-you-go API rates.)[/dim]",
        "",
        f"  Input tokens:    [bold]{_fmt_tokens(t.input_tokens)}[/bold]",
        f"  Output tokens:   [bold]{_fmt_tokens(t.output_tokens)}[/bold]",
        f"  Cache writes:    [bold]{_fmt_tokens(t.cache_write_tokens)}[/bold]",
        f"  Cache reads:     [bold]{_fmt_tokens(t.cache_read_tokens)}[/bold]",
        f"  Total sessions:  [bold]{t.sessions}[/bold]",
        f"  Total messages:  [bold]{t.messages}[/bold]",
        "",
        f"  Equivalent cost: [bold green]{_fmt_cost(t.cost_usd)}[/bold green]",
        f"  vs Max $100/mo:  [bold yellow]{multiplier:.1f}x value[/bold yellow]",
    ]
    console.print()
    console.print(Panel("\n".join(header_lines), title="[bold]shenron stats[/bold]", border_style="cyan"))
    console.print()

    if not report.groups:
        return

    # ── Breakdown table ──
    max_cost = max(g.cost_usd for g in report.groups) or 1.0

    table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold cyan",
        expand=False,
        pad_edge=True,
    )
    table.add_column(group_label, no_wrap=True, max_width=30)
    table.add_column("Sessions", width=8, justify="right")
    table.add_column("Input", width=7, justify="right")
    table.add_column("Output", width=7, justify="right")
    table.add_column("Cost (est.)", width=10, justify="right")
    table.add_column("Share", width=14, no_wrap=True)

    for g in report.groups:
        share = g.cost_usd / t.cost_usd if t.cost_usd > 0 else 0
        bar = _bar(g.cost_usd / max_cost)
        pct = f"{share * 100:.1f}%"
        table.add_row(
            _truncate(g.label, 30),
            str(g.sessions),
            _fmt_tokens(g.input_tokens),
            _fmt_tokens(g.output_tokens),
            _fmt_cost(g.cost_usd),
            f"{bar} {pct}",
        )

    console.print(table)
    console.print()
