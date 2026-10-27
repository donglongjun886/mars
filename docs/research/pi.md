# Pi 竞品调研笔记

> 调研对象：https://github.com/earendil-works/pi （commit 6c384aa，2026-10 拉取）
> 说明：pi 是 **TypeScript/Node.js** 项目（要求 Node ≥ 22.19），不是 Python。以下设计结论与语言无关，可直接迁移到 Mars 的 Python 实现。

## 一句话总结

Pi 是一个**极简、可扩展的 coding agent "harness"（骨架）**：核心只提供一个事件驱动的 agent 循环 + 4 个默认工具（read/bash/edit/write），刻意不做 sub-agents、plan mode、权限审批系统，把这些全部推给扩展（extensions）机制让用户自己搭。它的"少即是多"体现在：默认 system prompt 极短、工具 schema 极简、无内置审批，但**会话存储（JSONL 树）、压缩（compaction）、扩展系统、供应链安全**这些"地基"工程做得异常扎实。

来源：`README.md:15-19` —— "Pi is a minimal, extensible agent harness that you can make your own. ... Pi ships with powerful defaults but skips features like sub-agents and plan mode. Ask Pi to build what you want, or install a package that does it your way."

---

## 1. 项目定位与核心理念

- **自我定位**：不是"功能齐全的 agent 产品"，而是"可以据为己有的 agent 骨架"（`README.md:15`）。口号是 "Adapt Pi to your workflows, not the other way around"。
- **刻意不做**（`README.md:19`、`packages/coding-agent/README.md`）：
  - 无 sub-agents、无 plan mode（官方态度：想要就用自然语言让 pi 给你造一个，或装扩展；仓库里有 `plan-mode-extension.test.ts` 说明 plan mode 是用扩展实现的示例）
  - **无内置权限/审批系统**（见第 5 节）
- **Monorepo 分层**（`README.md` Packages 表）：`pi-ai`（多 provider LLM 统一 API）→ `pi-agent-core`（agent 运行时）→ `pi-coding-agent`（CLI）+ `pi-tui`（终端 UI 库）、`chord`（插件运行时）、`pi-telemetry`、`pi-durable` 等。agent 核心与 CLI 产品彻底解耦，agent-core 可单独作为 SDK 使用。
- **扩展即一等公民**：extensions（TS 模块，进程内执行）、skills（agentskills.io 规范，按需加载的指令包）、prompt templates、themes 四种定制机制，可打包成 "Pi packages" 通过 npm/git 分发（`README.md:17`、`packages/coding-agent/docs/extensions.md`、`docs/skills.md`）。

## 2. Agent 主循环

核心实现：`packages/agent/src/agent-loop.ts`（约 960 行，可读性很好）。

**循环结构**——双层循环（`runLoop`，agent-loop.ts:172-330）：

- **内层循环**：`while (hasMoreToolCalls || pendingMessages.length > 0)` —— 每次迭代：注入排队消息 → `prepareRequest` 钩子 → 流式请求 LLM → 执行工具调用 → 工具结果作为 `toolResult` 消息**追加到 context.messages** 回灌 → `finishTurn` 钩子 → `turn_end`。
- **外层循环**：当内层结束（模型不再调用工具）时，检查 follow-up 队列，有则继续，无则 `agent_end` 退出。

**终止条件**：

- 正常：无工具调用、无 steering 消息、无 follow-up 消息。
- `stopReason === "error" | "aborted"`：硬退出，忽略 `finishTurn` 决策（agent-loop.ts:254-265）。
- `stopReason === "length"`（输出被 token 上限截断）：**该消息里所有工具调用全部判失败**，给模型返回"参数可能被截断，请重新发起调用"的错误，而不是冒险执行（agent-loop.ts:273-279, 488-513）。这是个很细的安全网。
- 工具/钩子可返回 `terminate: true` 提示跳过下一次 LLM 调用；只有**整批**工具结果都 terminate 才提前停（agent-loop.ts:700-702）。

