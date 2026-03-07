"""
Focus analyzer — extract keyword frequency from recent sessions.

Analyzes user messages (what Rob types) to surface hot topics.
Outputs a focus.md showing current attention distribution.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from shenron.models import SessionMeta
from shenron.parser import stream_messages

# ─── Stop words ───────────────────────────────────────────────────────────────

_STOP_ZH_CHARS = set("的了是在我他你这那和也就都而及与着被地得到说要会没有人上下来去对不")

_STOP_ZH_WORDS = {
    # ── 口语虚词
    "这个", "那个", "一个", "没有", "可以", "什么", "我们", "你们", "他们",
    "因为", "所以", "但是", "如果", "已经", "现在", "时候", "东西", "一下",
    "还是", "还有", "然后", "不是", "就是", "这样", "那样", "一些", "感觉",
    "觉得", "知道", "一起", "所有", "应该", "需要", "这里", "那里", "看看",
    "一直", "继续", "开始", "完成", "而且", "不过", "虽然", "其实", "对于",
    "关于", "通过", "进行", "可能", "基本", "主要", "相关", "对应", "具体",
    "直接", "简单", "正常", "默认", "自动", "手动", "本地", "全局", "当前",
    "之前", "之后", "以下", "如下", "上面", "下面", "左边", "右边",
    # ── 通用开发术语
    "文件", "目录", "命令", "运行", "执行", "输出", "输入", "结果",
    "使用", "添加", "更新", "设置", "配置", "安装", "启动", "停止",
    "创建", "删除", "修改", "查看", "检查", "测试", "部署", "发布",
    "代码", "函数", "变量", "参数", "返回", "调用", "接口", "模块",
    "数据库", "服务器", "客户端", "请求", "响应", "错误", "日志",
    "版本", "更新", "升级", "依赖", "环境", "路径", "格式", "类型",
    "方法", "属性", "对象", "实例", "继承", "实现", "定义", "声明",
    "导入", "导出", "编译", "构建", "打包", "部署", "监控", "报警",
    "任务", "进程", "线程", "队列", "缓存", "索引", "查询", "过滤",
    "加载", "保存", "读取", "写入", "解析", "渲染", "转换", "处理",
    "工具", "插件", "框架", "库", "包", "组件", "模板", "脚本",
    "内容", "方式", "问题", "情况", "功能", "效果", "结构", "逻辑",
}

_STOP_EN = {
    # ── Articles / conjunctions / prepositions
    "the", "and", "for", "are", "but", "not", "you", "all", "can",
    "was", "one", "our", "out", "get", "has", "him", "his", "how",
    "its", "new", "now", "she", "use", "way", "who", "did", "let",
    "say", "too", "via", "yes", "yet", "your", "with", "this", "that",
    "they", "have", "from", "been", "will", "more", "when", "than",
    "then", "some", "what", "into", "just", "like", "time", "know",
    "also", "make", "here", "each", "most", "need", "such", "well",
    "would", "could", "should", "there", "about", "which", "after",
    "before", "where", "these", "those", "their", "them", "were",
    "had", "does", "doing", "done", "every", "only", "even", "very",
    "over", "back", "want", "take", "give", "keep", "look", "work",
    # ── Python language keywords & builtins
    "self", "none", "true", "false", "null", "import", "return",
    "class", "elif", "else", "pass", "with", "from", "raise", "yield",
    "async", "await", "lambda", "global", "nonlocal", "assert", "del",
    "isinstance", "type", "repr", "iter", "next", "list", "dict",
    "tuple", "print", "open", "range", "super", "object", "args",
    "kwargs", "init", "main", "name", "attr",
    # ── Shell / bash
    "bash", "echo", "grep", "curl", "exit", "export", "source",
    "chmod", "mkdir", "touch", "sudo", "exec", "eval", "pipe",
    "stdin", "stdout", "stderr", "argv", "envs", "vars",
    # ── General dev / tool nouns
    "code", "file", "files", "line", "lines", "path", "text", "read",
    "write", "data", "user", "users", "step", "steps", "test", "tests",
    "docs", "note", "notes", "todo", "type", "mode", "flag", "keys",
    "args", "opts", "logs", "log", "run", "runs", "call", "calls",
    "func", "param", "params", "value", "values", "item", "items",
    "name", "names", "info", "list", "dict", "node", "root", "base",
    "true", "false", "null", "none", "bool", "int", "str", "var",
    "config", "setup", "build", "built", "tool", "tools", "task",
    "tasks", "repo", "push", "pull", "diff", "branch", "merge",
    "commit", "patch", "sync", "load", "save", "send", "recv",
    "open", "close", "start", "stop", "init", "done", "fail",
    "pass", "skip", "next", "prev", "curr", "last", "first",
    "output", "input", "result", "results", "check", "error",
    "debug", "trace", "stack", "heap", "port", "host", "addr",
    "token", "tokens", "block", "chunk", "byte", "bytes", "size",
    "count", "total", "index", "offset", "limit", "range",
    "command", "commands", "option", "options", "param", "params",
    "module", "package", "install", "release", "version", "update",
    "request", "response", "handler", "router", "server", "client",
    "socket", "proto", "http", "https", "json", "yaml", "toml",
    "class", "method", "function", "variable", "instance", "object",
    "interface", "struct", "field", "schema", "model", "query",
    "insert", "select", "delete", "create", "table", "index",
    "cache", "queue", "event", "loop", "thread", "mutex", "lock",
    "import", "export", "require", "include", "define", "declare",
    "phase", "stage", "layer", "level", "tier", "rank", "order",
    "parse", "render", "format", "encode", "decode", "hash",
    "match", "find", "sort", "filter", "reduce", "apply", "bind",
    "wrap", "hook", "emit", "listen", "watch", "poll", "fetch",
    "test", "spec", "mock", "stub", "fixture", "assert", "expect",
    "source", "target", "dest", "origin", "remote", "local",
    "stdin", "stdout", "stream", "buffer", "frame", "packet",
    "symbol", "token", "literal", "keyword", "operator", "syntax",
    # ── Path / env noise
    "titans", "home", "library", "desktop", "bots", "framework",
    "venv", "site", "packages", "dist", "temp", "cache",
    # ── Tool output noise
    "successfully", "updated", "created", "showing", "matches",
    "session", "sessions", "failed", "warning", "message", "messages",
    "enabled", "disabled", "active", "inactive", "running", "stopped",
    "installed", "removed", "loaded", "unloaded", "found", "missing",
}


# ─── Token extraction ─────────────────────────────────────────────────────────

def _extract_tokens(text: str) -> list[str]:
    """Extract meaningful tokens from mixed Chinese/English text."""
    tokens: list[str] = []

    # English: words 4+ chars, not in stop list
    for word in re.findall(r'\b[a-zA-Z]{4,}\b', text):
        w = word.lower()
        if w not in _STOP_EN:
            tokens.append(w)

    # Chinese: extract sequences of 2-6 non-stop characters
    # Split on stop chars and punctuation to get natural chunks
    zh_chunks = re.findall(r'[\u4e00-\u9fff]{2,8}', text)
    for chunk in zh_chunks:
        # Skip if chunk is all stop chars
        clean = ''.join(c for c in chunk if c not in _STOP_ZH_CHARS)
        if len(clean) < 2:
            continue
        # Emit 2-char and 3-char substrings as candidate terms
        for length in (2, 3):
            for i in range(len(clean) - length + 1):
                term = clean[i:i + length]
                if term not in _STOP_ZH_WORDS and len(term) >= 2:
                    tokens.append(term)

    return tokens


# ─── Analysis ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FocusEntry:
    term: str
    count: int
    pct: float     # relative to max count


@dataclass(frozen=True)
class FocusReport:
    generated_at: datetime
    hours_window: int
    sessions_scanned: int
    messages_scanned: int
    top_terms: tuple[FocusEntry, ...]


def _count_tokens(sessions: list[SessionMeta], user_only: bool = True) -> tuple[Counter, int]:
    """Scan sessions and return (token_counter, messages_scanned)."""
    counter: Counter[str] = Counter()
    messages_scanned = 0

    _noise_prefixes = (
        "<local-command", "<system-reminder", "<task-notification",
        "Updated task", "The file", "File created", "Found ",
        "No files", "Showing ", "Tool loaded", "Usage: ",
        "/Users/", "~/", "---", "```",
    )

    for meta in sessions:
        for msg in stream_messages(meta.file_path):
            if user_only and msg.msg_type != "user":
                continue
            if not user_only and msg.msg_type not in ("user", "assistant"):
                continue

            text = msg.content_text
            if not text or len(text) < 5:
                continue

            if any(text.startswith(p) for p in _noise_prefixes):
                continue
            if text.count("/") / max(len(text), 1) > 0.05:
                continue

            tokens = _extract_tokens(text)
            counter.update(tokens)
            messages_scanned += 1

    return counter, messages_scanned


def analyze(
    sessions: list[SessionMeta],
    hours: int = 24,
    top_n: int = 20,
    user_only: bool = True,
) -> FocusReport:
    """
    Scan recent sessions and count keyword frequency.
    hours=0 means scan all sessions (full history).
    """
    if hours > 0:
        cutoff = datetime.now(tz=UTC) - timedelta(hours=hours)
        target = [s for s in sessions if s.modified_time >= cutoff]
    else:
        target = sessions  # full history

    counter, messages_scanned = _count_tokens(target, user_only=user_only)

    max_count = counter.most_common(1)[0][1] if counter else 1
    top = [
        FocusEntry(term=term, count=count, pct=count / max_count)
        for term, count in counter.most_common(top_n)
    ]

    return FocusReport(
        generated_at=datetime.now(tz=UTC),
        hours_window=hours,
        sessions_scanned=len(target),
        messages_scanned=messages_scanned,
        top_terms=tuple(top),
    )


def analyze_with_baseline(
    sessions: list[SessionMeta],
    hours: int = 24,
    top_n: int = 20,
    user_only: bool = True,
) -> tuple[FocusReport, FocusReport, list[tuple[str, float]]]:
    """
    Returns (recent_report, baseline_report, spikes).

    spikes: top terms sorted by relative uplift (recent_freq / baseline_freq).
    Terms that are spiking today but absent historically get infinite uplift.
    """
    # Recent window
    cutoff = datetime.now(tz=UTC) - timedelta(hours=hours)
    recent_sessions = [s for s in sessions if s.modified_time >= cutoff]

    recent_counter, recent_msgs = _count_tokens(recent_sessions, user_only=user_only)
    all_counter, all_msgs = _count_tokens(sessions, user_only=user_only)

    # Normalize both counters to per-session rates
    n_recent = max(len(recent_sessions), 1)
    n_all = max(len(sessions), 1)

    # Recent report
    max_r = recent_counter.most_common(1)[0][1] if recent_counter else 1
    recent_top = [
        FocusEntry(term=t, count=c, pct=c / max_r)
        for t, c in recent_counter.most_common(top_n)
    ]
    recent_report = FocusReport(
        generated_at=datetime.now(tz=UTC),
        hours_window=hours,
        sessions_scanned=len(recent_sessions),
        messages_scanned=recent_msgs,
        top_terms=tuple(recent_top),
    )

    # Baseline report
    max_b = all_counter.most_common(1)[0][1] if all_counter else 1
    baseline_top = [
        FocusEntry(term=t, count=c, pct=c / max_b)
        for t, c in all_counter.most_common(top_n)
    ]
    baseline_report = FocusReport(
        generated_at=datetime.now(tz=UTC),
        hours_window=0,
        sessions_scanned=len(sessions),
        messages_scanned=all_msgs,
        top_terms=tuple(baseline_top),
    )

    # Compute relative spikes: (recent_rate) / (baseline_rate)
    # rate = count / n_sessions to normalize volume
    spikes: list[tuple[str, float]] = []
    for term, r_count in recent_counter.most_common(top_n * 2):
        r_rate = r_count / n_recent
        b_rate = all_counter.get(term, 0) / n_all
        if b_rate == 0:
            uplift = r_rate * 10  # new term, high signal
        else:
            uplift = r_rate / b_rate
        spikes.append((term, uplift))

    spikes.sort(key=lambda x: x[1], reverse=True)

    return recent_report, baseline_report, spikes[:top_n]


# ─── Renderer ─────────────────────────────────────────────────────────────────

_BAR_FULL = "█"
_BAR_WIDTH = 16


def _bar(pct: float) -> str:
    filled = round(pct * _BAR_WIDTH)
    return _BAR_FULL * filled + "░" * (_BAR_WIDTH - filled)


def render_markdown(report: FocusReport) -> str:
    """Render a single FocusReport (recent or baseline only)."""
    ts = report.generated_at.strftime("%Y-%m-%d %H:%M UTC")
    window = f"{report.hours_window}h" if report.hours_window > 0 else "全量历史"
    lines = [
        f"## 当前聚焦 · Focus Weights",
        f"> 更新: {ts} · 扫描窗口: {window} · "
        f"{report.sessions_scanned} sessions · {report.messages_scanned} 条消息",
        "",
        "| # | 关键词 | 频率 | 次数 |",
        "|---|--------|------|------|",
    ]
    for i, entry in enumerate(report.top_terms, 1):
        bar = _bar(entry.pct)
        lines.append(f"| {i:2d} | {entry.term} | {bar} | {entry.count} |")
    lines.append("")
    return "\n".join(lines)


def render_full_markdown(
    recent: FocusReport,
    baseline: FocusReport,
    spikes: list[tuple[str, float]],
) -> str:
    """Render a three-section focus report: spikes + recent + baseline."""
    ts = recent.generated_at.strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"## Focus Weights · 注意力权重",
        f"> 更新: {ts}",
        "",
        # ── Section 1: Spikes (the most actionable signal)
        f"### 近期热词 · Spikes（过去{recent.hours_window}h vs 全量基线）",
        f"> 相对基线的上升倍数 — 数值越高说明这个词今天异常活跃",
        "",
        "| # | 关键词 | 上升倍数 |",
        "|---|--------|---------|",
    ]
    for i, (term, uplift) in enumerate(spikes[:15], 1):
        bar = _bar(min(uplift / 5, 1.0))  # cap at 5x for bar display
        lines.append(f"| {i:2d} | {term} | {bar} ×{uplift:.1f} |")

    lines += [
        "",
        # ── Section 2: Recent window
        f"### 近期频率 · Recent（{recent.hours_window}h · "
        f"{recent.sessions_scanned} sessions · {recent.messages_scanned} msgs）",
        "",
        "| # | 关键词 | 频率 | 次数 |",
        "|---|--------|------|------|",
    ]
    for i, entry in enumerate(recent.top_terms, 1):
        lines.append(f"| {i:2d} | {entry.term} | {_bar(entry.pct)} | {entry.count} |")

    lines += [
        "",
        # ── Section 3: Baseline
        f"### 历史基线 · Baseline（{baseline.sessions_scanned} sessions · "
        f"{baseline.messages_scanned} msgs）",
        "",
        "| # | 关键词 | 权重 | 总次数 |",
        "|---|--------|------|--------|",
    ]
    for i, entry in enumerate(baseline.top_terms, 1):
        lines.append(f"| {i:2d} | {entry.term} | {_bar(entry.pct)} | {entry.count} |")

    lines.append("")
    return "\n".join(lines)
