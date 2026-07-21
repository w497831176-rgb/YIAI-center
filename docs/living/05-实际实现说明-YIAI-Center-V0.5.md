# YIAI Center 实际实现说明

> 当前版本：V0.5.7  
> 文档性质：Living Implementation Doc（动态实现记忆）  
> 用途：对照产品、架构和版本规划，说明代码事实上怎样运行、为什么这样实现、当前没做什么  
> 当前部署：已部署并通过后端自测  
> 配套文档：01 产品全局、02 架构全局、03 版本规划、04 测试用例与自测记录。

## 0. 使用规则

- 本文件记录“现在实际上怎样实现”，不是重复抄写 PRD 和架构理想。
- 实现与原规划不同时，必须写出真实证据、调整原因和产品影响。
- 代码变化后同步更新本文件；不能让实现长期领先文档。
- 不记录 SSH 密码、Git Token、DeepSeek Key 和其他密钥值。
- 本文件可以随版本重写，不是不可修改的竣工档案。

## 1. 当前交付结论

V0.5.0—V0.5.7 已形成一个可以真实演示的最小闭环：

1. 打开一个无登录、无行业迹象的三 TAB 页面。
2. 用户发送一条消息。
3. 系统在消息到达时固定当时 Active Release。
4. 唯一 Router 选择一个垂直 Agent。
5. Router 与主 Agent 都真实调用 DeepSeek V4-Flash 思考模式。
6. 主 Agent 通过 SSE 流式返回答案。
7. 每次云调用分别记录模型、三类 Token、延迟、单价快照和成本。
8. 平台管理可以查看 Release、Run、Trace 和 CloudCallSnap。
9. 人工发布或回滚只影响之后的新消息，历史气泡不变。
10. 用户页显示历史对话和所有消息时间戳。
11. AI 气泡下方可以打开右侧 Run 详情抽屉。
12. 新 Run 的 Trace 同时记录完整用户输入和客服最终回答。
13. CloudCallSnap 直接嵌入对应 Trace 步骤，页面统一显示人民币本步成本，底部汇总 Run 总成本。
14. 平台创建和编辑自然语言 Skill，每次保存形成不可变 SkillVersion。
15. 只有已校验、已绑定且随 Candidate 人工发布的 SkillVersion 才进入新 Run Prompt；历史 Run 保留旧 Release 快照。
16. 公开 GitHub URL 可以固定到具体 commit，在临时隔离目录扫描后把纯文本 `SKILL.md` 导入为未绑定 Draft；脚本和可执行内容整次拒绝并留存原因。

当前访问地址：

- `http://192.168.50.232:19080`。

当前 GitHub：

- `https://github.com/w497831176-rgb/YIAI-center`。
- 核心实现提交：`e47ca3f`；Living Docs 在后续提交持续同步。

## 2. 产品规划如何落地

### 2.1 领域无关

实际页面和默认数据没有物业、医保、商场或其他行业名称。

三个默认 Agent 只使用通用名称：

- 一般客服。
- 投诉客服。
- 工单处理。

工单 Agent 的 Prompt 明确说明当前版本尚未接入工单 Tool，因此不能声称已经创建、更新或关闭工单。

### 2.2 三个 TAB，无登录

实际只有三个顶层 TAB：

- 用户。
- 员工。
- 平台管理。

没有：

- 登录、注册、退出。
- 用户、员工、管理员账号。
- 身份切换器。
- 角色和权限编辑。

三个 TAB 只是同一个演示页面的导航。

### 2.3 用户页面

用户页面实际包括：

- 新对话按钮。
- 历史对话列表：标题、最近消息时间和消息数。
- 对话消息区。
- 用户与 AI 消息时间戳。
- 三个示例问题快捷按钮。
- 输入框和发送按钮。
- SSE 流式回答。
- AI 气泡下方的 Run 状态、垂直 Agent、Release 和详情入口。
- 从右侧打开的 Run 详情抽屉。

Run 详情实际展示：

- Run ID。
- Release。
- 垂直 Agent。
- 固定模型 `deepseek-v4-flash · thinking`。
- 本次用户输入和客服最终回答。
- 每个 TraceEvent 的时间。
- 嵌在云调用完成步骤中的 CloudCallSnap。
- 输入缓存未命中 Token。
- 输入缓存命中 Token。
- 输出 Token。
- 总延迟。
- 每步人民币成本和 Run 人民币总成本。

页面明确说明隐藏思考内容不展示、不保存。

