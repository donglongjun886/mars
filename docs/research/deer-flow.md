# DeerFlow 竞品调研：一个非 coding agent 框架对 coding agent 的借鉴意义

> 调研时间：2026-10-27。调研对象：https://github.com/bytedance/deer-flow
>
> **重要版本说明**：DeerFlow 在 2026 年 2 月发布了 2.0，是**从零重写**，与 v1 无共享代码。仓库 `main` 分支现在是 2.0（"super agent harness"），而任务所指的"深度研究框架"（planner/coordinator/researcher 多角色流水线）维护在 `main-1.x` 分支。本笔记以 **1.x（深度研究框架）为主体**（这正是一次典型多智能体架构的完整样本），同时把 **2.0 的重写决策本身**作为重要一手证据引用。来源标注：`[1.x]` = main-1.x 分支文件路径；`[2.0]` = main 分支文件路径。

## 一句话总结

DeerFlow 1.x 是字节跳动开源的**深度研究（Deep Research）框架**：基于 LangGraph 状态机编排一条 `coordinator → (background_investigator) → planner → human_feedback → research_team → {researcher / analyst / coder} → reporter` 的固定多角色流水线，核心理念是**"计划先行 + 角色专精 + 人在环路"**——把开放式研究任务先冻结成一份结构化 JSON 计划（Plan/Step 的 pydantic schema），再按计划逐步派发给只持有各自工具集的专职 agent 执行，最后由 reporter 聚合产出报告。值得注意的是，字节自己在 2.0 中放弃了这条固定流水线，重写为"单一 lead agent + 动态 subagent + 中间件链 + skills"的 harness 架构——这对 Mars 的架构选型是最有价值的一手信号（详见末节）。

---

## 1. 项目定位与架构总览

- **解决的问题**：自动化深度研究——给一个开放式问题，自动完成"澄清需求 → 制定研究计划 → 多路检索/爬取 → 分析/计算 → 生成带引用的长报告"，外加播客、PPT 等内容再生产（README.md §Features [1.x]）。
- **架构形态**：**固定拓扑的多智能体状态机**，不是动态 multi-agent 协作。全部节点和边在编译期写死（`src/graph/builder.py` [1.x]）：
  - 节点：`coordinator`、`background_investigator`、`planner`、`human_feedback`、`research_team`（空节点，纯路由）、`researcher`、`analyst`、`coder`、`reporter`。
  - 唯一的条件边在 `research_team` 上：`continue_to_running_research_team()` 扫描当前计划里第一个没有 `execution_res` 的 step，按 `step_type`（research/analysis/processing）路由到 researcher/analyst/coder；全部完成则回到 planner（`src/graph/builder.py:23-47` [1.x]）。
- **关键结构观察**：所谓 "research_team" 根本不是 supervisor 模式下的动态调度——它是一个 `pass` 的空节点（`src/graph/nodes.py:957-961` [1.x]），真正的调度逻辑是"**顺序扫描 plan 里第一个未完成的 step**"。即 DeerFlow 的"multi-agent"实质是：**一份共享的 Plan 数据结构 + 一个确定性分发器 + 若干同构的 ReAct agent 实例**。researcher/coder/analyst 复用同一个 `_execute_agent_step()` 执行器，只是工具列表和 prompt 模板不同（`src/graph/nodes.py:1354-1505` [1.x]）。

## 2. 编排模型：LangGraph 节点/状态机设计