**工具执行**：默认**并行**（同批 tool calls 并发执行，但持久化的 toolResult 消息顺序仍按 assistant 原始顺序）；某工具声明 `executionMode: "sequential"` 则整批退化为串行（`packages/agent/README.md:109-116`）。

**钩子体系**（把策略点全部外置，核心循环保持极简）：`transformContext`（裁剪/注入）、`convertToLlm`（自定义消息类型 → LLM 三角色）、`beforeToolCall`（可 block，天然是权限审批挂载点）、`afterToolCall`、`prepareRequest`、`prepareNextTurn`、`finishTurn`（返回 end/continue 控制循环）。

**事件流**：`agent_start / turn_start / message_start / message_update(仅 assistant，携带 delta) / message_end / tool_execution_start / tool_execution_update / tool_execution_end / turn_end / agent_end`（`packages/agent/README.md:185-200`）。所有 UI 形态（交互/JSON/RPC）都消费同一个事件流。

## 3. 工具集设计

内置工具在 `packages/coding-agent/src/core/tools/`。**默认只启用 4 个：read、bash、edit、write**（`src/core/system-prompt.ts:64`）；grep/find/ls 是可选的（启用后 system prompt 会相应改写规则，例如有 grep 就不再提示"用 bash 做 ls/rg/find"，system-prompt.ts:102-116）。

**Schema 粒度——刻意极简**（TypeBox 定义 JSON Schema）：

- `read`: `{path, offset?, limit?}`（read.ts:15-19）
- `bash`: `{command, timeout?}`，timeout 无默认值（bash.ts:40-43）
- `edit`: `{path, edits: [{oldText, newText}]}` —— **一次调用支持多处不相交编辑**，guidelines 明确"多处修改用一次 edit 调用"、"oldText 尽可能短但唯一"（edit.ts:21-51）
- `grep`: pattern + 少量可选过滤参数，**自带 .gitignore 感知**，结果限 100 条/50KB，长行截断 500 字符（grep.ts:21-38, 78）

**每个工具自带 prompt 贡献**：导出 `promptSnippet`（一句话工具简介）和 `guidelines`（使用规则 bullet），system prompt 按当前启用的工具动态拼装（如 read.ts:21-24、edit.ts:44-51）。工具说明不进工具 description 长篇大论，而是拆到 prompt 的规则区。

**错误返回**：约定是**直接 throw**，由 agent 循环捕获后以 `isError: true` 的 toolResult 回灌给模型（`packages/agent/README.md:493-509`："Throw an error when a tool fails. Do not return error messages as content."）。bash 的非零退出码也算错误结果，但 output 照常返回。

**输出截断**（truncate.ts）：所有工具输出受双重限制——**2000 行 或 50KB，先到先截**，绝不返回半行。bash 输出截断时把**完整输出写入临时文件**，在结果里附 `[Showing lines X-Y of N. Full output: /path/...]`，模型可自行 read 该文件（bash.ts:343-352）。

其他细节：edit/write 通过 `file-mutation-queue` 按文件串行化写操作（配合并行工具执行防竞态）；edit 成功后 diff 放在 `details`（给 UI）而非 content（给模型的只是 "Successfully replaced N block(s)"）；read 支持图片并自动 resize。

## 4. 上下文工程

**System prompt 结构**（`src/core/system-prompt.ts`）——这是 pi 最有特色的设计之一：

- prompt 由**命名的有序 section** 组成：`preamble`（无标签）+ `tools` / `rules` / `docs` / `addendum` / `project_context` / `skills` / `cwd`，每节包在同名 XML 标签里（system-prompt.ts:188-192）。
- **默认 preamble 只有一句话**："You are an expert coding assistant operating inside pi, a coding agent harness..."（system-prompt.ts:155-156）。默认 rules 也只有寥寥几条："Be concise in your responses"、"Show file paths clearly when working with files" + 各工具贡献的 guideline。
- **Sections 可在会话中途打补丁**：transcript 里的 system message 支持 `sections` 字段做命名替换，`diffSystemPromptSections` 计算增量（system-prompt.ts:217-229；agent README "Agent State" 节）。即 system prompt 是"可重放的状态"而不是一次性字符串。