### 2.4 员工页面

V0.5.5 只实现员工 TAB 页面骨架。

页面明确写出：

- 人机共驾和工单处理在后续版本实现。
- 当前不伪造员工队列、工单结果和人工接管数据。

### 2.5 平台管理页面

当前实现两个真实子页面。

Release 页面：

- 查看 Active、Candidate 和 Historical Release。
- 输入候选版本名和变更说明。
- 复制 Active 配置创建 Candidate。
- 人工发布 Candidate。
- 人工回滚 Historical Release。

Run 与 Trace 页面：

- 查看真实 Run 列表。
- 查看 Run 状态、时间、Release 和垂直 Agent。
- 查看只追加 Trace Event。
- 查看 Run 的用户输入与客服回答。
- 在对应 Trace 步骤内查看每次 Router／主 Agent 云调用的 CloudCallSnap。
- 查看三类 Token、延迟、Usage 状态、人民币本步成本和 Run 底部汇总。

Agent、RAG、MCP、Badcase 和完整成本治理页面仍为后续版本；Skill 页面已经接入真实数据与发布闭环。

## 3. 实际技术形态

当前运行拓扑：

```text
浏览器
  │ HTTP / SSE
  ▼
Python 3.12 标准库单容器
  ├─ 静态 HTML / CSS / JavaScript
  ├─ HTTP API
  ├─ SSE Runtime
  ├─ Release / Run / Trace 权威
  ├─ DeepSeek Adapter
  └─ SQLite WAL
       │
       └─ D:\docker\yiai-center\data
```

Compose project：

- `yiai-center`。

容器：

- `yiai-center-api-1`。

端口：

- 主机 19080 映射到容器 8000。

## 4. 为什么没有按最初技术栈实现

最初架构候选是：

- React、TypeScript、Vite。
- Nginx。
- FastAPI、Pydantic、httpx。
- 两个容器。

目标机真实验证发现：

1. Docker Hub 拉取 Node 和 Nginx 镜像时，目标机现有代理多次重置连接。
2. 改用已缓存 Python 镜像后，PyPI 下载 FastAPI 等依赖仍被同一代理中断。
3. 目标机已缓存 `python:3.12-slim`。

因此实际调整为：

- 原生 HTML、CSS、JavaScript。
- Python 3.12 标准库 HTTP Server。
- 标准库 urllib 调用 DeepSeek。
- 单容器。
- 零第三方运行依赖。

调整后的产品影响：

- 三个 TAB、对话、Release、Run、Trace、SSE、Usage 和成本功能均保留。
- 页面无需从公网加载 CDN。
- 构建不再依赖 Node、Nginx 和 PyPI。
- 模块仍分离，没有把所有逻辑塞进一个文件。

重新评估 React 或 FastAPI 的触发条件：

- 页面出现大量复用组件和复杂交互状态。
- 后端出现复杂参数校验、开放接口或多人协作开发。
- 目标机依赖下载链路稳定。

当前没有这些触发条件，因此不为面试演示恢复框架复杂度。

## 5. 代码模块与唯一权威

### 5.1 `apps/api/app/config.py`

负责：

- 读取环境变量。
- 固定普通模型为 `deepseek-v4-flash`。
- 固定 thinking enabled 的 effort。
- 校验 V0.5.0—V0.5.5 不允许普通路径换成其他模型。

### 5.2 `apps/api/app/db.py`

是以下事实的唯一数据访问模块：

- Workspace 和 Active Release。
- Release。
- Conversation 和 Message。
- Run。
- TraceEvent。
- CloudCallSnap。
- BadcaseCandidate 最小数据记录。

数据库使用 SQLite WAL。

当前迁移策略：

- `schema_migrations` 表。
- 一份初始化迁移。
- 没有为一次初始化引入 Alembic。

### 5.3 `apps/api/app/deepseek.py`

是 DeepSeek 请求和 Usage 解析的唯一权威。

每次请求固定：

- Provider：DeepSeek。
- Model：`deepseek-v4-flash`。
- `thinking.type=enabled`。
- `reasoning_effort=high`。
- 流式调用设置 `stream_options.include_usage=true`。

Adapter 只输出最终 `content`。

`reasoning_content`：

- 不返回页面。
- 不写数据库。
- 不写 Trace。
- 不写日志。

成本使用 2026-07-20 读取的官方单价快照：

- V4-Flash 缓存命中输入：0.0028 USD／百万 Token。
- V4-Flash 缓存未命中输入：0.14 USD／百万 Token。
- V4-Flash 输出：0.28 USD／百万 Token。