- **State 定义**（`src/graph/types.py` [1.x]）：继承 LangGraph `MessagesState`，扩展字段包括 `research_topic`、`current_plan: Plan`、`observations: list[str]`、`plan_iterations`、`final_report`、澄清状态（`clarification_rounds` 等）、`citations`、`goto`。`messages` 走 LangGraph 默认的 append reducer，业务字段走默认覆盖语义。
- **节点返回 `Command(update=..., goto=...)`**：LangGraph 把"更新状态"和"跳转"合并在一个返回值里，这是 1.x 所有节点的统一交接方式。
- **角色分工与交接**：
  - **coordinator**：入口路由器。它不做研究，只用 tool-calling 做意图分类：`handoff_to_planner` / `handoff_after_clarification` / `direct_response` 三个"信号工具"（tool 函数体为空，仅靠 LLM 选择哪个 tool 来表达路由决策，`src/graph/nodes.py:48-76` [1.x]）。可选的多轮澄清（默认关闭，最多 3 轮）也在这里。
  - **planner**：产出严格符合 `Plan` pydantic schema 的 JSON（`src/prompts/planner_model.py` [1.x]）。若 `has_enough_context=true` 直接跳 reporter；否则进 human_feedback。`max_plan_iterations`（默认 1）限制 re-plan 次数。
  - **human_feedback**：用 LangGraph `interrupt()` 挂起图，等人审计划；接受 `[ACCEPTED]` / `[EDIT_PLAN]` 前缀的反馈协议（`src/graph/nodes.py:458-497` [1.x]）。CLI 模式可 `auto_accepted_plan` 跳过。
  - **执行层**：researcher（web_search + crawl + RAG 工具）、analyst（零工具纯推理）、coder（python_repl）各自是独立的 `create_react_agent` 式 agent 子图，有自己的 recursion_limit（默认 25，env `AGENT_RECURSION_LIMIT` 可调）。
  - **reporter**：收 `observations` + `citations`，一次性生成最终报告，然后 END。
- **防御性工程很厚**：planner 输出要过 `repair_json_output`（修 markdown 代码块包裹）、`extract_plan_content`（兼容 str/AIMessage/dict/多模态 content 等各种畸形返回）、`validate_and_fix_plan`（自动补缺失的 `step_type`、强制至少一个 search step）——`nodes.py:125-200, 398-455` [1.x]。这侧面说明：**让 LLM 产出严格结构化计划是这套架构最脆弱的环节**，他们用了大量代码兜底。
- **逃逸阀**：agent 子图撞 recursion_limit 时，`enable_recursion_fallback`（默认开）会把已积累的 messages 换一个"recursion_fallback" prompt 让 LLM 不带工具总结收尾，而不是整个 step 失败（`nodes.py:1007-1077`、`src/prompts/recursion_fallback.md` [1.x]）。

## 3. Prompt 工程

- **组织方式**：**Jinja2 模板 + 按角色一个 `.md` 文件**（`src/prompts/template.py` [1.x]）。`src/prompts/{coordinator,planner,researcher,analyst,coder,reporter}.md`，每个还有 `*.zh_CN.md` 本地化变体，运行时按 locale 回退加载。
- **注入变量**：state 全量字段 + Configuration dataclass 全量字段 + `CURRENT_TIME`（每个模板头部都注入当前时间，对抗模型知识截止日期问题）。
- **写法特点**（以 `planner.md`、`researcher.md` [1.x] 为例）：
  - 大量"CRITICAL/MANDATORY"级别的硬约束对抗模型的系统性失败模式，例如 planner 强制 `need_search: true`（"Without web search, the report will contain hallucinated/fabricated data"）、researcher 强制"NEVER generate URLs on your own"。
  - **用 TypeScript interface 描述输出 schema** 而不是 JSON Schema——`planner.md:224-239` 用 ```ts interface Plan``` 块定义输出契约，附完整 JSON 示例和"常见错误❌/✅"对照。
  - prompt 与代码双重强制：prompt 里喊 MANDATORY，代码里再 `validate_and_fix_plan` / `validate_web_search_usage` 兜底（`nodes.py:964-1004` [1.x]）。**Prompt 约束不可信，必须有程序化校验**这一原则体现得很彻底。
- **reporter 的风格化**：`reporter.md` 用 Jinja `{% if report_style %}` 分支支持 academic / popular_science / news / social_media / strategic_investment 五种文风，由配置 `report_style` 驱动（`src/config/report_style.py` [1.x]）——同一个节点通过配置换人格。

## 4. 状态与上下文管理（防上下文爆炸）

这是 1.x 最值得细看的部分，有四层机制：

