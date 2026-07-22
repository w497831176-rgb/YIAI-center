# YIAI Center V0.5.13 实际实现说明（全局累计）

> 文档性质：Living Implementation Doc  
> 当前文档版本：V0.5.13  
> 累计覆盖：V0.5.0—V0.5.13 的真实实现与部署结果  
> 更新日期：2026-07-22  
> 当前正式地址：http://192.168.50.112:19080  
> 当前 Active Release：V0.5.13-unlimited-codrive  
> Active Release ID：rel_191f4cfd72b14a69ab6969e74c775c68  
> 当前功能代码基线：a50e795

## 1. 文档范围

本文件记录 YIAI Center 当前实际上怎样运行、从 V0.5.0 到 V0.5.13 怎样演进、关键代码和数据权威在哪里、哪些真实 Release/Run/Action 可以证明功能，以及当前明确没有实现什么。

它按当前版本 V0.5.13 命名，但不是只描述 V0.5.10—V0.5.13。此前的 Release、Run、Skill、RAG、MCP、Agent 配置和成本实现均属于当前系统，必须累计保留。

## 2. 当前交付结论

YIAI Center 已形成一条完整、可解释的演示链路：

1. 管理员在垂直 Agent 中装配 Skill、RAG、MCP Tool 和预置 Tool。
2. 配置先进入 Candidate，查看 Diff 后人工发布。
3. 用户消息创建 Run并固定当时 Active Release。
4. Router 从该 Release 中只选择一个垂直 Agent。
5. Runtime 只使用该 Agent 已发布的能力。
6. Skill、RAG、MCP、预置 Tool 和模型调用均留下 Trace 或专用快照。
7. 写操作通过 Action Gateway 确认、幂等执行并审计。
8. AI 与员工可以在同一会话反复切换输出权，员工不限回复轮次，AI 永远待命，没有共驾完结状态。
9. 历史 Run 保留原 Release、能力、参数、结果、用量和成本，不被后续发布改写。

当前服务已经从 Windows 台式机迁移到 Ubuntu 小主机。迁移前后业务表数量一致，最终镜像回归 40/40 通过，Active Release 未变化，源端数据库和一致性备份仍保留。

## 3. 实际技术形态

### 3.1 运行栈

- 后端：Python 标准库 HTTP 服务。
- 前端：静态 HTML、CSS、JavaScript。
- 数据库：SQLite。
- 流式协议：Server-Sent Events。
- 模型：DeepSeek，主要使用 deepseek-v4-flash。
- 部署：Docker Compose。
- 外部能力：远程 Streamable HTTP MCP。

项目最初考虑过更常见的前后端框架，但目标主机当时经代理访问 Docker Hub 和 PyPI 不稳定。最终选择零第三方运行依赖，保留了三个端、对话、Release、Run、Trace、SSE、Usage、成本和扩展能力，同时减少临时下载造成的部署风险。

### 3.2 代码模块

当前后端模块：

- config.py：产品版本、模型和环境配置。
- db.py：数据库、迁移、Release、Run、Trace、资源和会话数据。
- deepseek.py：DeepSeek 调用、流式解析、Usage 和 CloudCallSnap。
- runtime.py：一次 Run 的唯一主链路。
- main.py：HTTP/SSE API 编排。
- git_skill_import.py：Git Skill 静态导入安全检查。
- rag.py：切片、索引、检索、排序和 Citation 校验。
- mcp_client.py：通用 Streamable HTTP MCP Client。
- mcp_runtime.py：MCP 激活、白名单、Schema、参数与 MCPCallSnap。
- work_orders.py：工单表、六个预置 Tool 和真实执行器。
- action_gateway.py：Action 草稿、确认、幂等、执行和审计。
- codrive.py：AI/员工输出权、员工消息和并发版本。

当前测试文件：

- test_contracts.py。
- test_runtime_usage.py。
- test_skills.py。
- test_git_skill_import.py。
- test_rag.py。
- test_mcp.py。
- test_agent_config.py。
- test_work_orders_actions_codrive.py。

## 4. V0.5.0—V0.5.5 基础实现

### 4.1 V0.5.0 文档与边界

最初建立五份 Living Docs，并确定领域无关、单 Router、单 Agent、Release 固定、Trace 唯一终态、成本诚实和历史不删除等边界。这些规则后来落实到数据库契约和自动测试，不只是文档口号。

