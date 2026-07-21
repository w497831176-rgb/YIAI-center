# YIAI Center 架构说明

> 当前版本：V0.5.9
> 最近复核：2026-07-21，已启用第五号前向迁移、通用 Streamable HTTP Client、MCP 快照与 Release 热切换
> 文档视角：系统架构与后端工程
> 文档性质：Living Doc（动态工作记忆），不是不可变技术规范
> 用途：回答“技术上必须怎样实现、哪些权威只能有一个、哪些实现绝对禁止”
> 禁止写入：页面文案争论、面试包装和零散开发过程
> 配套文档：01 产品说明、03 版本规划、04 测试用例与自测记录、05 实际实现说明
> 部署目标：局域网尾号 232 的 Windows 10 Docker 主机。

## 0. 文档说明

- 本文直接陈述当前架构必须满足的约束。
- 当前不采用的方案使用“不引入”“不得”“仅”等自然语言明确说明，不代表未来永久禁止。
- 本文记录当前技术判断，可以根据目标主机、真实依赖、验证结果和产品变化动态调整。
- 本文件用于防止注意力漂移、重复造权威和局部补丁失控，不是为了强迫事实适配旧设计。
- 真实证据与当前架构冲突时，先停止扩散修改，说明证据和影响，更新五份文档后再继续。
- 允许重构、替换技术栈和改变边界，但不得静默进行。
- 本文件只描述全局架构、状态、契约、数据和部署边界。
- 具体开发顺序、当前完成度和下一步只写在版本规划。

## 1. 总体原则

- 使用模块化单体，先完成一个可运行闭环。
- Web、API、数据和 AI Adapter 的边界明确。
- 所有在线行为能够关联到 Run、Release 和 Trace。
- 所有配置变化经过不可变版本和人工发布。
- 所有业务写操作经过统一 Action Gateway。
- 所有云模型 API 调用经过统一 Model Adapter。
- 不创建第二套 Router、Runtime、Release 或写入权威。
- 不把所有逻辑继续堆进一个 mega-chat 文件或函数。
- 不为面试演示引入微服务、消息队列和分布式一致性。

## 2. 技术栈

- V0.5 前端使用原生 HTML、CSS 和 JavaScript，由同一个 Python 标准库 HTTP 服务同源提供静态文件。
- 当前页面复杂度不需要单独前端构建链；出现复杂可复用组件需求时再评估 React。
- 当前不引入 Node、Vite 和 Nginx 镜像，避免目标机 Docker Hub 代理问题增加演示复杂度。
- V0.5 后端使用 Python 3.12 标准库 HTTP Server、SQLite 和 urllib，保持零第三方运行依赖。
- 当前不引入 FastAPI、Pydantic 和 httpx；目标机外部 Python 包下载被代理中断，演示闭环不应被框架依赖阻塞。
- 对话和运行事件使用 SSE。
- 数据使用 SQLite WAL 和可重复执行的轻量前向迁移；V0.5.8 已按顺序执行到第四号迁移，不删除或重建历史数据。
- 当前演示版本不引入 Alembic；迁移由单一数据库模块按版本顺序执行，不删除或重建 SQLite。
- Embedding 默认本地运行。
- DeepSeek API 作为云模型 Provider。
- FastGPT 只能作为可替换 Engine Adapter 候选。
- 使用单一 Docker Compose project，project name 为 `yiai-center`。
- 不引入 Redis、Celery、Kafka、RabbitMQ 和 Kubernetes。
- 不直接读写 FastGPT 内部数据库。
- 不让 FastGPT 成为配置或 Trace 事实来源。

### 2.1 DeepSeek 模型策略

系统只允许两个显式 Model Profile：

```text
DEFAULT
provider: deepseek
model: deepseek-v4-flash
thinking.type: enabled
reasoning_effort: high

EXPERT
provider: deepseek
model: deepseek-v4-pro
thinking.type: enabled
reasoning_effort: high
```

