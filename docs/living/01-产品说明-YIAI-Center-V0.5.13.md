# YIAI Center V0.5.13 产品说明（全局）

> 文档性质：全局 Living Product Doc  
> 当前产品版本：V0.5.13  
> 覆盖范围：V0.5.0—V0.5.13 的完整产品能力与演进结果  
> 更新日期：2026-07-22  
> 当前正式地址：http://192.168.50.112:19080  
> 当前 Active Release：V0.5.13-unlimited-codrive

## 1. 文档范围与维护规则

本文件说明 YIAI Center 整体是什么、为谁服务、解决什么问题、有哪些产品对象和全局规则。它不是 V0.5.13 单版本需求说明，也不是只描述工单与人机共驾的专题文档。

文档随产品持续累积：当前版本新增能力时，应在全局产品结构中补充其位置，同时保留此前已经实现并仍然有效的能力。版本完成情况、真实测试证据和代码实现细节分别由《版本规划》《测试用例与自测记录》《实际实现说明》承接。

文档不再强行使用 Y/N 标记。已经实现、当前限制、明确不做和未来规划均使用完整文字说明。

## 2. 产品定位

YIAI Center 是一个领域无关的 AI 能力装配、发布、运行解释和治理演示平台。它通过垂直 Agent 把自然语言 Skill、知识库 RAG、远程只读 MCP 和平台预置 Tool 装配成可发布版本，再以真实 Run、Trace、模型调用快照和成本记录解释一次 AI 服务究竟怎样完成。

平台当前面向三个角色：

- 普通用户：与 AI 客服对话、查看历史会话、工单、确认卡和每条回答的 Run 详情。
- 员工：查看工单与 Action，接受人工协同，在同一会话中连续回复，并把输出权交还 AI。
- 系统管理员或产品运营：配置 Agent 和能力资源，创建候选 Release、查看 Diff、人工发布或回滚，检查 Run、Trace、Badcase 线索与成本。

当前项目定位是个人面试演示系统。重点是证明产品闭环真实、能力可解释、版本可追溯、成本不造假，而不是建设企业级多租户、组织权限、计费结算和高可用运维体系。

## 3. 核心产品故事

### 3.1 一次回答可以被完整解释

用户发出消息后，平台创建唯一 Run，固定当时的 Active Release，经过 Router 选择一个垂直 Agent，再按该 Agent 在 Release 中的绑定使用 Skill、RAG、MCP 或预置 Tool。气泡下方可以打开 Run 详情，查看输入、Release、Agent、能力选择、外部调用、模型用量、成本、延迟、最终回答或失败原因。

### 3.2 能力变更通过 Release 发布

Agent 草稿和资源配置不会直接改变在线运行。管理员先创建 Candidate，查看 Agent、Skill、RAG、MCP、Tool 绑定 Diff，再人工发布。发布从下一条新消息开始生效；历史 Run 保留创建时的 Release 和能力快照。历史会话可以继续发送新消息，但新消息使用发送时的 Active Release。

### 3.3 失败和降级也保留证据

外部模型、远程 MCP 或网络失败时，平台不删除错误 Run，不伪造 Tool 结果、Token 或成本。若本地真实 Tool 已成功而主回答模型失败，可以基于真实结果确定性降级；Trace 同时记录成功事实和降级原因。

### 3.4 AI 与员工共享同一服务链路

AI 可以请求人工协同，员工接受后拥有当前输出权，可以连续回复任意轮。人工期间 AI 保持待命但不抢答。员工点击“交还 AI”后，仅把输出权切回 AI，不代表事项完结；AI 承接后仍可再次请求人工。系统没有共驾“完结”状态，AI 永远处于可再次承接的待命关系中。

## 4. 信息架构

### 4.1 用户端

用户端提供：

- 新建与继续历史会话。
- SSE 流式 AI 回答。
- AI 气泡下方的 Run 状态、垂直 Agent、Release 和详情入口。
- 当前用户的工单列表与详情。
- 写操作确认卡、重复确认幂等反馈和执行收据。
- 人工协同状态、员工消息和 AI 重新承接后的连续上下文。

### 4.2 员工端

