# YIAI Center V0.5.9 架构说明

> 文档版本：V0.5.9
> 创建日期：2026-07-21
> 架构主题：以垂直 Agent 为中心的 Control Plane 装配模型

## 1. 权威边界

V0.5.9 修复后的配置权威如下：

- Agent 草稿表是 Agent 基础信息和能力绑定的唯一可编辑权威。
- Skill、RAG、MCP 表是资源内容、版本、校验和连接状态的权威，不拥有 Agent 绑定编辑权。
- Candidate Release 在创建时读取 Agent 草稿与当时有效资源，生成不可变 Release 配置和 `release_bindings`。
- Runtime 只读取本次 Run 固定的 Release 快照，不读取 Agent 草稿或资源页临时状态。

## 2. 数据模型

新增第六号前向迁移，创建 `agent_configs`：

- `id`：稳定 Agent ID。
- `name`：Agent 名称。
- `description`：业务说明。
- `system_prompt`：系统提示词。
- `skill_ids_json`：绑定的 Skill 资源 ID。
- `rag_document_ids_json`：绑定的 RAG 文档 ID。
- `mcp_tool_bindings_json`：`server_id + tool_name` 组合。
- `tool_ids_json`：预置 Tool ID。
- `validation_errors_json`：Agent 草稿校验结果。
- `updated_at`：最近更新时间。

现有 `skills.agent_ids_json`、`rag_documents.agent_ids_json`、`mcp_servers.agent_ids_json` 暂时保留用于无损兼容，但 Candidate 构建与页面编辑不再读取这些字段作为权威。

## 3. 初始化与兼容迁移

数据库启动时按以下顺序执行：

1. 创建 `agent_configs`。
2. 若表中还没有 Agent，则读取当前 Active Release 的 Agent 和能力快照。
3. 把每个 Skill、RAG 的旧 `agent_ids` 转成对应 Agent 的资源绑定。
4. 把每个 MCP Server 的旧 Agent 绑定转成该 Agent 对当前允许只读 Tool 的逐 Tool 绑定。
5. 不修改任何历史 Release 配置。

迁移可重复执行，已有 `agent_configs` 时不得覆盖产品负责人的新草稿。

## 4. API

新增：

- `GET /api/agents`：返回 Agent 草稿、绑定详情和可验证状态。
- `GET /api/agents/{agent_id}`：返回单个 Agent 草稿。
- `PUT /api/agents/{agent_id}`：保存 Agent 基础信息和能力绑定。

现有 Skill、RAG、MCP API 保持路径兼容，但：

- 保存资源时忽略客户端提交的 Agent 绑定。
- 资源校验不再把“未绑定 Agent”视为错误。
- 列表响应中的 `bound_agent_ids` 从 `agent_configs` 反向计算，仅用于展示。

## 5. Candidate Release 构建

`_candidate_config` 以 `agent_configs` 为入口：

- `agents` 复制 Agent 基础信息。
- 仅把 Agent 选择且当前状态为 `VALIDATED` 的 Skill 当前版本写入 `skills`。
- 仅把 Agent 选择且当前状态为 `VALIDATED` 的 RAG 当前版本写入 `rag`。
- 仅把 Agent 选择、Server 状态为 `CONNECTED`、Tool 在只读白名单且连接测试允许的 MCP Tool 写入 `mcp`。
- MCP Release 快照保存每个 Tool 对应的 `agent_ids`，Runtime 在调用前同时校验 Server、Tool 和 Agent。
- 当前没有真实预置 Tool，`tools` 保持空数组。

## 6. Release Diff 与运行兼容

- Release Diff 增加 Agent 基础信息变化和按 Agent 统计的绑定变化。
- `release_bindings` 继续保存 SkillVersion、RAGVersion、MCP Tool 与 Agent 的关系。
- 历史 Release 的旧 MCP Server 级绑定继续可运行。
- 新 Release 使用逐 Tool Agent 绑定；Runtime 对旧快照缺少逐 Tool映射时按旧 `agent_ids` 兼容。
- 聊天主流程保持领域无关，不加入具体 Skill、RAG 或 MCP 业务名称判断。

## 7. 前端边界

- 平台侧边导航增加 Agent。
- Agent 页面负责编辑与绑定。
- Skill、RAG、MCP 页面删除绑定复选框，只显示反向使用关系。
- 前端不直接修改 Active Release，也不自行拼装 Release 快照。

## 8. 安全与持久化

- 不删除 SQLite、Volume、历史 Release、Run、Trace 或 Secret。
- Bearer Secret 不返回前端，不进入 Agent 配置和 Release 明文。
- MCP Tool 仍需通过连接测试、只读声明和白名单三重约束。
- 迁移和保存操作使用现有 SQLite 事务。