### 4.2 V0.5.1 主机与模型 Gate

在正式开发页面前先验证目标主机、Docker、DeepSeek 网络、非流式 Usage 和流式最终 Usage。4 条成功 Run 共形成 8 个 CloudCallSnap，确定模型策略和 Token 事实来源。

### 4.3 V0.5.2 应用骨架

应用实现用户、员工和平台管理三个端，无登录。后端以 Python 标准库提供 API，前端以静态文件交付，SQLite 持久化在容器外。健康检查、镜像构建和容器重建后数据保留均完成。

### 4.4 V0.5.3 Release、Run、Trace

db.py 建立 Workspace、Release、Conversation、Message、Run、Trace 等权威：

- Workspace 只保存一个 active_release_id。
- Candidate 从 Active 不可变配置复制，创建后不影响在线。
- 人工发布把原 Active 转 Historical，并更新 active_release_id。
- 人工回滚重新激活指定 Historical。
- Run 创建时固定 release_id，此后不变。
- Conversation 不永久绑定某一 Release，因此同一历史会话的新消息使用发送时的 Active Release。
- Trace 每个 Run 恰好一个 done 或 error。

### 4.5 V0.5.4 SSE、Usage 与成本

deepseek.py 和 runtime.py 实现：

- Router 与主回答的真实模型调用。
- SSE run_started、route_decision、agent_selected、delta、done/error。
- 每次模型调用形成独立 CloudCallSnap。
- 保存输入、缓存输入、输出 Token、价格快照、延迟和错误。
- Run 成本从 Snap 聚合；Usage 缺失时为未知，不补零。

代表 Run run_bf042f987a964d4eacb04bf677591020 完成真实 SSE；其早期 USD Estimated Cost 为 0.00015442。

### 4.6 V0.5.5 唯一 Router 与对话解释

Router 最初面向一般客服、投诉客服和工单处理三个 Agent。契约只接受一个 target_agent；数组、未知 ID 或多 Agent 输出被拒绝，Runtime 使用唯一确定性兜底。

前端增加历史会话、消息时间戳、AI 气泡下的 Run/Agent/Release 信息和 Run 抽屉。Trace 把 CloudCallSnap 嵌入对应步骤并显示人民币汇总。

代表证据：

- 一般咨询 run_bf042f987a964d4eacb04bf677591020。
- 投诉 run_361b93eb9d11479b87fef99e809c6fd6。
- 工单意图 run_25c70909fdb44cd2ab6534f3403e3554。
- 人民币调用快照 run_4e283b75bca3456cbd436bf2c5d93bf3。
- 保留失败 Run run_c8a77c0324a2460e9f45b7b46e048372。

## 5. V0.5.6 Skill 实现

第二号迁移增加 Skill 与 SkillVersion。Skill 采用：

- 可编辑 Draft。
- 独立校验状态。
- 校验后不可变版本。
- Agent 绑定。
- Candidate Diff 和 Release 快照。

保存或校验 Skill 不影响在线；只有进入 Candidate 并人工发布后，新 Run 才激活。代表 Release 为 V0.5.6-skill-demo，代表 Run run_80e84830fb3b455b839869a6f9a962af 的 Trace 包含 skill_considered 和 skill_activated。

部署前保存 yiai-center.sqlite.pre-v056-20260721，历史 Run 与 Conversation 没有减少。

## 6. V0.5.7 Git Skill 安全导入

git_skill_import.py 把 Git 导入限制为静态文本摄取：

- 仅接受公开 URL。
- 拒绝 URL 中的用户名、密码或 Token。
- 限制仓库、文件和文本体积。
- 只允许规定文本类型。
- 发现脚本、二进制或可执行内容时拒绝。
- 不执行仓库代码、不安装依赖。
- 导入结果只形成未绑定 Draft，不自动创建 Release 或发布。

第三号迁移增加导入所需字段。V0.5.7 当时 12/12 回归通过，Health 为 V0.5.7，Active Release 仍保持 V0.5.6-skill-demo。

## 7. V0.5.8 RAG 实现

第四号迁移增加 RAG 文档、版本、Chunk 和检索元数据。rag.py 实现：

- markdown-paragraph-v1 确定性切片。
- sqlite-fts5-bm25 关键词检索。
- local-tfidf-lsa-v1 局部向量检索。
- weighted-rrf 混合排序。
- 无召回保护和 Citation 白名单校验。

