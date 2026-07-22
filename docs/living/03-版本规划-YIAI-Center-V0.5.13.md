# YIAI Center V0.5.13 版本规划（全局）

> 文档性质：全局 Living Roadmap  
> 当前产品版本：V0.5.13  
> 覆盖范围：V0.5.0 起的完整版本路线、实际状态和后续计划  
> 更新日期：2026-07-22  
> 当前 Active Release：V0.5.13-unlimited-codrive

## 1. 规划原则

YIAI Center 采用小步、连续、可演示的版本节奏。每个版本只增加一个能够独立解释的核心能力，但必须完整经过实现、测试、文档、候选 Release、人工发布和部署验证。

版本规划是全局累积文档，不只描述当前 V0.5.13。已经完成的版本保留真实交付结论和代表证据；未来版本明确标为计划，不能写成已经实现。

每次迭代共同遵守：

- 不清空或改写历史 Release、Run、Trace 和业务数据。
- 数据结构变化使用前向迁移，部署前形成一致性备份。
- 配置先进入 Agent 草稿和 Candidate，发布后从下一条新消息生效。
- 每个 Run 固定一个 Release，只选择一个垂直 Agent。
- 外部调用、Token、人民币成本和失败状态必须如实记录。
- 先保障可解释的真实闭环，再增加更复杂的治理能力。

## 2. 全局版本总览

| 版本 | 核心目标 | 实际状态 | 代表结果 |
| --- | --- | --- | --- |
| V0.5.0 | 建立产品、架构、路线图、测试、实现五份 Living Docs | 已完成 | 五类文档职责分离 |
| V0.5.1 | 主机与 DeepSeek Usage Gate | 已完成 | 非流式、流式 Usage 与模型策略验证 |
| V0.5.2 | 应用骨架、三个端和持久化 | 已完成 | 零依赖镜像、SQLite、健康检查 |
| V0.5.3 | Release、Run、Trace | 已完成 | Candidate、人工发布、回滚、历史固定 |
| V0.5.4 | 真实 SSE、模型调用与成本 | 已完成 | CloudCallSnap、Token、人民币成本与缺失 Usage 兜底 |
| V0.5.5 | 唯一 Router 与单 Agent | 已完成 | 三类意图、历史会话、Run 抽屉 |
| V0.5.6 | 自然语言 Skill | 已完成 | 草稿、校验、不可变版本、Agent 绑定、发布 |
| V0.5.7 | Git Skill 安全导入 | 已完成 | 纯文本允许、凭据 URL/脚本仓库拒绝 |
| V0.5.8 | Release 绑定的混合 RAG | 已完成 | BM25、LSA、RRF、引用保护和历史快照 |
| V0.5.9 | 远程只读 MCP 与 Agent 中心配置 | 已完成 | 命语/官方文档 MCP、热拔插、卡片 UI、动态 Agent |
| V0.5.10 | 只读工单 | 已完成 | list/get Tool、真实查询和降级回答 |
| V0.5.11 | 创建工单与确认 | 已完成 | Action 草稿、一次确认、幂等收据 |
| V0.5.12 | 更新、关闭、删除 | 已完成 | 前后快照、一次/两次确认、软删除审计 |
| V0.5.13 | 无限轮人机共驾 | 已完成 | AI/员工反复切换、无完结状态、AI 永远待命 |
| V0.5.14 | Badcase 治理 | 计划中 | 尚未实现 |
| V0.5.15 | Darwin/Eval 评估 | 计划中 | 尚未实现 |
| V0.5.16 | 成本优化策略 | 计划中 | 尚未实现 |
| V0.5.17 | 面试演示整合版 | 计划中 | 尚未实现 |

## 3. 已完成版本

### V0.5.0：全局文档基线

目标：先建立产品边界、架构权威、版本节奏、测试记忆和实际实现记录，避免代码先行后失去解释。

交付：

- 五份 Living Docs 职责分离。
- 定义领域无关、单 Router、单 Agent、Release 固定、Trace 可追溯等全局边界。
- 文档随后持续跟随真实实现更新。

### V0.5.1：主机与 DeepSeek Gate

目标：在建设页面前证明目标主机、模型网络、非流式 Usage 和流式最终 Usage 可用。

交付：

- 完成主机只读检查和部署隔离边界。
- 验证 DeepSeek 非流式三类 Usage 与流式最终 Usage。
- 确定主要模型使用 deepseek-v4-flash，并把 Usage 作为成本事实来源。

### V0.5.2：应用骨架与三个端

目标：形成可独立部署、可持久化、可浏览的最小应用。

交付：

