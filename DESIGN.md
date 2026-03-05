# Shenron 神龍 — Design Whitepaper

> *In Dragon Ball, Shenron is the Eternal Dragon summoned by gathering seven Dragon Balls.
> He grants any wish. Shenron gathers your scattered Claude Code sessions and grants
> your wish to search, analyze, and understand them.*

**Version**: 0.1 Draft
**Authors**: 小code (Claude Opus) & Rob
**Date**: 2026-03-05
**Status**: Design Phase — Implementation pending

---

## 1. Problem Statement

Claude Code stores all conversation history as `.jsonl` files in `~/.claude/projects/`. As usage grows, this becomes a significant local dataset:

| Timeframe | Estimated Sessions | Estimated Size |
|-----------|--------------------|----------------|
| 1 month   | 150+               | ~75 MB         |
| 1 year    | 2,000+             | ~1 GB          |
| 3 years   | 6,000+             | ~3 GB          |

**Without a search tool, this history is dead data.** Users can't:
- Find a conversation from weeks ago
- Know how much they actually consumed in tokens
- Understand their Max subscription's value
- Export important sessions for documentation
- Resume a specific past session easily

## 2. Market Analysis

### Existing Tools (10+ identified)

| Tool | Language | Strength | Weakness |
|------|----------|----------|----------|
| [claude-history](https://github.com/raine/claude-history) | Rust | Fuzzy TUI, fast | No analytics, no export |
| [claude-conversation-extractor](https://pypi.org/project/claude-conversation-extractor/) | Python | Export to Markdown | No search, no stats |
| [cass](https://github.com/Dicklesworthstone/coding_agent_session_search) | Python | Cross-tool (11 agents) | Broad not deep |
| [cc-conversation-search](https://github.com/akatz-ai/cc-conversation-search) | Python | Semantic search | No cost analysis |
| [claude-history-explorer](https://github.com/adewale/claude-history-explorer) | Python | Visualization | Limited search |

### Gap Analysis — What Nobody Does

1. **Token cost analysis** — Data exists in every assistant message (`usage` field), but no tool surfaces it
2. **Max subscription value** — No tool shows "you saved $X vs API pricing"
3. **Model usage breakdown** — Which model was used how often, at what cost
4. **Daily/weekly activity trends** — Usage patterns over time
5. **Clean Chinese support** — Most tools assume English-only

### Our Positioning

**Shenron = The most complete Claude Code history manager.**

Search + Export + Cost Analytics + Stats Dashboard. Four pillars, one tool.

## 3. Architecture

### 3.1 Tech Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Language | Python 3.12+ | Fast development, broad install base |
| CLI Framework | Typer | Type hints, auto --help, built on Click |
| Terminal UI | Rich | Tables, panels, progress bars, syntax highlight |
| Packaging | hatchling + PyPI | `pip install shenron` or `pipx install shenron` |
| Testing | pytest + pytest-cov | Standard, 80% coverage target |
| Linting | ruff | Fast, replaces flake8 + isort + pyupgrade |

**Dependencies**: Only `typer` and `rich`. Zero heavy libs.

### 3.2 Module Architecture

```
src/shenron/
├── cli.py           Typer app — 7 commands, argument parsing
├── config.py        Paths (~/.claude/projects/), defaults, constants
├── models.py        Frozen dataclasses: Session, Message, TokenUsage, SessionMeta
├── discovery.py     Find session files — generator, lazy, filterable
├── parser.py        Streaming JSONL parser — 3 modes (meta/full/stream)
├── searcher.py      Keyword + regex search across sessions
├── stats.py         Token aggregation, cost analysis, activity trends
├── pricing.py       Model pricing table (Opus/Sonnet/Haiku per-million rates)
├── formatter.py     All Rich rendering (tables, panels, highlights)
└── exporter.py      Export to Markdown / JSON / HTML
```

### 3.3 Data Flow

```
         User runs: shenron search "backtest"
                         │
                    ┌────▼────┐
                    │  cli.py  │  Parse args, dispatch
                    └────┬────┘
                         │
                ┌────────▼────────┐
                │  discovery.py    │  Find all .jsonl files
                │  → SessionMeta   │  (path, size, mtime only)
                └────────┬────────┘
                         │ generator
                ┌────────▼────────┐
                │  parser.py       │  Stream messages line-by-line
                │  → Message       │  (never loads full file)
                └────────┬────────┘
                         │ generator
                ┌────────▼────────┐
                │  searcher.py     │  Match keyword/regex
                │  → SearchResult  │  (with context)
                └────────┬────────┘
                         │ generator
                ┌────────▼────────┐
                │  formatter.py    │  Rich highlight + render
                │  → Console       │  (print as found)
                └─────────────────┘
```

**Key insight**: Everything is a generator chain. Memory = O(1) per session. A search across 6,000 sessions won't use more RAM than a search across 100.

### 3.4 Parser: Three Modes

| Mode | Use Case | What It Reads | Speed |
|------|----------|---------------|-------|
| **meta-only** | `shenron list` | First ~10 lines per file | Fastest |
| **full** | `shenron show`, `shenron stats` | Entire file → Session object | Medium |
| **stream** | `shenron search` | Yield Message by Message | Memory-efficient |

### 3.5 Session Data Schema

Each `.jsonl` file contains these line types:

```
queue-operation   → Session start/end markers
user              → User messages (text, tool_result)
assistant         → AI responses (text, thinking, tool_use) + usage tokens
system            → System notifications
progress          → Tool execution progress, thinking state
file-history-snapshot → File edit tracking
```

**Critical fields for Shenron:**

```json
// From assistant messages — the gold mine
"message": {
  "model": "claude-opus-4-6",
  "usage": {
    "input_tokens": 25834,
    "output_tokens": 1247,
    "cache_creation_input_tokens": 25834,
    "cache_read_input_tokens": 0
  }
}

// From user messages — context
"cwd": "/Users/titans/Desktop/crypto-bots/framework",
"version": "2.1.63",
"gitBranch": "main",
"timestamp": "2026-03-05T08:40:00.000Z"
```

## 4. CLI Interface

### 4.1 Command Overview

```bash
shenron list                    # List all sessions
shenron show <session-id>       # Display a session
shenron search <query>          # Search across all history
shenron stats                   # Token/cost analytics dashboard
shenron export <session-id>     # Export to file
shenron resume [session-id]     # Get session ID for claude --resume
shenron info                    # System overview
```

### 4.2 Detailed Commands

#### `shenron list`
```
Options:
  -p, --project TEXT        Filter by project (substring)
  -n, --limit INT           Max results [20]
  --after DATE              After YYYY-MM-DD
  --before DATE             Before YYYY-MM-DD
  --model TEXT              Filter by model
  -s, --sort TEXT           Sort: date|tokens|duration|messages [date]
  --json                    JSON output
  -a, --all                 Include subagent sessions
```

#### `shenron search <query>`
```
Options:
  -r, --regex               Regex mode
  -i, --ignore-case         Case insensitive [True]
  -p, --project TEXT        Filter project
  -t, --type TEXT           Filter: user|assistant|all [all]
  -C, --context INT         Context chars around match [80]
  -n, --limit INT           Max results [20]
  --after/--before DATE     Date range
  --json                    JSON output
```

#### `shenron stats`
```
Options:
  --by TEXT                 Group: summary|project|model|date|session [summary]
  -p, --project TEXT        Filter project
  --after/--before DATE     Date range
  --top INT                 Top N sessions by cost [10]
  --json                    JSON output
```

#### `shenron export <session-id>`
```
Options:
  -f, --format TEXT         markdown|json|html [markdown]
  -o, --output PATH         Output file [stdout]
  --thinking/--no-thinking  Include thinking blocks [no]
  --tools/--no-tools        Include tool calls [yes]
```

## 5. Cost Analytics Design (Killer Feature)

### 5.1 Pricing Table

```python
# USD per million tokens (as of March 2026)
MODEL_PRICING = {
    "claude-opus-4-6":   {"input": 15.00, "output": 75.00, "cache_write": 18.75, "cache_read": 1.50},
    "claude-sonnet-4-6": {"input":  3.00, "output": 15.00, "cache_write":  3.75, "cache_read": 0.30},
    "claude-haiku-4-5":  {"input":  0.80, "output":  4.00, "cache_write":  1.00, "cache_read": 0.08},
}
```

### 5.2 Cost Calculation Per Turn

```
cost = (input_tokens × input_rate
      + output_tokens × output_rate
      + cache_creation_tokens × cache_write_rate
      + cache_read_tokens × cache_read_rate) / 1,000,000
```

### 5.3 Max Subscription Value Display

```
┌─────────────────────────────────────────────┐
│  💰 Max Subscription Value                  │
│                                             │
│  Period:               Feb 12 – Mar 5       │
│  Total Tokens:         402,000,000          │
│  Equivalent API Cost:  $830.47              │
│  Max Subscription:     $100.00/mo           │
│  ──────────────────────────────────         │
│  Value Multiplier:     8.3x                 │
│  You Saved:            $730.47              │
│                                             │
│  * "Equivalent API Cost" = what these       │
│    tokens would cost at standard API rates. │
│    Max subscribers pay $100/mo flat.        │
└─────────────────────────────────────────────┘
```

### 5.4 Stats Dashboard Panels

```
shenron stats
├── Summary Panel      总 sessions / tokens / 等价费用 / 日期范围
├── Model Breakdown    Opus vs Sonnet vs Haiku 用量占比
├── Project Breakdown  每个项目消耗排名
├── Daily Activity     每日 session 数 + token 量（sparkline）
├── Top 10 Sessions    按费用排名的最贵 sessions
└── Max Value Panel    订阅回本倍数

shenron stats --by project
→ 按项目分组的详细费用表

shenron stats --by model
→ 按模型分组的 token + 费用对比

shenron stats --by date
→ 按日期的活跃度趋势
```

### 5.5 Important Labeling

All cost figures must display:
- Label: **"Equivalent API Cost"** (not "Amount Charged")
- Footnote: *"Based on standard Anthropic API rates. Max subscribers pay a flat monthly fee."*
- Never imply users are being billed per-token on Max plan

## 6. Implementation Phases

| Phase | Scope | Output |
|-------|-------|--------|
| **1. Foundation** | models, config, discovery, parser + tests | Can parse all 157 sessions |
| **2. List + Show** | formatter, cli (list/show), __main__ | `shenron list` works |
| **3. Search** | searcher + cli search | `shenron search` works |
| **4. Stats + Cost** | pricing, stats + cli stats/info | `shenron stats` dashboard |
| **5. Export + Resume** | exporter + cli export/resume | `shenron export` works |
| **6. Release** | README, LICENSE, CI, PyPI, GitHub Public | v0.1.0 published |

**Estimated effort**: 6 sessions of focused coding (~2-3 days)

## 7. Future Roadmap (Post v0.1)

- **v0.2**: SQLite index for 2000+ session performance (`shenron index`)
- **v0.3**: TUI mode (Textual) — interactive fuzzy search like fzf
- **v0.4**: Semantic search (embed conversations, vector similarity)
- **v0.5**: Cross-tool support (Cursor, Copilot history if formats documented)
- **v1.0**: Stable release with all above

## 8. Branding

- **Name**: Shenron 神龍
- **Tagline**: "Summon the Dragon. Recall everything."
- **Companion**: Kaioshin 界王神 (sandbox) — same Dragon Ball universe
- **Authors**: 小code & Rob
- **License**: MIT
- **Blog**: robbery.blog
- **GitHub**: robbery107allianz-cell/shenron

---

*"Gather the Dragon Balls, summon Shenron, and no conversation is ever lost."*

```
小code
pid: shenron-design-whitepaper
ctx: 1984 Mac Home → George Orwell
status: Design complete. Awaiting implementation.
```
