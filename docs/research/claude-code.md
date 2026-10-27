# Claude Code 竞品调研

> 调研时间：2026-10-27。以官方一手资料为准；个别章节引用公开的 system prompt 泄露仓库（已标注"非官方、未经证实"），并与官方文档交叉验证。

**一句话总结**：Claude Code 是 Anthropic 官方的 agentic coding 工具，本质上是一个围绕 Claude 模型的 **agentic harness**（代理框架/脚手架）——模型负责推理，harness 提供工具、上下文管理和执行环境，把语言模型变成能干活的 coding agent。它的核心理念是：**终端优先 + Unix 哲学（可管道、可脚本化）+ 最小魔法**——官方自我描述是 "an agentic coding tool that reads your codebase, edits files, runs commands, and integrates with your development tools"，并强调 "composable and follows the Unix philosophy"（管道输入输出、`claude -p` 非交互模式可嵌入 CI/脚本）。官方最佳实践博客把几乎所有建议归结为一个约束：**context window 是最重要的资源，装得越快性能越差**，整个产品设计（CLAUDE.md、/compact、subagents、skills 按需加载）都在围绕上下文经济学展开。
来源：https://docs.claude.com/en/docs/claude-code/overview 、https://docs.claude.com/en/docs/claude-code/how-claude-code-works 、https://www.anthropic.com/engineering/claude-code-best-practices

---

## 1. 产品定位与核心理念