三个领域无关文档形成 5、5、6 个 Chunk。Release rel_829f57da467c4cc59d4693cd3acbcfcf / V0.5.8-rag-demo 增加 3 个 RAGVersion。

发布前 Run run_10cacdd225e644f78fe9e225879f9b00 保持 0 条证据；发布后 Run run_1a2a5d2a4b5f4e81b8d776c939f3565 召回 4 个 Chunk，使用 2 个合法 Citation，注入 1408 字符。RAG 本地步骤成本为 0，模型上下文成本记录在 CloudCallSnap 中，Run 总成本 0.002268 CNY。

## 8. V0.5.9 远程只读 MCP 实现

### 8.1 通用平台能力

第五号迁移新增 mcp_servers 和 mcp_call_snaps。mcp_client.py 实现 initialize、notifications/initialized、tools/list、tools/call、JSON/SSE、Session、超时、响应长度和错误归一化。

连接测试保存：

- 初始化结果、协议与 serverInfo。
- Tool List 成功与数量。
- Tool Schema、hash 和读写属性。
- 允许白名单和拒绝列表。
- 耗时、错误和时间戳。

Candidate 只收录 CONNECTED、符合白名单且已绑定 Agent 的 Tool，并复制 Git、服务版本、Endpoint、Transport、鉴权、Schema、白名单、拒绝列表和运行配置。Runtime 在调用前再次校验 Server、Agent、Tool 名称和 Schema。

MCPCallSnap 保存 Server、Git、版本、Endpoint、Tool、参数、结果摘要/长度、起止时间、延迟、状态、错误、Release 和 model_api_cost=0。

### 8.2 命语 MCP

- Git：https://github.com/Brhiza/mingyu。
- 固定 commit：8e24d474d25d52d8b33533fe6e4dbc50aae6d9c8。
- 上游版本：0.1.0；Adapter 版本：0.1.0+8e24d47。
- 原生 Transport：stdio。
- 适配：独立最小 Streamable HTTP Adapter，复用上游 Tool，不复制算法。
- 原部署目录：D:\Docker\yiai-mcp-mingyu。
- 原 Compose/容器：yiai-mcp-mingyu。
- Endpoint：http://192.168.50.232:19120/mcp。
- Tool List：56。
- 白名单：仅 ziwei_calculate。
- 拒绝：其余 55 个 Tool，包括 ziwei_prompt、八字、六爻、塔罗、择日、星盘和提示词 Tool。

指定验收 Run run_c6a864bd64d04ed3b6d124fd6623dc78 使用 Release rel_8e71df9301be4b7e936941ceda531bb4，仅调用 ziwei_calculate。7:35 通过 Release 声明式范围映射为 timeIndex=4，原始小时/分钟与最终参数均进入 Trace。历史结果长度 3,642,960，延迟 3,563 ms，MCP 成本 0。

### 8.3 MCP 官方文档 Server

- Source：https://github.com/modelcontextprotocol/servers。
- Endpoint：https://modelcontextprotocol.io/mcp。
- 原生 Streamable HTTP，无 Adapter。
- 平台固定记录：remote-service-2026-07-21；initialize 服务版本 1.0.0。
- Tool List：3。
- 白名单：search_model_context_protocol。
- 未开放：query_docs_filesystem_model_context_protocol、submit_feedback。

代表 Run run_fccbf50fe28c4fbba496114ddf4102f9 使用 Release rel_da9c4e8d8eb540ed89c6738bdc7b9252，调用官方文档 Tool。A→B 热切换没有修改聊天代码或重建应用容器；旧命语 Run 仍保留原 Endpoint、Commit、Tool、参数和结果。

### 8.4 未接入候选

- Time MCP 被后续指定的命语核心要求替代。
- GitHub MCP 因没有独立最小只读 Token 未部署，不复用代码推送 Token。
- Fetch MCP 未启用，避免缺少域名和内网限制时扩大读取范围。

## 9. V0.5.9 Agent 中心配置与卡片管理修复

第六号迁移新增 agent_configs。首次运行从 Active Release 读取旧绑定并转为 Agent 草稿，使用 INSERT OR IGNORE 避免覆盖后续编辑，历史 Release 不改写。

