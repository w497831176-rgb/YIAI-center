# YIAI Center V0.5.13 架构说明（全局）

> 文档性质：全局 Living Architecture Doc  
> 当前产品版本：V0.5.13  
> 覆盖范围：V0.5.0—V0.5.13 的整体架构、权威边界与实际部署  
> 更新日期：2026-07-22  
> 当前正式地址：http://192.168.50.112:19080

## 1. 文档范围

本文件说明 YIAI Center 整体如何组成、数据与控制权分别在哪里、一次 Run 怎样执行、各类能力怎样进入 Release，以及当前 Ubuntu 部署如何隔离。它不是 V0.5.13 工单或人机共驾的单版本设计。

架构说明随版本累积维护。新增模块必须放回全局控制面、运行面、数据面和部署面的关系中；历史上已经成立的 Release、Run、Trace、Skill、RAG、MCP 和成本规则不能因新版本文档被删除。

## 2. 总体架构选择

YIAI Center 当前采用模块化单体：一个 Python API 进程、一个浏览器静态前端、一份 SQLite 数据库和若干独立外部 MCP 服务。

选择原则：

- 一个配置权威：Agent 草稿是能力装配的唯一可编辑入口。
- 一个发布权威：Release 是线上运行配置的唯一快照。
- 一个运行权威：Runtime 创建 Run 并控制 Router、能力调用、回答和终态。
- 一个写操作权威：Action Gateway 统一处理确认、幂等、执行和审计。
- 一个输出权权威：Codrive 状态机决定 AI 或员工谁能在当前会话输出。
- 一个模型适配层：DeepSeek 调用、Usage 和价格快照统一记录。
- 外部服务隔离：MCP Server 独立部署，聊天主链路只连接 Endpoint。

系统没有第二套 Release、第二套成本计算或隐藏的多 Agent Runtime。

## 3. 逻辑分层

### 3.1 展示层

apps/web/static 提供无构建依赖的 HTML、CSS 和 JavaScript 页面，包含用户端、员工端和平台管理端。

前端负责：

- 发起 HTTP 与 SSE 请求。
- 渲染会话、卡片、确认、共驾和 Run 抽屉。
- 保存一次性 Action 确认令牌到浏览器 localStorage。
- 展示后端返回的 Release、Trace、用量、成本和错误事实。

前端不自行决定 Router、能力绑定、Action 是否可执行、共驾输出权或成本数值。

### 3.2 API 与编排层

apps/api/app/main.py 提供 HTTP/SSE 路由、参数校验和响应编排。它调用领域模块，不在路由中复制业务状态机。

主要领域模块：

- config.py：产品版本、模型与运行配置。
- db.py：SQLite 连接、迁移、Repository、Release/Run/Trace 数据权威。
- deepseek.py：DeepSeek 请求、流式解析、Usage 和 CloudCallSnap。
- runtime.py：一次 Run 的主执行流程。
- git_skill_import.py：Git Skill 静态安全导入。
- rag.py：切片、索引、检索、排序和引用保护。
- mcp_client.py：通用 Streamable HTTP MCP Client。
- mcp_runtime.py：Release 白名单、Schema 校验、参数提取和 MCP Snap。
- work_orders.py：工单事实、预置 Tool 和自然语言计划。
- action_gateway.py：写操作草稿、确认、幂等、执行与审计。
- codrive.py：输出权状态、员工消息、版本冲突和交还 AI。

### 3.3 数据层

SQLite 是当前唯一业务数据库。所有持久化表位于独立数据目录，容器重建不删除数据。数据库通过前向迁移从版本 1 演进到版本 9，不以删库重建替代升级。

### 3.4 外部依赖层

外部依赖包括：

- DeepSeek 模型 API。
- 命语紫微斗数排盘 MCP。
- MCP 官方文档远程 Server。
- 公开 Git 仓库，仅用于受限的 Skill 文本导入。

外部网络失败形成真实失败快照或确定性降级，不改变本地事实。

## 4. 配置控制面

### 4.1 Agent 草稿是装配权威