- Router、主垂直 Agent 和普通运行阶段只能选择 `DEFAULT`。
- `EXPERT` 只能由服务端登记的高级专家工作流显式选择；首个允许场景是后续 Badcase AI Darwin。
- 每个 CloudCallSnap 保存实际 `model`、`phase` 和所选 profile。
- V0.5.0—V0.5.5 只调用 `deepseek-v4-flash`。
- 不允许模型根据自然语言自行决定升级到 `deepseek-v4-pro`。
- 不因低置信度、超时、失败或重试自动升级到 `EXPERT`。
- 隐藏思考内容不进入回答、Trace、数据库和日志。

## 3. 模块和唯一权威

### 3.1 Control Plane

- Agent、Skill、RAG、远程 MCP 连接、Tool 绑定和运行策略草稿只由 Control Plane 管理。
- Control Plane 负责校验并生成不可变 ComponentVersion。
- Control Plane 不直接切换在线 Release。

### 3.2 Release Manager

- Release Manager 是候选 Release、发布、Active Release 和回滚的唯一权威。
- 发布后 Release 内容不可原地修改。
- 回滚只切换 Active Release 指针。
- 其他模块不能直接更新 Active Release。

### 3.3 Runtime Kernel

- Runtime Kernel 是 Run、Router、单一垂直 Agent 选择、能力编排和终态的唯一权威。
- 每条新消息创建新 Run。
- 每个 Run 固定一个 release_id。
- 每个 Run 最多选择一个 vertical_agent_version_id。
- 一个 Run 不能重新路由并执行第二个 Agent。

### 3.4 Action Gateway

- Action Gateway 是预置业务写 Tool 的草稿、确认、幂等、执行和审计唯一入口。
- 创建、更新、关闭和删除使用同一套状态机和确认契约。
- Tool 实现不能绕过 Action Gateway 直接写业务数据。
- Prompt 不能代替服务端确认。

### 3.5 Observability

- Observability 是 TraceEvent、CloudCallSnap、Usage 和 Estimated Cost 的唯一事实来源。
- Run 汇总只能从原始 Snap 和事件计算。
- 前端不能自行估算并写回成本事实。

### 3.6 Quality

- Quality 是 BadcaseCandidate、Badcase、Darwin、EvalCase 和 EvalRun 的唯一权威。
- 自动规则只能创建 Candidate。
- 自动规则不能确认根因和关闭正式 Badcase。

### 3.7 Co-drive

- Co-drive 是 AI／人工输出权和人机状态的唯一权威。
- Runtime 和前端不能各自维护一套人机状态。

## 4. 推荐模块结构

```text
apps/
  web/
  api/

modules/
  control_plane/
  release_manager/
  runtime/
  skills/
  rag/
  remote_mcp/
  action_gateway/
  work_orders/
  co_drive/
  observability/
  quality/

adapters/
  engine/fastgpt/
  model/deepseek/
  embedding/
  mcp/streamable_http/

contracts/
tests/
deploy/
docs/
```

- 工单字段、SQL 和状态只能存在于 `work_orders` 与 Action Gateway。
- DeepSeek 请求和 Usage 解析只能存在于 Model Adapter。
- MCP 协议处理只能存在于 Remote MCP Adapter。
- Runtime 不直接执行 SQL、HTTP MCP 细节和 Provider 特有解析。

## 5. 三个 TAB 与无登录架构

- 前端只有 `/user`、`/employee`、`/platform` 三个顶层路由。
- 三个 TAB 共享同一个演示环境和 SQLite。
- V1 使用固定演示数据上下文。
- 不实现登录 API、Session、JWT、Cookie 登录态和密码表。
- 不实现角色授权中间件。
- 不把 TAB 当成安全边界。

V1 是本地面试演示。若未来对外开放，认证与权限必须作为新架构版本设计，不能在当前代码中零散补丁。

## 6. Release 与 Run 固定规则

- Workspace 同一时刻只有一个 `active_release_id`。
- 用户每发送一条新消息，后端读取一次当前 Active Release 并创建 Run。
- 新建会话的第一条消息使用当时 Active Release。
- 旧会话中继续发送的新消息也创建新 Run，并使用当时 Active Release。
- 历史消息保存各自的 source_run_id 和 source_release_id。
- 当前 Run 可以读取旧会话文本作为上下文，但能力、模型、Tool 和运行策略使用当前 Run 的 Release。
- Run 创建后 release_id 不允许改变。
- 已运行气泡、Trace 和 Usage 不重算。
- 发布和回滚只影响之后创建的 Run。
- 不按 conversation_id 永久固定 Release。
- 不在 Run 中途再次读取 Active Release。