修复后的权威关系：

- Agent 草稿是 Skill、RAG、MCP Tool、预置 Tool 绑定的唯一可编辑入口。
- Skill/RAG/MCP 页面只管理资源并只读展示使用 Agent。
- Candidate 从 Agent 草稿构建，不读取资源页反向绑定。
- Release 保存 Agent 到能力的不可变快照。
- Runtime 只读取 Run 固定 Release，不读取 Agent 草稿。

Agent API 支持新增、编辑和删除草稿。新 Agent 由服务端生成稳定 ID，可进入 Candidate；Router 从当前 Release Agent 列表动态选择，不再只认三个固定 ID。

平台管理 UI 把 Agent、Release、Skill、RAG、MCP、Run 首页改为卡片式：右上角新增或导入，编辑、校验、测试、发布、回滚和查看 Trace 从卡片进入。

当时迁移前 8 个 Release、23 个 Run、351 个 Trace、2 个 Skill、3 个 RAG、2 个 MCP、6 个 MCPCallSnap；迁移后在新增测试证据前数量不变。30/30 自动测试通过。

## 10. V0.5.10—V0.5.12 工单与 Action Gateway 实现

### 10.1 数据与 Tool

work_orders.py 建立工单事实与六个预置 Tool：

- list_work_orders。
- get_work_order。
- create_work_order。
- update_work_order。
- close_work_order。
- delete_work_order。

Tool 通过 Agent 草稿装配并随 Release 发布。Runtime 只能使用 Run 固定 Release 中绑定到唯一目标 Agent 的 Tool。

### 10.2 V0.5.10 只读查询

- Release：rel_92d43c98147844979b5c936a3eb03730。
- Run：run_7a9e0856d25b452e8bbe0202704beee6。
- Agent：work-order-service。
- Tool：list_work_orders，scope=USER。
- 结果：2 条真实工单，延迟 13 ms，长度 689，Tool 模型成本 0。

该 Run 的 Router DeepSeek 成功，主回答出现 URLError。Runtime 使用真实 Tool 结果确定性降级，Run 仍为 DONE，并记录 degraded_reason 和 fallback。Router 成本 0.000475776 CNY；失败主调用没有虚构 Usage。

### 10.3 V0.5.11 创建与确认

- Release：rel_98359d126d3f4202b3a0e35bd7c2bcef。
- 草稿 Run：run_eb63354876194ab599ed4b9ac4dce571。
- Action：action_68780600b79a4145ab862c6c8b477656。
- 确认 Run：run_bfb5e4f21ab64a239794db14f4bcf3b6。
- 新工单：WO-20260721-003。

自然语言阶段只生成 AWAITING_CONFIRMATION 草稿，不写入工单。一次确认后通过 create_work_order 执行；收据保存 Action、Tool、时间和编号。重复确认返回 idempotent_replay=true，不创建第二条工单。

### 10.4 V0.5.12 更新、关闭与删除

- Release：rel_92335d5414a54eb3aeb561367b0027aa。
- 更新：action_437409132c60488eb4c2a9adb81cd03e / run_f66cb54e6b654d748874787e2c507c0d。
- 关闭：action_b4117f9c8f3a413fb1a672e9b11a1300 / run_5c4584e4af6d449295cc5964a66caff5。
- 删除：action_e2580af2bb554b7caef8404195a50f5b。
- 删除第一次确认：run_8e657f62ecc94257982b5034b733aed7。
- 删除第二次确认：run_4145c1810a0140249aefef4354cb667d。

更新和关闭需要一次确认；删除需要两次确认。删除使用 deleted_at 软删除，普通查询不再显示，但 Action 结果、执行前快照和 action_audit_events 仍保留。

### 10.5 Action Gateway

action_gateway.py 统一实现：

- Tool 是否在指定 Release 发布的校验。
- Action 参数和执行前快照。
- 确认令牌哈希。
- 普通一次确认与删除两次确认。
- 幂等键和重复确认重放。
- AWAITING_CONFIRMATION、CONFIRMED、EXECUTING、SUCCEEDED、FAILED、RESULT_UNKNOWN 状态。
- 追加式审计事件和执行收据。

Action 确认创建独立 Run，并固定草稿创建时的 Release，避免后续发布改变待执行动作的语义。

## 11. V0.5.13 无限轮人机共驾实现