**文件内容注入**：项目指令文件（`AGENTS.override.md` → `AGENTS.md` → `CLAUDE.md`，从 cwd 逐级向上到根，外加全局文件）读入后包成 `<project_instructions path="...">` 注入 `project_context` 节（resource-loader.ts:212, 266-300；system-prompt.ts:79-86）。注意：**context 文件不受 project trust 限制，始终加载**（security.md:57）。编辑器输入侧的 `@文件`、粘贴图片、prompt template 展开则在用户消息层面注入（docs/usage.md、docs/how-pi-works.md:23）。

**Skills 按需加载**：prompt 里只放每个 skill 的 name+description，模型判断需要时用 read/bash 自己去读 SKILL.md 全文（docs/skills.md:3；system-prompt.ts:174-182）。

**压缩（compaction）**（`docs/compaction.md`，写得极好的文档）：

- 触发：`contextTokens > contextWindow - reserveTokens`（reserve 默认 16384）；多轮运行中在每轮工具结束后、下一次请求前检查；provider 报 context-overflow 错误时也会触发一次 compact-and-retry 恢复。
- 切点：从后往前累积 token 估算直到 `keepRecentTokens`（默认 20000），**只在 user message 边界切**（绝不在 tool result 处切，tool call 必须与结果共存）；单个 user 轮次超长时允许在该轮内部切，生成两份摘要再合并。
- 摘要格式是**结构化 Markdown**：Goal / Constraints & Preferences / Progress(Done/In Progress/Blocked) / Key Decisions / Next Steps / Critical Context + `<read-files>`/`<modified-files>` 清单（跨多次压缩累积传递）。
- 摘要请求前把对话**序列化成纯文本**（`[User]: ... [Assistant tool calls]: read(path=...)`），防止模型把它当成要继续的对话；序列化时 tool result 截断到 2000 字符、省略 thinking blocks。
- **原始消息不删除**：compaction 只是往会话树追加一个 `CompactionEntry`，后续请求从摘要+保留边界重建上下文。原文永远可回溯、可导出。
- 另有 `/tree` 切分支时的 branch summarization 机制（把离开的分支摘要带进新分支）。

## 5. 权限与安全

**核心理念：不做内置权限系统，把隔离推给操作系统/容器**（`README.md` "Permissions & Containerization"、`docs/security.md`）：

- "Pi does not include a built-in permission system ... it runs with the permissions of the user and process that launched it."（README.md:90）
- **不对每次工具调用请求审批**（usage.md: "Pi does not ask before every tool call"）。想要确认机制？用扩展（官方示例里有 `confirm-destructive.ts`、`dirty-repo-guard.ts`）。
- 官方推荐三种隔离姿势：Gondolin 扩展（工具调用路由进本地 micro-VM）、纯 Docker、OpenShell 沙箱（`docs/containerization.md`）。
- 安全文档非常坦诚：把模型输出当不可信输入、明示 prompt injection 风险、声明"无内置沙箱"不在安全边界内（security.md:1-7, 99）。

**唯一内置的闸门是 project trust**（security.md:27-83）：发现项目目录里有 `.pi/settings.json`、`.pi/extensions`、`.pi/skills`、`.pi/mcp.json`、`.pi/SYSTEM.md` 等**可执行/可配置资源**时，要求用户做信任决策（ask/always/never，存 `~/.pi/agent/trust.json`，支持 `--approve/--no-approve`）；不信任则跳过这些资源加载。注意它保护的是"启动时加载什么"，而不是"运行时工具能干什么"。