## 7. Router 与单 Agent 契约

RouteDecision 必须结构化包含：

```text
target_agent_version_id
confidence
reason_code
need_clarification
suggest_co_drive
user_facing_reason
```

- `target_agent_version_id` 最多一个。
- Router 只能从当前 Release 的 Agent 白名单选择。
- Router 不直接调用 Skill、RAG、MCP 和业务 Tool。
- 低置信度执行确定性澄清、兜底或人机共驾规则。
- RouteDecision 进入 Trace。
- 不解析自由文本猜测多个 Agent。
- 不在一个 Run 中顺序执行多个 Agent。

## 8. Git Skill 安全导入

- 支持公开 HTTPS Git URL。
- 导入时解析仓库到临时隔离目录。
- 固定到具体 commit hash。
- 必须存在合法 `SKILL.md`。
- 只读取 Markdown、纯文本和安全元数据。
- 展示文件清单、安全扫描结果和拒绝原因。
- 导入成功后生成不可变 SkillVersion。
- 不执行仓库内任何文件。
- 发现 `scripts/` 或可执行扩展名时拒绝整个导入。
- 发现 shell、Python、Node、PowerShell、批处理或二进制文件时拒绝。
- 发现 SKILL.md 要求执行本地脚本或安装依赖时拒绝。
- 不运行 Git hook。
- 不自动跟随 branch 更新。
- 不把 Git 凭据、仓库内容和临时目录写入 Trace。

建议拒绝扩展名至少包括：

```text
.py .js .ts .mjs .cjs .sh .bash .ps1 .bat .cmd
.exe .dll .so .dylib .jar .class .wasm
```

扫描规则只用于拒绝，不用于尝试理解或安全执行代码。

## 9. 文本 RAG

- 数据源只接受页面粘贴的 UTF-8 纯文本或 Markdown。
- 切分模式使用 Markdown 标题、段落和规则项的确定性切分。
- 每个 RagVersion 固定原文 hash、切分器版本、Chunk 和索引版本。
- 关键词检索使用 SQLite FTS5／BM25。
- 向量检索使用目标容器内真实本地向量模型，不以关键词分数、哈希或随机数冒充向量。
- V0.5.8 Gate 0 最终选择 `local-tfidf-lsa-v1`：用语料 TF-IDF 矩阵的截断潜语义空间生成查询和文档向量；目标机不需要下载模型，实际余弦排序已通过测试。该名称和能力如实展示，不冒充 BGE 或神经网络 Embedding。
- 混合检索使用固定 `weighted-rrf`（k=60，关键词／向量各 0.5）融合算法和版本。
- UI 返回实际 chunker、keyword engine、embedding model 和 fusion mode。
- 检索结果记录 document_version_id、chunk_id、score、引用文本和算法版本。
- 上线初始化 3 篇领域无关长文档。
- 文本修改后不原地覆盖已发布 RagVersion。
- 不支持文件解析、OCR、网页抓取和批量同步。
- 无检索证据时不生成 Citation。

三篇初始化文档在版本规划中单独验收，不与 RAG 引擎代码混成一个任务。

## 10. 远程只读 MCP

- V1 只支持已部署 MCP Server 的 HTTP／HTTPS Endpoint。
- 优先支持 MCP Streamable HTTP。
- 实现 initialize、tools/list 和 tools/call。
- Endpoint 必须由平台管理手工配置并进入 allowlist。
- tools/list 结果经人工选择后生成不可变 McpToolVersion。
- McpToolVersion 固定名称、描述、inputSchema、outputSchema 和 schema hash。
- 当前 Release 只暴露白名单中的 McpToolVersion。
- tools/list 变化只标记“有更新”，必须重新校验和发布。
- MCP 输入、输出、耗时和错误进入 Trace Snap。
- 不支持 Git MCP 导入。
- 不支持 stdio、本地子进程、源码构建和容器启动。
- 不支持动态写 Tool。
- 不把 DeepSeek Key、业务数据库和无关密钥传给 MCP。
- MCP 返回内容不能当作系统指令执行。

## 11. 预置工单读写 MCP／Tool

预置 Tool：