### 11.1 状态机

codrive.py 只定义 AI_ACTIVE、HANDOFF_REQUESTED、HUMAN_ACTIVE、AI_RESUMING 四种输出权状态，不包含 CLOSED 或 FINISHED。

产品负责人最终规则已落实到服务端：

- 员工回复不限轮次。
- HUMAN_ACTIVE 期间 AI 不抢答。
- ai_standby 始终为 true。
- “交还 AI”只切换输出权，不代表事项完结。
- 交还后仍可再次请求人工。
- 模型成功或失败都必须从 AI_RESUMING 恢复 AI_ACTIVE。

### 11.2 数据

- codrive_sessions：每个会话保存当前输出权和 version。
- codrive_events：追加保存请求、接受、员工回复、交还和恢复事件。
- human_messages：保存员工消息，进入历史展示和 AI 续接上下文。

员工写入必须携带 expected_version；旧版本返回 HTTP 409，避免并发覆盖。

### 11.3 Runtime 与 API

HUMAN_ACTIVE 期间用户新消息仍创建 Run、保存消息和 Trace，但不产生 AI delta，以 human_active + done 正常结束。交还 AI 使用 SSE 创建新 Run，读取人工消息与交接上下文，并使用交还时的 Active Release。

### 11.4 正式证据

- Release：rel_191f4cfd72b14a69ab6969e74c775c68 / V0.5.13-unlimited-codrive。
- Conversation：conv_e4647f87c1d045c38c7c53dc14f9963a。
- 人工期间抑制 Run：run_76fd4048cc1e4c689b9d3425bd4d12cf。
- 第一次交还：run_7d72c0f4fb3a4855b96a7923dcc090e8，输入 1,461、输出 201、成本 0.001877904 CNY。
- 第二次交还：run_86063811b4fa43a8a7e5b05584988490，输入 1,542、输出 594、成本 0.003612672 CNY。
- 最终 version 12、AI_ACTIVE、ai_standby=true、can_request_human=true。

## 12. 数据库迁移与当前数据

数据库迁移累计到版本 9：

1. 基础 Workspace、会话、消息、Release、Run、Trace、CloudCallSnap。
2. Skill 与不可变版本。
3. Git Skill 导入字段与状态。
4. RAG 文档、版本、Chunk 和检索元数据。
5. MCP Server 与 MCPCallSnap。
6. agent_configs 与 Agent 中心装配。
7. work_orders 与预置 Tool 集成。
8. action_requests 与 action_audit_events。
9. codrive_sessions、codrive_events、human_messages。

迁移前后关键数据最终一致：

| 表或对象 | 数量 |
| --- | ---: |
| Release | 13 |
| Run | 35 |
| Trace Event | 481 |
| Release Binding | 67 |
| Agent Config | 3 |
| Skill | 2 |
| RAG Document | 3 |
| RAG Chunk | 16 |
| MCP Server | 2 |
| MCP Call Snap | 6 |
| Cloud Call Snap | 49 |
| Action Request | 4 |
| Action Audit Event | 21 |
| Codrive Session | 4 |
| Codrive Event | 12 |
| Human Message | 3 |
| Conversation | 21 |
| Message | 65 |
| Work Order | 4，普通列表可见 3 |

## 13. 当前前端实现

apps/web/static/app.js 和 styles.css 当前提供：

- 用户对话、历史会话、SSE 和 Run 抽屉。
- 用户工单卡片和写操作确认卡。
- 员工工单工作台、Action 卡片和人工交接包。
- 无限轮员工回复与“交还 AI”。
- 平台管理卡片式 Agent、Release、Skill、RAG、MCP、Run 页面。
- Agent 新增、编辑、删除草稿和四类能力装配。
- Release Candidate、Diff、发布与回滚。
- RAG 检索测试、MCP 连接/Tool 测试、Trace 与成本展示。

前端只消费后端事实，不自行构造 Release、Run、能力绑定、成本和共驾状态。

## 14. 当前 API 范围

当前 API 覆盖：

- 健康检查和基础配置。
- Conversation、Message 和聊天 SSE。
- Agent 草稿新增、编辑、删除和能力候选数据。
- Skill 草稿、校验、版本和 Git 导入。
- RAG 文档、预览、校验和检索测试。
- MCP Server、连接测试、Tool List 和 Tool 测试。
- Release 列表、Candidate、Diff、发布和回滚。
- Run 列表、详情、Trace、CloudCallSnap 和 MCPCallSnap。
- Work Order 列表和详情。
- Action 草稿、确认、详情和审计。
- Codrive 请求、接受、员工消息、交还 AI 和状态读取。