- 用户、员工、平台管理三个端的页面骨架。
- Python 标准库 API、静态前端、SQLite 持久化。
- 零第三方运行依赖镜像、健康检查和容器重建后数据保留。

### V0.5.3：Release、Run 与 Trace

目标：让配置变化与每次运行具有版本边界。

交付：

- Candidate、Diff、人工发布和历史回滚。
- 每条消息创建 Run并固定当时 Active Release。
- 历史会话发布前后的消息分别保留原 Release。
- Trace 只允许一个 done 或 error 终态，失败 Run 不删除。

### V0.5.4：DeepSeek、SSE、Usage 与成本

目标：完成真实模型流式回答和调用级成本解释。

交付：

- SSE run_started、route_decision、agent_selected、delta、done/error 链路。
- 每次 Router 和主回答形成独立 CloudCallSnap。
- 记录输入、缓存输入、输出 Token、延迟、价格快照和人民币成本。
- Usage 缺失时 Run 成本为未知，不把部分成本冒充总成本。

### V0.5.5：唯一 Router 与单垂直 Agent

目标：完成一般咨询、投诉和工单意图的唯一 Agent 选择，并把 Run 详情放回对话体验。

交付：

- 单 Router、单 target_agent 契约。
- 模型错误或非法多 Agent 输出的确定性兜底。
- 历史对话读取不生成新 Run。
- AI 气泡下展示 Run、Agent、Release 和 Trace 抽屉。
- Trace 内展示对应 CloudCallSnap 与人民币汇总。

### V0.5.6：自然语言 Skill

目标：让可编辑业务指令以资源、版本和 Release 方式进入 Runtime。

交付：

- Skill 草稿、校验和不可变 SkillVersion。
- Agent 绑定和 Candidate Diff。
- Candidate 不影响在线，人工发布后从新 Run 生效。
- 代表 Run run_80e84830fb3b455b839869a6f9a962af 使用 V0.5.6-skill-demo，并记录 skill_considered → skill_activated。

### V0.5.7：Git Skill 安全导入

目标：从公开 Git 仓库导入自然语言 Skill，同时保持不执行、不泄密、不自动上线。

交付：

- 纯文本仓库允许导入为未绑定 Draft。
- 包含凭据的 URL 和包含脚本的仓库拒绝。
- 不执行仓库代码、不安装依赖、不自动绑定、不自动发布。
- 迁移版本升级到 3，12 项当时回归测试全部通过。

### V0.5.8：RAG 混合检索

目标：为 Agent 增加本地、可解释、随 Release 固定的知识检索。

交付：

- 确定性 Markdown 切片。
- SQLite FTS5 BM25、local-tfidf-lsa-v1 和 weighted-rrf。
- 无召回不伪造、未知 Citation 输出前移除。
- Release V0.5.8-rag-demo：rel_829f57da467c4cc59d4693cd3acbcfcf。
- 代表 Run run_1a2a5d2a4b5f4e81b8d776c939f3565 召回 4 个 Chunk、使用 2 个合法引用；旧 Run 保持 0 绑定。

### V0.5.9：远程只读 MCP、Agent 中心装配与卡片管理

目标：证明远程 MCP 可以独立部署、连接、白名单调用、Release 热切换，并纠正能力装配入口。

交付一：MCP 平台能力。

- 通用 Streamable HTTP Client、initialize、Tool List、Tool Call 和 MCPCallSnap。
- 命语 MCP 固定 commit 8e24d474d25d52d8b33533fe6e4dbc50aae6d9c8，stdio 经独立最小 Adapter 转为 HTTP。
- 命语 56 个 Tool 只允许 ziwei_calculate；官方文档 3 个 Tool 只允许 search_model_context_protocol。
- 命语 Run run_c6a864bd64d04ed3b6d124fd6623dc78 与官方文档 Run run_fccbf50fe28c4fbba496114ddf4102f9 完成同会话热切换；旧 Run 保留原 Endpoint、Tool、参数和 Release。

交付二：Agent 中心配置修复。

- agent_configs 成为 Skill、RAG、MCP Tool 和预置 Tool 绑定的唯一可编辑权威。
- 资源页删除 Agent 复选框，只读展示使用关系。
- Agent 支持真实新增、编辑、删除草稿和动态 Router。
- Agent、Release、Skill、RAG、MCP、Run 管理首页改为卡片式，右上角统一新增或导入。
- 第六号迁移无损转移旧绑定；历史 Release 和 Run 不重写。

### V0.5.10：只读工单

目标：让工单 Agent 通过 Release 绑定的预置 Tool 查询真实数据库事实。

交付：