```text
list_work_orders
get_work_order
create_work_order
update_work_order
close_work_order
delete_work_order
```

- list 和 get 是只读。
- create、update、close、delete 都走 Action Gateway。
- delete 使用软删除，保留审计和回放证据。
- Tool 与 Agent 的绑定随 Release 固定。
- Tool 代码变化必须重新构建应用。
- 预置写 Tool 不作为远程动态 MCP 接入。
- 不提供通用 SQL Tool。

统一写状态：

```text
DRAFT
→ AWAITING_CONFIRMATION
→ CONFIRMED
→ EXECUTING
→ SUCCEEDED / FAILED / INDETERMINATE
```

每个写草稿必须包含：

```text
draft_id
run_id
conversation_id
tool_name
target_id
before_snapshot
proposed_changes
confirmation_token_hash
idempotency_key
expires_at
status
```

- 确认时校验草稿状态、内容 hash、有效期和一次性 token。
- idempotency key 在数据库唯一。
- 成功、失败和结果不确定都有审计回执。
- INDETERMINATE 先按 idempotency key 对账。
- 结果未知时不盲目重试。
- 前端确认按钮不能直接操作数据库。

## 12. 人机共驾状态

```text
AI_ACTIVE
→ HANDOFF_REQUESTED
→ HUMAN_ACTIVE
→ AI_RESUMING
→ AI_ACTIVE

HUMAN_ACTIVE → CLOSED
AI_ACTIVE → CLOSED
```

- 同一会话同一时刻只有一个输出权持有者。
- HUMAN_ACTIVE 时拒绝新的 AI 生成。
- 人工消息和处置摘要作为下一条 AI Run 的上下文。
- AI_RESUMING 创建新 Run，并使用当时 Active Release。
- 所有状态转换使用事务和版本号。
- 不继续修改已经 done／error 的旧 Run。
- 不建设坐席队列和分配引擎。

## 13. Trace 与逐次云 API Snap

### 13.1 Trace 原则

- TraceEvent 只追加，不原地修改。
- 每个 Run 必须且只能有一个 done 或 error 终态。
- 每个事件关联 run_id、release_id、sequence 和 timestamp。
- `user_message_received` 保存本 Run 的用户消息 ID、角色和完整输入内容。
- `assistant_response_completed` 保存本 Run 的回答消息 ID、垂直 Agent 和完整最终回答。
- Run 详情同时读取消息事实记录；历史 Run 没有上述新事件时，从既有消息记录回显输入和回答，但不得补写或伪造历史 TraceEvent。
- 每个外部调用都有 started 和 completed／failed Snap。
- 不保存隐藏思维链、API Key、Bearer Token、Cookie 和数据库连接。

### 13.2 CloudCallSnap

每一次云模型 API 调用必须独立保存：

```text
cloud_call_id
run_id
parent_trace_id
phase
provider
model
request_started_at
response_finished_at
latency_ms
status
prompt_cache_miss_tokens
prompt_cache_hit_tokens
completion_tokens
total_tokens
usage_status
price_snapshot
estimated_cost
provider_request_id
error_code
```

phase 至少包括：

```text
router
main_agent
darwin
evaluation
```

若一个 Run 有两次模型调用，必须生成两个 CloudCallSnap，不能只保存 Run 汇总。

- Run 查询读模型把 `cloud_call_id` 与 `cloud_call_completed` 事件关联，使 CloudCallSnap 在对应 Trace 步骤内展示。
- Run 汇总位于 Trace 路径之后，只从该 Run 的 Snap 聚合，不覆盖逐步事实。

### 13.3 DeepSeek Usage

- 流式调用设置 `stream_options.include_usage=true`。
- Adapter 必须解析 `prompt_cache_miss_tokens`。
- Adapter 必须解析 `prompt_cache_hit_tokens`。
- Adapter 必须解析 `completion_tokens`。
- `prompt_tokens` 必须等于命中与未命中之和，否则标记 Usage 异常。
- Run Usage 从各 CloudCallSnap 聚合。
- Adapter 契约测试必须覆盖流式最终 usage chunk。
- 不用字符数或本地估算替代 Provider 已承诺返回的三类 Token。
- 不把缺失字段记为 0。

异常兜底：

