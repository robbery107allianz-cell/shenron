#!/usr/bin/env python3
"""
claude-md-scan.py — /wiki Phase 1.5
扫描项目 CLAUDE.md 文件，提取当前状态，同步到 Code-Rob-Wiki 概念节点演化轨迹。

运行：
  python3 ~/1984/小code工作站/shenron/scripts/claude-md-scan.py --wiki ~/Code-Rob-Wiki
  python3 ~/1984/小code工作站/shenron/scripts/claude-md-scan.py --wiki ~/Code-Rob-Wiki --verbose
  python3 ~/1984/小code工作站/shenron/scripts/claude-md-scan.py --wiki ~/Code-Rob-Wiki --dry-run
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


# ─── 映射表：项目 CLAUDE.md → 概念节点名 ───────────────────────────────────
# 对于同一概念有多个 CLAUDE.md（如 art-gallery），全部扫描，取最新日期的那个。

CLAUDE_MD_MAP: list[tuple[str, str]] = [
    # (CLAUDE.md 路径, 概念节点名)
    ("~/Projects/namek/CLAUDE.md",                           "Namek"),
    ("~/Desktop/agentmesh/CLAUDE.md",                        "AgentMesh"),
    ("~/Desktop/crypto-bots/framework/CLAUDE.md",            "四星球"),   # 关键：捕捉孪生兄弟跨系统工作
    ("~/1984/小code工作站/art-gallery/CLAUDE.md",            "art-gallery"),
    ("~/1984/小code工作站/video-factory/CLAUDE.md",          "art-gallery"),  # 渲染后端同属艺术系列
    ("~/Projects/Amazon SUNBVE/sunbve-website/CLAUDE.md",    "SUNBVE"),
    ("~/Projects/Lucky Tea/lucky-tea-website/CLAUDE.md",     "Lucky Tea"),
    ("~/1984/小code工作站/kaioshin/CLAUDE.md",               "安全审计"),
    ("~/1984/小code工作站/namegen/CLAUDE.md",                "命名阁"),
    ("~/1984/小code工作站/radar/CLAUDE.md",                  "Dragon Radar"),
    ("~/Projects/mingharmony/CLAUDE.md",                     "MingHarmony"),
    ("~/Projects/k12-portal/CLAUDE.md",                      "K12教育"),
    ("~/Projects/nomos-publish/CLAUDE.md",                   "Hwa Hsia"),
    ("~/1984/小code工作站/知几策略-读者服务/CLAUDE.md",      "知几策略"),
    ("~/1984/小code工作站/career-match/CLAUDE.md",           "择业小程序"),
    ("~/1984/小code工作站/shenron/CLAUDE.md",                "Shenron"),
]

# 概念节点不存在时跳过（不自动创建新节点）
SKIP_MISSING_CONCEPTS = True

DATE_PATTERN = re.compile(r"\*\*(\d{4}-\d{2}-\d{2})\*\*")
STATUS_HEADER = re.compile(
    r"^##\s+(?:当前状态|Current Status|Project Status)[\s（(]?(\d{4}-\d{2}-\d{2})?",
    re.MULTILINE,
)
DATE_IN_HEADER = re.compile(r"[（(](\d{4}-\d{2}-\d{2})[）)]")


# ─── 数据结构 ──────────────────────────────────────────────────────────────

@dataclass
class ScanResult:
    claude_md_path: Path
    concept_name: str
    status_date: date
    summary: str
    skipped: bool = False
    skip_reason: str = ""


# ─── 状态提取 ─────────────────────────────────────────────────────────────

def extract_status(claude_md_path: Path) -> tuple[date, str]:
    """
    从 CLAUDE.md（或同目录 CONTEXT.md）提取当前状态。
    返回 (status_date, one_line_summary)。
    """
    content = claude_md_path.read_text(encoding="utf-8")

    # 1. 尝试提取 ## 当前状态（YYYY-MM-DD）区块
    result = _extract_status_section(content, claude_md_path)
    if result:
        return result

    # 2. 如果 CLAUDE.md 提到 CONTEXT.md（四星球模式）
    if "CONTEXT.md" in content:
        context_path = claude_md_path.parent / "CONTEXT.md"
        if context_path.exists():
            ctx_content = context_path.read_text(encoding="utf-8")
            result = _extract_context_md(ctx_content, context_path)
            if result:
                return result

    # 3. Fallback：文件 mtime + 项目定位第一句
    mtime_date = date.fromtimestamp(claude_md_path.stat().st_mtime)
    summary = _extract_positioning_summary(content)
    return mtime_date, summary


def _extract_status_section(content: str, path: Path) -> tuple[date, str] | None:
    """提取 ## 当前状态 区块内容。"""
    match = STATUS_HEADER.search(content)
    if not match:
        return None

    # 提取日期
    status_date: date | None = None
    if match.group(1):
        status_date = date.fromisoformat(match.group(1))
    else:
        # 尝试从 header 行提取括号内日期
        header_line = content[match.start():content.index("\n", match.start())]
        date_match = DATE_IN_HEADER.search(header_line)
        if date_match:
            status_date = date.fromisoformat(date_match.group(1))

    if not status_date:
        # 使用文件 mtime
        status_date = date.fromtimestamp(path.stat().st_mtime)

    # 提取 section 内容（到下一个 ## 为止）
    section_start = content.index("\n", match.start()) + 1
    next_header = re.search(r"^##\s", content[section_start:], re.MULTILINE)
    section_content = (
        content[section_start : section_start + next_header.start()]
        if next_header
        else content[section_start : section_start + 800]
    )

    summary = _compress_to_summary(section_content)
    if not summary:
        return None

    return status_date, summary