agent_configs 保存垂直 Agent 草稿：基础信息、提示词、Skill、RAG、MCP Tool 和预置 Tool 绑定。平台管理中的 Agent 页面是唯一可编辑装配入口。

资源页面职责：

- Skill 页面维护 Skill 和 SkillVersion，并只读显示使用 Agent。
- RAG 页面维护文档、版本和检索测试，并只读显示使用 Agent。
- MCP 页面维护 Server、连接测试、Tool List、Schema 和白名单，并只读显示 Tool 使用 Agent。
- 预置 Tool 来自服务端注册表，仅在 Agent 页面装配。

资源页不得保存反向 Agent 勾选。V0.5.9 第六号迁移把旧 Release 中的资源侧绑定无损转入 agent_configs，历史 Release 不重写。

### 4.2 Agent 动态扩展

新 Agent 由服务端生成稳定 ID。Router 候选来自 Run 固定 Release 的 Agent 清单，而不是写死三个 ID。删除只影响未发布草稿；Active Release 和历史 Run 保持不可变。

### 4.3 Candidate 构建

创建 Candidate 时，服务端读取 Agent 草稿及资源当前可发布版本，校验：

- 资源存在且状态允许发布。
- Skill 和 RAG 有不可变版本。
- MCP Server 连接成功，Tool 位于只读白名单且 Schema 已固定。
- 预置 Tool 已在服务端注册。
- 每个绑定能够映射到明确 Agent。

随后生成不可变 Release 配置 JSON 和 release_bindings，并计算与 Active Release 的 Agent、资源、版本、Tool 和能力绑定 Diff。

Candidate 不直接生效；只有人工发布或回滚更新 Workspace 的 active_release_id。

## 5. Release、Run 与 Trace 数据权威

### 5.1 Release

Release 保存：

- 版本名称、状态和时间。
- Agent 基础信息与业务说明。
- Agent 对 SkillVersion、RAGVersion、MCP Tool、预置 Tool 的绑定。
- MCP Git、服务版本、Endpoint、Transport、鉴权、Tool Schema、白名单、拒绝列表和运行配置。
- 与候选发布相关的完整配置快照。

原 Active 发布新版本后变为 Historical。回滚是把指定 Historical 再设为 Active，不修改任何历史 Run。

### 5.2 Run

每条用户消息创建 Run。创建时只读取一次 Active Release 并写入 run.release_id。后续发布不会改变该字段。

Run 至少关联：

- Conversation 与消息。
- 固定 Release。
- 唯一目标 Agent。
- 状态、起止时间、耗时、降级原因。
- CloudCallSnap、MCPCallSnap、Tool 结果和 Trace。
- Token 与人民币 Estimated Cost 汇总。

Action 确认会创建独立 Run，并固定 Action 草稿创建时的 Release；共驾“交还 AI”会创建新 Run并使用交还时的 Active Release。

### 5.3 Trace

Trace 是追加式步骤记录。典型链路为：

用户消息 → Release 固定 → 信息完整性或协同状态检查 → Router → 垂直 Agent → Skill/RAG/Tool 选择 → 外部或本地能力调用 → 客服回答生成 → 最终输出。

每个 Run 恰好一个 done 或 error 终态。人工承接期间的新用户消息可以形成无 AI delta 的 DONE Run，Trace 明确 human_active；这不是丢失回答。

### 5.4 CloudCallSnap

每次真实模型 API 调用单独保存快照：模型、调用目的、输入 Token、缓存命中输入 Token、输出 Token、价格版本、人民币成本、延迟、状态和错误。

Run 成本是其 CloudCallSnap 聚合。任一必要调用缺失 Usage 时，不展示不完整的“总成本”；失败调用不能补造 Token。

## 6. Runtime 主链路

### 6.1 普通 AI Run