- Provider 已经生成可用答案但 Usage 缺失时，答案继续返回。
- 对应 CloudCallSnap 标记 `usage_status=INCOMPLETE`。
- 三个缺失字段保持 null。
- estimated_cost 保持 null。
- Trace 记录 `usage_incomplete`。
- 自动生成 BadcaseCandidate。
- 不因 Usage 缺失丢弃已经生成的答案。
- 不编造 Usage 和 Estimated Cost。

### 13.4 FastGPT 边界

- FastGPT Adapter 必须返回与直接 DeepSeek Adapter 相同的 CloudCallSnap 契约。
- Gate 0 验证 FastGPT 是否能够提供每次底层云调用的完整 Usage。
- 如果 FastGPT 只能提供聚合 Usage 或缺少三类 Token，不允许它成为该运行路径的云模型事实来源。
- 不修改 FastGPT 内部数据库补齐 Trace。

## 14. 其他外部调用 Snap

远程 MCP、Embedding 和其他外部 API 必须保存：

```text
external_call_id
run_id
phase
service_type
service_name
operation
started_at
finished_at
latency_ms
request_size
response_size
status
error_code
```

- 有 Provider 用量和单价时保存真实字段。
- 没有计费字段时明确保存 `cost_status=NOT_AVAILABLE`。
- 不虚构 MCP 和本地 Embedding 成本。

## 15. 成本计算和控制

- 每个 CloudCallSnap 保存当时单价快照。
- DeepSeek Estimated Cost 按缓存未命中输入、缓存命中输入和输出分别计算。
- 新 CloudCallSnap 的用户展示币种为 CNY；快照同时保留 DeepSeek 官方 USD 原价、固定演示汇率和换算后的人民币单价。
- V0.5.5 固定演示汇率为 `1 USD = 7.20 CNY`，用于面试演示对账，不宣称是实时外汇牌价。
- 旧 USD CloudCallSnap 保持原始事实不变；查询读模型使用同一固定演示汇率生成兼容的人民币展示字段，不回写旧 Snap。
- Run 成本等于 CloudCallSnap 成本之和。
- Release、Agent、模型和时间汇总从 Run 聚合。
- CostPolicyVersion 随 Release 固定。
- 单价变化不重算历史成本。

CostPolicyVersion 至少包含：

```text
max_history_messages
max_skill_context_chars
max_rag_chunks
max_rag_context_chars
max_mcp_calls_per_run
max_mcp_result_chars
max_builtin_tool_calls_per_run
max_model_calls_per_run
max_output_tokens
single_run_estimated_cost_warning
daily_estimated_cost_warning
```

- 硬限制由服务端执行。
- 触发限制产生 `cost_guardrail_triggered` TraceEvent。
- 上下文裁剪使用固定优先级并记录前后长度。
- 金额阈值只产生预警。
- 金额预警不自动停服、切模型、改配置和发布。

## 16. BadcaseCandidate

自动抓捕规则代码至少包括：

```text
RUN_ERROR
ROUTE_EMPTY
ROUTE_LOW_CONFIDENCE
ROUTE_CONTRACT_ERROR
CAPABILITY_FAILURE
WRITE_FAILED
WRITE_INDETERMINATE
FINAL_OUTPUT_EMPTY
FINAL_OUTPUT_CONTRACT_ERROR
AI_FAILURE_HANDOFF
USER_DOWNVOTE
USAGE_INCOMPLETE
COST_GUARDRAIL_DEGRADED
COST_OUTLIER
LATENCY_OUTLIER
TRACE_INCOMPLETE
```

- 同一 run_id 和 rule_code 唯一。
- Candidate 保存自动一级、二级分类建议和证据事件。
- Darwin 可以重新建议分类。
- 人工确认后创建正式 Badcase。
- `WRONG_AGENT`、事实错误和 Skill 漏触发等推断不能在没有证据时自动确认为根因。

正式分类代码与产品文档七个一级分类一一对应：

```text
RUNTIME_MODEL
ROUTER_AGENT
SKILL_RAG
MCP_TOOL_WORKORDER
ANSWER_QUALITY
CO_DRIVE
COST_PERFORMANCE
```

## 17. 核心数据

至少包含：

