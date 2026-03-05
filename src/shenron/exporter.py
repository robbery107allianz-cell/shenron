"""Export sessions to Markdown, JSON, or HTML."""

from __future__ import annotations

import json

from shenron.models import Message, Session
from shenron.pricing import compute_cost

# ─── Markdown ─────────────────────────────────────────────────────────────────

def _msg_to_markdown(msg: Message) -> str:
    lines: list[str] = []
    ts = msg.timestamp.strftime("%H:%M:%S") if msg.timestamp else ""

    if msg.msg_type == "user":
        lines.append(f"### 👤 You  `{ts}`")
    else:
        model = msg.model or "assistant"
        lines.append(f"### 🤖 {model}  `{ts}`")
        if msg.usage:
            u = msg.usage
            lines.append(
                f"> `+{u.input_tokens:,} in  {u.output_tokens:,} out`"
            )

    lines.append("")

    text = msg.content_text.strip()
    if text:
        lines.append(text)

    if msg.tool_names:
        for t in msg.tool_names:
            lines.append(f"- ⚙ `{t}`")

    return "\n".join(lines)


def to_markdown(session: Session) -> str:
    meta = session.meta
    usage = session.total_usage
    date_str = session.first_timestamp.strftime("%Y-%m-%d %H:%M") if session.first_timestamp else "—"
    models = ", ".join(sorted(session.models_used)) or "—"

    cost = sum(
        compute_cost(
            model=m.model,
            input_tokens=m.usage.input_tokens if m.usage else 0,
            output_tokens=m.usage.output_tokens if m.usage else 0,
            cache_write_tokens=m.usage.cache_creation_input_tokens if m.usage else 0,
            cache_read_tokens=m.usage.cache_read_input_tokens if m.usage else 0,
        )
        for m in session.assistant_messages
    )

    lines = [
        f"# Session: {meta.session_id}",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| Project | `{session.cwd or meta.project_name}` |",
        f"| Date | {date_str} |",
        f"| Model | {models} |",
        f"| Branch | {session.git_branch or '—'} |",
        f"| Input tokens | {usage.input_tokens:,} |",
        f"| Output tokens | {usage.output_tokens:,} |",
        f"| Est. API cost | ${cost:.4f} |",
        "",
        "---",
        "",
    ]

    for msg in session.messages:
        if msg.msg_type in ("user", "assistant"):
            lines.append(_msg_to_markdown(msg))
            lines.append("")
            lines.append("---")
            lines.append("")

    return "\n".join(lines)


# ─── JSON ─────────────────────────────────────────────────────────────────────

def to_json(session: Session, indent: int = 2) -> str:
    meta = session.meta

    messages = []
    for msg in session.messages:
        if msg.msg_type not in ("user", "assistant"):
            continue
        entry: dict = {
            "uuid": msg.uuid,
            "role": msg.msg_type,
            "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
            "content": msg.content_text,
        }
        if msg.model:
            entry["model"] = msg.model
        if msg.usage:
            entry["usage"] = {
                "input_tokens": msg.usage.input_tokens,
                "output_tokens": msg.usage.output_tokens,
                "cache_creation_input_tokens": msg.usage.cache_creation_input_tokens,
                "cache_read_input_tokens": msg.usage.cache_read_input_tokens,
            }
        if msg.tool_names:
            entry["tools"] = list(msg.tool_names)
        messages.append(entry)

    usage = session.total_usage
    doc = {
        "session_id": meta.session_id,
        "project": session.cwd or meta.project_name,
        "date": session.first_timestamp.isoformat() if session.first_timestamp else None,
        "git_branch": session.git_branch,
        "models": sorted(session.models_used),
        "usage": {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
        },
        "messages": messages,
    }
    return json.dumps(doc, ensure_ascii=False, indent=indent)


# ─── HTML ─────────────────────────────────────────────────────────────────────

_HTML_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       max-width: 860px; margin: 40px auto; padding: 0 20px;
       background: #0d1117; color: #c9d1d9; }