1. 接收用户消息并保存消息事实。
2. 读取并固定 Active Release。
3. 创建 RUNNING Run，写入 run_started 和 release_pinned。
4. 检查是否处于 HUMAN_ACTIVE；若是，记录 human_active 后正常结束，不产生 AI 文本。
5. 进行领域无关的完整性或能力前置检查。
6. Router 从当前 Release 的 Agent 清单中选择一个 Agent。
7. 校验 target_agent 为单值且确实存在。
8. 只读取该 Agent 在固定 Release 中的能力绑定。
9. 执行 Skill、RAG、MCP 或预置 Tool。
10. 由 DeepSeek 生成回答，或在允许场景使用真实结果确定性降级。
11. 保存 CloudCallSnap、能力 Snap、最终消息、成本与唯一终态。

### 6.2 Router 失败兜底

Router 模型不可用或输出无效时，Runtime 根据当前 Release 中 Agent 的名称、业务说明和已绑定 Tool 描述进行确定性选择。它不按 Agent 列表顺序盲选，也不会尝试多个 Agent。

### 6.3 领域无关约束

特定行业词、MCP 名称和参数规则只能存在于 Agent、MCP、Tool、Release 和演示数据中。通用 Router、主链路、导航和数据结构不写死“紫微斗数”“命语”或其他行业判断。

## 7. Skill 架构

Skill 使用草稿和不可变 SkillVersion。校验通过不等于上线；只有 Agent 绑定进入 Candidate 并人工发布后，Runtime 才能使用。

Git 导入边界：

- 只接受公开 URL，不接受包含用户名、密码或 Token 的 URL。
- 下载后只检查允许的文本文件和体积限制。
- 含脚本或其他可执行内容的仓库拒绝导入。
- 导入过程不执行代码、不安装依赖、不自动绑定 Agent、不创建 Release。

## 8. RAG 架构

RAG 当前采用本地、可解释的混合检索：

- markdown-paragraph-v1 确定性切片。
- SQLite FTS5 BM25 关键词召回。
- local-tfidf-lsa-v1 局部向量表示和余弦召回。
- weighted-rrf 混合排序。

RAGVersion 固定文档版本与 Chunk。Trace 保存检索算法、Chunk ID、分数、正文 hash、实际注入长度和 Citation。RAG 本地步骤 model_api_cost=0；注入模型上下文的 Token 由主回答 CloudCallSnap 计费。

## 9. MCP 架构

### 9.1 部署边界

MCP Server 不进入 YIAI Center 应用容器。命语 MCP 位于独立目录、独立 Compose、独立容器和独立端口，固定上游 Git Commit。其 stdio 到 Streamable HTTP 的 Adapter 只做协议转换，复用上游 Tool，不复制算法。

外部官方文档 MCP 使用原生 Streamable HTTP Endpoint。

### 9.2 通用 Client

mcp_client.py 处理 initialize、notifications/initialized、tools/list、tools/call、JSON/SSE 解析、Session、超时、响应长度和错误归一化。新增、删除或更换 Endpoint 不需要修改聊天主链路。

### 9.3 三重约束

MCP Tool 执行前同时校验：

- Server 位于当前 Release。
- Tool 已绑定目标 Agent 并位于只读白名单。
- 参数满足固定 Tool Schema 的必填、类型、枚举和范围。

MCPCallSnap 保存 Server、Git、服务版本、Endpoint、Transport、Tool、参数、结果摘要与长度、起止时间、延迟、状态、错误、Release 和 model_api_cost=0。

## 10. 工单与 Action Gateway 架构

### 10.1 工单事实

work_orders 表保存工单编号、主题、描述、类别、优先级、状态、处理结果和 deleted_at。删除采用软删除；普通列表与详情默认排除 deleted_at 非空记录。

### 10.2 Tool 注册与 Release 边界

六个预置 Tool 由 work_orders.py 注册。Agent 装配后随 Release 发布。Runtime 不能调用未在固定 Release 中绑定到目标 Agent 的 Tool。

### 10.3 Action 状态机

写 Tool 不在自然语言阶段直接执行，而是产生 action_requests 草稿：

草稿 → 等待确认 → 已确认 → 执行中 → 成功 / 失败 / 结果未知。

普通写操作需要一次确认；软删除需要两次确认。Action 保存参数、执行前快照、确认步数、幂等键、结果和收据。action_audit_events 只追加，不覆盖旧事件。重复确认返回同一结果，不产生第二次写入。