- workspaces。
- component_drafts。
- component_versions。
- releases。
- release_bindings。
- conversations。
- messages。
- runs。
- trace_events。
- cloud_call_snaps。
- external_call_snaps。
- usage_aggregates。
- cost_policy_versions。
- agents。
- skills。
- rag_documents。
- rag_chunks。
- mcp_servers。
- mcp_tool_versions。
- work_orders。
- work_order_events。
- action_drafts。
- action_executions。
- co_drive_sessions。
- co_drive_events。
- badcase_candidates。
- badcases。
- eval_cases。
- eval_runs。
- eval_results。

不可变：

- 已发布 Release。
- ComponentVersion。
- McpToolVersion Schema 快照。
- Run 的 release_id。
- Trace 原始事件。
- CloudCallSnap 原始 Usage。
- 已执行写操作审计。
- 历史单价快照。

会话与 Run 查询读模型：

- `GET /api/conversations` 从 Conversation 与 Message 事实生成历史列表，包含标题、创建时间、最近消息时间和消息数。
- `GET /api/conversations/{conversation_id}/messages` 返回消息时间、run_id、Run 状态、Release 和垂直 Agent 展示名。
- `GET /api/runs/{run_id}` 返回 Run、输入/输出消息、TraceEvent 和逐次 CloudCallSnap 的同一份只读详情。
- 前端气泡和平台管理复用同一个 Run 详情 API，不建立第二套 Trace 或成本逻辑。

## 18. SSE 运行事件

至少支持：

```text
run_started
release_pinned
route_decision
agent_selected
skill_considered
skill_activated
rag_requested
rag_evidence
mcp_requested
mcp_completed
mcp_failed
action_draft_created
action_confirmed
action_completed
action_failed
action_indeterminate
cloud_call_started
cloud_call_usage
cloud_call_completed
usage_incomplete
cost_guardrail_triggered
cost_warning
co_drive_requested
human_message
ai_resumed
badcase_candidate_created
done
error
```

- SSE 是展示流，不是唯一持久化事实。
- 关键事件先持久化或保证最终收敛后再声明完成。
- 客户端断开不能让 Run 永久停在 RUNNING。
- 前端不能根据缺失事件猜测成功。

## 19. Gate 0

正式功能开发前只验证：

- Windows 10 Docker 主机资源和网络。
- DeepSeek 流式回答。
- `include_usage` 和三类 Token 完整返回。
- DeepSeek Tool Calling。
- 本地 Embedding 候选模型资源占用。
- FTS5/BM25、向量和混合检索。
- 远程 MCP Streamable HTTP。
- Git Skill 安全扫描和拒绝脚本。
- FastGPT 能否满足逐次 CloudCallSnap 契约。
- SQLite WAL 和数据持久化。
- Gate 0 不开发完整 UI。
- 未得到证据前不下载大模型和批量依赖。

若 FastGPT 无法满足 Usage 与 Trace 契约，只允许：

1. 保留 Adapter 并直接调用 DeepSeek。
2. 缩小 FastGPT 使用范围。
3. 完全替换 FastGPT。

禁止多处打补丁伪造逐次用量。

## 20. 最小验证

- 每条新消息固定当前 Active Release。
- 旧会话新消息使用新 Release，旧气泡不变。
- 一个 Run 只有一个 Agent。
- Git Skill 有脚本时拒绝。
- RAG 页面展示实际技术信息。
- 远程 MCP 只读且 Schema 固定。
- create、update、close、delete 全部先确认。
- 相同 idempotency key 只执行一次。
- 每次云模型调用都有独立 CloudCallSnap。
- 三类 Token 完整。
- Usage 缺失时答案继续、字段为 null、Candidate 生成。
- 人工输出期间 AI 不并发。
- Candidate 需要人工确认。
- Trace 只有一个终态。
- 不用假数据通过测试。

真实后端验证优先使用少量直接 API／SSE 请求。UI 由用户手动体验，除非用户明确要求，不建设 Playwright、浏览器容器和大型端到端测试工程。

## 21. 演示部署最小边界

