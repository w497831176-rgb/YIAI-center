# YIAI Center V0.5.9 产品说明

> 文档版本：V0.5.9
> 创建日期：2026-07-21
> 本次范围：修复垂直 Agent 配置入口与能力装配归属
> 当前部署地址：`http://192.168.50.92:19080`

## 1. 问题与结论

V0.5.9 当前页面把 Skill、RAG、MCP 与垂直 Agent 的绑定入口放在各资源编辑页，平台中没有完整的垂直 Agent 配置页。这不符合产品原定的“垂直 Agent 是能力装配单元”原则。

本次修复后：

- 垂直 Agent 是 Skill、RAG、MCP Tool 与预置 Tool 绑定的唯一配置入口。
- Skill、RAG、MCP 页面只负责资源自身的创建、版本、校验、连接测试与停用。
- 资源页面可以只读显示当前被哪些 Agent 使用，但不能在资源页面修改绑定。
- Agent 草稿保存后不立即影响在线运行，必须进入候选 Release、查看 Diff 并人工发布。
- 历史 Release、Run、Trace 和消息继续保留原绑定快照。

## 2. Agent 配置页面

平台管理增加“Agent”页面，并作为 Control Plane 的首要配置入口。

页面至少展示三个现有垂直 Agent：

- 一般客服。
- 投诉客服。
- 工单处理。

每个 Agent 可以配置：

- 名称。
- 业务说明。
- System Prompt。
- 已校验 Skill。
- 已校验 RAG 文档。
- 已连接 MCP Server 下允许的只读 Tool。
- 平台已登记的预置 Tool；当前没有真实预置 Tool 时明确显示为空，不制造假 Tool。

## 3. 能力资源页面

### 3.1 Skill

- 创建和编辑 Skill 正文、适用条件、不适用条件与输出要求。
- 保存产生不可变 SkillVersion。
- Skill 校验只判断 Skill 内容是否完整、合法，不再要求在 Skill 页面选择 Agent。
- 卡片只读显示当前使用该 Skill 的 Agent。

### 3.2 RAG

- 创建文档、预览切片、保存不可变 RAGVersion、校验与检索测试。
- RAG 校验只判断文档、标签、版本说明、切片与索引是否有效，不再要求在 RAG 页面选择 Agent。
- 卡片只读显示当前使用该 RAG 的 Agent。

### 3.3 MCP

- 创建和编辑远程 Endpoint、固定版本、鉴权、只读声明、Tool 白名单和通用运行配置。
- 连接测试负责获取 Tool List 并判断哪些 Tool 可以绑定。
- MCP 页面不再选择 Agent。
- 卡片只读显示每个 Tool 当前被哪些 Agent 使用。

### 3.4 预置 Tool

- 预置 Tool 也必须从 Agent 页面绑定。
- 当前版本没有真实可执行的预置 Tool，因此 Agent 页面展示空状态，不使用占位 Tool 冒充已接入能力。

## 4. 保存、发布与生效

1. 产品负责人进入 Agent 页面编辑 Agent 与能力绑定。
2. 保存 Agent 草稿。
3. 创建候选 Release。
4. Release Diff 展示 Agent 基础信息变化及 Skill、RAG、MCP Tool、预置 Tool 绑定变化。
5. 人工发布。
6. 发布后的下一条新消息使用新 Agent 配置。
7. 旧消息与旧 Run 保留原 Release 和能力绑定快照。

## 5. 数据迁移要求

- 升级时把现有 Skill、RAG、MCP 的 Agent 关系迁移到 Agent 配置中。
- 迁移不得删除资源、资源版本、Release、Run、Trace、会话或 MCP 调用快照。
- 已有 MCP Server 绑定到某 Agent 时，把该 Server 当前允许的只读 Tool 迁移为该 Agent 的 MCP Tool 绑定。
- 原资源表中的 `agent_ids` 仅作为兼容字段保留，不再作为新 Release 的配置权威。

## 6. 验收标准

- 平台管理可以进入 Agent 页面并编辑三个垂直 Agent。
- Skill、RAG、MCP 编辑表单中没有“绑定垂直 Agent”控件。
- Agent 页面可以装配 Skill、RAG、MCP Tool，并展示预置 Tool 空状态。
- 保存 Agent 草稿不会立即改变 Active Release。
- Candidate Release 使用 Agent 草稿生成不可变绑定快照。
- 发布后新消息使用新绑定，历史 Run 保留旧绑定。
- 现有资源和绑定在迁移后没有丢失。
