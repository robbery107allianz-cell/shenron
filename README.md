# 🐉 Shenron 神龍

> *"Speak your wish and it shall be granted."*
>
> Shenron is the eternal dragon of Claude Code — summon it to recall every conversation,
> search your entire history, distill decisions into persistent memory, and see exactly
> how much value you're getting from your Claude Max subscription.

[![PyPI version](https://img.shields.io/pypi/v/shenron.svg)](https://pypi.org/project/shenron/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Tests](https://github.com/robbery107allianz-cell/shenron/actions/workflows/ci.yml/badge.svg)](https://github.com/robbery107allianz-cell/shenron/actions)

---

## What is Shenron?

Claude Code stores every conversation in `~/.claude/projects/` as JSONL files.
After weeks of use, you have hundreds of sessions — an enormous personal knowledge base
with no way to search it.

**Shenron** gives you that power:

- **Compile** sessions into an Obsidian wiki — entity extraction, weight classification, daily digests, concept graphs
- **Search** your entire Claude Code history — ripgrep-accelerated, with keywords, regex, or multi-term AND
- **Browse** sessions with readable conversation formatting
- **Track** token usage and equivalent API costs across all projects
- **Weekly** Opus vs Sonnet usage breakdown — see your model mix trend per week
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

# Compile all sessions into an Obsidian wiki
shenron compile --all

# Distill latest session into a decisions log
shenron digest --append ~/decisions.md

# Weekly Opus vs Sonnet breakdown
shenron weekly

# See what topics are hot right now vs your full history
shenron focus
```

---

## Commands

### `shenron compile` — Compile sessions into an Obsidian wiki

The knowledge compiler. Transforms raw JSONL sessions into a structured,
searchable Obsidian vault with wikilinks, concept nodes, and a visual graph.

```
shenron compile --all                          # compile all sessions
shenron compile abc12345                       # compile a single session
shenron compile --all --after 2026-03-01       # recent sessions only
shenron compile --all --output ~/my-wiki       # custom output directory
shenron compile --dry-run                      # preview without writing
```

**What it produces:**

```
~/Code-Rob-Wiki/
├── sessions/           ← daily digests (multiple sessions merged per day)
│   └── 2026-03-15.md   ← entities, key points, file changes, weight
├── concepts/           ← cross-session concept nodes (auto-extracted)
│   └── 四星球.md        ← definition stub + evolution trail + wikilinks
├── ideas/              ← incubator for unnamed ideas
└── INDEX.md            ← master index with weight distribution
```

**Key design decisions:**

| Feature | How |
|---------|-----|
| Entity extraction | Seed dictionary matching against USER messages only (system messages contain MEMORY.md which would match everything) |
| Weight system | Three layers: ★ strategy (research/ideas), ● dev (code/iteration), ○ ops (checks/confirmations) |
| Density filtering | High-frequency entities need 3+ mentions to link; rare entities need 1 |
| Daily merge | Multiple sessions from the same day → one daily digest node |
| Enrichment protection | Files manually enriched (no "stub" marker) keep their content; only frontmatter is updated |
| Archaeological protection | Files with `source: archaeological-recovery` are never overwritten |

**Viewing in Obsidian:**

The compiled wiki is a plain folder of `.md` files with `[[wikilinks]]` — Obsidian
reads it natively with zero configuration:

```bash
# 1. Compile your sessions
shenron compile --all --output ~/my-wiki

# 2. Open in Obsidian
#    Launch Obsidian → "Open folder as vault" → select ~/my-wiki
#    Or from terminal (macOS):
open -a Obsidian ~/my-wiki
```

Once opened, you get for free:
- **Graph View** — visual knowledge graph of sessions ↔ concepts (Ctrl/Cmd+G)
- **Backlinks** — click any concept to see every session that mentions it
- **Search** — Obsidian's built-in full-text search across all compiled notes
- **Daily Notes** — session digests are date-named, compatible with Obsidian's calendar plugins

No Obsidian plugins are required. The vault works with default settings. If you
want to customize the graph (colors, groups), edit `.obsidian/graph.json` — but
it's entirely optional.

> **Don't have Obsidian?** The output is standard Markdown. You can browse it
> with any text editor, VS Code, or even `cat`. Obsidian just makes the
> wikilinks and graph clickable.

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

Uses **ripgrep** (`rg`) under the hood to pre-filter session files, then applies
structured Python parsing for role/model/date filtering. One command, best of
both worlds — rg speed with full session awareness.

```
shenron search "authentication"                     # basic keyword
shenron search "docker" "compose"                   # multi-term AND logic
shenron search "TODO" --type user                   # only your messages
shenron search "Error" --type assistant             # only Claude's responses
shenron search "def \w+\(" --regex                  # regex search
shenron search "封号|appeal" --regex                # regex OR
shenron search "secret" --case-sensitive
shenron search "api" --project myproject            # scope to one project
shenron search "bug" --model opus                   # filter by model
shenron search "fix" --after 2026-03-01             # recent sessions only
shenron search "bug" -n 100 -C 120                 # 100 results, 120-char context
```

> **Tip:** `rg` (ripgrep) is optional but recommended. If installed, search is
> ~10x faster on large histories. Without it, Shenron falls back to pure Python
> scanning — still works, just slower.
>
> Install: `brew install ripgrep`

### `shenron stats` — Cost & usage dashboard

```
shenron stats                       # grouped by project (default)
shenron stats --by model            # grouped by model
shenron stats --by date             # grouped by day
shenron stats --by week             # grouped by ISO week
shenron stats --top 5               # top 5 groups
shenron stats --after 2026-03-01    # this month only
shenron stats --subscription 200    # custom plan cost for multiplier
```

**Sample output:**
```
╭─────────────────────── shenron stats ────────────────────────╮
│ Claude Code — Equivalent API Cost                             │
│                                                               │
│   Input tokens:    197K                                       │
│   Output tokens:   4.5M                                       │
│   Cache writes:    45.6M                                      │
│   Cache reads:     1259.8M                                    │
│   Total sessions:  87                                         │
│   Total messages:  27,098                                     │
│                                                               │
│   Equivalent cost: $1,877.22                                  │
│   vs Max $100/mo:  18.8x value                                │
╰───────────────────────────────────────────────────────────────╯

  Project                  Sessions   Input   Output   Cost (est.)   Share
 ────────────────────────────────────────────────────────────────────────
  ~/Desktop/crypto/…            24    144K     2.4M     $1289.70    ████████████ 68.7%
  ~/                            32     52K     1.9M      $505.53    █████░░░░░░░ 26.9%
  ...
```

> **Note:** Claude Max subscribers pay a flat monthly fee. The "Equivalent API Cost" shows
> what the same token consumption would cost at pay-as-you-go API rates — so you can see
> your actual subscription value.

### `shenron weekly` — Opus vs Sonnet weekly breakdown

Shows per-week model distribution so you can track your Opus/Sonnet usage
trend over time — the local equivalent of the Claude Max web dashboard.

```
shenron weekly                         # all weeks
shenron weekly --after 2026-03-01      # this month only
shenron weekly --project myproject     # scope to one project
```

**Sample output:**
```
╭──────────────────── shenron weekly ────────────────────╮
│ Weekly Model Breakdown — Opus vs Sonnet                 │
│                                                         │
│   Total weeks:     5                                    │
│   Opus sessions:   56   Sonnet: 22   Other: 12          │
│   Opus output:     3.4M  (52.6%)                        │
│   Sonnet output:   2.9M  (47.4%)                        │
╰─────────────────────────────────────────────────────────╯

  Week       Dates         Opus  Son.  Opus Out  Son. Out  Opus%  Cost($)
 ─────────────────────────────────────────────────────────────────────────
  2026-W09   02/23-03/01      9     0      634K        0   100%     558
  2026-W10   03/02-03/08     22    10      1.1M     1.5M    41%    1.1K
  2026-W11   03/09-03/15      8     9      1.1M     1.5M    42%    1.3K
  2026-W12   03/16-03/22     16     0      671K        0    85%     913

  TOTAL                      56    22      3.4M     2.9M    53%    3.8K
```

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

### Search architecture

```
shenron search "keyword" --model opus --type user
        │
        ▼
   ┌─────────┐    rg --files-with-matches     ┌──────────────┐
   │ ripgrep  │ ──────────────────────────────▶│ matched files │
   └─────────┘    (skip 90% of files)          └──────┬───────┘
                                                      │
                                                      ▼
                                              ┌───────────────┐
                                              │ Python parser  │
                                              │ • role filter  │
                                              │ • model filter │
                                              │ • AND logic    │
                                              │ • context      │
                                              └───────┬───────┘
                                                      │
                                                      ▼
                                              ┌───────────────┐
                                              │ Rich renderer  │
                                              │ • highlights   │
                                              │ • interactive  │
                                              └───────────────┘
```

---

## Performance

| Scenario | Time | Engine |
|----------|------|--------|
| `shenron list` (87 sessions) | ~0.3s | Python streaming |
| `shenron search "keyword"` (87 sessions, 27K messages) | ~0.2s | rg pre-filter + Python |
| `shenron search "word1" "word2"` (AND logic) | ~0.4s | rg pre-filter + Python |
| `shenron stats` (87 sessions) | ~0.4s | Python streaming |

No background daemon. No SQLite. No indexing.
Search uses ripgrep for file-level pre-filtering, then Python for structured message parsing — fast *and* smart.

---

## Dragon Ball Universe

Shenron pairs with **[Kaioshin](https://github.com/robbery107allianz-cell/kaioshin)**,
the Supreme Kai security sandbox for Claude Code.

| Tool | Dragon Ball | Role |
|------|-------------|------|
| [Kaioshin](https://github.com/robbery107allianz-cell/kaioshin) | 界王神 Supreme Kai | Read-only security audit |
| Shenron | 神龍 Eternal Dragon | Session history & knowledge compiler |
| Code-Rob-Wiki | 龙珠雷达 Dragon Radar | Obsidian vault — Shenron's compiled output |

```
kaioshin      →  keeps Claude safe while it works
shenron       →  remembers everything Claude did
code-rob-wiki →  the living knowledge graph that grows from every session
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

## Acknowledgments

The **compile** module — transforming raw session logs into a living Obsidian
knowledge graph — was inspired by [Andrej Karpathy](https://x.com/karpathy)'s
"LLM Knowledge Bases" workflow (April 2026). Karpathy described a pattern of
collecting raw data into a directory, having an LLM "compile" it into a `.md`
wiki with backlinks and concept articles, and using Obsidian as the viewing
frontend — with the LLM as the primary editor, not the human.

We adopted this core insight — **raw data → LLM-compiled wiki → Obsidian** —
and built Shenron's compiler on top of it. Where we diverge:

| Karpathy's approach | Shenron's approach |
|---------------------|-------------------|
| Manual data ingest (web clipper, papers) | Automatic ingest from Claude Code JSONL sessions |
| LLM-driven compilation (needs API calls) | Heuristic compiler — zero LLM, pure algorithm (entity extraction, weight classification, density filtering) |
| Generic wiki structure | Three-layer output: session digests → concept nodes → idea seeds |
| Single-user research wiki | Multi-instance support (Mac + VPS sessions compile into one wiki) |
| No history protection | Archaeological recovery — restored sessions are never overwritten |
| — | Concept evolution tracking across sessions over time |

We built on the idea; the implementation is entirely our own.

## License

AGPL-3.0 © 小code & Rob

Previous versions (up to the last MIT-licensed commit) remain available under
MIT. From this commit forward, all new code is licensed under the
[GNU Affero General Public License v3.0](https://www.gnu.org/licenses/agpl-3.0.html).

---

*Summon the Dragon. Recall everything. Compile knowledge.*
