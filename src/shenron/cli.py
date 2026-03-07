"""Shenron CLI — Typer application with all commands."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from shenron import __version__
from shenron.config import DEFAULT_LIMIT, DEFAULT_TOP_N, PROJECTS_DIR
from shenron.discovery import discover_sessions as _discover_sessions
from shenron.formatter import (
    console,
    print_info,
    print_search_results,
    print_session_detail,
    print_session_list,
    print_stats,
)
from shenron.models import SessionMeta
from shenron.parser import parse_session, parse_session_meta_fields, stream_messages

app = typer.Typer(
    name="shenron",
    help="Shenron 神龍 — Claude Code Session History Manager\n\nSummon the Dragon. Recall everything.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    add_completion=False,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_date(date_str: str | None, label: str) -> datetime | None:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as err:
        console.print(f"[red]Invalid {label} date '{date_str}'. Use YYYY-MM-DD format.[/red]")
        raise typer.Exit(1) from err


def _find_session(session_id_prefix: str, projects_dir: Path = PROJECTS_DIR) -> SessionMeta | None:
    """Find a session by full or partial UUID."""
    prefix = session_id_prefix.lower()
    for meta in _discover_sessions(projects_dir=projects_dir):
        if meta.session_id.lower().startswith(prefix):
            return meta
    return None


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"shenron {__version__}")
        raise typer.Exit()


# ─── Commands ─────────────────────────────────────────────────────────────────

@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", "-V", callback=_version_callback, is_eager=True, help="Show version"),
    ] = None,
) -> None:
    pass


@app.command(name="list")
def list_sessions(
    project: Annotated[str | None, typer.Option("--project", "-p", help="Filter by project name")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max sessions to show")] = DEFAULT_LIMIT,
    after: Annotated[str | None, typer.Option("--after", help="Show sessions after date (YYYY-MM-DD)")] = None,
    before: Annotated[str | None, typer.Option("--before", help="Show sessions before date (YYYY-MM-DD)")] = None,
    model: Annotated[str | None, typer.Option("--model", help="Filter by model name")] = None,
    sort: Annotated[str, typer.Option("--sort", "-s", help="Sort by: date|tokens|messages")] = "date",
    include_agents: Annotated[bool, typer.Option("--all", "-a", help="Include subagent sessions")] = False,
) -> None:
    """List Claude Code sessions."""
    after_dt = _parse_date(after, "after")
    before_dt = _parse_date(before, "before")

    all_sessions: list[tuple[SessionMeta, dict]] = []

    for meta in _discover_sessions(
        project_filter=project,
        after=after_dt,
        before=before_dt,
        include_agents=include_agents,
    ):
        fields = parse_session_meta_fields(meta.file_path)

        # Count messages and tokens in one pass
        msg_count = 0
        total_tokens = 0
        for msg in stream_messages(meta.file_path):
            msg_count += 1
            if msg.usage:
                total_tokens += msg.usage.input_tokens + msg.usage.output_tokens

        fields["msg_count"] = msg_count
        fields["total_tokens"] = total_tokens

        # Duration from timestamps
        first_ts = fields.get("first_timestamp")
        last_ts = meta.modified_time
        if first_ts and last_ts:
            fields["duration_seconds"] = (last_ts - first_ts).total_seconds()

        # Use cwd for a better project name when available
        cwd = fields.get("cwd")
        if cwd:
            home = str(Path.home())
            display = cwd.replace(home, "~") if cwd.startswith(home) else cwd
            fields["display_project"] = display
        else:
            fields["display_project"] = meta.project_name

        # Model filter
        if model and model.lower() not in (fields.get("model") or "").lower():
            continue

        all_sessions.append((meta, fields))

    # Sort
    if sort == "tokens":
        all_sessions.sort(key=lambda x: x[1].get("total_tokens", 0), reverse=True)
    elif sort == "messages":
        all_sessions.sort(key=lambda x: x[1].get("msg_count", 0), reverse=True)
    else:  # date (default)
        all_sessions.sort(
            key=lambda x: x[1].get("first_timestamp") or x[0].modified_time,
            reverse=True,
        )

    total = len(all_sessions)
    shown_sessions = all_sessions[:limit]

    if not shown_sessions:
        console.print("\n  [yellow]No sessions found.[/yellow]\n")
        return

    print_session_list(shown_sessions, total=total, shown=len(shown_sessions))


@app.command()
def show(
    session_id: Annotated[str, typer.Argument(help="Session UUID or prefix (first 8+ chars)")],
    thinking: Annotated[bool, typer.Option("--thinking/--no-thinking", help="Include thinking blocks")] = False,
    tools: Annotated[bool, typer.Option("--tools/--no-tools", help="Include tool calls")] = True,
    limit: Annotated[int | None, typer.Option("--limit", "-n", help="Show only first N messages")] = None,
    raw: Annotated[bool, typer.Option("--raw", help="Show raw JSONL")] = False,
) -> None:
    """Display a session in readable format."""
    meta = _find_session(session_id)
    if not meta:
        console.print(f"\n  [red]Session not found:[/red] [bold]{session_id}[/bold]\n")
        console.print("  [dim]Tip: Use [bold]shenron list[/bold] to see available sessions.[/dim]\n")
        raise typer.Exit(1)

    if raw:
        with open(meta.file_path, encoding="utf-8") as f:
            for line in f:
                console.print(line, end="")
        return

    session = parse_session(meta)
    print_session_detail(session, include_thinking=thinking, limit=limit)


@app.command()
def info() -> None:
    """Show overview: total sessions, disk usage, projects, date range."""
    all_meta = list(_discover_sessions())

    if not all_meta:
        console.print("\n  [yellow]No sessions found in ~/.claude/projects/[/yellow]\n")
        return

    total_size = sum(m.file_size for m in all_meta)
    projects = list({m.project_name for m in all_meta})  # unique

    # Date range
    dates = [m.modified_time for m in all_meta]
    date_range = (
        min(dates).strftime("%Y-%m-%d"),
        max(dates).strftime("%Y-%m-%d"),
    ) if dates else None

    print_info(
        total_sessions=len(all_meta),
        total_size=total_size,
        projects=projects,
        date_range=date_range,
    )


@app.command()
def resume(
    session_id: Annotated[str | None, typer.Argument(help="Session UUID or prefix (omit for latest)")] = None,
    project: Annotated[str | None, typer.Option("--project", "-p", help="Filter to project")] = None,
    copy: Annotated[bool, typer.Option("--copy", help="Copy to clipboard (macOS pbcopy)")] = False,
) -> None:
    """Print session ID for use with 'claude --resume'."""
    if session_id:
        meta = _find_session(session_id)
        if not meta:
            console.print(f"\n  [red]Session not found:[/red] {session_id}\n")
            raise typer.Exit(1)
    else:
        # Get latest session
        sessions = list(_discover_sessions(project_filter=project))
        if not sessions:
            console.print("\n  [yellow]No sessions found.[/yellow]\n")
            raise typer.Exit(1)
        meta = sorted(sessions, key=lambda m: m.modified_time, reverse=True)[0]

    sid = meta.session_id

    if copy:
        import subprocess
        subprocess.run(["pbcopy"], input=sid.encode(), check=True)
        console.print(f"\n  [green]✓ Copied to clipboard:[/green] {sid}\n")
        console.print(f"  [dim]Run:[/dim] claude --resume {sid}\n")
    else:
        # Print bare ID for shell piping: claude --resume $(shenron resume)
        print(sid)


@app.command()
def search(
    query: Annotated[list[str], typer.Argument(help="Search terms — multiple terms = AND logic")],
    project: Annotated[str | None, typer.Option("--project", "-p", help="Filter by project name")] = None,
    regex: Annotated[bool, typer.Option("--regex", "-r", help="Treat query as regex")] = False,
    case_sensitive: Annotated[bool, typer.Option("--case-sensitive", "-c", help="Case-sensitive search")] = False,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max total matches")] = 50,
    context: Annotated[int, typer.Option("--context", "-C", help="Context chars around match")] = 80,
    message_type: Annotated[str | None, typer.Option("--type", "-t", help="Filter: user|assistant|both")] = None,
    model: Annotated[str | None, typer.Option("--model", help="Filter by model name")] = None,
    after: Annotated[str | None, typer.Option("--after", help="Sessions after date (YYYY-MM-DD)")] = None,
    before: Annotated[str | None, typer.Option("--before", help="Sessions before date (YYYY-MM-DD)")] = None,
) -> None:
    """Search across all Claude Code sessions."""
    from shenron.searcher import search as _search

    after_dt = _parse_date(after, "after")
    before_dt = _parse_date(before, "before")

    sessions = list(_discover_sessions(
        project_filter=project,
        after=after_dt,
        before=before_dt,
    ))

    if not sessions:
        console.print("\n  [yellow]No sessions found.[/yellow]\n")
        return

    # Build message type filter
    type_filter: set[str] | None = None
    if message_type == "user":
        type_filter = {"user"}
    elif message_type == "assistant":
        type_filter = {"assistant"}
    # "both" or None → default (user + assistant)

    results_iter = _search(
        terms=query,
        sessions=sessions,
        regex=regex,
        case_sensitive=case_sensitive,
        message_types=type_filter,
        model_filter=model,
        limit=limit,
        context_chars=context,
    )

    query_display = " AND ".join(query)
    matched_sessions, total_matches = print_search_results(results_iter, query=query_display, total_limit=limit)

    # Interactive follow-up: open a session for full view
    if total_matches > 0 and len(matched_sessions) > 0:
        console.print()
        choices = "/".join(str(i + 1) for i in range(len(matched_sessions)))
        raw = console.input(f"  [dim]Open session ❲{choices}❳ or Enter to exit: [/dim]").strip()
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(matched_sessions):
                chosen = matched_sessions[idx]
                from shenron.parser import parse_session
                session = parse_session(chosen)
                print_session_detail(session)
            else:
                console.print("  [yellow]Invalid number.[/yellow]\n")
        console.print()


@app.command()
def stats(
    group_by: Annotated[str, typer.Option("--by", "-b", help="Group by: project|model|date")] = "project",
    top: Annotated[int, typer.Option("--top", "-t", help="Show top N groups")] = DEFAULT_TOP_N,
    project: Annotated[str | None, typer.Option("--project", "-p", help="Filter by project name")] = None,
    after: Annotated[str | None, typer.Option("--after", help="Sessions after date (YYYY-MM-DD)")] = None,
    before: Annotated[str | None, typer.Option("--before", help="Sessions before date (YYYY-MM-DD)")] = None,
    subscription: Annotated[float, typer.Option("--subscription", help="Monthly subscription cost USD")] = 100.0,
) -> None:
    """Show token usage and equivalent API cost dashboard."""
    from shenron.stats import compute_stats

    after_dt = _parse_date(after, "after")
    before_dt = _parse_date(before, "before")

    if group_by not in ("project", "model", "date"):
        console.print("[red]--by must be one of: project, model, date[/red]")
        raise typer.Exit(1)

    sessions = list(_discover_sessions(
        project_filter=project,
        after=after_dt,
        before=before_dt,
    ))

    if not sessions:
        console.print("\n  [yellow]No sessions found.[/yellow]\n")
        return

    report = compute_stats(sessions, group_by=group_by, top_n=top)
    print_stats(report, subscription_usd=subscription)


@app.command()
def focus(
    hours: Annotated[int, typer.Option("--hours", "-h", help="Look-back window in hours")] = 24,
    top: Annotated[int, typer.Option("--top", "-t", help="Top N terms to show")] = 20,
    output: Annotated[str | None, typer.Option("--output", "-o", help="Write to file (default: stdout)")] = None,
    all_messages: Annotated[bool, typer.Option("--all-msg", help="Include assistant messages too")] = False,
) -> None:
    """Analyze recent session keyword frequency — what topics are hot right now."""
    from shenron.focuser import analyze, render_markdown

    sessions = list(_discover_sessions())
    if not sessions:
        console.print("\n  [yellow]No sessions found.[/yellow]\n")
        raise typer.Exit(1)

    report = analyze(sessions, hours=hours, top_n=top, user_only=not all_messages)

    if not report.top_terms:
        console.print(f"\n  [yellow]No keywords found in the last {hours}h.[/yellow]\n")
        raise typer.Exit(0)

    content = render_markdown(report)

    if output:
        out_path = Path(output)
        out_path.write_text(content, encoding="utf-8")
        console.print(f"\n  [green]✓ Focus report written to:[/green] {out_path}\n")
    else:
        console.print(content)


@app.command()
def digest(
    session_id: Annotated[str | None, typer.Argument(help="Session UUID or prefix (omit for latest)")] = None,
    project: Annotated[str | None, typer.Option("--project", "-p", help="Filter to project")] = None,
    tail: Annotated[int, typer.Option("--tail", "-t", help="Tail exchanges for closing context")] = 3,
    max_key: Annotated[int, typer.Option("--max-key", "-k", help="Max key decision exchanges")] = 8,
    append: Annotated[str | None, typer.Option("--append", "-a", help="Append to decisions.md file")] = None,
    after: Annotated[str | None, typer.Option("--after", help="Digest sessions after date (YYYY-MM-DD)")] = None,
    before: Annotated[str | None, typer.Option("--before", help="Digest sessions before date (YYYY-MM-DD)")] = None,
    all_recent: Annotated[bool, typer.Option("--all", help="Digest all sessions in date range")] = False,
) -> None:
    """Digest a session into a structured decisions.md entry."""
    from shenron.digester import digest_session, render_markdown
    from shenron.parser import parse_session

    after_dt = _parse_date(after, "after")
    before_dt = _parse_date(before, "before")

    if all_recent:
        sessions = list(_discover_sessions(
            project_filter=project,
            after=after_dt,
            before=before_dt,
        ))
        if not sessions:
            console.print("\n  [yellow]No sessions found.[/yellow]\n")
            raise typer.Exit(1)
        metas = sorted(sessions, key=lambda m: m.modified_time, reverse=True)
    elif session_id:
        meta = _find_session(session_id)
        if not meta:
            console.print(f"\n  [red]Session not found:[/red] [bold]{session_id}[/bold]\n")
            raise typer.Exit(1)
        metas = [meta]
    else:
        sessions = list(_discover_sessions(project_filter=project))
        if not sessions:
            console.print("\n  [yellow]No sessions found.[/yellow]\n")
            raise typer.Exit(1)
        metas = [sorted(sessions, key=lambda m: m.modified_time, reverse=True)[0]]

    blocks: list[str] = []
    for meta in metas:
        session = parse_session(meta)
        entry = digest_session(session, tail_n=tail, max_key=max_key)
        blocks.append(render_markdown(entry))

    output = "\n".join(blocks)

    if append:
        out_path = Path(append)
        # Write header if file doesn't exist yet
        if not out_path.exists():
            out_path.write_text("# Decisions Log\n\n", encoding="utf-8")
        with out_path.open("a", encoding="utf-8") as f:
            f.write(output)
        console.print(f"\n  [green]Appended {len(metas)} digest(s) to:[/green] {out_path}\n")
    else:
        console.print(output)


@app.command()
def export(
    session_id: Annotated[str, typer.Argument(help="Session UUID or prefix")],
    fmt: Annotated[str, typer.Option("--format", "-f", help="Output format: markdown|json|html")] = "markdown",
    output: Annotated[str | None, typer.Option("--output", "-o", help="Output file (default: stdout)")] = None,
) -> None:
    """Export a session to Markdown, JSON, or HTML."""
    from shenron.exporter import export_session

    if fmt not in ("markdown", "json", "html"):
        console.print("[red]--format must be one of: markdown, json, html[/red]")
        raise typer.Exit(1)

    meta = _find_session(session_id)
    if not meta:
        console.print(f"\n  [red]Session not found:[/red] [bold]{session_id}[/bold]\n")
        raise typer.Exit(1)

    session = parse_session(meta)
    content = export_session(session, fmt=fmt)

    if output:
        out_path = Path(output)
        out_path.write_text(content, encoding="utf-8")
        console.print(f"\n  [green]✓ Exported to:[/green] {out_path}\n")
    else:
        print(content)
