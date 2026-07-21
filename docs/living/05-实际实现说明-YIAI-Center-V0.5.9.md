# YIAI Center V0.5.9 实际实现说明

> 文档版本：V0.5.9
> 创建日期：2026-07-21
> 部署地址：`http://192.168.50.92:19080`
> Active Release：`V0.5.9-agent-config-fix`
> Release ID：`rel_600de34d421a49d09a7cb0841b560b16`

## 1. 交付结论

V0.5.9 已把能力装配入口从 Skill、RAG、MCP 资源页迁移到垂直 Agent 页面。Agent 草稿现在是基础信息和能力绑定的唯一可编辑权威；资源页只管理资源本身并只读显示使用关系。

当前三个 Agent 的迁移结果：

- 一般客服：1 个 Skill、1 个 RAG、1 个 MCP Tool、0 个预置 Tool。
- 投诉客服：0 个 Skill、1 个 RAG、0 个 MCP Tool、0 个预置 Tool。
- 工单处理：0 个 Skill、1 个 RAG、0 个 MCP Tool、0 个预置 Tool。

## 2. 前端实现

平台管理侧边导航新增 Agent，并放在 Release 之前。

Agent 页面包含：

- 三个现有 Agent 的选择器。
- Agent 名称、稳定 ID、业务说明和 System Prompt。
- 已校验 Skill 复选框。
- 已校验 RAG 文档复选框。
- 按 MCP Server 分组的只读 Tool 复选框。
- 预置 Tool 空状态。
- “保存 Agent 草稿”操作及“需要 Candidate + 人工发布才生效”的说明。

Skill、RAG、MCP 表单已经删除 Agent 复选框。资源卡片通过 `bound_agent_ids` 或 `tool_agent_ids` 只读显示当前使用关系。

主要文件：

- `apps/web/static/app.js`
- `apps/web/static/styles.css`

## 3. 数据与迁移

第六号前向迁移新增 `agent_configs`，字段包括：

- Agent 基础信息。
- `skill_ids_json`。
- `rag_document_ids_json`。
- `mcp_tool_bindings_json`。
- `tool_ids_json`。
- 校验错误和更新时间。

迁移首次运行时读取 Active Release，把旧资源侧 `agent_ids` 转成 Agent 草稿。已有 Agent 草稿时使用 `INSERT OR IGNORE`，不会覆盖后续编辑。

原资源表的 `agent_ids_json` 暂时保留用于兼容和取证，但不再参与新 Candidate 构建，也不再由资源页面修改。

升级前后业务数据对比：

- Release：8 → 8（迁移本身不新增；发布修复 Release 后为 9）。
- Run：23 → 23（迁移本身不新增；真实冒烟后为 24）。
- Trace：351 → 351（迁移本身不新增；真实冒烟后为 365）。
- Skill / SkillVersion：2 / 2，未减少。
- RAG / RAGVersion：3 / 3，未减少。
- MCP Server / MCPCallSnap：2 / 6，未减少。
- AgentConfig：新增 3。

主要文件：`apps/api/app/db.py`。

## 4. API 实现

新增：

- `GET /api/agents`
- `GET /api/agents/{agent_id}`
- `PUT /api/agents/{agent_id}`

PUT 校验：

- Agent 必须存在。
- Skill 和 RAG 必须存在且已校验。
- MCP 必须已连接。
- MCP Tool 必须同时位于配置白名单和连接测试允许清单。
- 当前没有预置 Tool，因此非空 `tool_ids` 被拒绝。

资源 API 保持原路径兼容。客户端即使提交旧 `agent_ids` 也不会把它作为新绑定写入 Candidate；响应保留派生的 `agent_ids` 并新增明确的 `bound_agent_ids`。

主要文件：

- `apps/api/app/main.py`
- `apps/api/app/db.py`
- `apps/api/app/rag.py`

## 5. Release 构建与 Diff

Candidate 创建时：

1. 读取三个 AgentConfig。
2. 固定 Agent 名称、说明和 System Prompt。
3. 解析每个 Agent 选择的资源 ID。
4. 只纳入当前有效的 SkillVersion、RAGVersion 和 MCP Tool。
5. 保存 Tool → Agent 映射 `tool_agent_ids`。
6. 生成不可变 `release_bindings`。

MCP 新快照使用 `MCP_TOOL` 类型及 `server_id::tool_name` 组件 ID，避免同一个 Server 的多个 Tool 绑定同一 Agent 时主键冲突。

Release Diff 新增：

- Agent 新增、移除和基础信息变化。
- 能力绑定变化 Agent。
- 候选 Release 的完整 Agent 绑定快照。

本次修复 Release 与旧 Active Release 的语义绑定相同，因此 Agent 绑定 Diff 为空；MCP 因从 Server 级升级为 Tool 级快照显示配置变化。

## 6. Runtime 兼容

Runtime 调用 MCP 前使用 `tool_bound_to_agent`：

- 新 Release 按 `tool_agent_ids[tool_name]` 校验 Agent。
- 历史 Release 没有 `tool_agent_ids` 时回退到旧 `server.agent_ids`。

Skill 与 RAG 继续读取 Run 已固定 Release 中的 `agent_ids`，聊天主流程没有读取 Agent 草稿，也没有新增任何领域专用判断。

主要文件：

- `apps/api/app/mcp_runtime.py`
- `apps/api/app/runtime.py`

## 7. 部署与 Release

- Docker Compose project：`yiai-center`。
- 容器：`yiai-center-api-1`。
- 端口：19080。
- 数据卷：沿用现有 `./data:/app/data`，没有删除或重建数据库。
- 镜像构建成功，容器健康。
- Candidate：`V0.5.9-agent-config-fix`。
- Candidate ID：`rel_600de34d421a49d09a7cb0841b560b16`。
- 已人工发布，当前为 Active。

## 8. 测试证据

- 生产镜像内 26 项 unittest 全部通过，耗时 3.773 秒。
- 新地址健康与 Agent API 从开发机访问成功。
- 非白名单 MCP Tool 的 Agent PUT 请求返回 400。
- Agent 草稿原样保存后 Active Release 未变化。
- 容器重启后 Agent 绑定保持。
- Headless Edge 等待 5 秒后成功执行页面模块并渲染聊天表单；页面布局和交互体验仍由产品负责人手动验收。

历史快照证据：

- 旧 Run：`run_fccbf50fe28c4fbba496114ddf4102f9`。
- 旧 Release：`V0.5.9-mcp-docs-hot-swap`。
- 旧 MCP Tool：`search_model_context_protocol`。
- 旧 Run 状态：DONE。

新 Release 冒烟：

- Run：`run_62c532ccda3f41a89bef2ebdb57c48b7`。
- Release：`V0.5.9-agent-config-fix`。
- Router 结果：只选择 `general-service`。
- 最终状态：ERROR。
- 原因：电脑切换 Wi-Fi 后，容器使用的 Clash 代理 `host.docker.internal:7890` 中止 DeepSeek TLS；宿主机直连 DeepSeek 可达，容器代理和容器直接 TLS 均失败。
- 系统行为：保留错误 Trace，不伪造回答、Usage 或成本。

## 9. 当前待产品负责人确认

- 打开“平台管理 → Agent”，确认三个 Agent 的信息层级和操作是否符合预期。
- 确认 Skill、RAG、MCP 页面已经没有反向勾选 Agent 的入口。
- 确认 Agent 页面按 Skill、RAG、MCP Tool、预置 Tool 四类装配的交互是否需要进一步调整。
- Wi-Fi 环境下需要恢复 Clash 到 DeepSeek 的可用代理链路，之后补跑一次真实成功聊天 Run。