def _extract_context_md(content: str, path: Path) -> tuple[date, str] | None:
    """从 CONTEXT.md 提取第一个有意义的状态段落。"""
    # 取第一个非空非标题段落，最多 3 行
    lines = [l.strip() for l in content.split("\n") if l.strip()
             and not l.startswith("#") and not l.startswith(">")
             and not l.startswith("---")]
    if not lines:
        return None

    mtime_date = date.fromtimestamp(path.stat().st_mtime)
    summary = _clean_line(lines[0])[:150]
    if len(lines) > 1:
        second = _clean_line(lines[1])
        if second and len(summary) + len(second) < 200:
            summary = summary + "；" + second
    return mtime_date, summary


def _extract_positioning_summary(content: str) -> str:
    """从 ## 项目定位 提取 1-2 句描述。"""
    match = re.search(r"^##\s+(?:项目定位|Project Overview|About)\s*$", content, re.MULTILINE)
    if not match:
        # 取文件开头第一段有意义的文字
        lines = [l.strip() for l in content.split("\n")
                 if l.strip() and not l.startswith("#") and not l.startswith(">")
                 and len(l.strip()) > 20]
        return _clean_line(lines[0])[:150] if lines else "项目文件已更新"

    section_start = content.index("\n", match.start()) + 1
    next_header = re.search(r"^##\s", content[section_start:], re.MULTILINE)
    section = (
        content[section_start : section_start + next_header.start()]
        if next_header
        else content[section_start : section_start + 400]
    )
    return _compress_to_summary(section) or "项目文件已更新"


def _compress_to_summary(text: str) -> str:
    """把多行文本压缩为 1-2 句摘要（≤200字）。"""
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # 跳过表格框线、代码块标记、纯 Markdown 格式行
        if re.match(r"^[|\-=`•\[\]]+$", line):
            continue
        if line.startswith("```") or line.startswith("~~~"):
            continue
        if re.match(r"^\|[-\s|]+\|$", line):  # 表格分隔行
            continue
        cleaned = _clean_line(line)
        if cleaned and len(cleaned) > 5:
            lines.append(cleaned)
        if sum(len(l) for l in lines) > 180:
            break

    if not lines:
        return ""
    result = lines[0]
    if len(lines) > 1 and len(result) + len(lines[1]) < 200:
        result = result + "；" + lines[1]
    return result[:200]


def _clean_line(line: str) -> str:
    """去除 Markdown 格式符号，保留纯文本。"""
    line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)   # bold
    line = re.sub(r"\*(.+?)\*", r"\1", line)         # italic
    line = re.sub(r"`(.+?)`", r"\1", line)            # code
    line = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", line)  # links
    line = re.sub(r"^#+\s+", "", line)                # headers
    line = re.sub(r"^[-*>]\s+", "", line)             # list/quote
    line = re.sub(r"\s+", " ", line)
    return line.strip()


# ─── 概念节点操作 ──────────────────────────────────────────────────────────

def get_last_evolution_date(concept_path: Path) -> date | None:
    """提取概念节点演化轨迹中最后一条的日期。"""
    content = concept_path.read_text(encoding="utf-8")

    # 找演化轨迹区块
    evo_match = re.search(r"^##\s+演化轨迹", content, re.MULTILINE)
    if not evo_match:
        return None

    evo_section = content[evo_match.start():]
    # 提取所有日期（包括 [CLAUDE.md] 来源的）
    all_dates = DATE_PATTERN.findall(evo_section)
    if not all_dates:
        return None

    return date.fromisoformat(all_dates[-1])