1. **结构化中间结果，而非消息堆积**：每个 step 的执行结果写入 `step.execution_res` 和全局 `observations: list[str]`。下游节点拿到的是**压缩过的 findings**（reporter 只读 observations + citations，不读全部 messages，`nodes.py:877-954` [1.x]）。`messages` 虽在 append，但关键交接走专用字段。
2. **确定性 token 预算压缩**：`src/utils/context_manager.py` 的 `ContextManager`——
   - 自实现的粗略 token 估算（ASCII 4字符≈1 token，CJK 1字符≈1 token；ToolMessage 加权 ×1.3）；
   - 超限时两段压缩：先把 `web_search` ToolMessage 里每条结果的 `raw_content` 截断到 1024 字符；仍超限则**丢中间的老消息**、保留前缀 N 条（`preserve_prefix_message_count=3`，保住 system+任务说明）和最近消息；
   - 以 `pre_model_hook` 挂在每个执行 agent 的模型调用前（`nodes.py:1412-1413` [1.x]），也在调用前对整个 agent_input 做一次压缩（`nodes.py:1183-1199`）。
3. **源头截断**：crawl 工具本身就把网页正文截到前 1000 字符（`src/tools/crawl.py:48-55` [1.x]）；token 上限来自 `conf.yaml` 的 `MODEL_TOKEN_LIMITS`/模型 `token_limit` 配置。
4. **引用外置**：citations 从 tool 消息里程序化抽取（`src/citations/`），作为独立 list 传给 reporter 并**放在 observations 之后、最靠近生成点**，注释明确说这是为了降低模型"忘记真实 URL 而编造"的概率（`nodes.py:929-938` [1.x]）。

另有 `validate_message_content`（`context_manager.py:286-341`）在调 LLM 前统一修 None/非字符串/超长 content（单条上限 100000 字符），属于防御性清洗。

## 5. 工具与外部集成

- **内置工具极少**：researcher = `web_search` + `crawl_tool` + 可选 `local_search_tool`（RAG）；coder = `python_repl_tool`（`src/tools/python_repl.py`）。每个 agent 只挂自己角色的工具（`nodes.py:1426-1505` [1.x]）。
- **搜索引擎可插拔**：`src/tools/search.py` 用统一工厂 `get_web_search_tool()` 按 `SEARCH_API` env 选择 Tavily / Brave / DuckDuckGo / Serper / SearXNG / arXiv / Wikipedia / InfoQuest，全部经 `create_logged_tool` 装饰器包一层 IO 日志。工具名统一叫 `web_search`，上层无感知。
- **爬虫**：`src/crawler/` 用 Jina reader 把 URL 转 markdown，再由 `compress_crawl_content` 截断。
- **MCP 动态工具**：`nodes.py:1385-1410` 用 `MultiServerMCPClient` 按配置把 MCP server 的工具注入指定 agent（`add_to_agents` 字段控制归属），工具描述前缀 "Powered by '<server>'"。配置见 `docs/mcp_integrations.md` [1.x]。
- **RAG**：RAGFlow / VikingDB / Milvus retriever（`src/rag/`），用户上传的 Resource 列表进 state。
- **HITL 工具拦截**：`src/agents/tool_interceptor.py` 可把任意工具包一层，执行前触发 LangGraph `interrupt` 等人确认（`interrupt_before_tools` 配置）——**工具粒度的人审**，不止计划粒度。

## 6. 工程质量

- **测试**：pytest，`tests/unit/`（graph/config/tools/llms/citations 等）+ `tests/integration/test_nodes.py`（直接单测每个节点函数，mock LLM，重点测各种畸形 plan JSON 的解析路径）+ `make coverage`。测试重心明显放在"LLM 输出不规范"的兜底逻辑上。
- **可观测性**：三重——stdlib logging（`DEBUG=True` 全开）；LangChain `LANGCHAIN_VERBOSE/DEBUG`；LangSmith tracing（env 一键开，README §Enabling LangSmith Tracing、`docs/DEBUGGING.md` [1.x]）。LangGraph Studio 可视化调试图（`langgraph.json` 注册）。所有工具 IO 过 `@log_io`。
- **配置管理**：两层——`conf.yaml`（模型端点/key/搜索引擎参数/token limit，含 `BASIC_MODEL`/`REASONING_MODEL`/`VISION_MODEL`/`CODE_MODEL` 四档模型分级，见 `conf.yaml.example`）+ `.env`（密钥、开关）；运行时 per-request 的 `Configuration` dataclass 从 RunnableConfig + env 合并（`src/config/configuration.py`）。**AGENT_LLM_MAP**（`src/config/agents.py`）把每个角色映射到一档模型——角色可配不同模型（如 planner 用 reasoning 模型），但默认全 basic。
- **人机交互**：两级 HITL——计划级（`interrupt()` + `[ACCEPTED]`/`[EDIT_PLAN]` 协议，支持 auto-accept 关闭）和工具级（ToolInterceptor）。澄清循环（coordinator 多轮提问，有 max rounds 强制收口，防止无限问下去）。
- **工程坦白**：`builder.py:76` 还留着 `# TODO: be compatible with SQLite / PostgreSQL`——1.x 的 checkpointer 只有 MemorySaver，持久化没做完（2.0 才补齐）。