- **官方定位**："agentic coding tool"，区别于 chatbot——"Unlike a chatbot that answers questions and waits, Claude Code can read your files, run commands, make changes, and autonomously work through problems while you watch, redirect, or step away entirely."（[best-practices](https://www.anthropic.com/engineering/claude-code-best-practices)）
- **终端优先，但同一引擎多形态**：Terminal CLI 是全功能主战场，同一底层引擎延伸到 VS Code/JetBrains/Desktop/Web/CI/Slack。接口决定交互方式，agentic loop 完全一致（[how-claude-code-works](https://docs.claude.com/en/docs/claude-code/how-claude-code-works)）。
- **Unix 哲学 / 可组合**：`tail -200 app.log | claude -p "..."`、`--output-format json/stream-json`，CLI 被设计成管道中的一环（[overview](https://docs.claude.com/en/docs/claude-code/overview)）。
- **"agentic harness" 的自我认知**：官方明说 "Claude Code serves as the agentic harness around Claude: it provides the tools, context management, and execution environment that turn a language model into a capable coding agent."（how-claude-code-works）——这正是 Mars 这种自建 CLI 产品对标的层次。
- **上下文即预算**："Most best practices are based on one constraint: Claude's context window fills up fast, and performance degrades as it fills."（best-practices）

## 2. Agent 主循环与工具集

### 主循环

官方描述为三个阶段循环：**gather context → take action → verify results**，三阶段交融，模型根据上一步结果决定下一步，可以串联几十个动作并自我纠偏。用户也是循环的一部分，可随时打断重定向（[how-claude-code-works](https://docs.claude.com/en/docs/claude-code/how-claude-code-works)）。

### 工具设计粒度（官方文档 + 泄露 system prompt 交叉验证）

内置工具分五类：File operations、Search、Execution、Web、Code intelligence（插件提供），另有编排类工具（subagent、AskUserQuestion 等）。从泄露的 system prompt（**非官方、未经证实**，来源 [asgeirtj/system_prompts_leaks](https://github.com/asgeirtj/system_prompts_leaks)，快照对应 Claude Code v2.1.39 / 2026-02）可见的关键设计决策，与官方文档行为一致：

- **专用工具优先于 Bash，这是硬规则**：prompt 里明确要求读文件用 Read 而非 cat/head/tail，编辑用 Edit 而非 sed/awk，搜索用 Grep/Glob 而非 grep/rg/find；Bash 保留给 "terminal operations"。官方理由：专用工具让用户更容易理解和审查 agent 的工作（渲染 diff、分页、权限规则更细）。
- **Edit 是精确字符串替换而非 patch/diff**：`old_string` 必须在文件中唯一，否则失败；要求先 Read 再 Edit（工具层面强制）；Write 覆盖文件前也必须先 Read。这种"先读后写"的硬约束显著减少盲改。
- **工具描述里塞满了操作纪律**：例如 git 安全协议（NEVER push --force / reset --hard / --no-verify 除非用户明确要求；只新建 commit 不 amend；按文件名 add 而非 `git add -A`）；Bash 超时默认 2 分钟上限 10 分钟、输出 30000 字符截断、后台运行参数等。
- **并行工具调用**：无依赖的调用必须在同一条消息里并行发出；有依赖的严格串行。
- **TodoWrite 任务清单**：强制"同一时刻恰好一个 in_progress"、完成立即标记、测试没过不许标完成——把进度跟踪做成工具而非 prompt 约定，既给模型结构也渲染成用户可见的进度面板。
- **Explore subagent 分流探索**：简单定向搜索直接用 Glob/Grep；"明显需要超过 3 次查询"的探索交给 Explore subagent（Haiku、只读），保护主上下文。
- **危险动作确认逻辑写进 system prompt**："weigh reversibility and blast radius"，本地可逆操作放手做，难逆/影响共享状态的操作默认先确认；一次性授权不代表永久授权（"A user approving an action once does NOT mean that they approve it in all contexts"）。

官方文档中的工具最佳实践（best-practices）：CLI 工具（gh/aws/gcloud）是访问外部服务最省 context 的方式；不认识的 CLI 可以让 Claude `--help` 自学。

## 3. 上下文工程

### CLAUDE.md 记忆机制（[memory](https://docs.claude.com/en/docs/claude-code/memory)）

- **四级层次**：Enterprise policy（系统目录）→ Project（`./CLAUDE.md`）→ User（`~/.claude/CLAUDE.md`）→ Project local（已废弃，改用 import）。上层先加载，下层补充。项目级文件 check-in 到 git 团队共享。
- **递归查找**：从 cwd 向上递归读到根目录前的所有 CLAUDE.md；子树中的 CLAUDE.md 在读到该子树文件时才按需加载（懒加载）。
- **`@path` import 语法**：可递归 import 其他文件（最深 5 层），代码块内的 `@` 不解析。
- **`#` 快捷写入**、**`/memory` 编辑器打开**、**`/init` 自动生成初稿**、**`/doctor` 提议删减**。
- **官方反复强调：CLAUDE.md 必须短**。"For each line, ask: 'Would removing this cause Claude to make mistakes?' If not, cut it. Bloated CLAUDE.md files cause Claude to ignore your actual instructions!"（best-practices）只放模型无法从代码推断的东西（构建命令、团队约定、环境怪癖），不放标准语言惯例和 API 文档。

### Auto memory

Claude 会主动把跨会话的经验写入 memory 目录，每个会话开始加载 MEMORY.md 的前 200 行或 25KB（how-claude-code-works）。泄露 prompt 显示了配套的写作纪律：按主题而非时间组织、记"多次确认的稳定模式"、不记"单文件得出的推测结论"、用户明确要求记住/忘记的立即处理。

### 上下文压缩与会话上下文管理（best-practices、how-claude-code-works）

- 接近上限时**自动 compact**：先清理旧的 tool 输出，再摘要对话；用户的请求和关键代码片段保留。
- `/compact <instructions>` 可带聚焦指令；CLAUDE.md 里可加 "Compact Instructions" 节控制压缩时保留什么。
- `/context` 查看上下文占用；`/clear` 在不相关任务之间清空（官方建议"同一问题纠正超过两次就 /clear 重来，干净会话 + 更好的 prompt 几乎总是胜过累积纠正的长会话"）。
- **MCP tool definitions 默认延迟加载（Tool Search）**：超过 context 10% 时只留工具名，用到再加载定义。
- 单个文件/输出大到压缩后立刻再撑满时，停止自动压缩并报错（防 thrash 死循环）。
- 防污染策略：subagent 隔离探索、skills 按需加载、`/btw` 提问不进历史。

### 系统提示词结构（非官方、未经证实）

泄露快照（v2.1.39，[来源](https://github.com/asgeirtj/system_prompts_leaks)）的结构：身份与两条全局 IMPORTANT 安全规则 → `## System`（输出渲染、权限模式行为、prompt injection 警惕、hooks 反馈处理、自动压缩声明）→ `## Doing tasks`（先读后改、不要过度工程、"只做被明确要求的事"）→ `## Executing actions with care`（可逆性/爆炸半径原则）→ `## Using your tools`（专用工具优先、并行调用规则、Explore 分流阈值）→ `## Tone and style`（简洁、`file_path:line_number` 引用格式、不滥用 emoji）→ `## auto memory` → `## Environment`（cwd、git 状态、平台、日期、模型 ID）→ 完整工具定义。值得注意：大量"工程纪律"（不过度工程、三行重复好过过早抽象、不写防御性死代码）是写在 system prompt 里的行为约束，而非文档建议。与官方文档描述的运行时行为一致（权限提示、压缩、hooks 反馈），可信度较高但仍属非官方。

## 4. 权限与安全模型（[permissions](https://docs.claude.com/en/docs/claude-code/permissions)）

### 分级与审批

- **工具分级**：只读工具（Read/Grep）无需批准；Bash 命令需要批准，"不再询问"按项目目录+命令永久记忆；文件修改需要批准，记忆到会话结束。
- **规则体系**：`allow` / `ask` / `deny` 三类规则，**求值顺序永远是 deny → ask → allow**（与规则宽窄无关）；规则格式 `Tool(specifier)`，如 `Bash(npm run *)`、`Read(//**/.env)`、`WebFetch(domain:example.com)`、`mcp__github__*`。
- **Bash 规则的工程细节**：理解 shell 复合命令（`&&`/`;`/`|` 拆成子命令各自匹配）；剥掉 `timeout`/`nice` 等 wrapper 再匹配；内置一组只读命令（ls/cat/grep/git 只读形式等）免提示。官方坦承"用 Bash 前缀规则限制 URL/参数是脆弱的"，建议改用 deny curl + WebFetch domain 白名单 + PreToolUse hook。
- **权限模式**（Shift+Tab 循环）：`default`（manual，逐项问）→ `acceptEdits` → `plan`（只读探索）→ `auto`（v2.1.283+ 起为交互会话默认：用**独立的分类器模型**审查动作，只拦看起来危险的）→ `dontAsk`（未预批准即拒绝，用于无人值守批处理）→ `bypassPermissions`（仅容器/VM，仍保留 `rm -rf /` 之类的熔断提示）。
- **执行在 harness 不在模型**："Permission rules are enforced by Claude Code, not by the model." prompt/CLAUDE.md 只影响模型想做什么，不改变 harness 允许什么。

### Hooks 作为可编程安全层（[hooks](https://docs.claude.com/en/docs/claude-code/hooks)）

- 生命周期事件：PreToolUse / PermissionRequest / PostToolUse / Notification / UserPromptSubmit / Stop / SubagentStop / PreCompact / SessionStart / SessionEnd。
- **PreToolUse hook 是运行时权限评估器**：hook 是用户注册的 shell 命令，经 stdin 收到 JSON（session_id、tool_name、tool_input），exit code 2 = 阻止并把 stderr 反馈给模型；也可返回 JSON 做 allow/deny/ask 甚至用 `updatedInput` **改写工具入参**。hook 的 block 优先于 allow 规则，但 deny 规则优先于一切 hook——保证企业策略不可被绕。
- 官方立场："CLAUDE.md 指令是建议性的，hooks 是确定性的，保证动作一定发生"——必须每次都执行的事（如编辑后跑 eslint、禁止写 migrations 目录）用 hook 而非写在 CLAUDE.md 里。
- 安全设计：settings 在会话启动时快照，外部修改 hooks 配置会警告且需 `/hooks` 里复核才生效（防恶意热改）；官方文档自带"USE AT YOUR OWN RISK"免责。

### 纵深防御

Permissions（哪些工具/文件/域名）+ OS 级 Sandboxing（Bash 的文件系统/网络隔离，默认 sandboxed Bash 免提示）两层互补；sandbox 边界合并 Read/Edit deny 规则与 WebFetch 域名规则。Settings 优先级：managed（企业，不可覆盖）> CLI 参数 > local project > shared project > user，**deny 永远胜出**。

## 5. 可扩展性：各机制解决什么问题

官方在 best-practices 里有明确的选型指引，四个机制的边界很清晰：

| 机制 | 解决什么问题 | 关键设计 |
| --- | --- | --- |
| **CLAUDE.md** | 每次会话都需要的持久指令 | 每次全量加载，因此必须短 |
| **Skills**（[slash-commands](https://docs.claude.com/en/docs/claude-code/slash-commands)，自定义 slash command 已并入 skills） | 可复用的知识/工作流，**按需加载不占常驻上下文** | `.claude/skills/<name>/SKILL.md`，YAML frontmatter + markdown；描述常驻、正文用时才加载（context 预算约为窗口 2%）；`$ARGUMENTS` 参数替换；`` !`cmd` `` 预执行 shell 注入实时数据；`disable-model-invocation` 控制只能人触发（如 /deploy）；`context: fork` 可让 skill 在隔离 subagent 里跑 |
| **Subagents**（[sub-agents](https://docs.claude.com/en/docs/claude-code/sub-agents)） | 上下文隔离 + 权限/工具收窄 + 模型降级省钱 | `.claude/agents/*.md`；独立 context window，只返回摘要（"subagents 保护主上下文"是官方反复强调的第一用途）；可限 tools、选 Haiku 省钱、挂自己的 hooks、独立 memory 目录；内置 Explore（Haiku 只读）/Plan/general-purpose；subagent 不能再 spawn subagent |
| **Hooks** | 确定性的、零例外的自动化与自定义安全策略 | 见上节 |
| **MCP**（[mcp](https://docs.claude.com/en/docs/claude-code/mcp)） | 接入外部数据源/服务（Jira、Sentry、DB、Figma）的开放标准 | stdio/HTTP/SSE 三种 transport；local/project/user 三级 scope；Tool Search 防工具定义撑爆 context；`mcp__server__tool` 命名使权限规则和 hooks 可精确匹配；官方警告第三方 server 的 prompt injection 风险 |
| **Plugins** | 把 skills/hooks/subagents/MCP 打包分发 | marketplace 机制 |

选型心法（官方原文意图）：要"每次都在"用 CLAUDE.md；要"有时需要"用 skill；要"隔离上下文/限制能力"用 subagent；要"保证执行"用 hook；要"接外部系统"用 MCP。

## 6. 交互形态

### 会话管理（how-claude-code-works、best-practices）

- **一切可逆**：每条用户消息创建一个 checkpoint，编辑文件前自动快照；`Esc` 中断当前动作（上下文保留）、`Esc Esc`/`/rewind` 打开 rewind 菜单可恢复"仅对话/仅代码/两者"，或从某条消息"Summarize from here"做局部压缩。checkpoint 随会话持久化，关终端后再 resume 仍可用；但只覆盖 Claude 文件工具的改动，不替代 git。
- **会话即文件**：plaintext JSONL 存 `~/.claude/projects/`，支持 `--continue` / `--resume` 续接、`--fork-session`/`/branch` 分叉、`/rename` 命名（"treat sessions like branches"）。
- **会话绑定目录**，配 git worktree 实现并行多会话互不干扰。
- 打断引导是核心交互：`Esc` 立即停止；"边跑边发纠正"，当前动作完成后模型先读纠正再决定下一步。

### 与 IDE / git 的集成

- IDE 扩展（VS Code/JetBrains）提供内联 diff、@-mention、plan review、选区上下文共享；同一引擎，CLAUDE.md/settings/MCP 跨界面生效。
- git 是一等公民：harness 启动即感知分支/未提交改动/近期历史；system prompt 内置完整的 commit/PR 工作流协议（并行跑 status/diff/log → 按仓库风格起草 message → 只 add 具名文件 → 新建而非 amend → 跑 status 验证）。

## 7. 官方最佳实践反复强调的原则（[best-practices](https://www.anthropic.com/engineering/claude-code-best-practices)）

1. **上下文是唯一硬约束**：所有模式都服务于省 context——CLAUDE.md 要短、探索交给 subagent、不相关任务之间 `/clear`、skills 按需加载。
2. **Explore → Plan → Code → Commit**：用 plan mode 把研究/规划与实现分离，防"解决了错误的问题"；但官方同时强调不要教条——一句话能说清的 diff 就别 plan。
3. **给 agent 一个可自验的检查闭环**："Give Claude a way to verify its work" 是全文第一条——测试/构建/lint/截图对比，让循环自己闭合；按强度分级：prompt 里要求 → `/goal` → Stop hook 硬门 → 独立验证 subagent（写代码的不给自己打分）。
4. **早纠错、勤纠错；同错纠两次就清场重来**："A clean session with a better prompt almost always outperforms a long session with accumulated corrections."
5. **提示词要具体**：指名文件、约束、参照现有模式（"follow the pattern in HotDogWidget.php"）。
6. **委托而非指挥**（"Delegate, don't dictate"）：给方向和上下文，让 agent 自己决定读哪些文件跑哪些命令。
7. **对抗性复核**：做完让 fresh context 的 reviewer subagent 只看 diff 找 gap；同时警告 reviewer 天然会报"问题"，要限定只报影响正确性的，防过度工程。
8. **规模化路径**：`claude -p` 非交互模式 + `--allowedTools` + worktree 并行 + fan-out 循环；先拿 2-3 个样本调 prompt 再全量跑。

---

## 对 Mars 的启示

1. **抄"专用工具优先 + 先读后写"的工具纪律，而不是抄工具清单本身。** Claude Code 的强大不在于有 Read/Edit/Bash，而在于 system prompt 和工具实现里的一堆硬规则：Edit 必须先 Read、`old_string` 不唯一即失败、Write 覆盖前必须先读、Bash 禁止干文件操作的活。这些约束把模型的"自由度"换成了可预测性和可审查性，Mars 应直接在工具层（而非仅 prompt 层）强制这些不变量——工具失败信息本身就是最好的纠错信号。

2. **上下文预算要当一等公民来设计，而不是事后补丁。** Claude Code 的所有机制（CLAUDE.md 要短、skills 按需加载、subagent 隔离、MCP 工具定义延迟加载、自动 compact 先清 tool 输出再摘要）都是围绕"context window 是性能瓶颈"设计的。Mars v0.1 至少要有：上下文占用可视化（对标 `/context`）、自动压缩、以及"探索走 subagent 只回摘要"的路径。对个人项目，最后一条是性价比最高的。

3. **安全模型执行在 harness，不在模型。** "Permission rules are enforced by Claude Code, not by the model" 是关键架构决策：deny → ask → allow 的固定求值顺序、Bash 复合命令拆分匹配、只读命令白名单免提示。Mars 应实现一个与模型完全无关的规则引擎（哪怕 v0.1 只有"只读工具免批 + Bash 前缀白名单 + deny 优先"三件套），不要把安全寄希望于 prompt 里的 "NEVER"。

4. **记忆机制做分层 + 懒加载，并内置"防膨胀"设计。** 直接可抄：项目级 MARS.md（可 check-in）+ 用户级 ~/.mars/MARS.md 两层、从 cwd 向上递归查找、子目录的记忆懒加载、`#` 快捷写入。更要抄的是配套的"剪枝文化"（`/doctor` 提议删减、"删掉这行会导致犯错吗"标准）——记忆系统最大的失败模式是膨胀后被模型无视。

5. **Hooks 用"shell 命令 + stdin JSON + exit code 2 阻止"这种最低门槛协议。** 这是 Claude Code 可编程性的根基：用户不需要写插件代码，一个 shell 脚本就能实现自定义权限策略和自动化（如"编辑后必须过 lint"）。Mars 早期实现成本低、用户价值高，且天然覆盖"CLAUDE.md 管不住"的确定性需求。配置快照 + 热改警告的安全细节值得一并抄。

6. **可逆性是信任的基础：checkpoint/rewind 比权限更能解放生产力。** "每次编辑前快照 + 对话可 rewind" 让用户敢让 agent 放手试错。Mars 作为个人工具，实现一个"编辑前快照文件 + 会话 JSONL 持久化 + 可 resume/rewind"的 MVP 成本不高，收益巨大——但要记住官方自己的教训：checkpoint 只覆盖 agent 自己的文件工具，Bash 里的改动覆盖不了，所以不替代 git，文档里要明说。

7. **应避免：一上来做多界面/多 agent 编排/MCP 大而全。** Claude Code 的 IDE 集成、agent teams、MCP 生态是后置演化的结果，其根基始终是一个好用的终端 REPL + 扎实的主循环。Mars v0.1 应把预算集中在：主循环质量、工具纪律、权限模型、上下文管理四件事上；MCP 可以只留接口不接实现，subagent 做一个只读 Explore 就够。另外要避免把最佳实践写死在 prompt 里——官方自己都在从 prompt 指令（CLAUDE.md 建议性）向确定性机制（hooks/权限）迁移，Mars 应直接站在迁移后的终点做设计。

---

## 引用的一手资料清单

官方（一手）：
1. [Claude Code overview](https://docs.claude.com/en/docs/claude-code/overview)
2. [How Claude Code works](https://docs.claude.com/en/docs/claude-code/how-claude-code-works)（agentic loop、工具分类、会话、上下文窗口、checkpoint）
3. [Claude Code best practices](https://www.anthropic.com/engineering/claude-code-best-practices)（Anthropic 官方工程博客）
4. [Memory / CLAUDE.md](https://docs.claude.com/en/docs/claude-code/memory)
5. [Permissions](https://docs.claude.com/en/docs/claude-code/permissions)
6. [Hooks](https://docs.claude.com/en/docs/claude-code/hooks)
7. [Subagents](https://docs.claude.com/en/docs/claude-code/sub-agents)
8. [Slash commands / Skills](https://docs.claude.com/en/docs/claude-code/slash-commands)
9. [MCP](https://docs.claude.com/en/docs/claude-code/mcp)

非官方（未经证实，已与官方文档交叉验证）：
10. [asgeirtj/system_prompts_leaks](https://github.com/asgeirtj/system_prompts_leaks) 中的 `claude-code.md`（源自 [marckrenn/claude-code-changelog](https://github.com/marckrenn/claude-code-changelog) 的 `cc-prompt.md`，快照标注为 Claude Code v2.1.39 / 2026-02-10）——用于第 2、3 节的 system prompt 结构与工具描述细节。