## 15. 部署与迁移实际状态

### 15.1 Ubuntu 正式环境

- 主机：192.168.50.112，Ubuntu Server 24.04 LTS。
- 地址：http://192.168.50.112:19080。
- 代码目录：/home/wang/apps/yiai-center-v0513。
- 功能代码固定：a50e795；其后提交只修正文档时不改变运行镜像。
- Compose 项目：yiai-center-v0513。
- 应用容器：yiai-center-v0513-api-1。
- Docker 网络：yiai-center-v0513_default。
- 数据库：/home/wang/apps/yiai-center-v0513/data/yiai-center.sqlite。
- 项目代理：yiai-center-v0513-proxy-host、yiai-center-v0513-proxy-bridge 和共享 Unix Socket。

项目代理适配没有开放新的局域网代理端口，没有修改 Mihomo、DNS、TUN、UFW 或其他 Docker 项目。

### 15.2 一致性备份

迁移前通过 SQLite 在线备份生成：

- 路径：D:\Docker\yiai-center\data\yiai-center-migration-20260722.sqlite。
- 大小：2,461,696 字节。
- integrity_check：ok。
- SHA-256：1d364115d403fa07d9b699eb6d21dd21e4ce2730b0b888b2f78b78449cf4d4e5。

### 15.3 迁移验证

- 首页 HTTP 200。
- 健康检查 status=ok、version=V0.5.13、database=ok、deepseek_configured=true。
- 目标镜像 40/40 测试通过，2.461 秒。
- Active Release 仍为 V0.5.13-unlimited-codrive。
- 全部关键表逐项对账一致。
- 两个 MCP 均 initialize、Tool List 和白名单 Tool 实际调用成功。
- DeepSeek /models 无业务内容鉴权请求 HTTP 200，返回 2 个模型。

### 15.4 源端回滚

目标验证完成后仅停止源端 yiai-center-api-1。源容器、原数据库、目录和一致性备份均保留，没有删除数据、Volume、网络或其他容器。

## 16. 测试结果

- V0.5.7：12/12。
- V0.5.8：16/16。
- V0.5.9 MCP：21/21。
- V0.5.9 Agent 配置修复：30/30，4.103 秒。
- V0.5.13 隔离源码：40/40，7.543 秒。
- V0.5.13 原正式镜像：40/40，7.374 秒。
- V0.5.13 Ubuntu 镜像：40/40，2.461 秒。

自动测试覆盖当前 Agent、Skill、Git 导入、RAG、MCP、Release、Runtime Usage、成本、工单、Action Gateway、无限轮共驾和静态 UI 契约。

## 17. 已知情况与明确未实现

- 当前是个人演示系统，工单范围使用固定演示用户，没有登录、权限、多租户和组织体系。
- 网络仍可能偶发 URLError；系统保留失败恢复和确定性降级，失败调用不伪造 Token。
- 员工工作台没有排队、抢单、绩效、结案和共驾完结状态。
- GitHub MCP 未因缺少独立最小只读 Token 而部署；不复用代码推送凭据。
- Fetch MCP 未启用。
- Badcase 管理页、Darwin/Eval 和成本优化策略仍在 V0.5.14—V0.5.16 规划中。
- 本轮没有浏览器自动化和产品负责人主观视觉验收；API、SSE、静态契约、真实业务闭环、镜像测试和迁移已完成。

## 18. 最终状态

YIAI Center V0.5.13 已在 http://192.168.50.112:19080 正式运行。当前实现不是单一工单演示，而是从 V0.5.0 文档与运行基线，连续演进到 Release、Trace、成本、Skill、RAG、MCP、Agent 装配、Action Gateway 和无限轮人机共驾的完整平台。

AI 与员工的关系是可反复切换的输出权协同：员工点击“交还 AI”后，AI 重新承接但事项不会自动完结；AI 始终 standby，并可在之后再次请求人工。历史 Release、Run、MCP 参数、Action 审计和共驾事件均被保留，Ubuntu 迁移没有减少数据，源端具备安全回滚能力。
