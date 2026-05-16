# TODO: shenron compile --with-observations

**状态**: 设计阶段
**创建**: 2026-04-17
**预期动手**: 2026-04-24 前后（observations buffer 攒够 1 周数据后）
**背景**: 对标 claude-mem 的 PostToolUse observation 机制，详见 `~/Code-Rob-Wiki/.observations/README.md`

---

## 目标

让 `shenron compile` 除了读 Claude Code 原始 JSONL 对话流，还能读 `~/Code-Rob-Wiki/.observations/YYYY-MM-DD/<session_id>.jsonl`（PostToolUse 事件流），**把工具视角的语义写入 Wiki concept 节点**。

## 当前 compile 流程（需要修改的地方）

```
shenron compile --after 2026-04-14 --output ~/Code-Rob-Wiki
  ├── discovery.py: 扫 ~/.claude/projects/**/*.jsonl（对话流）
  ├── parser.py:    解析 user/assistant 消息
  ├── compiler.py:  概念匹配 + 权重计算 + session .md 生成
  └── exporter.py:  写入 Wiki/sessions/
```

## 新增数据源

```
~/Code-Rob-Wiki/.observations/YYYY-MM-DD/<session_id>.jsonl
```

每行 JSON: `{session_id, tool_name, tool_input, tool_response, cwd, observed_at}`

## 设计要点

### 1. CLI 增加 flag

```bash
shenron compile --with-observations [--observations-dir PATH]
```

默认 dir: `~/Code-Rob-Wiki/.observations`

### 2. discovery 按 session_id 关联

原对话流 JSONL 有 session_id；observations JSONL 文件名就是 session_id。**按 session_id join**。

### 3. 新增聚合字段（per session）

在每个 session 的编译结果里，除了现有字段，加：

- `tools_used`: `{Bash: 12, Read: 8, Edit: 3, ...}`（工具调用计数）
- `files_touched`: 去重文件路径列表（从 Edit/Write/Read 的 `file_path` 提取）
- `commands_run`: 去重命令列表（从 Bash 的 `command` 字段提取，**截断敏感 args**）
- `web_fetched`: WebFetch/WebSearch 的 URL/query 列表

### 4. 写入 session .md

在 session 文件的 frontmatter 或正文末尾追加"工具履历"段落：

```markdown
## 工具履历（observations）
- 改动: `file1.py`, `file2.md`
- 命令: `git commit`, `npm run build`
- 查询: "claude-mem architecture"
```

### 5. concept 节点增强（Phase 2 的事）

当前 concept 的 sessions 列表只有 session_id 和日期。用 observations 之后：

- "Kaioshin" 概念节点可列出：**"被扫描过的仓库"**（从 Bash 的 `kai scan` 命令聚合）
- "SUNBVE" 可列出：**"涉及的具体文件"**
- "Ming Harmony" 可列出：**"实际跑过的部署命令"**

这会让概念从"讨论过"升级到"做过"。

## 验收标准

- [ ] `shenron compile --with-observations --dry-run --after 2026-04-17` 能识别 observations 目录
- [ ] 生成的 session .md 里有"工具履历"段落
- [ ] Phase 2 `/wiki` 充实概念节点时能引用工具履历
- [ ] 不破坏现有 compile 速度（observations 读取 < 1s / session）

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| observations 含敏感输入（token、路径） | 只展示聚合统计，不展示原始 tool_input；敏感字段正则脱敏 |
| 数据量膨胀 | 按日期目录；compile 时只读 `--after` 范围内 |
| session_id 在两处不匹配（版本升级） | 提前写单元测试验证 |

## 代码入口（改动预估）

- `src/shenron/discovery.py` — 加 `discover_observations(session_id)` 函数
- `src/shenron/compiler.py` — 加 `merge_observations(session_data, obs_data)` 函数
- `src/shenron/exporter.py` — session .md 模板加"工具履历"段落
- `src/shenron/cli.py` — `compile` 命令加 `--with-observations` / `--observations-dir`
- `tests/test_observations.py` — 新增

预估工作量: 半天 ~ 一天（视测试覆盖度）

## 动手提示（给未来的小code）

1. 先看 `~/Code-Rob-Wiki/.observations/$(ls ~/Code-Rob-Wiki/.observations | tail -1)/` 实际数据形态
2. 写单元测试前先 `shenron compile --dry-run` 理解当前输出
3. 小步迭代：先只加 `tools_used` 聚合，跑通，再加 `files_touched` 等
4. 记得脱敏：Bash 的 `command` 字段会含完整命令，别把 token 漏进 Wiki