页面人民币口径：

- 固定演示汇率：`1 USD = 7.20 CNY`。
- 新 Snap 保存换算后的 CNY 单价、官方 USD 原价和汇率快照。
- 新 Run 的 `estimated_cost` 按 Snap 快照币种计算；API 明确输出 `estimated_cost_cny`。
- 修复前的历史 USD Snap 不改写，API 只读生成 CNY 兼容展示字段。
- 该汇率只用于面试演示对账，不宣称是实时外汇牌价。

单价来源：

- `https://api-docs.deepseek.com/quick_start/pricing/`。

### 5.4 `apps/api/app/runtime.py`

负责一次 Run 的唯一执行流程。

实际顺序：

```text
收到用户消息
→ 读取当时 Active Release
→ 写入用户消息
→ 创建 RUNNING Run
→ 写 run_started
→ 写 user_message_received（完整用户输入）
→ 写 release_pinned
→ V4-Flash Router 调用
→ 解析唯一 RouteDecision
→ 写 agent_selected
→ V4-Flash 主 Agent 流式调用
→ 持续发送 delta
→ 保存主 Agent CloudCallSnap
→ 保存 AI 消息
→ 写 assistant_response_completed（完整客服回答）
→ 聚合 Run 成本
→ 写 done
```

Router 正常输出必须满足：

- `target_agent` 是字符串。
- 只能是当前默认 Release 中的三个 Agent 之一。
- 不允许数组。

Router 云调用失败或结构非法时：

- 使用同一个 Runtime 内的确定性兜底分类。
- 仍然只选择一个 Agent。
- Trace 写 `router_fallback`。
- 不自动改用 V4-Pro。

### 5.5 `apps/api/app/main.py`

负责：

- HTTP 路由。
- JSON 读写。
- SSE Response。
- 静态文件。
- Health。

它不负责 Router 决策、Release 状态和 Usage 计算。

### 5.6 `apps/web/static`

包含：

- `index.html`。
- `styles.css`。
- `app.js`。

前端只调用公开 API，不自行写成本和 Release 事实。

气泡抽屉和平台管理共用同一个 Run 详情渲染函数与 `GET /api/runs/{run_id}`，没有第二套 Trace 或成本计算。

### 5.7 Skill 与 Release 快照

- `skills` 保存可编辑控制面记录和当前版本指针。
- `skill_versions` 每次保存追加不可变正文、内容 Hash 和版本号。
- `release_bindings` 保存 Release、SkillVersion 与垂直 Agent 的绑定快照。
- Candidate 从当前已校验控制面能力生成配置；只创建 Candidate 不切换 Active。
- Runtime 只读取 Run 固定的 Release 配置，写入 `skill_considered` 与 `skill_activated`，并把已发布正文注入对应 Agent Prompt。

### 5.8 `apps/api/tests`

包含十二条标准库 unittest：

- 完整 Usage。
- 缺失 Usage。
- 非法多 Agent。
- 缺失 Usage 时答案继续、成本为 null、创建疑似 Badcase。
- Skill 未发布不进入 Prompt、Candidate 不影响在线、发布后新消息激活。
- 编辑产生不可变新版本且 Active Release 仍保留旧版本。
- 未绑定 Skill 校验失败，正文不执行脚本。
- GitHub URL 规范化与含凭据 URL 拒绝。
- 纯文本 Skill 扫描通过，`scripts/`、可执行权限和脚本扩展名拒绝。
- Git commit、文件清单、扫描结果和来源持久化，不记录临时目录。

### 5.9 `apps/api/app/git_skill_import.py`

- 只接受公开 GitHub HTTPS 仓库或 `/tree/{ref}/{path}` URL。
- 通过 GitHub API 把 ref 固定为 40 位 commit，再下载该 commit 的 tar.gz。
- 压缩包、文件数、目标目录总大小、路径和文件类型都有确定性上限。
- 只手工提取目标路径到随机临时目录，不调用 Git、不执行 Hook、不安装依赖。
- 扫描 `scripts/`、脚本/二进制扩展名、可执行位、非 UTF-8、空字节和明确执行/安装命令。
- 临时目录在成功、拒绝和失败路径均由上下文自动清理。

## 6. Release 实际实现

默认 Release：

- ID：`rel_v055_default`。
- 版本：`V0.5.5-default`。

Candidate：

- 从当前 Active Release 复制不可变配置 JSON。
- 保存版本名、变更说明和创建时间。
- 创建后不影响在线运行。

