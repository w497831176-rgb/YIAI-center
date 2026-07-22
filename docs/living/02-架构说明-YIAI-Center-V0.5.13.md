# YIAI Center V0.5.13 架构说明

> 文档版本：V0.5.13
> 创建日期：2026-07-21
> 更新日期：2026-07-22
> 架构范围：工单 Tool、Action Gateway、无限轮人机共驾与 Release 快照
> 正式部署：`192.168.50.112:19080`

## 1. 架构结论

V0.5.13 沿用 YIAI Center 的 Control Plane 与 Runtime 分离模型，并新增三个通用运行能力：

- 预置业务 Tool 运行器：负责真实工单查询与受控变更。
- Action Gateway：负责写操作草稿、确认、幂等、执行、收据和审计。
- Co-driving Runtime：负责 AI 与员工之间可反复切换的输出权。

三者都由 Release 快照驱动，不在 Router 中写死工单行业判断。移除 Agent 的 Tool 绑定并发布新 Release 后，下一条新消息自然失去该能力，聊天主链路不需要改代码。

## 2. 权威边界

### 2.1 配置权威

- `agent_configs` 是 Agent 基础信息和 Skill、RAG、MCP Tool、预置 Tool 绑定的唯一可编辑权威。
- 工单、Skill、RAG、MCP 页面只管理资源自身，不编辑 Agent 绑定。
- Candidate Release 在创建时冻结 Agent、资源和 Tool 绑定。
- Runtime 只读取本 Run 固定的 Release 配置，不读取发布后的 Agent 草稿变化。

### 2.2 业务数据权威

- `work_orders` 保存工单事实。
- `action_requests` 保存写操作状态、参数、前置快照、结果和收据。
- `action_audit_events` 以追加方式保存 Action 状态变化。
- `codrive_sessions` 保存每个会话当前输出权和版本。
- `codrive_events` 保存共驾状态变化。
- `human_messages` 保存员工消息，和用户、AI 消息合并展示。

### 2.3 运行证据权威

- `runs` 固定本轮 Release、Agent、状态、延迟和模型成本。
- `trace_events` 保存可核对的运行步骤。
- `cloud_call_snaps` 保存真实 Provider 用量与价格快照。
- 历史 Run 不回查当前 Agent 草稿，不因后续发布而改变。

## 3. 前向迁移

本轮新增三个可重复执行的前向迁移：

### 迁移 7：工单

创建 `work_orders`，主要字段：

- `id`、`user_id`。
- `subject`、`description`、`category`、`priority`。
- `status`、`result`。
- `created_at`、`updated_at`、`deleted_at`。

启动时以 `INSERT OR IGNORE` 写入三条领域无关演示数据。迁移不会覆盖已有记录。

### 迁移 8：Action Gateway

创建 `action_requests` 与 `action_audit_events`。

Action 状态为：

`DRAFT → AWAITING_CONFIRMATION → CONFIRMED → EXECUTING → SUCCEEDED / FAILED / INDETERMINATE`

用户取消时进入 `CANCELLED`。`idempotency_key` 唯一；确认令牌只保存 SHA-256 哈希；删除操作的第二次确认使用新令牌。

### 迁移 9：人机共驾

创建 `codrive_sessions`、`codrive_events` 和 `human_messages`。

共驾状态只有：

- `AI_ACTIVE`
- `HANDOFF_REQUESTED`
- `HUMAN_ACTIVE`
- `AI_RESUMING`

数据结构和服务端校验中都不存在 `CLOSED` 共驾状态。

## 4. Release 中的 Tool 快照

平台登记六个预置 Tool：

- `list_work_orders`，只读。
- `get_work_order`，只读。
- `create_work_order`，写操作。
- `update_work_order`，写操作。
- `close_work_order`，写操作。
- `delete_work_order`，写操作。

Agent 草稿保存 `tool_ids_json`。创建 Candidate 时，服务端将 Tool 定义、输入结构、读写属性和 `agent_ids` 写入 Release 配置。Release Diff 显示新增或移除的 Tool。

Router 的模型提示和确定性兜底都读取当前 Release 中 Agent 的名称、说明和已发布 Tool 描述。这样即使模型 Router 不可用，也能依据能力数据选择 Agent，而不是依赖固定 Agent 顺序或行业关键词分支。

## 5. 只读运行链路

只读请求的主要顺序为：

1. `prepare_run` 创建 Run、用户消息并固定 Active Release。
2. Router 从该 Release 的 Agent 清单中选择一个 Agent。
3. Runtime 读取该 Agent 在 Release 中绑定的预置 Tool。
4. 参数规划器在允许清单中选择只读 Tool。
5. `work_orders.execute_read` 查询 SQLite。
6. Trace 写入 `preset_tool_request` 与 `preset_tool_response`，包含参数、结果长度、延迟和 `model_api_cost=0`。
7. 真实 Tool 结果注入主模型上下文。
8. 主模型失败时，Runtime 使用同一 Tool 结果生成确定性答案，并明确标记降级。

