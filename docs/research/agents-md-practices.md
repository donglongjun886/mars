# AGENTS.md / CLAUDE.md 写法调研：业界标准与最佳实践

> 调研目的：为 Mars 仓库撰写 AGENTS.md 提供写法参考。本文只做"怎么写"的调研，不替 Mars 起草具体内容。
> 调研日期：2026-10-27。文中每条结论标注来源，并区分**官方标准/官方建议**与**社区观点**。

---

## 1. agents.md 开放标准定义的内容骨架

来源：[https://agents.md/](https://agents.md/)（官方标准站点，现由 Linux 基金会下的 Agentic AI Foundation 托管）

### 1.1 定位

- **"README for agents"**：AGENTS.md 是给 coding agent 读的 README，是一个"专门的、可预测的位置"，放置 agent 工作所需的上下文和指令。
- 与 README.md 的关系是**互补而非替代**：README 面向人类（快速上手、项目介绍、贡献指南）；AGENTS.md 放那些会弄乱 README、或对人类贡献者不相关的细节（构建步骤、测试、约定）。
- 刻意做成**跨厂商开放格式**而非专有文件：由 OpenAI Codex、Amp、Google Jules、Cursor、Factory 等共同推动，被 6 万+ 开源项目采用。

### 1.2 官方推荐的内容板块

agents.md 官网"Cover what matters"一节列出的常见板块（官方建议）：

- **Project overview**（项目概览）
- **Build and test commands**（构建与测试命令）
- **Code style guidelines**（代码风格）
- **Testing instructions**（测试指引）
- **Security considerations**（安全注意事项）
- 额外的：commit message / PR 规范、安全陷阱、大数据集说明、部署步骤——"任何你会告诉新同事的东西都属于这里"。

### 1.3 格式与机制层面的规则（官方标准）

- **纯 Markdown，无必填字段**："AGENTS.md is just standard Markdown. Use any headings you like"，没有规定的 schema。
- **嵌套覆盖**：monorepo 中在子包放嵌套 AGENTS.md；agent 读取离被编辑文件**最近**的那份，就近优先（"the closest one takes precedence"）。举例：OpenAI 主仓库有 88 个 AGENTS.md 文件。
- **冲突裁决**：离文件最近的 AGENTS.md 胜出；用户在对话中的显式指令凌驾一切。
- **可执行性**：列出测试命令，agent 会在结束任务前主动执行并修复失败（即 AGENTS.md 里的命令会被当作验证闭环）。
- **迁移建议**：旧文件改名 + 软链兼容（`mv AGENT.md AGENTS.md && ln -s AGENTS.md AGENT.md`）。
- **当作活文档维护**："Treat AGENTS.md as living documentation."

---

## 2. Anthropic 官方对 CLAUDE.md 的指导

来源 A：[Claude Code memory 官方文档](https://docs.claude.com/en/docs/claude-code/memory)
来源 B：[Claude Code Best Practices（Anthropic 官方工程博客）](https://www.anthropic.com/engineering/claude-code-best-practices)

### 2.1 记忆层级与机制（官方文档，来源 A）

- CLAUDE.md 分四级：企业策略级（系统目录）→ 项目级（`./CLAUDE.md` 或 `./.claude/CLAUDE.md`，入版本库共享）→ 用户级（`~/.claude/CLAUDE.md`）→ 本地项目级（`CLAUDE.local.md`，已废弃，改用 imports）。
- **所有记忆文件在启动时自动加载进上下文**——这是"每行都要付出代价"的根本原因。
- 支持 `@path/to/file` **import 语法**（递归最深 5 层），可把长文档拆出去按需引入。
- 查找方式：从 cwd 向上递归读取；子树中的 CLAUDE.md 只在 agent 读取该子树文件时才加载（天然的分层/渐进披露机制）。
- `/init` 可生成初始 CLAUDE.md；`#` 前缀快速追加；`/memory` 编辑。

### 2.2 内容取舍：官方 Include / Exclude 表（来源 B，最直接的一份反模式清单）

官方原文是一张两列表：

| ✅ 该写（Include） | ❌ 不该写（Exclude） |
|---|---|
| Claude 猜不到的 Bash 命令 | 任何 Claude 读代码就能推断的东西 |
| 与默认惯例不同的代码风格规则 | 标准语言惯例（Claude 本来就会） |
| 测试指引与首选测试运行器 | 详细 API 文档（改为放链接） |
| 仓库礼仪（分支命名、PR 约定） | 频繁变化的信息 |
| 项目特有的架构决策 | 长篇解释或教程 |
| 开发环境的坑（必需的环境变量等） | 逐文件描述代码库 |
| 不显而易见的常见坑/行为 | "写干净的代码"之类不言自明的废话 |

### 2.3 篇幅与维护原则（官方建议，来源 B）

- **保持短小、人类可读**："keep it short and human-readable"。
- **删减测试**：对每一行问一句 *"删掉这行会导致 Claude 犯错吗？"* 不会就删。
- **核心警告**："Bloated CLAUDE.md files cause Claude to ignore your actual instructions!"（臃肿的 CLAUDE.md 会导致模型无视你真正的指令）。失败模式一节再次点名 "The over-specified CLAUDE.md"：太长 → 重要规则淹没在噪音里 → Claude 无视一半内容。修法："Ruthlessly prune. If Claude already does something correctly without the instruction, delete it or convert it to a hook."
- **只放普适内容**：CLAUDE.md 每次会话都加载，"only include things that apply broadly"；领域知识、偶发工作流应放到 **skills**（按需加载）。
- **强调技巧**：某条规则老被无视，可单独给该行加 "IMPORTANT" 强调；但若很多行都强调，等于没有强调。
- **像对待代码一样对待 CLAUDE.md**：出问题时 review 它、定期修剪、通过观察 Claude 行为变化来"测试"改动；入 git 让团队共建，"The file compounds in value over time."
- `/doctor` 可让 Claude 对签入的 CLAUDE.md 提出可删减内容建议。

### 2.4 记忆文件自身写法（官方文档，来源 A）

- **具体**："Use 2-space indentation" 好过 "Format code properly"。
- **结构化**：每条记忆写成 bullet，相关条目归组到有描述性的 markdown 标题下。
- **定期 review**：随项目演进更新，保证信息不过时。

---

## 3. 其他厂商与社区共识

### 3.1 OpenAI Codex（官方文档）

来源：[Codex AGENTS.md 官方指南](https://developers.openai.com/codex/guides/agents-md)

- **指令链（instruction chain）分层**：全局 `~/.codex/AGENTS.md`（或 `AGENTS.override.md`）→ 项目根到 cwd 路径上每层目录的 AGENTS.md / AGENTS.override.md，**从根到当前目录拼接，越靠近当前目录的文件越靠后、优先级越高**。
- **体积上限**：合并后的指令默认上限 `project_doc_max_bytes = 32 KiB`，超出即截断——官方建议超限就"拆到嵌套目录"而不是写大文件。这是"短"的一个硬约束佐证。
- **fallback 文件名**：可通过 `project_doc_fallback_filenames` 配置把其他文件名（如 `TEAM.md`、`.agents.md`）当作指令文件。
- **Code Review 规则**：GitHub 上的 Codex code review 支持在 AGENTS.md 里加 `## Code Review Rules` 节；官方建议是规则要简洁、说明"要标记什么行为 + 安全路径/例外"，**格式和 lint 检查交给 CI，不写进规则**。
- 验证方法：跑 `codex "Summarize the current instructions."` 确认加载了哪些文件。

### 3.2 Google（Gemini CLI / Jules）

- **Jules**：是 agents.md 标准的共创方之一（来源：[agents.md About](https://agents.md/)），直接采用 AGENTS.md。
- **Gemini CLI**：默认上下文文件是 `GEMINI.md`，层级为全局 `~/.gemini/GEMINI.md` + 项目/子目录文件，**串接后作为系统提示的一部分**；支持 `@file` import 和 `/memory` 命令；通过在 `.gemini/settings.json` 配置 `"context": { "fileName": "AGENTS.md" }` 可让它读 AGENTS.md（来源：[agents.md FAQ](https://agents.md/)；层级加载行为见 [google-gemini/gemini-cli#16058](https://github.com/google-gemini/gemini-cli/issues/16058) 中引用的官方文档描述）。
- 推论（社区共识）：写一份根目录 `AGENTS.md` 作为主文件，其他厂商文件（CLAUDE.md / GEMINI.md）用软链或一行 import 指向它，是当前跨工具兼容的主流做法。

### 3.3 社区：真实高 star 项目的 AGENTS.md 结构

**[langchain-ai/langchain 的 AGENTS.md](https://github.com/langchain-ai/langchain/blob/master/AGENTS.md)**（直接读取了原文），结构：

1. 项目架构与 monorepo 结构图（含各包职责一句话）
2. 开发工具与命令（uv / make / ruff / mypy / pytest，明确"不要用 pip/poetry"这类否定指令）
3. 关键配置文件清单
4. PR/commit 规范（Conventional Commits 示例）、分支命名、PR 描述写法
5. 核心开发原则（公共 API 稳定性、类型注解、测试要求 checklist、安全红线如禁止 `eval()`）
6. 文档/docstring 标准
7. CI/CD 与发布流程细节、仓库特有的坑

**[vercel/next.js 的 AGENTS.md](https://github.com/vercel/next.js/blob/canary/AGENTS.md)**，结构：

1. 代码库结构（monorepo 概览 + 关键入口点）
2. 构建/测试/lint 命令（含"优先跑单个测试而非全量"之类的性能提示）
3. 大量"agent 专属操作指引"：watch 模式开发流程、throwaway worktree、测试输出存文件再分析（避免重复跑）、context-efficient 工作流（大文件先 grep 再读局部）
4. 测试编写规范（带正反例代码片段）
5. PR/Issue 权限与流程规则、安全红线（不打印 secret、SSH 失败就停下来问人）
6. 指向 skills 的索引（"条件性深度工作流放 skills，基线规则留本文件"——官方 Include/Exclude 思想的实践版）
7. 仓库特有的坑（stale native binary、快照测试的环境差异等）

两个文件的共同点（社区事实归纳）：**结构图 + 命令 + 规范 + 红线 + 坑**；大量"做这个、别做那个"的祈使句；针对 agent 特有的失败模式写预防性指令（而非泛泛风格指南）。注意：这两个文件都很长（数百行），属于大型成熟 monorepo 的写法，与下文"越短越好"的共识存在张力——它们用嵌套文件（如 next.js 的 `test/AGENTS.md`）和 skills 索引来缓解。

### 3.4 社区最佳实践文章（高质量来源）

来源：[HumanLayer: Writing a good CLAUDE.md](https://www.humanlayer.dev/blog/writing-a-good-claude-md)（社区观点，但论证扎实、被引用广泛，且明确说明同样适用于 AGENTS.md）

核心论点：

1. **LLM 是无状态的**，CLAUDE.md/AGENTS.md 是**唯一默认进入每一次会话**的文件，所以它是整个 harness 中杠杆最高的点——值得逐行手工打磨，**不要用 `/init` 自动生成**（auto-generate 会产出平庸内容）。
2. 文件应回答 **WHY / WHAT / HOW**：项目目的、技术栈与代码地图（monorepo 尤其重要）、如何验证改动（测试/类型检查/编译命令）。
3. **少即是多的实证依据**：前沿 thinking 模型大约能稳定遵守 150–200 条指令，小模型衰减快得多；Claude Code 系统提示本身已占约 50 条；指令越多，模型不是忽略"靠后"的指令，而是**均匀降低对所有指令的遵守度**。
4. 机制佐证：Claude Code 给 CLAUDE.md 内容包了 `<system-reminder>`，提示"可能不相关，除非高度相关否则无视"——**非普适内容越多，整个文件被无视的概率越大**。
5. **篇幅共识**：无官方数字，社区共识是 **< 300 行，越短越好**；HumanLayer 自己的根 CLAUDE.md 不到 60 行。
6. **渐进披露（Progressive Disclosure）**：把任务特定的指令拆到 `agent_docs/` 下自命名的 markdown 文件，主文件只放索引和"按需阅读"的指令；**用 `file:line` 指针代替复制代码片段**（复制会过时）。
7. **不要让 LLM 当 linter**：代码风格交给确定性工具（linter/formatter/hook/CI），LLM 是 in-context learner，会模仿现有代码风格，不需要你在文件里教。

---

## 4. 反模式清单（公认"不要写什么"）

按来源性质分组：

**官方（Anthropic，[best practices](https://www.anthropic.com/engineering/claude-code-best-practices)）：**

1. ❌ 任何读代码/配置文件就能推断出来的内容
2. ❌ 标准语言惯例（模型本来就会的）
3. ❌ 详细 API 文档（放链接即可）
4. ❌ 频繁变化的信息
5. ❌ 长篇解释、教程
6. ❌ 逐文件描述代码库
7. ❌ "写干净的代码"之类不言自明的废话
8. ❌ 整体臃肿——"Bloated CLAUDE.md files cause Claude to ignore your actual instructions!"

**官方（OpenAI Codex，[AGENTS.md 指南](https://developers.openai.com/codex/guides/agents-md)）：**

9. ❌ 把格式/lint 检查写进指令文件——交给 CI
10. ❌ 单文件超过 32 KiB（会被截断，应拆分嵌套）

**社区（[HumanLayer](https://www.humanlayer.dev/blog/writing-a-good-claude-md) 等）：**

11. ❌ 大段代码风格指南——用 linter/formatter/hook 等确定性工具替代
12. ❌ 复制代码片段进指令文件（会过时）——用 `file:line` 指针
13. ❌ 任务特定/偶发才用的指令堆在主文件里——拆到独立文档/skills，主文件只放索引（渐进披露）
14. ❌ 用 `/init` 之类工具自动生成后不加打磨
15. ❌ 不加选择地追加"行为补丁"式指令（这次 agent 犯错就加一条）——导致文件变成不普适规则的坟场，整体被无视
16. ❌ 到处加 "IMPORTANT" 强调——强调多了等于没强调（此条为 Anthropic 官方）

---

## 5. 综合推荐结构模板

以下模板综合了 agents.md 官方骨架（§1）、Anthropic 的 Include 表（§2）、以及 langchain/next.js 的实际结构（§3.3）。每节注明"该写什么"与"不写什么的自检问题"。**总篇幅目标：< 300 行，个人项目建议 < 60–100 行；每行通过"删掉它 agent 会犯错吗？"测试。**

```markdown
# AGENTS.md

## Project overview          ← 项目是什么、为什么存在（WHY）
# 写：一两句话的项目定位 + 技术栈。
# 不写：README 里已有的营销性介绍；能从 pyproject.toml/package.json 读到的依赖清单。

## Codebase map              ← 代码地图（WHAT），monorepo/多模块项目尤其重要
# 写：目录结构简图，每个部分一句话职责；关键入口点 file:line。
# 不写：逐文件描述；会随重构迅速过时的细节。

## Setup & commands          ← agent 猜不到的命令（HOW）
# 写：安装依赖、起 dev server、跑测试、lint、类型检查的**确切命令**，
#     含包管理器选择（如"用 uv，不要用 pip"）和"优先跑单个测试"之类的效率提示。
# 不写：标准惯例命令（agent 知道的）；命令本身的详细文档。

## Workflow & verification   ← 完成标准
# 写：改完代码后必须跑什么验证才算完成（agent 会把它当闭环执行）；
#     commit/PR 规范（标题格式、分支命名）。
# 不写：每次任务都不同的具体指令。

## Conventions & red lines   ← 与默认不同的约定 + 不可逾越的红线
# 写：项目特有的架构决策、安全红线（如禁止 eval、不打印 secret）、
#     公共 API 稳定性要求、"行为 + 原因/安全路径"形式的简短规则。
# 不写：模型默认就遵守的通用最佳实践；交给 linter 的格式规则。

## Gotchas                   ← 不显而易见的坑
# 写：环境坑（必需的环境变量）、已知陷阱、CI 与本地差异。
# 不写：能从错误信息中自愈的一次性问题。

## Pointers                  ← 渐进披露索引（文件变长时启用）
# 写：任务特定文档/skills 的清单 + 一句话说明，指示 agent 按需阅读。
# 不写：把那些文档的内容复制进来。
```

**配套机制建议（来自官方标准，与写法无关但影响结构决策）：**

- 子目录/子包差异化规则 → 用**嵌套 AGENTS.md**（就近优先），不要把所有规则塞进根文件。
- 偶发的领域知识/长工作流 → 拆成独立文档或 skills，主文件只留索引。
- 格式与 lint → 交给确定性工具（linter、formatter、CI、hooks），不占指令预算。
- 维护节奏：当作活文档 + 当作代码——入版本库、定期修剪、出问题时 review 它。

---

## 附：引用来源清单

| # | 来源 | 性质 |
|---|---|---|
| 1 | [agents.md 官方站点](https://agents.md/) | 开放标准官方定义 |
| 2 | [Claude Code memory 文档](https://docs.claude.com/en/docs/claude-code/memory) | Anthropic 官方文档 |
| 3 | [Claude Code Best Practices](https://www.anthropic.com/engineering/claude-code-best-practices) | Anthropic 官方工程博客 |
| 4 | [OpenAI Codex: AGENTS.md 指南](https://developers.openai.com/codex/guides/agents-md) | OpenAI 官方文档 |
| 5 | [google-gemini/gemini-cli#16058（引用 Gemini CLI 官方文档对 GEMINI.md 层级的描述）](https://github.com/google-gemini/gemini-cli/issues/16058) | 官方文档转述（issue） |
| 6 | [langchain-ai/langchain AGENTS.md](https://github.com/langchain-ai/langchain/blob/master/AGENTS.md) | 社区实例（高 star 项目） |
| 7 | [vercel/next.js AGENTS.md](https://github.com/vercel/next.js/blob/canary/AGENTS.md) | 社区实例（高 star 项目） |
| 8 | [HumanLayer: Writing a good CLAUDE.md](https://www.humanlayer.dev/blog/writing-a-good-claude-md) | 社区观点（高质量） |
