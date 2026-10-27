# 调研横向对比

> 2026-10-27。基于四份调研笔记：[claude-code.md](claude-code.md)、[pi.md](pi.md)、[deepseek-harness.md](deepseek-harness.md)、[deer-flow.md](deer-flow.md)。
> 本文档只做事实对比与信号归纳，**不包含 Mars 的设计决策**——决策待作者读完调研后自行做出。

## 1. 四对象横向对比

| 维度 | Claude Code | pi | deepseek-harness | deer-flow |
| --- | --- | --- | --- | --- |
| 定位 | 终端优先的 agentic 产品 | 极简可扩展骨架 | 插件化 agent 平台（Web GUI 主形态） | 深度研究框架（非 coding） |
| 语言 | 闭源（TS 系） | TypeScript | TypeScript | Python（LangGraph） |
| 编排 | 单主循环 + subagent（仅用于隔离上下文） | 单事件循环，刻意无 subagent/plan mode | 单循环，一切插件化（60+ 包） | 1.x 固定多角色 graph；2.0 重写为单 lead agent + 动态 subagent |
| system prompt | 厚重，工程纪律写进 prompt | 极短，规则由各工具自带 guideline 拼装 | 极短 persona（一句话）+ 分段注册制 | 按角色 Jinja 模板，大量 MANDATORY 硬约束 |
| 上下文策略 | CLAUDE.md 分层懒加载 + 自动 compact + subagent 隔离 + 工具定义延迟加载 | 结构化 compaction：追加摘要 entry，原文永存 | KV-cache 感知 append-only 注入；压缩请求逐字节重放前缀 | token 预算 hook + 工具输出源头截断 + 结构化中间结果（observations） |
| 会话存储 | JSONL 会话文件 + checkpoint/rewind | JSONL 树（id/parentId），fork/resume/tree 从同一抽象长出 | append-only 日志派生上下文（"Model-visible ⟺ logged"） | 1.x 只有 MemorySaver（持久化没做完，2.0 补齐） |
| 工具输出处理 | 30000 字符截断 | 2000 行/50KB 双限截断，全文落盘附路径 | tail 截断 + spill 落盘返回 locator | 源头截断（crawl 截 1000 字符） |
| 错误回灌 | 工具失败信息即纠错信号（先读后写等由工具层强制） | 工具 throw → 框架转 isError toolResult | 异常归一化为 isError + 结构化错误码 + 指导下一步的文本 | JSON 修复/校验/兜底代码厚重 |
| 安全 | deny→ask→allow 规则引擎 + hooks 可编程安全层 | 无内置审批，推给容器；仅启动时 project trust 闸门 | 三档沙箱 + 一次性审批 + fail-closed | 两级 HITL（计划级 interrupt + 工具级拦截器） |
| 测试 | —（闭源） | 709 个测试 + env 完全隔离 + faux provider 不碰真实 API | 分层测试：逐文件 100% 行覆盖门 + real-API e2e + recorded-session 无 key 回放 | mock LLM 单测节点，重心在畸形 JSON 兜底路径 |
| 打断/交互 | Esc 中断 + 边跑边纠正 + rewind | steering（下一轮生效）/ follow-up（结束后执行）双队列 + Esc | steering 入 inbox 下一 step 认领；协作式取消 | 计划确认 interrupt；澄清循环有 max rounds 收口 |

## 2. 跨产品共识（四方独立得出相同结论的信号）

1. **工具输出必须截断 + 全文落盘返回路径。** 四家全部做了，只是阈值不同。
2. **会话 = append-only 日志，上下文从日志派生而非内存维护。** resume/fork/审计/回放全都从这个抽象免费获得（Claude Code、pi、dsh 三家一致；deer-flow 1.x 没做持久化，2.0 补齐）。
3. **固定多智能体/graph 编排被证伪。** deer-flow 2.0 亲手拆掉 1.x 固定流水线重写为 lead-agent harness；pi 刻意不做；Claude Code 的 subagent 只用于"隔离上下文、只回摘要"。
4. **工具错误要结构化回灌给模型，而不是裸异常或伪装成正常内容。** pi/dsh 都归一化为 isError；错误文本会指导模型下一步动作（如"仅只读操作可重试"）。
5. **system prompt 存在两种流派**：厚重派（Claude Code，工程纪律写进 prompt）vs 极简派（pi/dsh，一句话身份 + 规则由工具携带）。两派都成立，但极简派是较新的趋势。
6. **"prompt 约束不可信，程序化校验兜底"**：deer-flow 的"prompt 喊 MANDATORY + 代码 validate"双保险、Claude Code 的"安全执行在 harness 不在模型"、dsh 的 fail-closed，本质是同一条原则。

## 3. 主要分歧点（决策时需要自己选边的）

| 分歧 | 一派 | 另一派 |
| --- | --- | --- |
| system prompt 厚薄 | Claude Code：纪律写进 prompt | pi/dsh：prompt 极简，纪律进工具实现 |
| 安全模型 | Claude Code/dsh：权限引擎/沙箱内建 | pi：零审批，完全推给容器 |
| 架构复杂度 | dsh：一切插件化，缝全部留好 | pi：硬编码内核，功能推给事后扩展 |
| compaction 时机 | pi/dsh：自动触发 + 恢复路径 | Claude Code：自动 + 鼓励用户主动 /clear 重开 |

## 4. 开放问题（留给作者决策）

1. Mars v0.1 的架构基线更接近谁——pi 的极简内核，还是 Claude Code 的功能完整度？
2. 模型选型：接哪家 API？（影响 tool-calling 协议、context window、成本）
3. 安全策略选边：权限引擎（重）/ 危险命令确认（轻）/ 容器隔离（零内置）？
4. system prompt 厚薄选边？
5. 测试策略：faux provider 和 recorded-session 回放分别在什么阶段引入？
