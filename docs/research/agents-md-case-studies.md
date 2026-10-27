# AGENTS.md 案例解剖：pi / deepseek-harness / deer-flow

> 2026-10-27。基于 /tmp/research/ 下三个项目的 AGENTS.md（及 CLAUDE.md）原文逐行阅读。
> 本文只做案例分析，主流写法调研见 [agents-md-practices.md](agents-md-practices.md)。

## 0. 一览

| | pi | deepseek-harness | deer-flow 2.0 | deer-flow 1.x（Agent.md，对照组） |
| --- | --- | --- | --- | --- |
| 篇幅 | 125 行 | 187 行 | 248 行（根）+ 前后端各有子文件 | 186 行 |
| 标题 | "Development Rules" | "AGENTS.md" | "AGENTS.md" | "Agent.md" |
| 性质 | **纯行为规则**，无项目介绍 | **宪法**：方向指引 + 仓库地图 + 命令 + 大量带理由链接的规则 | **路由枢纽**：根文件轻，深度内容在模块级文件 | 教科书式"架构概览"文档 |
| CLAUDE.md 关系 | 无 CLAUDE.md | symlink 指向 AGENTS.md | 薄壳：`@AGENTS.md` import | 无（当时只有 Agent.md） |

一个值得注意的演化证据：deer-flow 1.x 的 `Agent.md` 是典型"AI 生成味"文档（架构概览、目录树、命令罗列、"Common Development Tasks"），2.0 换成了 AGENTS.md 路由枢纽模式，并在根文件里明文写"Don't edit CLAUDE.md——它只是 import 壳"。**业界收敛方向：单一事实源 AGENTS.md + CLAUDE.md 薄壳。**

## 1. pi：纯行为规则，零项目介绍

结构（按节）：

1. **Conversational Style** —— 回复风格（短、无 emoji、先答问题再动手、表态先于改动）
2. **Code Quality** —— 代码规则（读全文件再改、禁 `any`、禁 inline import、生成文件不许手改）
3. **Commands** —— 命令纪律（改完代码必须 `npm run check`；**不许跑** build/test 除非用户要求；怎么跑单个测试；faux provider 测试套件；不主动 commit）
4. **Dependency and Install Security** —— 供应链安全（钉版本、ignore-scripts、lockfile 闸门）
5. **Git** —— 多 agent 并发场景的 git 安全（只提交自己改的文件、禁 `git add -A`、禁 `reset --hard` 清单、rebase 冲突处理）
6. **Issues and PRs** —— gh CLI 使用纪律（不 checkout PR 分支、评论用 body-file、AI 评论署名）
7. **Changelog / Releasing** —— 长流程不进正文，**指针指向 skill 文件**（`.pi/skills/release.md`）
8. **User Override** —— 收尾规则：用户指令与本文档冲突时，先确认再执行

特点：

- **没有一句"这个项目是什么"**——它假设读文件的 agent 是在干活，不是在了解项目；项目信息由 system prompt 的 project_context 机制另行注入。
- 规则全是"agent 容易踩的坑"，不是泛泛的代码风格（没有一句"写干净的代码"）。
- 多 agent 并发是头等约束：Git 一节开篇就声明"同一 cwd 可能有多个 pi 会话在跑"。
- 长流程全部指针化（release、interactive-testing 各是一行指针）。

## 2. deepseek-harness：带理由链接的"宪法"

结构（按节）：

1. **开篇一句定位 + 两个必读指针**（改 `packages/` 前先读 architecture.md；文档规范看 docs/AGENTS.md）
2. **Pre-stable APIs** —— 当前阶段最重要的兼容性政策
3. **Repository layout** —— 注释式目录树（60+ 包，每行一个短语）
4. **Commands** —— 注释式命令表 + "本地跑哪些检查"的纪律（不要默认跑全量、CI 拥有穷尽覆盖）
5. **Secrets / .env** —— 密钥纪律
6. **Conventions** —— 主体：约 30 条加粗规则，**每条一行规则 + 一个理由/出处链接**（`.agents/notes/` 决策档案或 docs）
7. **Defensive patterns** —— 指针
8. **Type safety and documentation** —— 散文标准（"注释写契约不写推理过程"、禁隐喻）
9. **Editing these instructions** —— **元规则：怎么编辑 AGENTS.md 本身**（每条规则自足、能压缩就压缩、超预算要提 verify-doc-budgets 上限）
10. **Vendoring policy**