发布：

- 原 Active Release 变为 Historical。
- Candidate 变为 Active。
- Workspace 的 `active_release_id` 更新。

回滚：

- 使用同一个服务端激活权威。
- 被选择的历史 Release 重新成为 Active。
- 不建设第二套回滚状态机。

Run 固定：

- 每条用户消息创建 Run 时读取一次 Active Release。
- `run.release_id` 之后不变。
- Conversation 不保存永久 release_id。
- 因此旧会话的新消息会使用当时最新 Active Release。

已验证：

- 同一会话旧气泡保留默认 Release。
- 发布后新气泡使用测试 Release。
- 回滚后 Active 恢复默认 Release。

## 7. Router 与三个 Agent

默认 Agent：

### 一般客服

- ID：`general-service`。
- 处理一般咨询、说明和澄清。

### 投诉客服

- ID：`complaint-service`。
- 处理不满、投诉和服务补救沟通。

### 工单处理

- ID：`work-order-service`。
- 识别工单意图。
- 当前没有工单 Tool，因此只说明准备执行的步骤。

真实验收：

- 一般咨询命中一般客服。
- 明确投诉命中投诉客服。
- 工单查询命中工单处理。
- 每个成功 Run 只有一个 agent_selected。

## 8. Usage、成本与异常诚实性

每个 CloudCallSnap 实际保存：

- cloud_call_id。
- run_id。
- phase。
- provider。
- model。
- started／finished。
- latency_ms。
- status。
- prompt_cache_miss_tokens。
- prompt_cache_hit_tokens。
- completion_tokens。
- total_tokens。
- usage_status。
- price_snapshot。
- estimated_cost。
- provider_request_id。
- error_code。

完整性判断：

```text
miss、hit、completion、prompt 都必须是整数
且 prompt = miss + hit
```

只有满足完整性判断才计算 Estimated Cost。

任一次云调用 Usage 不完整时：

- 已生成答案继续返回。
- 缺失 Token 保持 null。
- 对应 Snap 成本为 null。
- Run 总成本也为 null，不能展示部分成本。
- 写 `usage_incomplete` 相关证据。
- 创建 `MODEL_USAGE_INCOMPLETE` 疑似 Badcase。

## 9. 当前 API

健康和工作区：

- `GET /api/health`
- `GET /api/workspace`

Release：

- `GET /api/releases`
- `GET /api/releases/{release_id}`（含 Diff）
- `POST /api/releases/candidates`
- `POST /api/releases/{release_id}/publish`
- `POST /api/releases/{release_id}/rollback`

Skill：

- `GET /api/skills`
- `POST /api/skills`
- `GET /api/skills/{skill_id}`
- `PUT /api/skills/{skill_id}`
- `POST /api/skills/{skill_id}/validate`
- `POST /api/skills/{skill_id}/disable`
- `GET /api/skill-imports`
- `POST /api/skill-imports`

对话：

- `POST /api/chat/stream`
- `GET /api/conversations`
- `GET /api/conversations/{conversation_id}/messages`

Run 与 Trace：

- `GET /api/runs`
- `GET /api/runs/{run_id}`

## 10. 部署实际状态

部署目录：

- `D:\docker\yiai-center`。

持久化目录：

- `D:\docker\yiai-center\data`。

环境配置：

- `.env` 只在目标主机存在，不进入 Git。

环境变量名称：

- `DEEPSEEK_API_KEY`。
- `DEEPSEEK_BASE_URL`。
- `DEEPSEEK_DEFAULT_MODEL`。
- `DEEPSEEK_THINKING_EFFORT`。
- 三个 V4-Flash 单价变量。
- `YIAI_USD_CNY_RATE`，当前固定为 7.20。
- `YIAI_HTTPS_PROXY`。
- `YIAI_WEB_PORT`。

容器联网：

- 直接 TLS 连接在目标机网络中被中断。
- 目标机已有 7890 HTTP 代理可以正常到达 DeepSeek。
- 只给 YIAI Center 容器注入该 HTTPS_PROXY。
- 未修改系统代理和 Immich 容器。

当前状态：

- `yiai-center-api-1`：healthy。
- 首页：HTTP 200。
- SQLite：存在并在容器重建后保留 Run。
- `immich_machine_learning`：running。
- 数据库迁移版本：3；V0.5.7 部署前副本为 `data/yiai-center.sqlite.pre-v057-20260721`。
- Active Release：`V0.5.6-skill-demo`。