**供应链安全倒是做了重投入**（README.md "Supply-chain hardening"）：直接依赖全部钉死精确版本、`.npmrc` 设 `min-release-age=2` 防同日发版投毒、lockfile 提交需显式环境变量放行、安装全程 `--ignore-scripts`、install-lock 对 lifecycle scripts 维护显式 allowlist、CI 定期跑 `npm audit` + `npm audit signatures`。

## 6. 交互形态

**会话模型**（`docs/sessions.md`、`docs/how-pi-works.md`）：

- 会话持久化为 **JSONL 文件，条目构成一棵树**：每条 entry 有 id + parentId，"当前 entry" 决定活动分支。回到历史任意点继续**不会丢失**旧分支——`/tree`（会话内移动）、`/fork`（从某个 user 消息开新会话文件）、`/clone`（拷贝当前分支）。
- 会话按工作目录分组存于 `~/.pi/agent/sessions/`；`pi --continue` / `--resume` 恢复；`--no-session`  ephemeral。
- **多轮 + 运行中打断**：agent 工作时按 Enter 发 steering 消息（当前轮工具执行完后注入、下一轮生效）；Alt+Enter 发 follow-up（当前任务全部结束后执行）；Esc 中止并把排队消息退回编辑器（usage.md "Change direction"；agent README "Steering and Follow-up"）。

**四种接口共用同一 agent/session 机制**（how-pi-works.md:33-39）：交互式 TUI（自研 `pi-tui`，差分渲染）、print 模式（一次性输出）、JSON 模式（事件 JSONL 输出）、RPC 模式（stdin/stdout JSONL 双向）、外加 TS SDK。流式输出靠第 2 节的事件流：`message_update` 携带 text_delta 等增量；bash 输出流式累积并按节流刷新 UI。

小亮点：`!` 前缀直接在会话里跑 shell 命令并把输出注入对话（`!!` 只运行不注入）；会话可导出 HTML/JSONL、`/share` 传 gist。

## 7. 值得注意的工程实践

- **分层 monorepo，agent 核心可独立用**：agent-core 不依赖 TUI/CLI，任何宿主（CLI、RPC、第三方 app 如 OpenClaw）都复用同一运行时。README 本身就是最好的 API 文档。
- **事件溯源式会话存储**：一切（消息、压缩、分支摘要、模型切换）都是 JSONL 树里的 entry，恢复/分叉/导出/分享全部从这个单一抽象免费获得。
- **测试投入巨大**：709 个 `*.test.ts`；`test.sh` 用 `env -i` + 临时 HOME 做**完全隔离的测试环境**（连 git/npm 配置都重定向到临时目录，清理前校验目录归属标记防误删）；`test/suite/` 用 faux provider 跑 harness 测试，**不碰真实 LLM API**（AGENTS.md:37-38）。
- **AGENTS.md 即开发宪法**：125 行高密度规则——多 agent 会话并发时的 git 安全（禁 `git add -A`、`reset --hard`，只提交自己改的文件）、代码风格（禁 inline import、禁 `any`、只用 erasable TS 语法）、"用户指令与本文档冲突时先确认"。这本身就是一份"如何约束 coding agent"的实战样本。
- **文档即产品**：40+ 篇 docs，`docs/how-pi-works.md` 49 行讲清整体架构；compaction.md 带 ASCII 图解释切点算法。文档路径甚至直接进了 system prompt（让 agent 能自查文档，system-prompt.ts:162-169）。
- **可观测性独立成包**：`pi-telemetry` 提供 vendor-neutral 的遥测契约——显式传递 context、NOOP 默认实现、无全局状态、无后端依赖，适配器可接 OpenTelemetry/Sentry（`packages/telemetry/README.md`）。外加 crash-log、diagnostics、cache-stats 等模块。
- **模型数据代码化**：模型 catalog 从 pi.dev 生成进 `models.generated.ts`（禁止手改，必须改生成脚本），Nix 离线构建时用 pinned catalog 快照（README.md:66-70）。
- **贡献者闸门**：新贡献者的 issue/PR 默认自动关闭，维护者每天复查——用自动化抵挡 AI 生成的低质量 PR 洪水（README.md:11、CONTRIBUTING.md）。

