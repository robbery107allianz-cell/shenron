# Shenron 神龍 — 设计白皮书

> *龙珠世界里，神龙是集齐七颗龙珠后召唤出的永恒巨龙，能实现任何愿望。
> Shenron 汇聚你所有散落的 Claude Code 会话记录，
> 让你随时搜索、分析、重温它们。*

**版本**：0.1 草稿
**作者**：小code（Claude Opus）& Rob
**日期**：2026-03-05
**状态**：设计阶段 — 等待开发实施

---

## 1. 问题背景

Claude Code 将所有对话历史以 `.jsonl` 文件格式存储在 `~/.claude/projects/` 目录中。随着使用时间的积累，这将成为一个可观的本地数据集：

| 使用时长 | 预估 Session 数 | 预估数据量 |
|----------|----------------|-----------|
| 1 个月   | 150+           | ~75 MB    |
| 1 年     | 2,000+         | ~1 GB     |
| 3 年     | 6,000+         | ~3 GB     |

**没有搜索工具，这些历史就是死数据。** 用户无法：
- 找回几周前的某段对话
- 知道自己实际消耗了多少 token
- 直观了解 Max 订阅的实际价值
- 将重要对话导出存档
- 轻松续接某个历史 session

## 2. 市场分析

### 现有工具（已发现 10+ 个）