- Tool：list_work_orders、get_work_order。
- Release：rel_92d43c98147844979b5c936a3eb03730。
- 代表 Run：run_7a9e0856d25b452e8bbe0202704beee6。
- Router 唯一选择 work-order-service，list_work_orders 返回 2 条真实工单，Tool 成本为 0。
- 主回答模型网络异常时，基于真实 Tool 结果降级并记录原因；失败模型调用不虚构 Token。

### V0.5.11：创建工单、确认与幂等

目标：把写操作从模型自由输出收敛到可确认 Action。

交付：

- Tool：create_work_order。
- Release：rel_98359d126d3f4202b3a0e35bd7c2bcef。
- 草稿 Run：run_eb63354876194ab599ed4b9ac4dce571。
- Action：action_68780600b79a4145ab862c6c8b477656。
- 确认 Run：run_bfb5e4f21ab64a239794db14f4bcf3b6。
- 确认前不写入；一次确认后创建 WO-20260721-003；重复确认只返回幂等重放。

### V0.5.12：更新、关闭与软删除

目标：复用 Action Gateway 覆盖更多写操作，并为不可逆风险增加双确认。

交付：

- Tool：update_work_order、close_work_order、delete_work_order。
- Release：rel_92335d5414a54eb3aeb561367b0027aa。
- 更新和关闭一次确认，保存 before 与 result。
- 删除两次确认，最终写 deleted_at，普通查询不可见。
- action_audit_events 保留从草稿到执行成功的追加式证据。

### V0.5.13：无限轮人机共驾

目标：让员工和 AI 在同一历史会话中反复切换输出权，取消一次性接管和完结概念。

交付：

- Release：rel_191f4cfd72b14a69ab6969e74c775c68。
- Active Release：V0.5.13-unlimited-codrive。
- 人工接受后员工可连续回复任意轮，没有轮次上限。
- HUMAN_ACTIVE 期间 AI 不抢答，但始终 standby。
- “交还 AI”仅恢复 AI 输出权，不结束事项；之后仍可再次请求人工。
- 状态机没有 CLOSED/FINISHED，模型失败也会恢复 AI_ACTIVE。
- 正式会话 conv_e4647f87c1d045c38c7c53dc14f9963a 完成两轮 AI↔人工循环。
- 最终镜像 40/40 自动测试通过，并迁移到 Ubuntu 192.168.50.112。

## 4. 后续规划

### V0.5.14：Badcase 治理

计划目标：把运行失败、Usage 缺失、低置信路由、空召回、能力拒绝和人工标记统一收集为可管理 Badcase。

计划范围：

- Badcase 来源、分类、严重度和关联 Run。
- 从 Run/Trace 一键创建或自动产生疑似 Badcase。
- 状态流转、备注和修复 Release 关联。
- 保留失败事实，不自动删除历史证据。

本能力尚未实现。

### V0.5.15：Darwin/Eval 评估

计划目标：用可解释的评估集比较 Candidate 与 Active Release，而不是仅凭主观发布。

计划范围：

- 评估用例、预期 Agent、能力调用和关键事实。
- Candidate 回放与 Active 对照。
- 规则指标和必要的模型评判快照。
- 评估结果进入 Release Diff，但仍由人工决定发布。

本能力尚未实现。

### V0.5.16：成本优化策略

计划目标：基于现有 CloudCallSnap 和 Run 成本，形成可解释的成本分布、异常和优化建议。

计划范围：

- 按模型、Agent、能力、Release 和时间聚合。
- 缓存命中、输入膨胀和失败调用分析。
- 预算或策略提示，不伪造节省金额。

本能力尚未实现。

### V0.5.17：面试演示整合版

计划目标：把“配置—发布—真实运行—Trace—失败治理—成本治理”整理成一条稳定演示故事。

计划范围：

- 统一演示数据和讲解顺序。
- 关键页面信息密度与交互复核。
- 最终回归、备份和交付说明。
- 不以企业级生产化替代面试演示价值。

本能力尚未实现。

## 5. 当前版本基线与继续开发规则

- 正式地址：http://192.168.50.112:19080。
- 当前 Active Release：V0.5.13-unlimited-codrive。
- 当前功能代码基线：a50e795，后续提交为文档修正时不改变运行镜像。
- 当前最终回归：40/40 通过。
- 源主机 192.168.50.232 的原容器、数据库和一致性备份保留。

继续开发 V0.5.14 时，应以本文件、全局产品说明、全局架构说明以及 V0.5.13 的累计测试和实现说明为输入；不得把产品范围重新缩成单版本专题，也不得绕开 Agent、Release、Run、Trace、Action Gateway 和 Codrive 的现有权威。