h1 { color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 12px; }
table { border-collapse: collapse; margin-bottom: 24px; }
td, th { padding: 6px 12px; border: 1px solid #30363d; }
th { background: #161b22; color: #8b949e; }
.msg { margin: 16px 0; padding: 14px 18px; border-radius: 8px; }
.user { background: #1c2333; border-left: 3px solid #388bfd; }
.assistant { background: #161b22; border-left: 3px solid #bc8cff; }
.label { font-weight: bold; font-size: 0.85em; margin-bottom: 6px; }
.user .label { color: #388bfd; }
.assistant .label { color: #bc8cff; }
.ts { color: #8b949e; font-size: 0.8em; margin-left: 8px; }
.meta { color: #8b949e; font-size: 0.8em; margin-top: 4px; }
.content { white-space: pre-wrap; word-break: break-word; }
.tool { color: #e3b341; font-size: 0.85em; }
hr { border: none; border-top: 1px solid #30363d; margin: 8px 0; }
"""


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
    )


def _msg_to_html(msg: Message) -> str:
    ts = msg.timestamp.strftime("%H:%M:%S") if msg.timestamp else ""

    if msg.msg_type == "user":
        role_class = "user"
        label = "You"
    else:
        role_class = "assistant"
        label = msg.model or "Assistant"

    content = _escape_html(msg.content_text.strip()) if msg.content_text else ""

    usage_html = ""
    if msg.usage:
        u = msg.usage
        usage_html = (
            f'<div class="meta">+{u.input_tokens:,}&nbsp;in&nbsp;&nbsp;'
            f'{u.output_tokens:,}&nbsp;out</div>'
        )

    tools_html = ""
    if msg.tool_names:
        tool_items = "".join(f'<span class="tool">⚙ {_escape_html(t)}</span><br>' for t in msg.tool_names)
        tools_html = f"<div>{tool_items}</div>"

    return (
        f'<div class="msg {role_class}">'
        f'<div class="label">{_escape_html(label)}<span class="ts">{ts}</span></div>'
        f"{usage_html}"
        f'<div class="content">{content}</div>'
        f"{tools_html}"
        f"</div>"
    )


def to_html(session: Session) -> str:
    meta = session.meta
    usage = session.total_usage
    date_str = session.first_timestamp.strftime("%Y-%m-%d %H:%M") if session.first_timestamp else "—"
    models = ", ".join(sorted(session.models_used)) or "—"

    cost = sum(
        compute_cost(
            model=m.model,
            input_tokens=m.usage.input_tokens if m.usage else 0,
            output_tokens=m.usage.output_tokens if m.usage else 0,
            cache_write_tokens=m.usage.cache_creation_input_tokens if m.usage else 0,
            cache_read_tokens=m.usage.cache_read_input_tokens if m.usage else 0,
        )
        for m in session.assistant_messages
    )

    project = _escape_html(session.cwd or meta.project_name)

    meta_table = f"""
<table>
  <tr><th>Session</th><td><code>{meta.session_id}</code></td></tr>
  <tr><th>Project</th><td><code>{project}</code></td></tr>
  <tr><th>Date</th><td>{date_str}</td></tr>
  <tr><th>Model</th><td>{_escape_html(models)}</td></tr>
  <tr><th>Branch</th><td>{_escape_html(session.git_branch or '—')}</td></tr>
  <tr><th>Input tokens</th><td>{usage.input_tokens:,}</td></tr>
  <tr><th>Output tokens</th><td>{usage.output_tokens:,}</td></tr>
  <tr><th>Est. API cost</th><td>${cost:.4f}</td></tr>
</table>"""

    messages_html = "\n".join(
        _msg_to_html(m)
        for m in session.messages
        if m.msg_type in ("user", "assistant")
    )

    title = f"Session {meta.session_id[:8]}"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — Shenron 神龍</title>
  <style>{_HTML_CSS}</style>
</head>
<body>
  <h1>🐉 {title}</h1>
  {meta_table}
  <hr>
  {messages_html}
</body>
</html>"""


# ─── Dispatch ─────────────────────────────────────────────────────────────────

def export_session(session: Session, fmt: str) -> str:
    """Return exported content as a string. fmt: 'markdown' | 'json' | 'html'."""
    if fmt == "json":
        return to_json(session)
    if fmt == "html":
        return to_html(session)
    return to_markdown(session)  # default: markdown