---

## 对 Mars 的启示

1. **默认 prompt 要短，工具规则按需注入（可直接抄）**。pi 的默认 preamble 只有一句话，规则只有 2 条通用 + 每个启用工具自带的 1-4 条 guideline。Mars v0.1 不该写一大段"你是资深工程师……"的八股 prompt；让每个工具自己声明 snippet/guidelines，system prompt 按启用的工具集动态拼装。理由：prompt 越短越不容易自相矛盾，且工具启用/禁用时规则自动保持一致。

2. **工具错误用异常回灌 + 输出双重截断 + 完整输出落盘（可直接抄）**。工具失败就抛异常，框架统一转成 `isError: true` 的 tool result，不要让工具把错误伪装成正常内容；输出按"行数 + 字节数"双限截断，截断时把完整输出写临时文件并把路径告诉模型。理由：这套约定让工具实现极其简单（不用每个工具设计错误 schema），模型又能自愈（重试、读完整输出）。

3. **会话用 JSONL 树（id/parentId），压缩是追加 entry 而非删除历史（强烈建议抄）**。pi 的 resume/fork/tree/导出/分享全都从这一个存储抽象长出来；compaction 追加摘要 entry、原文永存，调试"模型当时到底看到了什么"时极其有用。Mars 跑 benchmark 时需要精确复盘轨迹，事件溯源式存储几乎是必要条件。理由：存储模型决定了交互形态的上限，事后补分叉能力比重做存储贵得多。

4. **把 agent 循环做成事件流，接口形态复用同一事件（建议抄）**。pi 的交互 TUI、print、JSON、RPC、SDK 全是同一组事件的消费者。Mars 哪怕 v0.1 只做交互 CLI，也应在循环层先发结构化事件（turn/tool/delta 粒度），而不是直接 print——后续接 benchmark runner（等价于 pi 的 JSON/RPC 模式）时零改动。理由：benchmark 需要程序化驱动 agent，事件流是最干净的接缝。

5. **steering/follow-up 双队列打断模型（可借鉴）**。运行中 Enter=插话纠正（下一轮生效）、Alt+Enter=排队后续任务、Esc=中止并退回队列。理由：日常编码中"agent 跑偏了要立刻纠"是高频场景；实现只需在循环的两个固定点轮询队列，成本极低，体验收益大。

6. **权限问题：不要照抄 pi 的"零审批"，但也别先做复杂权限系统（明确取舍）**。pi 是"自带干粮的高级用户"产品，敢把安全完全推给容器；Mars 是作者自己的日常工具，逃逸成本是个人承担，v0.1 建议学 pi 把审批做成循环外的 `beforeToolCall` 钩子接口，默认全放行 + 留一个"危险命令确认"的最简实现（pi 官方示例 `confirm-destructive.ts` 就是这个思路）。理由：pi 证明了审批可以完全不进核心循环；但无审批跑公开 benchmark 或无人值守任务时，至少要有沙箱/容器这层故事的答案。

7. **学 pi 的"地基重于功能"分配，警惕其复杂度（应避免的点）**。pi 的极简是**功能面**的极简，工程面并不简：monorepo 7+ 包、扩展/技能/包/主题四套机制、信任管理、遥测包……这些是为了"让所有人定制"付出的复杂度。Mars 是个人产品，v0.1 不需要扩展系统和插件生态，应把 pi 省下来的"功能复杂度"预算花在 pi 做得好的地方：会话存储、compaction（含其结构化摘要格式，几乎可直接照搬）、工具截断、测试环境隔离（`test.sh` 的 env 隔离思路在 Python 里同样适用）。理由：pi 作者本人也是先做了极简内核、生态是长出来的，不是第一天设计的。