特点：

- **每条规则都有"为什么"的链接**，规则本体保持一行——规则是索引，理由在决策档案里。
- **有专门的"如何维护本文件"一节**——把 AGENTS.md 当代码管（还有 `verify-doc-budgets` CI 门限制篇幅）。
- 大量规则是这个仓库特有的失败模式的解药（"registrations are effects"、"waterfall 必须 next()"），不是通用最佳实践。
- 和 pi 一样，收尾处强调"规则链接高层文档，保持每条自足"。

## 3. deer-flow 2.0：路由枢纽 + 分层

结构（根文件）：

1. **开篇：指针分流** —— backend 深度看 backend/AGENTS.md，frontend 看 frontend/AGENTS.md
2. **What is DeerFlow** —— 一段话说清项目是什么
3. **Service Topology** —— 四服务表 + 端口 + 关键坑（nginx 路由顺序有测试钉死）
4. **Repository Map** —— 注释式目录树
5. **Commands: Root vs. Module** —— 明确区分根级编排命令与模块级命令；含"跑单个测试"
6. **References** —— 指针清单（安装、贡献、安全、changelog、release）
7. **Cross-Cutting Conventions** —— 只有少数真正跨模块的规则（TDD 强制、push 前格式化、版本号多处同步、**"不要编辑 CLAUDE.md"**）

特点：

- **monorepo 分层模式**：根文件是枢纽，深度内容下沉到模块级 AGENTS.md；agent 在 backend/ 下干活时读到的是 backend/AGENTS.md。
- 根文件大量篇幅给了"环境与服务拓扑"——因为这是 agent 无法从单文件代码推断的信息。
- CLAUDE.md 只有 5 行：声明"agent 指导统一放 AGENTS.md，多 agent 共享"，然后 `@AGENTS.md` 导入。

## 4. 三家的共同结构骨架

剥掉规模差异后，三份文件共享的骨架是：

1. **开篇定位句 + 必读指针**（dsh、deer-flow 有；pi 刻意没有）
2. **仓库地图 / 目录树**（注释式，一行一个）——agent 无法快速自查的信息
3. **命令清单 + 运行纪律**（跑什么、**不许跑什么**、怎么跑单个测试）
4. **行为规则**（代码、git、提交、PR）——全部针对具体踩坑，无一条空泛风格要求
5. **长流程指针化**（release、交互测试 → skill/子文档）
6. **收尾的元规则**（用户冲突时先确认 / 如何编辑本文件）

共同的内容取舍原则（从实际内容归纳）：

- **只写 agent 不能从环境自查的东西**：约定背后的理由、多 agent 并发的坑、"不要跑全量测试"这类反直觉纪律。能从 pyproject/package.json 查到的命令反而做成注释式清单是为了省 agent 的探索轮次。
- **每条规则可执行、可检查**："禁 `git add -A`"是可检查的；"写高质量代码"不会出现在任何一份里。
- **否定式清单被允许且常见**（"Never run..."），但都配了正向替代（"改为跑 ./test.sh"）。
- **篇幅与项目规模成正比，但增长方式是分层而非膨胀**：dsh 用理由链接外置，deer-flow 用模块文件分层，pi 保持 125 行不变。

## 5. 对 Mars 的直接参照（待作者决策，此处仅列选项）

- Mars 是单包 Python 小项目，**pi 模式（单文件纯规则）天然适配**；dsh 的"理由链接 + 元规则"可以等规则超过一屏后再引入；deer-flow 的分层模式当前用不上。
- 三家都有而 Mars 一开始就该有的：**命令纪律（跑什么/不跑什么）、git 纪律（commit message 格式、不主动 commit）、长流程指针化的习惯**。
- 值得从第一天抄的元规则：pi 的 "User Override"（用户指令与本文档冲突时先确认）。