Tool 成功后不因模型失败而丢失事实，也不把失败的模型调用伪装成成功。

## 6. Action Gateway

所有写 Tool 共用同一服务端网关：

1. 校验 Tool 是否存在于指定 Release，并绑定到某个 Agent。
2. 校验参数结构与字段范围。
3. 读取执行前工单快照。
4. 创建 `DRAFT`，随后进入 `AWAITING_CONFIRMATION`。
5. 返回一次性确认令牌，数据库只保存哈希。
6. 确认后以原 Release 创建确认 Run。
7. 转为 `EXECUTING`，调用工单写入函数。
8. 保存结果、收据和审计事件。

创建、更新和关闭需要一次确认；软删除需要两次。第一次删除确认只记录状态并签发第二个令牌，不调用写入函数。

终态为 `SUCCEEDED` 时，再次确认直接返回原收据并标记幂等重放，不再次执行。异常中断且无法判断真实结果时使用 `INDETERMINATE`，禁止盲目重试。

## 7. 人机共驾状态机

共驾只控制输出权：

```text
AI_ACTIVE
  └─请求人工→ HANDOFF_REQUESTED
                   └─员工接受→ HUMAN_ACTIVE
                                    └─交还 AI→ AI_RESUMING
                                                    └─恢复→ AI_ACTIVE
```

关键约束：

- `HUMAN_ACTIVE` 期间，新的用户消息仍写入消息和 Run，但 `execute_chat` 不生成 AI `delta`。
- 员工消息不限制数量；每条消息都递增 `codrive_sessions.version`。
- 员工提交时必须带 `expected_version`。旧版本返回 409，避免并发双写。
- “交还 AI”先进入 `AI_RESUMING`，再把人工消息和摘要合并到对话上下文。
- AI 使用交还时刻的 Active Release 新建 Run。
- 无论模型成功或失败，`finally` 都调用 `complete_return_to_ai` 恢复 `AI_ACTIVE`。
- 恢复后 `can_request_human=true`，允许下一轮循环。

## 8. 消息与上下文

`get_messages` 按时间合并：

- 用户消息。
- AI 消息。
- 员工消息。

员工消息在模型历史上下文中带有明确的员工来源前缀，避免被误认为用户指令。员工交还摘要用于快速续接，但不能代替完整人工消息。

## 9. API

### 工单

- `GET /api/work-orders?scope=USER|EMPLOYEE`
- `GET /api/work-orders/{id}`

### Action

- `GET /api/actions`
- `GET /api/actions/{id}`
- `POST /api/actions/drafts`
- `POST /api/actions/{id}/confirm`
- `POST /api/actions/{id}/cancel`

### 共驾

- `GET /api/codrive/sessions`
- `GET /api/conversations/{id}/codrive`
- `POST /api/conversations/{id}/codrive/request`
- `POST /api/conversations/{id}/codrive/accept`
- `POST /api/conversations/{id}/codrive/messages`
- `POST /api/conversations/{id}/codrive/return-ai/stream`

## 10. Trace 与成本

新增 Trace 类型包括：

- `preset_tool_selected`
- `preset_tool_request`
- `preset_tool_response`
- `action_draft_created`
- `action_confirmation_requested`
- `action_confirmation_completed`
- `action_execution_started`
- `action_execution_completed`
- `codrive_handoff_requested`
- `codrive_human_active`
- `codrive_ai_resuming`
- `codrive_ai_active`

本地数据库和状态机步骤的 `model_api_cost` 为 0。真实 DeepSeek 调用仍通过 `cloud_call_snaps` 保存模型、Token、缓存命中、价格快照、人民币估算和 Provider 请求 ID。未返回用量时保持 `null`。

## 11. 部署边界

- 目标主机为 Ubuntu Server 24.04 LTS，YIAI Center 使用独立目录 `/home/wang/apps/yiai-center-v0513`。
- Compose 项目名为 `yiai-center-v0513`，应用容器为 `yiai-center-v0513-api-1`，应用网络为 `yiai-center-v0513_default`。
- 业务数据库持久化到 `/home/wang/apps/yiai-center-v0513/data/yiai-center.sqlite`，不使用主机其他项目的 Volume。
- 应用代码固定为 Git 提交 `a50e795`，镜像名为 `yiai-center-v0513-api`。
- 目标机 Mihomo 只监听主机回环地址，因此项目使用两个专用桥接容器和共享 Unix Socket 连接主机代理；不开放额外局域网端口，不修改 Mihomo、UFW、DNS、TUN 或现有 Docker 网络。
- `yiai-center-v0513-proxy-host` 只负责访问主机 `127.0.0.1:7890`；`yiai-center-v0513-proxy-bridge` 只在项目网络内提供代理入口。
- 命语 MCP 仍是独立服务，YIAI Center 只保存并调用远程 Endpoint，没有把 MCP 服务并入应用容器。
- 源机 `192.168.50.232` 的 YIAI API 已停止，原数据库和一致性备份 `yiai-center-migration-20260722.sqlite` 保留，未执行 Compose down、Volume 删除或全局 Docker 清理。