- SSH 提供后先只读检查主机、Docker、端口、网络、资源和已有容器。
- 新项目使用独立 Compose project、网络、端口和持久化目录。
- API Key 只通过主机环境变量或不入 Git 的 `.env` 注入。
- 目标机需要联网代理时，只在本项目 `.env` 中注入容器 HTTPS 出口，不修改系统代理和其他容器。
- 仅在可能改变 SQLite 结构或演示数据前做一次人工文件副本；这不是备份系统。
- 应用代码可以回退到上一个 Git 版本，配置可以人工激活历史 Release。
- 不修改 NAS 和旧半成品。
- 不运行 `docker system prune`。
- 不删除 Volume、数据库和持久化目录解决问题。
- 不把密码和 API Key 写入代码、文档、Trace 和 Git。
- 不建设 Vault、SSO、RBAC、WAF、限流平台和安全运营中心。
- 不建设 Prometheus、Grafana、ELK、链路监控平台和自动值班告警。
- 不建设高可用、容灾、自动扩缩容、蓝绿发布、灰度发布和复杂 CI/CD。
- 不让生产级安全运维机制成为演示开发的前置条件。

## 22. 开发任务控制

每次编码前必须输出：

```text
五份文档版本：
本次产品要求：
本次架构约束：
只完成的小功能：
允许修改的模块：
不得变化的行为：
真实验收证据：
停止条件：
```

- 一个任务只完成一个可验收切片。
- 同一故障两次尝试没有新增证据时停止碰运气并报告阻塞点。
- 完成后同步更新五份文档版本。
- 只把已验证事实标为完成。
- 不因局部 Bug 跨模块重写。
- 未经用户确认不得突破本文件的明确限制。

## 23. 当前架构禁区

以下是 V0.5.0 当前不采用的实现，不是永远不可修改的教条。若真实验证证明必须调整，应先给出原因、替代方案和影响范围，并同步更新五份文档。

- 不得建立第二个配置事实来源。
- 不得建立第二个 Release 权威。
- 不得建立第二个 Runtime 权威。
- 不得建立第二个写入权威。
- 一个 Run 不得执行多个 Agent。
- conversation 不得永久固定旧 Release。
- 不得执行 Git Skill 中的脚本。
- YIAI Center 平台不得从 Git 部署 MCP 源码；独立部署层可由获授权的交付动作固定版本部署。
- 不得开放远程动态写 MCP。
- 写 Tool 不得绕过确认。
- CloudCallSnap 不得因聚合而丢失逐次调用记录。
- Usage 缺失时不得补零或猜测。
- 不得持久化隐藏思维链。
- 密钥不得进入日志和 Trace。
- 不得自动修改配置、发布或回滚。
- 不得使用会破坏持久化数据的修复命令。

在文档尚未更新前，任何当前禁区被静默突破，版本不得标记完成。经产品负责人确认并更新基线后，应按最新约定执行，不再受旧条目约束。

## 24. V0.5.9 MCP 两层架构实测边界

- MCP Server 部署层使用独立目录、Compose project、容器和端口；不得进入 YIAI Center 应用镜像或 Compose project。
- stdio 上游可以在独立服务侧增加最小 Streamable HTTP Adapter；Adapter 只注册上游 Tool，不复制或重写业务算法。
- 上游 Git commit、运行时版本和下载校验值固定，容器启动不拉取 `main`。
- 平台层只保存远程 Endpoint、固定版本、Tool Schema hash、只读声明、白名单、Agent 绑定、测试结果和运行配置。
- `mcp_servers` 是可编辑 Control Plane 事实；Candidate 将当时配置复制进 Release，运行只读 Release 快照。
- `mcp_call_snaps` 保存 Server、Git、版本、Endpoint、Tool、参数、摘要、长度、时间、延迟、状态、错误、Release 和 `model_api_cost=0`。
- Runtime 依据 Release 中的通用激活词、业务说明、声明式提取器、Schema 和白名单选择 Tool；主流程不存在命理专用条件分支。
- Streamable HTTP Client 支持 JSON 和 SSE 响应、`Mcp-Session-Id`、initialize、initialized、tools/list 和 tools/call，并限制单响应最大字节数。
- 外部 Server 短暂网络失败形成 FAILED MCP Snap，回答降级且不伪造结果；历史失败证据不删除。
- Router 不成为 MCP 连接、参数或业务规则权威。
- Release 不保存 Bearer 明文，页面不回显 Secret，Trace 不记录鉴权值。