## 11. 与产品和架构 Y/N 的对照结论

已实际满足：

- [Y] 领域无关。
- [Y] 三个 TAB，无登录。
- [Y] 每条消息创建 Run。
- [Y] Run 固定当时 Active Release。
- [Y] 旧会话新消息使用最新 Active Release。
- [Y] 历史气泡保持旧 Release。
- [Y] 人工发布和回滚。
- [Y] 唯一 Router。
- [Y] 一个 Run 只选择一个 Agent。
- [Y] V4-Flash 思考模式。
- [Y] 每次云调用独立 Snap。
- [Y] 三类 Token 和 Estimated Cost。
- [Y] 历史对话列表和消息时间戳。
- [Y] AI 气泡右侧 Run 详情抽屉。
- [Y] Trace 保存新 Run 的完整输入和客服回答。
- [Y] 每个云调用 Trace 步骤内显示人民币 Snap 成本，底部汇总 Run。
- [Y] Usage 缺失时不丢答案、不编造数字。
- [N] 没有自动升级 V4-Pro。
- [N] 没有保存隐藏思考内容。
- [N] 没有第二套 Release、Runtime 和成本权威。
- [N] 没有生产级权限、安全和运维平台。

## 12. 当前明确未实现

以下功能仍是产品全局中的后续规划，不是 V0.5.5 已完成功能：

- Agent 配置编辑页面。
- 文本 RAG 和三篇通用长文档。
- 远程只读 MCP。
- 工单真实读写 Tool。
- 写操作确认和幂等回执。
- 人机共驾。
- 疑似 Badcase 页面和人工确认。
- V4-Pro Darwin。
- Evaluation。
- 成本趋势、策略编辑、预警和限制页面。

## 13. 已知历史证据

数据库保留一个 ERROR Run：

- `run_c8a77c0324a2460e9f45b7b46e048372`。

原因：

- 初次部署时容器没有显式 HTTPS_PROXY，访问 DeepSeek 出现 URLError。

Trace 证明：

- Run 和 Release 已固定。
- Router 云调用失败。
- Runtime 使用确定性兜底并只选择一般客服。
- 主 Agent 云调用失败。
- Run 以唯一 error 终态结束。

修复：

- 只给本项目容器增加目标机现有 7890 HTTPS 代理。

修复后：

- 原有 4 条真实 Run DONE，后续手动体验与本轮自测继续追加真实 Run。
- 本轮代表 Run `run_4e283b75bca3456cbd436bf2c5d93bf3` 为 DONE，包含 2 个 V4-Flash CloudCallSnap、完整输入事件和完整回答事件。
- 本轮部署后共有 9 条 Run 和 8 个 Conversation，历史记录均保留。

该 ERROR Run 不删除，用于展示真实 Trace 和问题闭环。

## 14. V0.5.6 代表证据

- Skill：`skill_029d70e05b8146b68eed17a1107e8845`。
- SkillVersion：`skillv_e14783966d0f49ef80dc354faa367082`。
- Candidate／当前 Active Release：`rel_9194ba42cc254102b6f46017908f92ca`／`V0.5.6-skill-demo`。
- 发布前 Run：`run_dfe0fa51b40940a187d6fa66ab160267`，无 Skill 激活。
- 发布后同会话 Run：`run_80e84830fb3b455b839869a6f9a962af`，Trace 固定上述 SkillVersion，回答遵循正文，2 个真实 V4-Flash Snap，总成本 `0.000797328 CNY`。

## 15. V0.5.7 代表证据

- 成功 Attempt：`skillimport_03a7261643c0408cab42be7864c70fe8`；固定 commit `3d8c60c85732e32b618521a8f0ff6ff25666297b`；仅 `SKILL.md`；结果为未绑定 Draft。
- 拒绝 Attempt：`skillimport_486b00b9068b40b9b2849e4ca512d5a8`；同一 commit；因 `scripts/check.py` 被拒绝。
- 外部读取使用公开 GitHub，不传 Git Token；服务日志、Trace 和数据库均不含凭据和临时目录。

## 16. 下一版本如何继续

开始 V0.5.8 前：

1. 产品负责人先完成 04 文档的三条手动体验。
2. 修复任何阻塞 V0.5.5 演示的问题。
3. 重新阅读 01—05。
4. 在 03 中填写 V0.5.8 开工卡。
5. 先验证目标主机可用的真实本地 Embedding，再实现 FTS5、向量和混合检索。
