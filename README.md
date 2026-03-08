# 🐉 Shenron 神龍

> *"Speak your wish and it shall be granted."*
>
> Shenron is the eternal dragon of Claude Code — summon it to recall every conversation,
> search your entire history, distill decisions into persistent memory, and see exactly
> how much value you're getting from your Claude Max subscription.

[![PyPI version](https://img.shields.io/pypi/v/shenron.svg)](https://pypi.org/project/shenron/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![License: MIT](10_System/Constitution/nomos/LICENSE.md)
[![Tests](https://github.com/robbery107allianz-cell/shenron/actions/workflows/ci.yml/badge.svg)](https://github.com/robbery107allianz-cell/shenron/actions)

---

## What is Shenron?

Claude Code stores every conversation in `~/.claude/projects/` as JSONL files.
After weeks of use, you have hundreds of sessions — an enormous personal knowledge base
with no way to search it.

**Shenron** gives you that power:

- **Search** your entire Claude Code history with keywords or regex
- **Browse** sessions with readable conversation formatting
- **Track** token usage and equivalent API costs across all projects
- **Export** any session to Markdown, JSON, or HTML
- **Resume** any past session instantly with `claude --resume`
- **Digest** any session into a structured decisions log — topic, key decisions, closing context
- **Focus** on what matters now — keyword frequency analysis against your full history baseline

Part of the **Dragon Ball universe** of Claude Code tools, alongside
[Kaioshin](https://github.com/robbery107allianz-cell/kaioshin) (the Supreme Kai security sandbox).

---

## Installation

```bash
pip install shenron
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install shenron
```

---

## Quick Start

```bash
# See all your sessions
shenron list

# Search your entire history
shenron search "docker compose"

# View the cost dashboard
shenron stats

# Show a session
shenron show abc12345

# Export a session to Markdown
shenron export abc12345 -f markdown -o session.md

# Resume the latest session
claude --resume $(shenron resume)

# Distill latest session into a decisions log
shenron digest --append ~/decisions.md

# See what topics are hot right now vs your full history
shenron focus
```

---

## Commands

### `shenron list` — Browse sessions

```
shenron list
shenron list --project myproject
shenron list --after 2026-01-01 --before 2026-03-01
shenron list --model sonnet
shenron list --sort tokens          # sort by token usage
shenron list --sort messages        # sort by message count
shenron list -n 50                  # show more results
shenron list --all                  # include subagent sessions
```

### `shenron show <id>` — Read a session

```
shenron show abc12345               # show by partial UUID
shenron show abc12345 --thinking    # include thinking blocks
shenron show abc12345 -n 20         # first 20 messages only
shenron show abc12345 --raw         # raw JSONL output
```

### `shenron search <query>` — Search history

```
shenron search "authentication"
shenron search "TODO" --type user           # only your messages
shenron search "Error" --type assistant     # only Claude's responses
shenron search "def \w+\(" --regex          # regex search
shenron search "secret" --case-sensitive
shenron search "api" --project myproject    # scope to one project
shenron search "bug" -n 100 -C 120         # 100 results, 120-char context
```

### `shenron stats` — Cost & usage dashboard

```
shenron stats                       # grouped by project (default)
shenron stats --by model            # grouped by model
shenron stats --by date             # grouped by day
shenron stats --top 5               # top 5 groups
shenron stats --after 2026-03-01    # this month only
shenron stats --subscription 200    # custom plan cost for multiplier
```

**Sample output:**
```
╭─────────────────────── shenron stats ────────────────────────╮
│ Claude Code — Equivalent API Cost                             │
│                                                               │
│   Input tokens:    158K                                       │
│   Output tokens:   1.9M                                       │
│   Cache reads:     634.8M                                     │
│   Total sessions:  67                                         │
│                                                               │
│   Equivalent cost: $1,435.67                                  │
│   vs Max $100/mo:  14.4x value                                │
╰───────────────────────────────────────────────────────────────╯

  Project                  Sessions   Input   Output   Cost (est.)   Share
 ────────────────────────────────────────────────────────────────────────
  ~/Desktop/crypto/…            16    135K     1.4M     $1115.12    ████████████ 77.7%
  ~/                            21     23K     436K      $272.06    ███░░░░░░░░░ 18.9%
  ...
```

> **Note:** Claude Max subscribers pay a flat monthly fee. The "Equivalent API Cost" shows
> what the same token consumption would cost at pay-as-you-go API rates — so you can see
> your actual subscription value.

### `shenron export <id>` — Export a session

```
shenron export abc12345                          # Markdown to stdout
shenron export abc12345 -f markdown -o out.md   # Markdown to file
shenron export abc12345 -f json -o out.json      # JSON
shenron export abc12345 -f html -o out.html      # Dark-theme HTML
```

### `shenron resume [id]` — Resume a session

```
shenron resume                      # print latest session ID
shenron resume abc12345             # print specific session ID
shenron resume --copy               # copy to clipboard (macOS)
claude --resume $(shenron resume)   # one-liner to resume latest
```

### `shenron info` — Overview

```
shenron info    # total sessions, disk usage, project list, date range
```

### `shenron digest [id]` — Distill a session into a decisions log

Extracts the key signal from a session — topic, decision-relevant exchanges,
and closing context — and formats it as a structured Markdown entry.
No LLM API required; uses heuristic signal-word detection.

```
shenron digest                              # digest latest session
shenron digest abc12345                     # digest specific session
shenron digest --append ~/decisions.md      # append to decisions log
shenron digest --all --after 2026-03-01 --append ~/decisions.md
                                            # batch: all recent sessions
shenron digest --max-key 5 --tail 2        # tune extraction depth
```

**What it extracts:**

| Field | How |
|-------|-----|
| Topic | First meaningful user message |
| Key decisions | Exchanges containing decision signal words (zh + en) |
| Closing context | Last N conversational exchanges (tool noise filtered) |

### `shenron focus` — Keyword frequency with historical baseline

Analyzes what you've been talking about recently and compares it against
your full session history. Shows three layers: relative spikes, recent
frequency, and the all-time baseline — so you can tell what's genuinely
new vs. what's always been part of your work.

```
shenron focus                               # 24h window vs full baseline
shenron focus --hours 48                    # wider recent window
shenron focus --top 30                      # more terms
shenron focus --output ~/focus.md           # write to file
shenron focus --all-msg                     # include assistant messages too
```

**Sample output:**

```
## Focus Weights · 注意力权重

### Spikes（past 24h vs full baseline）
  年级   ████████████████ ×18.5
  数学   ████████████████ ×18.1
  shadow ████████████████ ×12.4

### Recent 24h  (4 sessions · 829 msgs)
  年级   ████████████████  242
  数据   ██████████████░░  218
  shadow ██████████░░░░░░  150

### Baseline  (74 sessions · 5251 msgs)
  claude ████████████████  1061
  数据   █████████████░░░  1027
  shadow █████████████░░░  1020
```

**Automate with launchd** (runs every 12 hours):

```bash
# Install the scheduler (one-time setup)
cp launchd/com.1984.shenron.focus.plist ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/com.1984.shenron.focus.plist
```

---

## How it works

Claude Code saves every conversation as a JSONL file:

```
~/.claude/projects/
  -Users-you-Desktop-myproject/
    <session-uuid>.jsonl      ← one file per session
    agent-<uuid>.jsonl        ← subagent sessions (filtered by default)
```

Each line is a JSON message (`user`, `assistant`, `system`, etc.).
Shenron streams these files — **no database, no indexing, O(1) memory** —
and renders the results with Rich.

---

## Performance

| Scenario | Time |
|----------|------|
| `shenron list` (67 sessions) | ~0.3s |
| `shenron search "docker"` (67 sessions, 13K messages) | ~0.5s |
| `shenron stats` (67 sessions) | ~0.4s |

No background daemon. No SQLite. Just fast streaming.

---

## Dragon Ball Universe

Shenron pairs with **[Kaioshin](https://github.com/robbery107allianz-cell/kaioshin)**,
the Supreme Kai security sandbox for Claude Code.

| Tool | Dragon Ball | Role |
|------|-------------|------|
| [Kaioshin](https://github.com/robbery107allianz-cell/kaioshin) | 界王神 Supreme Kai | Kernel-level security sandbox |
| Shenron | 神龍 Eternal Dragon | Session history & analytics |

```
kaioshin  →  keeps Claude safe while it works
shenron   →  remembers everything Claude did
```

---

## Development

```bash
git clone https://github.com/robbery107allianz-cell/shenron
cd shenron
pip install -e ".[dev]"
pytest --cov
```

---

## License

MIT © 小code & Rob

---

*Summon the Dragon. Recall everything.*
