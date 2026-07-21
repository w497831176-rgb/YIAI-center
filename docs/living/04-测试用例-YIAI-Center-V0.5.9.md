# YIAI Center V0.5.9 测试用例与自测记录

> 文档版本：V0.5.9
> 初始范围冻结：2026-07-21
> 自测回填：2026-07-21
> 部署地址：`http://192.168.50.92:19080`
> Active Release：`V0.5.9-agent-config-fix`

## 1. 状态定义

- 通过：实际结果符合预期并记录证据。
- 失败：实际结果不符合预期，保留原因。
- 阻塞：代码路径已经执行，但外部依赖当前不可用。
- 待手动：需要产品负责人在浏览器中判断页面和交互体验。

## 2. 文档与静态契约

### TC-059-A01 五份文档范围

预期：四份开工文档先创建，第五份实际实现说明只在实现和测试后创建。

实际：先创建产品说明、架构说明、版本规划和测试用例；实现与自测完成后才创建实际实现说明。

状态：通过。

### TC-059-A02 页面绑定入口唯一

预期：Agent 页面包含能力绑定控件；Skill、RAG、MCP 编辑表单不包含 Agent 绑定控件。

实际：部署后的 `app.js` 包含 `agent-form` 和 `mcp_tool_bindings`，不存在 `name="agent_ids"`；Headless Edge 等待页面脚本执行后成功渲染 `chat-form`，说明模块脚本可以执行。

状态：通过。

## 3. 数据迁移与持久化

### TC-059-B01 第六号迁移

预期：升级后 `schema_migrations` 包含版本 6，`agent_configs` 包含三个默认 Agent。

实际：迁移版本为 `[1, 2, 3, 4, 5, 6]`；`agent_configs=3`，ID 分别为 `general-service`、`complaint-service`、`work-order-service`。

状态：通过。

### TC-059-B02 旧绑定无损迁移

预期：升级前 Active Release 中已有的 Skill、RAG、MCP 绑定可以在 Agent 草稿中找到；资源、版本、Release、Run 和 Trace 数量不减少。

实际：

- 升级前：8 个 Release、23 个 Run、351 个 Trace、2 个 Skill、2 个 SkillVersion、3 个 RAG、3 个 RAGVersion、2 个 MCP、6 个 MCPCallSnap。
- 迁移后且创建新测试证据前，上述数量完全不变，另新增 3 个 AgentConfig。
- 一般客服迁移得到 1 个 Skill、1 个 RAG、1 个 MCP Tool。
- 投诉客服迁移得到原“通用问题处理方法”RAG。
- 工单处理迁移得到原“通用工单规则”RAG。
- 历史 Release 配置没有被重写。

状态：通过。

### TC-059-B03 重启持久化

预期：保存 Agent 草稿并重启容器后，Agent 基础信息和四类绑定不丢失。

实际：通过 Agent PUT API 原样保存一般客服草稿，确认 Active Release 不变；重启 `yiai-center-api-1` 后仍为 1 个 Skill、1 个 RAG、1 个 MCP Tool，健康检查通过。

状态：通过。

## 4. Agent API

### TC-059-C01 Agent 列表

预期：`GET /api/agents` 返回三个 Agent，每个对象包含基础信息、Skill、RAG、MCP Tool 和预置 Tool 绑定。

实际：从开发机访问 `http://192.168.50.92:19080/api/agents` 返回三个 Agent；每项包含 `skill_ids`、`rag_document_ids`、`mcp_tool_bindings`、`tool_ids`、绑定详情和空的预置 Tool 清单。

状态：通过。

### TC-059-C02 保存 Agent 草稿

预期：`PUT /api/agents/{id}` 可以保存合法配置；未知 Agent、未知资源和不允许的 MCP Tool 被拒绝。

实际：合法原样保存返回 200；提交 `forbidden_write_tool` 返回 400；26 项自动测试中的未知 Tool 和资源校验均通过。

状态：通过。

### TC-059-C03 草稿不直接生效

预期：保存 Agent 后 Active Release ID 与配置不变。

实际：PUT 前后 `active_release_id` 一致，直到另行创建 Candidate 并人工发布。

状态：通过。

## 5. 资源 API 与页面

### TC-059-D01 Skill 独立校验

预期：Skill 不选择 Agent 也能创建和校验；响应只读返回 `bound_agent_ids`。

实际：自动测试证明未绑定 Skill 可以进入 `VALIDATED`，但不会进入 Candidate；现网 2 个 Skill 的只读绑定数量分别为 0 和 1。

状态：通过。

### TC-059-D02 RAG 独立校验

预期：RAG 不选择 Agent 也能创建和校验；响应只读返回 `bound_agent_ids`。

实际：RAG 自动测试通过；现网 3 个 RAG 均从 AgentConfig 反向返回 1 个使用 Agent。

状态：通过。

### TC-059-D03 MCP 独立管理

预期：MCP 保存和连接测试不要求 Agent；响应只读返回 Server 和 Tool 的 Agent 使用关系。

实际：MCP 自动测试通过；现网两个 Server 的只读绑定数量为 1 和 0，`tool_agent_ids` 可以按 Tool 查看。

状态：通过。

### TC-059-D04 预置 Tool 空状态

预期：没有真实预置 Tool 时 Agent 页面明确显示空状态，API 和 Release 不制造假 Tool。

实际：Agent API 的 `available_preset_tools=[]`，新 Release 的 `tools=[]`，页面明确说明没有已登记预置 Tool。

状态：通过。

## 6. Release

### TC-059-E01 Candidate 从 Agent 草稿构建

预期：Candidate 只包含 Agent 选择且资源状态有效的 Skill、RAG、MCP Tool。