员工端提供：

- 工单列表、详情和处理结果。
- 待确认或已执行 Action 的状态与审计信息。
- 人工协同请求与交接包。
- 接受协同、连续员工回复、并发版本冲突提示。
- 唯一明确的输出权操作“交还 AI”。

员工端当前不建设排队、抢单、绩效、班组、客服席位和“结束会话”流程。

### 4.3 平台管理端

平台管理采用卡片式管理。新增或导入入口位于页面右上角；每张卡片展示该对象的关键信息，并提供编辑、校验、测试、查看版本、发布、回滚、停用或删除草稿等对象级操作。

主要对象包括：

- 垂直 Agent。
- Release。
- Skill。
- RAG 知识库。
- MCP Server。
- Run 与 Trace。
- 模型调用和成本记录。
- Badcase 与评估能力的后续入口。

## 5. 核心产品对象

### 5.1 垂直 Agent

垂直 Agent 是能力装配的中心，也是唯一可编辑的绑定入口。每个 Agent 包含名称、业务说明、提示词和四类能力绑定：

- 自然语言 Skill。
- RAG 知识库。
- 远程只读 MCP Tool。
- 平台预置 Tool。

Skill、RAG、MCP 和 Tool 的独立管理页面只管理资源本身，并只读展示“哪些 Agent 正在使用”。资源页不反向勾选 Agent。

Agent 支持新增、编辑和删除草稿。新增 Agent 由服务端生成稳定 ID，可进入下一份 Candidate；Router 从当前 Release 的 Agent 清单动态选择，不依赖固定的三个 Agent 名称。删除草稿不会改写 Active Release 或历史 Run。

### 5.2 Release

Release 是线上运行的唯一配置快照。它包含 Agent 基础信息及其 Skill、RAG、MCP Tool、预置 Tool 绑定，并保存相关版本、白名单和必要运行配置。

Release 状态包括 Candidate、Active 和 Historical。Candidate 不影响线上；发布和回滚必须人工触发。每条 Run 在创建时固定 Release ID，此后不随 Active Release 改变。

### 5.3 Run、Trace 与模型调用快照

每条用户消息对应一个 Run。Run 保存会话、消息、Release、唯一 Agent、状态、起止时间、用量和成本汇总。

Trace 保存运行步骤。模型调用单独形成 CloudCallSnap，保存模型、请求类型、输入 Token、缓存输入 Token、输出 Token、单价快照、人民币 Estimated Cost、延迟和错误。Usage 缺失时成本为未知，不用 0 或估算数字冒充真实值。

### 5.4 Skill

Skill 是自然语言业务能力，可通过草稿、校验、不可变版本、Agent 绑定和 Release 发布进入运行。平台支持从公开 Git URL 安全导入纯文本 Skill；含凭据 URL 或包含可执行脚本的仓库会被拒绝，导入过程不执行仓库代码，也不会自动绑定或发布。

### 5.5 RAG

RAG 以领域无关 Markdown 文档为输入，执行确定性切片、关键词检索、局部向量检索和混合排序。Release 固定 RAGVersion；Run Trace 保存召回 Chunk、算法、分数、引用和正文 hash。没有有效召回时不伪造引用，模型返回的未知 Citation 会在输出前被移除。

### 5.6 MCP Server

MCP Server 是平台外部的独立服务。YIAI Center 不负责下载、安装或升级 MCP，只保存远程 Endpoint，通过通用 Streamable HTTP Client 完成连接测试、Tool List、只读校验、Tool 白名单、Agent 绑定、Release 发布、运行调用和 Trace 留痕。

V0.5.9 已接入：

- 命语紫微斗数排盘 MCP：只允许 ziwei_calculate；其他 55 个 Tool 均不进入白名单。
- MCP 官方文档远程 Server：只允许 search_model_context_protocol。

领域内容仅存在于 MCP、Agent、Release、Run 和当前演示数据中，不写入平台导航、通用数据结构或 Router 固定规则。解绑并发布后，新的 Run 不再获得该能力，历史 Run 仍保留原快照。

### 5.7 预置 Tool 与 Action

平台当前提供六个领域演示 Tool：