确认令牌只将哈希持久化，原始令牌只返回浏览器保存。

## 11. 人机共驾架构

### 11.1 输出权状态

共驾只有四个输出权状态：

- AI_ACTIVE。
- HANDOFF_REQUESTED。
- HUMAN_ACTIVE。
- AI_RESUMING。

没有 CLOSED 或 FINISHED。ai_standby 对外始终为 true。

### 11.2 状态规则

- AI 可以在 AI_ACTIVE 请求人工。
- 员工接受后进入 HUMAN_ACTIVE，可连续回复任意轮。
- HUMAN_ACTIVE 期间用户新消息被保存，AI 不输出。
- 员工点击“交还 AI”进入 AI_RESUMING，AI读取员工消息和交接上下文。
- 无论模型成功或失败，交还流程都恢复到 AI_ACTIVE，避免卡死。
- AI_ACTIVE 仍允许再次请求人工，形成无限次循环。

### 11.3 并发与历史

codrive_sessions.version 用作乐观并发控制，旧 expected_version 返回 HTTP 409。codrive_events 追加状态变化，human_messages 保存员工回复并进入历史会话和后续模型上下文。

## 12. 数据库迁移与主要表

迁移 1—9 累计建立和扩展：

- Workspace、Conversation、Message、Release、Run、Trace、CloudCallSnap。
- Skill、SkillVersion 与 Release 绑定。
- Git Skill 导入所需字段和状态。
- RAG 文档、版本、Chunk 与检索元数据。
- MCP Server、MCPCallSnap 与 Tool 快照。
- agent_configs 与 Agent 中心装配。
- work_orders。
- action_requests、action_audit_events。
- codrive_sessions、codrive_events、human_messages。

迁移只向前执行。部署前使用 SQLite 在线备份形成一致性副本，并通过 integrity_check 校验。

## 13. 当前部署架构

### 13.1 Ubuntu 目标机

- 主机：192.168.50.112，Ubuntu Server 24.04 LTS。
- 代码目录：/home/wang/apps/yiai-center-v0513。
- 应用代码基线：a50e795；其后提交仅更新文档。
- Compose 项目：yiai-center-v0513。
- 应用容器：yiai-center-v0513-api-1。
- 独立网络：yiai-center-v0513_default。
- 数据库：/home/wang/apps/yiai-center-v0513/data/yiai-center.sqlite。
- 对外端口：19080。

### 13.2 代理适配

目标机原有 Mihomo 只监听主机回环。YIAI Center 使用项目内独立的 yiai-center-v0513-proxy-host 与 yiai-center-v0513-proxy-bridge，通过共享 Unix Socket 使用代理，不开放新的局域网代理端口，也不修改 Mihomo、DNS、TUN、UFW 或其他 Docker 项目。

### 13.3 源端回滚

源主机 192.168.50.232 的 yiai-center-api-1 在目标验证后停止，但容器、原数据库和一致性备份仍保留。没有删除源数据，也没有执行全局 Docker 清理。

## 14. 安全与隔离边界

- SSH 私钥不复制到项目、服务器或 Git。
- Git Token 和模型密钥不写入源码、文档、镜像或仓库。
- MCP 写 Tool 默认不允许；命语仅开放 ziwei_calculate，官方文档仅开放 search_model_context_protocol。
- Fetch MCP 当前不启用，避免未限制域名时访问局域网。
- GitHub MCP 在没有独立最小只读 Token 时不部署，不复用代码推送凭据。
- 不修改目标机固定 IP、Mihomo、DNS、TUN、UFW 和现有 Docker 资源。
- 不因测试删除历史 Run、失败证据、Release、Action 审计或源端回滚数据。

## 15. 当前架构限制与后续方向

当前 SQLite、固定演示用户、单进程 API 和无登录设计适合个人演示，不等同于生产多租户架构。后续 V0.5.14—V0.5.17 计划继续增加 Badcase、评估和成本治理，但应复用现有 Release、Run、Trace、CloudCallSnap 和 Agent 权威，不新建平行运行链路。