## 7. 多智能体复杂度：哪些是过度设计，哪些是精华

**对单人 coding agent 属于过度设计的：**

- **固定角色流水线本身**。coordinator/planner/reporter 的分工是为"开放式研究 → 长报告"这个特定产物形态设计的。coding 任务是**目标确定、反馈即时（编译/测试可验证）**的活动，不需要专门的"意图路由节点"和"报告聚合节点"。
- **handoff 信号工具协议**（空 tool 函数体只为让 LLM 选路由）：这是对"LLM 不能做可靠结构化决策"的 workaround，引入了 coordinator 节点 + 三个伪工具 + 大量分支兜底代码（`coordinator_node` 有 280 行，`nodes.py:589-874`），而收益只是"寒暄时不去跑研究"。
- **逐节点 LLM 调用的链式兜底**：planner 输出 JSON → 修复 → 校验 → 人审 → 规范化再校验——1.x 有数百行代码在对抗"LLM 产不出合法计划 JSON"。这条链路在 coding agent 里完全可以不存在（计划不必是跨节点传递的严格 schema 对象）。

**精华（与领域无关的通用实践）：**

- **Plan 作为一等数据结构 + 确定性分发器**：`Plan/Step` pydantic 模型 + "扫第一个未完成 step"的派发，本质是把 LLM 的不确定性限制在"产计划"一刻，之后执行完全确定性。coding agent 的 todo list / task list 就是这个的简化版。
- **上下文工程四件套**：结构化中间结果（observations）代替消息堆积；模型调用前的 token 预算检查与截断 hook；工具输出源头截断；把易丢失的关键信息（citations）移到最靠近生成点的位置。每一条都能直接搬。
- **防御层与 prompt 分离**：prompt 里喊 MANDATORY，代码里做 validate & repair，两层都写、互不替代。
- **recursion/step 上限 + 优雅降级**：撞限不让整个任务死，而是用已有材料收尾。
- **工具粒度的人审拦截**、**模型分级**（简单活给便宜模型）、**工具 IO 全量日志**。

## 对 Mars 的启示

**核心问题：Mars v0.1 该不该引入多智能体/graph 编排？——不应该，至少不是 DeerFlow 1.x 这种。理由如下，且最有力的证据来自字节自己：**

1. **字节自己投票了：2.0 抛弃了固定多角色流水线。** DeerFlow 2.0 是"ground-up rewrite, shares no code with v1"（README.md §Note [2.0]），新架构是**单一 lead agent + 动态生成的 subagent + 中间件链 + skills**（`docs/ARCHITECTURE.md` §1、§3 [2.0]：`make_lead_agent()` + ThreadData/Sandbox/Summarization/TodoList/Clarification 等 middleware）。一个靠多智能体框架出名的团队，做完 1.x 后的结论是收敛到 lead-agent harness——这与业界（Claude Code、Codex、Aider 均为单 agent 主循环）一致。Mars 是单人项目，没有理由重走 1.x 的弯路。

2. **固定 graph 的价值随节点 LLM 化递减。** 1.x 里真正"确定性"的部分只有"扫 plan 找未完成 step"；每个节点内部仍是一个 LLM + 工具的 ReAct 循环。为这点确定性付出的成本是：状态 schema 要覆盖所有角色的字段、节点间 `preserve_state_meta_fields` 手工防丢字段（`nodes.py:100-122` [1.x]——这是 LangGraph 状态覆盖语义的坑）、数百行 JSON 修复代码。Mars 的单循环 agent 里，"计划"只是上下文里的一份 todo，不存在跨节点 schema 交接，这些成本整个消失。

