# DeepSeek Harness 竞品调研

> 调研时间：2026-10。源码获取方式：GitHub API + codeload tarball（默认分支 `master`，非 `main`）。
> 仓库：https://github.com/deepseek-ai/deepseek-harness ；文档站：https://deepseek-harness.github.io/deepseek-harness/

**一句话总结**：DeepSeek Harness（`dsh`）是 DeepSeek 官方开源的**通用 agent 运行时/宿主（harness）**，不是评测 harness，也不是传统终端 coding CLI——它的主交互形态是 Web GUI 和 Electron 桌面应用，外加 headless 一次性运行与 JSON-RPC SDK。核心理念是 **"Everything is a Plugin"**：模型适配器、工具注册表、会话日志乃至 agent 主循环本身都是可替换插件，全部构建在 Cordis 插件框架（[cordiverse/cordis](https://github.com/cordiverse/cordis)，配套论文 arXiv:2608.25512）之上。另一个贯穿始终的原则是 **"Model-visible ⟺ logged"**：任何进入模型请求的内容都必须能从 append-only 会话日志重建。项目处于 developer preview，明确警告会有破坏性变更（README.md、SAFETY.md）。

---

## 1. 定位与要解决的问题

- **它是什么**：一个 TypeScript monorepo（60+ 个 `packages/*/*` 工作区包 + `apps/` + Python SDK），产品形态是一个可组合的 agent 宿主。官方定位语："DeepSeek Harness: Everything is a Plugin"（README.md、GitHub repo description）。
- **要解决的问题**：不是"再造一个 CLI coding agent"，而是做一个**一切能力都可经配置替换/扩展的 agent 运行底座**——换文件系统/子进程 provider 到远程沙箱，Bash、PTY、LSP 全部跟着走，"no provider forks"（docs/architecture.md "Capability seams"）。生态面：插件市场、`dsh-plugin` topic、bundle 分发格式。
- **对名字歧义的澄清**：harness 指的是"agent harness"（驱动模型的宿主），其 `benchmarks/` 目录是**工程性能门**（时间/堆内存/扩展性预算，docs/testing.md），`BENCHMARK.md` 仅 5 行、指向 Python SDK 指南——它不是 SWE-bench 那类评测框架。
- **成熟度**：developer preview，SAFETY.md 坦承"未经过安全审计，不得当作安全/生产就绪软件"。

## 2. Agent 主循环

来源：docs/architecture.md "Turn flow"、docs/agent-lifecycle.md（时序图）、packages/core/agent-loop/README.md。

- **两级结构**：**step** = 一次模型请求 + 它触发的工具调用；**turn** = 0..n 个 step，"opens before its first input is claimed and closes once nothing is owed"。
- **循环流程**（简化）：`turn/start` → 认领 inbox 输入 → 组装 prompt + 本 step 工具 schema → `agent/pre-step` waterfall（可拒/可改写）→ `step/start` → `prepareCall()` 绑定适配器 → 从日志派生并冻结历史 → 流式调用 → 工具批执行 → `step/end` → 若工具欠下一轮请求则继续，否则 `agent/turn-stopping` → `turn/end`。
- **工具结果回灌**：工具调用/结果都先落 **durable session 事件**（`tool/call` 执行前记录，`tool/result` 为唯一模型可见结果），下一 step 用 `deriveMessages()` 从日志重新派生历史——**日志是上下文的唯一来源**，不是内存里维护一份 messages 数组。
- **终止条件**：模型自然停止（无工具调用）且 next-step inbox 为空 → 进入 `agent/turn-stopping` 串行检查点（插件可在此拦截续跑）→ `turn/end`。**没有内置 turn 预算**，官方说法是"要限制失控 turn 就从 `agent/turn-stopping` 取消"（agent-loop README "Known Limitations"）。
- **失败与取消的协议完整性**（很值得注意）：
  - 失败 step 收尾前，为每个未应答的工具调用**补录合成错误结果**：已记录 call 无结果的给 `TOOL_OUTCOME_UNKNOWN`（提示模型"仅只读/幂等操作可重试"），连 call 都没记录的给 `TOOL_NOT_STARTED`；取消后来不及派发的给 `ABORTED_BEFORE_DISPATCH`。保证历史里 tool call/result 永远配对。
  - 取消是协作式的；被取消的流会把**已交付给用户的文本前缀**作为 `interrupted: true` 落日志，"下一个请求包含用户实际看到的内容"。
  - 重试不重复 prompt 组装、`agent/pre-step` 和用户消息准入，只重发同一渲染结果。
- **并发**：单 step 内工具按 executionMode 分类——exclusive 调用构成屏障，parallel-safe 调用走有界滚动池（默认 `maxParallelToolCalls: 10`）。

## 3. 工具集设计

来源：docs/tool-catalog.md（**由脚本启动真实插件生成并经 CI 校验**）、docs/tool-execution-pipeline.md。

- **内置工具**（节选，`packages/*/tool-*`）：
  - 执行：`bash` / `pwsh`（每次新进程、可 `run_in_background`），另有 persistent PTY 版（状态跨调用保留）和 6 个 `terminal_*` 工具；
  - 文件：`read`（带行号、offset/limit 分页）/ `edit`（字面替换，非唯一即拒）/ `write` / `read_image` / `str_replace_editor`（Anthropic 风格）；
  - 搜索：`glob` / `grep`——**打包自带 `@vscode/ripgrep` 二进制**，不依赖宿主安装、不过 shell 层；
  - 其他：`lsp`、`web_fetch`/`web_search`、`todo_write`、`skill`（按需加载技能全文）、`subagent`（异步委托，立即返回 id，完成时通知）、`job_list/output/kill`（统一的后台任务控制面）、`schedule_*`、`session_search/trace`、PTC 模式 `run_code`（模型写一段 TS 程序编排多个工具调用）、`plugin_manager`（agent 自管理插件）。
- **schema 粒度**：细。JSON Schema 带 `minLength`、`oneOf` 判别联合、枚举封闭；`description` 写得像行为规约（bash 工具的描述里直接内嵌安全规则："删除/移动前必须验证解析后的绝对路径""用 `${VAR:?}` 防空变量展开"）。
- **执行管线**：统一的三段 waterfall——`tools/pre-execute`（钩子/权限/沙箱）→ 单调 guard（只能 deny 或弃权）→ `tools/execute`（超时/重试/metrics 环绕）→ `tools/post-execute`（可改写结果）→ `finalizeContent` → `tool/result` 落日志。**工具本体不耦合任何策略服务**，策略全挂 waterfall。
- **错误回灌模型**：
  - 管线把任何环节抛出的异常**归一化为 `isError` 结果**，不让异常裸奔到模型；
  - 结构化错误码 + 指导性文本：`LSP_UNAVAILABLE`（provider 缺失时 schema 不变、执行期报错）、`SANDBOX_UNAVAILABLE`、沙箱拒绝标记 `[sandbox: file access denied under <mode> mode]` 并附升级提示；
  - 长输出统一策略：**tail 截断 + 完整内容 spill 到文件、返回路径**（`spill/` 包族；glob 超 100 条、grep 超 250 条同理）。

## 4. 上下文工程

来源：docs/subsystems/system-prompt.md、packages/compaction/compaction-basic/README.md、agent-loop README "Model Experience"、docs/architecture.md "Session log"。

- **system prompt 结构**：分段注册制。每个插件注册 `PromptSection`（name + 数值 order + 静态文本或 provider 函数 + `{{variable}}` 插值），部署级 persona 有专门的 prefix/suffix 槽位；scoped 注册可 shadow 全局同名段。默认 persona 极简："You are a coding agent powered by the {{model}} model."（packages/bundle/web-app/presets/standard.patch.yml）——**身份靠工具和运行时上下文撑，不靠万字 prompt**。
- **system prompt 不走请求字段，而是作为 `system/message` 历史节点**：支持 KV-cache 感知的路由策略——能力够的路由把 prompt 变更**追加**在已缓存历史之后（`systemPromptUpdate: 'in-history'`），不够的才在首个 system 节点原位合并重写（agent-loop README，decision 2026-09-02）。
- **动态上下文（`PromptContext`）**：以 user-role 快照注入，**只有内容变化或 compaction 抹掉后才重新追加**；审批策略切换等事件也会注入一条"通告"user message。一切都是 append-only，刻意保 KV cache 前缀。
- **压缩（`compaction-basic`，默认开启）**：
  - 触发：`floor(min(W×0.8, W−O−B))`，B=65,536 token 余量；保留最新 16% 原文；支持 per-model 覆盖；`/compact` 手动触发；
  - 摘要调用**逐字节重放** system prompt + 工具声明 + 被压缩区段，使摘要请求成为会话的真实前缀，只吃尾部的缓存 miss；
  - provider 确认 `CONTEXT_WINDOW_EXCEEDED` 后的恢复路径：先做 tool-result 剪枝（不耗模型调用），不够才摘要，且只有 surface 代际前进才授权重试；
  - 切换模型时按**目标模型**容量预检历史，失败报 `MODEL_SWITCH_COMPACTION_FAILED`。
- **文件内容注入**：不内嵌——超长一律 spill 成文件返回 locator（`spill` 包）；图片经 `read_image` 转 durable attachment，并有 image-offload 压缩插件。

## 5. 权限与安全

来源：packages/sandbox/sandbox/README.md、packages/interaction/user-approval/README.md、packages/interaction/permission-presets/README.md、SAFETY.md。

- **沙箱三档**（per-call policy，不绑死 provider）：`read-only` / `workspace-write` / `danger-full-access`；后端按平台分（Linux bubblewrap/Landlock、macOS sandbox-exec、Windows ACL restricted-token），并如实报告 enforcement 是 `full` 还是 `partial`。
- **Fail-closed**：请求的模式无法强制时直接 `SANDBOX_UNAVAILABLE` 拒绝执行，**绝不无约束放行**。
- **升级阶梯封闭**：read-only→workspace-write/danger-full-access，workspace-write→danger-full-access；模型可携 `sandbox_permissions` + `justification` 重试原调用一次，审批只对该次调用生效。
- **审批（`ctx.approval`）**：一次性授权（**只有 `allowed-once`，没有 allow-always/规则记忆**）；策略仅 `ask`/`never`；answerer 缺失或抛错一律 `unavailable`→拒绝（fail closed）；每次请求与结果写 log-only 审计事件；`never` 在服务内部先于 waterfall 强制执行，后注册监听器也无法绕过。审批 policy 的完整含义会作为运行时上下文快照告知模型。
- **权限预设**：把 sandbox 模式 + 审批策略打包成用户可选预设（默认 `workspace-write`+`ask`），不匹配的旋钮组合显示为只读的 `custom`。
- **文件写保护**：read-before-write/edit 策略由独立的 `fs-observation-policy` 插件以 `fs/*` 事件门实现，不改工具 schema。
- **整体姿态**：SAFETY.md 明确"沙箱/审批只是减险，不作唯一安全边界"，建议一次性 VM/容器跑不可信负载。

## 6. 交互形态

来源：README.md、docs/architecture.md "Application launch"、python/README.md、packages/core/session 相关文档。

- **四种 shipped profile**（`dsh --profile <name>`）：`web`（本地 Web UI，默认 http://127.0.0.1:3080，主形态）、`headless`（一次性任务，无 server）、`sdk`（JSON-RPC over stdio，供 TS/Python SDK 把 harness 当子进程驱动）、`acp`（自动化协议，无人工交互）。Electron desktop 复用 web 应用。
- **没有终端 TUI profile**——这对 Mars（CLI 产品）是个重要差异点。
- **会话模型**：多轮、可 steering（运行中注入消息入 inbox，下一 step 认领）、可中断（协作式取消）、可恢复。
- **持久化**：append-only JSONL 会话日志（`session.jsonl[.zstd]`，版本化为 `session.vN.jsonl`；**已提交的 generation 永不改名/覆盖/删除**，格式升级走相邻迁移链 vN→vN+1）；支持 fork（turn 边界）、resume、崩溃修复（中断 tail 补 `turn/end`）。子 agent 会话同样持久化、可续聊（`send_message`）。

## 7. 值得注意的工程实践

来源：docs/testing.md、AGENTS.md、scripts/（gen-tool-catalog.ts 等）、各包 README。

1. **测试分层极清晰**：unit（vitest，CI 门是 `packages/*/*/src` **逐文件 100% 行覆盖**——"未覆盖行往往是要删的死代码"）→ real-API e2e（无 key 自动 skip，"我们是 DeepSeek，推理很便宜，不要省真实 API 测试"）→ **recorded-session snapshot**：录制真实会话，之后无 key 回放整机链路做回归；任何模型可见变更必须同 PR 更新快照 → expected-output 测试 → 性能 benchmark 门 → Chromium/WebKit 浏览器快照。
2. **"Verify the world, not the self-report"**：e2e 断言从外部重跑命令/重读文件，不许对 agent 自己的输出做关键词探测——防"作弊 agent 通过测试"。
3. **Mock 只挡昂贵/不确定边界**（LLM 适配器、网络、时钟），下游全用真实现：bridge 测试里真实工具注册表+管线+JSONL 持久化，只换一个 MockAdapter。
4. **文档即代码门**：tool-catalog / config-catalog / cordis API catalog 全部由脚本**启动真实插件**生成并 CI 校验新鲜度；新工具包若没进生成器清单直接 CI 失败（"新工具不可能不被记录"）。文档全双语。
5. **每个包 README 有固定结构**：Use this package / Understand the implementation / **Model Experience**（模型到底看到什么、token 成本、KV cache 影响，逐条列出）/ Known Limitations / Dev Note。把"模型体验"当一等文档是很少见的做法。
6. **配置组合可观测**：`dsh --profile web --dump-config` 打印实际启动的插件树，任何一行都可被 patch 替换；cordis.yml 分层（profile → bundles → 用户 patch → `--patch` overlay）。
7. **贡献规约写在 AGENTS.md 里且极其具体**（187 行）：注册即 effect、waterfall 必须 `next()`、禁 `as unknown`、空 catch 必须命名错误、"misconfiguration fails loud"、跨边界 id 用 branded type。配合 `.agents/notes/` 决策档案与 `.agents/skills/`——这个仓库本身就是"用自家 agent 开发自家 agent"的实验场。

---

## 对 Mars 的启示

1. **抄"单一 append-only 事件日志 + 派生上下文"（Model-visible ⟺ logged），但可以大幅简化。** 让会话日志成为模型历史的唯一来源，每步 `deriveMessages()` 重建请求，Mars 就免费获得 resume/fork/审计/快照回放四个能力，且调试 agent 行为时日志即真相。Mars 不需要 Cordis 式插件事件总线，一个 JSONL event log + 一个纯函数投影就够。
2. **抄"协议完整性优先"的失败处理。** 失败/取消的 step 必须为每个未应答 tool call 补合成结果（区分"已派发结果未知"与"未派发"），保证 call/result 配对；被取消的流把已交付文本落进历史。这类细节直接决定长会话里模型不自乱阵脚，成本极低、收益极高（来源：agent-loop README "Failure and cancellation"）。
3. **抄"长输出 spill + tail 截断"和结构化错误文本。** 工具输出超长时尾部截断、全文落盘、返回路径；错误返回错误码 + 指导模型下一步动作的文本（如"仅只读操作可重试"），而不是裸 stack trace。这是性价比最高的上下文工程手段。
4. **权限模型抄其骨架、砍其规模：** Mars v0.1 只需三档 sandbox 语义（read-only / workspace-write / danger-full-access）+ ask/never 审批 + 一次性授权 + **fail-closed**（无法强制就拒绝执行，绝不静默放行）。升级需 justification 的设计也很值得抄——它把安全博弈变成了模型可见的显式协议。
5. **建 recorded-session 回放测试要趁早。** Mars 目标是跑公开 benchmark，"录一次真实会话、之后无 key 回放全链路"既是回归测试也是 benchmark 调试器；配合"assert the world, not the self-report"（断言文件系统真实状态，不探测 agent 自报输出）。等 benchmark 跑挂了再补就晚了。
6. **上下文工程为 KV cache 让路。** 运行时上下文（cwd、git 状态、审批策略）只在变化时以 append-only 方式追加快照，不要每步重写 system prompt——既省 token 又保缓存。Mars 的 system prompt 也应保持极简（dsh 默认 persona 只有一句话），行为规约放工具 description 里。
7. **应避免：everything-is-a-plugin 的过度工程，和以 Web GUI 为主形态。** dsh 为了"换个 provider 全产品跟着换"付出了 60+ 包、三角色 seam、waterfall 语义、scope 机制的复杂度，这是平台型产品的玩法；Mars 是个人 v0.1，硬编码主循环 + 少数几个刻意留的缝（fs/shell 执行后端可替换）即可。另外 dsh 没有终端 TUI，交互形态（打字体验、中断、审批 UI）不要以它为参照，参考它的 headless/SDK 剖面即可。

---

## 引用的一手资料清单

仓库内文件（均为 master 分支 tarball）：

- `README.md` / `SAFETY.md` / `BENCHMARK.md` / `AGENTS.md`
- `docs/architecture.md`（turn flow、capability seams、session log）
- `docs/agent-lifecycle.md`（turn/step 时序图）
- `docs/tool-execution-pipeline.md`（工具管线）
- `docs/tool-catalog.md`（生成版工具 schema 目录）
- `docs/subsystems/system-prompt.md`（prompt 组装）
- `docs/testing.md`（测试分层策略）
- `packages/core/agent-loop/README.md`（循环实现、失败/取消、Model Experience）
- `packages/compaction/compaction-basic/README.md`（压缩策略）
- `packages/sandbox/sandbox/README.md`（沙箱模式/升级/fail-closed）
- `packages/interaction/user-approval/README.md`、`packages/interaction/permission-presets/README.md`（审批与权限预设）
- `packages/preset/persona/README.md`、`packages/bundle/base/cordis.patch.yml`、`packages/bundle/web-app/presets/standard.patch.yml`（persona 与默认组合）
- `packages/guard/repeat-tool-reminder/README.md`、`packages/guard/timeout-policy/README.md`（循环守卫）
- `packages/spill/README.md`（输出 spill）
- `python/README.md`（Python SDK 形态）

官方 URL：

- https://github.com/deepseek-ai/deepseek-harness
- https://deepseek-harness.github.io/deepseek-harness/
- https://github.com/cordiverse/cordis 、https://arxiv.org/abs/2608.25512（Cordis 框架与论文）