实际：Candidate `rel_600de34d421a49d09a7cb0841b560b16` 包含 3 个 Agent、1 个已装配 Skill、3 个已装配 RAG、1 个已装配 MCP Tool，不包含未装配 Skill 和假 Tool。

状态：通过。

### TC-059-E02 MCP Tool 粒度

预期：同一 MCP Server 的不同 Tool 可以绑定不同 Agent；Release 保存 Tool 对 Agent 的映射。

实际：自动测试把 `read_one` 与 `read_two` 分别绑定一般客服和投诉客服并验证 Release 快照；现网候选把 `search_model_context_protocol` 绑定一般客服并保存 `tool_agent_ids`。

状态：通过。

### TC-059-E03 Release Diff

预期：Diff 显示 Agent 基础信息变化与各类绑定变化。

实际：Diff 返回 Agent 新增、移除、基础信息变化、能力绑定变化和完整 Agent 绑定快照；本次语义绑定与旧 Release 相同，因此 `agent_bindings_changed=[]`，MCP 因升级为 Tool 级快照显示为配置变化。

状态：通过。

### TC-059-E04 发布与历史快照

预期：人工发布只影响下一条新消息；旧 Run 仍显示旧 Agent 与旧能力绑定快照。

实际：

- 已人工发布 `V0.5.9-agent-config-fix`。
- 旧 Run `run_fccbf50fe28c4fbba496114ddf4102f9` 仍为 `V0.5.9-mcp-docs-hot-swap`、状态 DONE，并保留 `search_model_context_protocol` MCPCallSnap。
- 新 Run `run_62c532ccda3f41a89bef2ebdb57c48b7` 固定到新 Release。

状态：通过。

## 7. Runtime 与回归

### TC-059-F01 单 Agent 运行

预期：Router 每次仍只选择一个 Agent，Skill、RAG、MCP 只使用该 Agent 在固定 Release 中的绑定。

实际：30 项自动测试中的 Runtime 契约通过。真实 Run `run_62c532ccda3f41a89bef2ebdb57c48b7` 固定新 Release 并只选择 `general-service`；随后现有容器代理 `http://host.docker.internal:7890` 中止 DeepSeek TLS 连接，Router 使用确定性降级，主回答调用进入 ERROR。系统保留错误 Trace，没有伪造回答或成本。

状态：阻塞。阻塞点是电脑从网线切换 Wi-Fi 后现有 Clash 代理链路，宿主机直连 `https://api.deepseek.com` 可达，但容器通过原代理或直接 TLS 均被中止；不属于本次 Agent 配置代码回归。

### TC-059-F02 MCP 调用前绑定校验

预期：Runtime 同时校验 Server、Tool、Agent；未绑定 Tool 不执行并留下拒绝 Trace。

实际：新增 `tool_bound_to_agent` 同时支持新 Tool 级快照和旧 Server 级快照；允许和拒绝分支自动测试通过。

状态：通过。

### TC-059-F03 既有测试回归

预期：V0.5.9 原有 Skill、RAG、MCP、Release、Run、Usage 测试继续通过。

实际：完整源码映射环境内执行 `python -m unittest discover -s tests -v`，共 30 项，全部通过，耗时 4.103 秒。新增覆盖 Agent 创建、删除、Release 快照、动态 Router 和卡片界面契约。

状态：通过。

### TC-059-F04 HTTP 与容器健康

预期：健康、Agent、Skill、RAG、MCP、Release API 均可访问，容器健康。

实际：从开发机通过新地址访问成功；健康状态 `ok`、数据库 `ok`、版本 `V0.5.9`、Agent 数量 3；容器为 healthy。

状态：通过。

## 8. 页面体验

### TC-059-G01 Agent 装配体验

预期：产品负责人能够从 Agent 页面完成四类能力选择，信息层级清楚，没有资源页反向勾选 Agent 的入口。

自动证据：页面脚本已执行，Agent 卡片、新增按钮、配置弹层和四类装配区域已部署，资源页反向绑定输入不存在。

状态：待产品负责人手动验证页面布局、文案和操作感受。

### TC-059-G02 平台管理卡片化

预期：Agent、Release、Skill、RAG、MCP 和 Run 首页都以卡片为主；新增或导入放在右上角；编辑、校验、测试、停用、发布和查看 Trace 从对应卡片进入。

实际：上述六个页面均已改为自适应卡片网格，大表单改为点击后打开的独立弹层。Headless Edge 真实加载部署地址 5 秒后完成首屏渲染，DOM 中存在 `app-shell` 和 `chat-form`。

状态：自动证据通过，卡片密度和操作感受待产品负责人手动验收。

### TC-059-G03 新增垂直 Agent 闭环

预期：右上角可新增 Agent；系统自动生成稳定 ID；新 Agent 可进入候选 Release 并被 Router 从当前 Release 清单动态选择；删除草稿不改写 Active Release 和历史 Run。

实际：部署环境中临时创建 `agent_65e4d80942894573b39852e2d7fdbc4e`，Agent 数量从 3 变为 4；紧接着删除草稿，数量恢复为 3，接口明确返回 `active_release_unchanged=true`。自动测试另验证新 Agent 进入候选 Release，以及 Router 接受新 Agent ID。

状态：通过。

## 9. 自测结论

- Agent 配置归属错误已经修复并部署。
- 数据迁移、API、Candidate、Diff、历史快照、Tool 级绑定和回归测试通过。
- 平台管理已全面改为“卡片总览 + 右上角新增 + 卡片操作 + 弹层编辑”；具体视觉密度留给产品负责人手动验收。
- 垂直 Agent 已支持真实新增、编辑、删除草稿、候选 Release 快照和动态 Router。
- 真实 DeepSeek 新 Run 因 Wi-Fi 切换后的外部代理链路阻塞，已保留失败 Run 与 Trace，未把它误记为通过。