- 只读：list_work_orders、get_work_order。
- 写操作：create_work_order、update_work_order、close_work_order、delete_work_order。

这些 Tool 仍由垂直 Agent 装配并随 Release 发布。只读调用可以直接执行；写调用先生成 Action 草稿。创建、更新和关闭需要一次确认，软删除需要两次确认。确认固定草稿创建时的 Release，使用幂等键防止重复写入，并保存前后快照、追加式审计事件和执行收据。

## 6. 全局运行规则

### 6.1 单 Router、单 Agent

每个 Run 只允许选择一个垂直 Agent。模型 Router 返回数组、未知 Agent 或无效结果时，契约拒绝并进入确定性兜底；不会串行尝试多个 Agent，也不进行多 Agent 讨论。

### 6.2 Agent 能力边界

Runtime 只使用当前 Run 所固定 Release 中、目标 Agent 已绑定的能力。Agent 草稿不能直接影响运行；未发布、未绑定、未在白名单或 Schema 不匹配的 Tool 不能执行。

### 6.3 成本诚实

本地 Skill、RAG、预置 Tool 和不调用云模型的 MCP Step 的模型 API 成本为 0。MCP 或 RAG 结果注入模型上下文后产生的 Token 和人民币成本，记录在对应模型 CloudCallSnap 中。失败调用没有 Usage 时不虚构 Token。

### 6.4 历史可追溯

旧消息、旧 Run、旧 Release、旧能力快照、Action 审计和共驾事件不能因后续发布、回滚、解绑或软删除而被覆盖。失败证据也属于产品资产。

## 7. V0.5.0—V0.5.13 累计交付范围

| 版本 | 累计新增能力 | 当前状态 |
| --- | --- | --- |
| V0.5.0 | 五份 Living Docs 与产品边界 | 已完成 |
| V0.5.1 | 主机检查、DeepSeek 与 Usage Gate | 已完成 |
| V0.5.2 | 三端页面骨架、SQLite 与零依赖镜像 | 已完成 |
| V0.5.3 | Candidate、发布、回滚、Run 与 Trace | 已完成 |
| V0.5.4 | 真实 SSE、CloudCallSnap、Token 与成本 | 已完成 |
| V0.5.5 | 唯一 Router、单垂直 Agent、历史会话与 Run 抽屉 | 已完成 |
| V0.5.6 | 自然语言 Skill 草稿、校验、版本和发布 | 已完成 |
| V0.5.7 | 公开 Git Skill 安全导入 | 已完成 |
| V0.5.8 | Release 绑定的混合 RAG 与引用保护 | 已完成 |
| V0.5.9 | 远程只读 MCP、Tool 白名单、热拔插、Agent 中心装配和卡片化管理 | 已完成 |
| V0.5.10 | 工单只读 Tool | 已完成 |
| V0.5.11 | 创建工单 Action、确认与幂等 | 已完成 |
| V0.5.12 | 更新、关闭、双确认软删除与审计 | 已完成 |
| V0.5.13 | 无限轮人机共驾、AI 永远待命、无完结状态 | 已完成 |

## 8. 当前明确边界

当前版本不包含：

- 登录、组织、租户、角色权限和真实用户身份体系。
- 公网、域名、HTTPS、路由器端口转发和隧道。
- 高可用、监控告警、自动扩缩容和企业级灾备。
- 多 Agent 协作、讨论、投票或链式调度。
- 任意 MCP 写操作和 Fetch 对局域网的开放读取。
- GitHub MCP 的代码推送凭据复用。
- 员工排队、抢单、结案、绩效和会话完结状态。
- 浏览器自动化作为当前交付门槛；主观视觉由产品负责人手动体验。

Badcase、Darwin/Eval 和成本优化策略保留在后续路线图中，不能在未实现前描述为当前功能。

## 9. 当前正式状态

YIAI Center V0.5.13 已运行在 Ubuntu 小主机 http://192.168.50.112:19080。Active Release 为 V0.5.13-unlimited-codrive。迁移前后业务表数量一致，当前最终镜像自动测试 40/40 通过；源主机上的原容器、数据库和一致性备份保留，用于回滚。