3. **直接可抄：上下文工程四件套。** 见第 7 节精华第二条。对 Mars 最具体的三件事：(a) 工具输出**在源头截断**（crawl_tool 截 1000 字符的先例）；(b) 每次模型调用前跑 token 预算 hook，超限先压缩工具结果、再丢中间老消息、保住前缀任务说明——`ContextManager` 的算法（`context_manager.py:189-270` [1.x]）不到 100 行，可直接改写；(c) 关键信息放最靠近生成点的位置。

4. **直接可抄：递归/步数上限 + 优雅降级收尾。** `AGENT_RECURSION_LIMIT`（默认 25）+ `recursion_fallback` 模式（撞限后摘掉工具让模型用已有材料总结，而不是报错退出，`nodes.py:1007-1077` [1.x]）。coding agent 的 agentic loop 必须有同一道保险，且"降级时输出已完成部分"比"硬失败"对 benchmark 得分也更友好。

5. **直接可抄：HITL 的两级设计 + 澄清收口。** 计划确认用 interrupt + 显式接受/编辑协议，但提供 auto-accept 开关（Mars 跑 benchmark 时必须能全自动）；危险工具（bash/写文件）用工具级拦截器逐个确认（`tool_interceptor.py` [1.x] 的实现模式可直接参考）。澄清类交互必须有 max rounds 强制收口，防止 agent 无限提问（`coordinator.md` 的"Max 3 rounds then MUST handoff"）。

6. **可借鉴：模型分级与 prompt 模板化。** `AGENT_LLM_MAP` 按角色选模型档位的思路，在 Mars 里可退化为"主循环用强模型、标题生成/压缩/摘要等杂活用小模型"。Prompt 用 Jinja 文件模板而非代码里拼字符串（`template.py` [1.x]），但**不要抄本地化多语言变体**——那是 to-C 研究产品的需求。

7. **应避免：把"计划"做成严格跨组件 schema + 为 LLM 输出写大量修复代码。** 1.x 的 `repair_json_output` / `extract_plan_content` / `validate_and_fix_plan` 几百行兜底代码（`nodes.py:125-200, 398-455` [1.x]）是"用 LLM 产出机器可解析协议"的固有税。Mars v0.1 的计划应该只是给人看和给模型自己看的 markdown todo，机器侧只跟踪 checkbox 状态；同时记下这个教训：**凡是依赖 LLM 输出严格 JSON 的环节，都要预算校验与修复代码**。

---

## 附：一手资料清单

**DeerFlow 1.x（main-1.x 分支，调研时的 main-1.x HEAD）**
- `README.md` — Architecture、Features、LangSmith tracing 章节
- `Agent.md` — 架构总览与开发命令
- `src/graph/builder.py` — StateGraph 拓扑、条件边、MemorySaver
- `src/graph/types.py` — State 定义
- `src/graph/nodes.py` — 全部节点实现、plan 修复/校验、recursion fallback、MCP 工具注入、上下文压缩挂载点
- `src/prompts/template.py`、`src/prompts/planner.md`、`coordinator.md`、`researcher.md`、`reporter.md`、`planner_model.py` — prompt 组织与 Plan schema
- `src/agents/agents.py`（create_agent + middleware）、`src/agents/tool_interceptor.py`（HITL 工具拦截）
- `src/utils/context_manager.py` — token 估算与压缩算法
- `src/tools/search.py`、`src/tools/crawl.py` — 工具工厂与源头截断
- `src/config/configuration.py`、`src/config/agents.py`、`conf.yaml.example` — 配置与模型分级
- `docs/DEBUGGING.md`、`docs/mcp_integrations.md` — 可观测性与 MCP
- `tests/integration/test_nodes.py`、`tests/` 目录结构 — 测试实践

**DeerFlow 2.0（main 分支，仅作架构演变证据）**
- `README.md` — "DeerFlow 2.0 is a ground-up rewrite... shares no code with v1"
- `AGENTS.md`、`docs/ARCHITECTURE.md` — harness/app 分层、lead agent + middleware 链、subagent/skills/sandbox 架构

注：受网络限制，本次通过 gh-proxy.com 镜像拉取 main / main-1.x 分支 tarball，未逐文件核对 commit hash；以上路径与内容以调研当日分支快照为准。