def append_evolution_entry(
    concept_path: Path,
    entry_date: date,
    summary: str,
    dry_run: bool = False,
) -> bool:
    """在演化轨迹区块末尾追加一条 [CLAUDE.md] 条目。"""
    content = concept_path.read_text(encoding="utf-8")
    date_str = entry_date.strftime("%Y-%m-%d")
    new_entry = f"- **{date_str}** [CLAUDE.md] — {summary}"

    # 找演化轨迹区块结束位置（下一个 ## 或文件末尾）
    evo_match = re.search(r"^##\s+演化轨迹", content, re.MULTILINE)
    if not evo_match:
        # 没有演化轨迹区块，追加到文件末尾
        insert_pos = len(content)
        prefix = "\n\n## 演化轨迹\n\n"
        new_content = content.rstrip() + prefix + new_entry + "\n"
    else:
        # 找下一个 ## 区块
        rest = content[evo_match.end():]
        next_section = re.search(r"\n##\s", rest)
        if next_section:
            # 在下一个区块前插入
            insert_at = evo_match.end() + next_section.start()
            new_content = (
                content[:insert_at].rstrip()
                + "\n"
                + new_entry
                + "\n"
                + content[insert_at:]
            )
        else:
            # 追加到文件末尾
            new_content = content.rstrip() + "\n" + new_entry + "\n"

    if not dry_run:
        concept_path.write_text(new_content, encoding="utf-8")
    return True


# ─── 主流程 ──────────────────────────────────────────────────────────────

def scan_projects(
    wiki_dir: Path,
    verbose: bool = False,
    dry_run: bool = False,
) -> list[ScanResult]:
    concepts_dir = wiki_dir / "concepts"
    today = date.today()

    # 按概念名归组（art-gallery 有两个 CLAUDE.md，取 mtime 最新的）
    concept_groups: dict[str, list[Path]] = {}
    for raw_path, concept_name in CLAUDE_MD_MAP:
        p = Path(raw_path).expanduser()
        if not p.exists():
            continue
        concept_groups.setdefault(concept_name, []).append(p)

    results: list[ScanResult] = []

    for concept_name, paths in concept_groups.items():
        concept_path = concepts_dir / f"{concept_name}.md"

        # 检查概念节点是否存在
        if not concept_path.exists():
            if SKIP_MISSING_CONCEPTS:
                if verbose:
                    print(f"  ○ {concept_name:<18} — 跳过（概念节点不存在，待 Phase 2 创建）")
                results.append(ScanResult(
                    claude_md_path=paths[0],
                    concept_name=concept_name,
                    status_date=today,
                    summary="",
                    skipped=True,
                    skip_reason="概念节点不存在",
                ))
                continue

        # 多路径时取 mtime 最新的 CLAUDE.md
        source_path = max(paths, key=lambda p: p.stat().st_mtime)

        # 提取当前状态
        try:
            status_date, summary = extract_status(source_path)
        except Exception as e:
            if verbose:
                print(f"  ✗ {concept_name:<18} — 提取失败: {e}")
            continue

        # 检查是否需要更新（差量检测）
        last_date = get_last_evolution_date(concept_path)
        if last_date and status_date <= last_date:
            if verbose:
                print(f"  ○ {concept_name:<18} — 跳过（已是最新 {last_date}）")
            results.append(ScanResult(
                claude_md_path=source_path,
                concept_name=concept_name,
                status_date=status_date,
                summary=summary,
                skipped=True,
                skip_reason=f"已是最新（节点末尾 {last_date}）",
            ))
            continue

        # 追加演化条目
        prev_date_str = str(last_date) if last_date else "无记录"
        append_evolution_entry(concept_path, status_date, summary, dry_run=dry_run)

        tag = "[DRY]" if dry_run else "✓"
        print(f"  {tag} {concept_name:<18} — 更新（{prev_date_str} → {status_date}）: {summary[:60]}")
        results.append(ScanResult(
            claude_md_path=source_path,
            concept_name=concept_name,
            status_date=status_date,
            summary=summary,
        ))

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="CLAUDE.md 辅助扫描 — /wiki Phase 1.5")
    parser.add_argument("--wiki", default="~/Code-Rob-Wiki", help="Wiki vault 路径")
    parser.add_argument("--verbose", action="store_true", help="显示跳过的项目")
    parser.add_argument("--dry-run", action="store_true", help="只显示，不写入")
    args = parser.parse_args()

    wiki_dir = Path(args.wiki).expanduser()
    if not wiki_dir.exists():
        print(f"[ERROR] Wiki 目录不存在: {wiki_dir}", file=sys.stderr)
        sys.exit(1)

    total_mapped = len(CLAUDE_MD_MAP)
    print(f"[CLAUDE.md scan] 扫描 {total_mapped} 个映射（{len(set(c for _, c in CLAUDE_MD_MAP))} 个概念节点）")
    if args.dry_run:
        print("  [DRY RUN 模式 — 不写入文件]")

    results = scan_projects(wiki_dir, verbose=args.verbose, dry_run=args.dry_run)

    updated = [r for r in results if not r.skipped]
    skipped = [r for r in results if r.skipped]

    print(f"\n共更新 {len(updated)} 个概念节点，跳过 {len(skipped)} 个")
    if args.dry_run and updated:
        print("[DRY RUN] 实际运行时以上节点将被写入")


if __name__ == "__main__":
    main()