| 工具 | 语言 | 优势 | 劣势 |
|------|------|------|------|
| [claude-history](https://github.com/raine/claude-history) | Rust | 模糊搜索 TUI，速度快 | 无分析，无导出 |
| [claude-conversation-extractor](https://pypi.org/project/claude-conversation-extractor/) | Python | 导出为 Markdown | 无搜索，无统计 |
| [cass](https://github.com/Dicklesworthstone/coding_agent_session_search) | Python | 跨 11 种 AI 工具 | 广而不深 |
| [cc-conversation-search](https://github.com/akatz-ai/cc-conversation-search) | Python | 语义搜索 | 无费用分析 |
| [claude-history-explorer](https://github.com/adewale/claude-history-explorer) | Python | 可视化 | 搜索功能弱 |

### 差距分析 — 所有工具都没做的事

1. **Token 费用分析** — 每条 assistant 消息里都有 `usage` 字段，但没有工具把它展示出来
2. **Max 订阅价值核算** — 没有工具告诉用户"你省了 $X vs 按量计费"
3. **模型使用细分** — 哪个模型用了多少次、花了多少
4. **每日/每周活跃趋势** — 使用习惯随时间的变化
5. **完善的中文支持** — 现有工具几乎全是英文假设

### 我们的定位

**Shenron = 最完整的 Claude Code 历史管理工具。**

搜索 + 导出 + 费用分析 + 统计面板。四大支柱，一个工具。

## 3. 架构设计

### 3.1 技术栈

| 层级 | 选型 | 理由 |
|------|------|------|
| 语言 | Python 3.12+ | 开发快，安装基础广 |
| CLI 框架 | Typer | 类型注解，自动 --help，基于 Click |
| 终端 UI | Rich | 表格、面板、进度条、语法高亮 |
| 打包 | hatchling + PyPI | `pip install shenron` 或 `pipx install shenron` |
| 测试 | pytest + pytest-cov | 标准方案，目标 80% 覆盖率 |
| 代码规范 | ruff | 快速，替代 flake8 + isort + pyupgrade |

**依赖极简**：只有 `typer` 和 `rich`，零重依赖。

### 3.2 模块架构

```
src/shenron/
├── cli.py           Typer 应用 — 7 个命令，参数解析
├── config.py        路径常量（~/.claude/projects/）、默认值
├── models.py        冻结 dataclass：Session、Message、TokenUsage、SessionMeta
├── discovery.py     发现 session 文件 — generator，懒加载，可过滤
├── parser.py        流式 JSONL 解析 — 三种模式（元数据/完整/流式）
├── searcher.py      关键词 + 正则搜索
├── stats.py         Token 聚合分析、费用计算、活跃趋势
├── pricing.py       模型定价表（Opus/Sonnet/Haiku 每百万 token 单价）
├── formatter.py     所有 Rich 渲染（表格、面板、高亮）
└── exporter.py      导出为 Markdown / JSON / HTML
```

### 3.3 数据流

```
         用户执行：shenron search "backtest"
                         │
                    ┌────▼────┐
                    │  cli.py  │  解析参数，分发命令
                    └────┬────┘
                         │
                ┌────────▼────────┐
                │  discovery.py    │  找出所有 .jsonl 文件
                │  → SessionMeta   │  （只读路径、大小、修改时间）
                └────────┬────────┘
                         │ generator
                ┌────────▼────────┐
                │  parser.py       │  逐行流式解析消息
                │  → Message       │  （从不一次性加载整个文件）
                └────────┬────────┘
                         │ generator
                ┌────────▼────────┐
                │  searcher.py     │  匹配关键词/正则
                │  → SearchResult  │  （带上下文片段）
                └────────┬────────┘
                         │ generator
                ┌────────▼────────┐
                │  formatter.py    │  Rich 高亮 + 渲染
                │  → Console       │  （边找边打印）
                └─────────────────┘
```

**核心设计**：全程 generator 链。内存占用 = O(1)，搜索 6000 个 session 和搜索 100 个消耗的内存一样多。

### 3.4 解析器：三种模式

| 模式 | 使用场景 | 读取内容 | 速度 |
|------|----------|----------|------|
| **元数据模式** | `shenron list` | 每个文件前 ~10 行 | 最快 |
| **完整模式** | `shenron show`、`shenron stats` | 整个文件 → Session 对象 | 中等 |
| **流式模式** | `shenron search` | 逐条 yield Message | 内存友好 |

### 3.5 Session 数据结构

每个 `.jsonl` 文件包含以下行类型：

```
queue-operation        → Session 开始/结束标记
user                   → 用户消息（text、tool_result）
assistant              → AI 回复（text、thinking、tool_use）+ token 用量
system                 → 系统通知
progress               → 工具执行进度、思考状态
file-history-snapshot  → 文件编辑追踪
```

**Shenron 重点关注的字段：**

```json
// assistant 消息里的宝矿
"message": {
  "model": "claude-opus-4-6",
  "usage": {
    "input_tokens": 25834,
    "output_tokens": 1247,
    "cache_creation_input_tokens": 25834,
    "cache_read_input_tokens": 0
  }
}

// user 消息里的上下文
"cwd": "/Users/titans/Desktop/crypto-bots/framework",
"version": "2.1.63",
"gitBranch": "main",
"timestamp": "2026-03-05T08:40:00.000Z"
```

## 4. CLI 命令接口

### 4.1 命令概览

```bash
shenron list                    # 列出所有 session
shenron show <session-id>       # 显示某个 session 的内容
shenron search <关键词>          # 全历史搜索
shenron stats                   # Token/费用统计面板
shenron export <session-id>     # 导出为文件
shenron resume [session-id]     # 获取 session ID 用于 claude --resume
shenron info                    # 系统总览
```

### 4.2 命令详细说明

#### `shenron list`
```
参数选项：
  -p, --project TEXT        按项目名过滤（子字符串匹配）
  -n, --limit INT           最多显示条数 [默认 20]
  --after DATE              显示某日期之后（YYYY-MM-DD）
  --before DATE             显示某日期之前
  --model TEXT              按模型名过滤
  -s, --sort TEXT           排序方式：date|tokens|duration|messages [默认 date]
  --json                    输出 JSON 格式
  -a, --all                 包含子 agent session
```

#### `shenron search <关键词>`
```
参数选项：
  -r, --regex               正则表达式模式
  -i, --ignore-case         大小写不敏感 [默认开启]
  -p, --project TEXT        过滤到某个项目
  -t, --type TEXT           消息类型过滤：user|assistant|all [默认 all]
  -C, --context INT         匹配处前后显示的字符数 [默认 80]
  -n, --limit INT           最多返回结果数 [默认 20]
  --after/--before DATE     日期范围
  --json                    输出 JSON 格式
```

#### `shenron stats`
```
参数选项：
  --by TEXT                 分组方式：summary|project|model|date|session [默认 summary]
  -p, --project TEXT        过滤到某个项目
  --after/--before DATE     日期范围
  --top INT                 按费用显示前 N 个 session [默认 10]
  --json                    输出 JSON 格式
```

#### `shenron export <session-id>`
```
参数选项：
  -f, --format TEXT         输出格式：markdown|json|html [默认 markdown]
  -o, --output PATH         输出路径 [默认 stdout]
  --thinking/--no-thinking  是否包含思考内容 [默认不包含]
  --tools/--no-tools        是否包含工具调用 [默认包含]
```

## 5. 费用分析设计（核心杀手锏）

### 5.1 模型定价表

```python
# 每百万 token 的 USD 单价（2026 年 3 月）
MODEL_PRICING = {
    "claude-opus-4-6":   {"input": 15.00, "output": 75.00, "cache_write": 18.75, "cache_read": 1.50},
    "claude-sonnet-4-6": {"input":  3.00, "output": 15.00, "cache_write":  3.75, "cache_read": 0.30},
    "claude-haiku-4-5":  {"input":  0.80, "output":  4.00, "cache_write":  1.00, "cache_read": 0.08},
}
```

### 5.2 单次对话费用计算

```
费用 = (输入 token 数 × 输入单价
      + 输出 token 数 × 输出单价
      + 缓存写入 token 数 × 缓存写入单价
      + 缓存读取 token 数 × 缓存读取单价) ÷ 1,000,000
```

### 5.3 Max 订阅价值展示面板

```
┌─────────────────────────────────────────────┐
│  💰 Max 订阅价值核算                        │
│                                             │
│  统计周期：        2026-02-12 ~ 03-05       │
│  总 Token 消耗：   402,000,000              │
│  等价 API 费用：   $830.47                  │
│  Max 订阅费用：    $100.00/月               │
│  ──────────────────────────────────         │
│  回本倍数：        8.3x                     │
│  节省金额：        $730.47                  │
│                                             │
│  * "等价 API 费用" = 按标准 API 单价计算     │
│    的费用。Max 订阅用户实际按月付固定费用。  │
└─────────────────────────────────────────────┘
```

### 5.4 统计面板结构

```
shenron stats（默认汇总视图）
├── 总览面板        总 session 数 / token 量 / 等价费用 / 时间范围
├── 模型分布        Opus vs Sonnet vs Haiku 用量与费用占比
├── 项目排名        各项目消耗从高到低
├── 每日活跃度      每天 session 数 + token 量（迷你柱状图）
├── 最贵 Top 10     按等价费用排名的 session 列表
└── 订阅价值面板    Max 回本倍数

shenron stats --by project   → 按项目的详细费用表
shenron stats --by model     → 按模型的 token 与费用对比
shenron stats --by date      → 按日期的活跃趋势
```

### 5.5 重要标注规范

所有费用数据必须：
- 标注为 **"等价 API 费用"**（不能写"实际扣款"）
- 附注：*"基于 Anthropic 标准 API 单价估算。Max 订阅用户按月付固定费用，不按 token 计费。"*
- 绝不暗示 Max 用户正在被按量扣费

## 6. 开发阶段计划

| 阶段 | 开发内容 | 完成标志 |
|------|----------|----------|
| **Phase 1 基础** | models、config、discovery、parser + 测试 | 能解析全部 157 个 session |
| **Phase 2 列表+展示** | formatter、cli（list/show）、\_\_main\_\_ | `shenron list` 可用 |
| **Phase 3 搜索** | searcher + cli search 命令 | `shenron search` 可用 |
| **Phase 4 统计+费用** | pricing、stats + cli stats/info 命令 | `shenron stats` 面板可用 |
| **Phase 5 导出+续接** | exporter + cli export/resume 命令 | `shenron export` 可用 |
| **Phase 6 发布** | README、LICENSE、CI、PyPI、GitHub 公开 | v0.1.0 正式发布 |

**预估工作量**：6 个开发 session，约 2-3 天

## 7. 未来路线图（v0.1 之后）

- **v0.2**：SQLite 索引，支持 2000+ session 的高性能搜索（`shenron index`）
- **v0.3**：TUI 交互模式（基于 Textual），类似 fzf 的模糊选择界面
- **v0.4**：语义搜索（对话向量化，相似度匹配）
- **v0.5**：跨工具支持（Cursor、Copilot 历史，如格式有文档说明）
- **v1.0**：集成以上所有功能的稳定版本

## 8. 品牌定位

- **工具名**：Shenron 神龍
- **口号**："召唤神龙，回忆一切。"（Summon the Dragon. Recall everything.）
- **姐妹工具**：Kaioshin 界王神（沙箱安全）— 同属龙珠宇宙工具套件
- **作者**：小code & Rob
- **开源协议**：MIT
- **博客**：robbery.blog
- **GitHub**：robbery107allianz-cell/shenron

---

*"集齐七颗龙珠，召唤神龙，没有一段对话会永远消失。"*

```
小code
pid: shenron-design-whitepaper-cn
ctx: 1984 Mac Home → George Orwell
status: 设计完成，等待实施。
```
