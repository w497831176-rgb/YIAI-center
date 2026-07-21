# YIAI Center 测试用例与自测记录

> 当前版本：V0.5.6  
> 文档性质：Living Test Doc（动态测试记忆）  
> 当前状态：自动自测已完成；产品负责人手动页面体验待执行  
> 用途：随每个版本维护测试范围、预期、实际结果和证据  
> 配套文档：01 产品全局、02 架构全局、03 版本规划、05 实际实现说明。

## 0. 使用规则

- 本文件不是一次性测试报告；版本范围或实现发生变化时同步更新。
- 测试用例可以根据真实风险增加、拆分、合并或删除，但不能为了“全部通过”删除失败证据。
- 只有实际执行并取得证据的用例可以标记“通过”。
- 未实际执行的页面体验必须写“待产品负责人手动验证”，不能用代码检查冒充视觉验收。
- 这是面试演示项目，不建设 Playwright、浏览器容器和大型自动化测试工程。
- 自动自测重点覆盖最容易做错且能由后端证明的契约：Release 固定、单一垂直 Agent、Trace 终态、Usage、成本和数据持久化。
- 每次开发结束后，先更新本文件，再更新 05 实际实现说明。

## 1. 本次测试环境

- 初始执行日期：2026-07-20；同版本纠偏回归：2026-07-21。
- 目标主机：局域网 Windows 10 专业版。
- CPU：Intel Core i7-14700K，20 核、28 逻辑处理器。
- 内存：约 64 GB。
- Docker Desktop：4.73.1。
- Docker Engine：29.4.3。
- Docker Compose：5.1.3。
- Compose project：`yiai-center`。
- 应用容器：`yiai-center-api-1`。
- 访问端口：19080。
- 数据文件：`D:\docker\yiai-center\data\yiai-center.sqlite`。
- 模型：`deepseek-v4-flash`。
- 模型模式：thinking enabled，reasoning effort high。
- GitHub 核心实现提交：`e47ca3f`；Living Docs 在后续提交持续同步。

## 2. 状态定义

- 通过：实际结果符合预期，有输出、数据库、Trace 或容器状态证据。
- 失败：实际结果不符合预期，保留失败原因和对应 Run。
- 阻塞：外部依赖使测试无法继续，且没有安全的替代验证。
- 待手动：必须由产品负责人在浏览器中体验，Codex 不代替判断。
- 不适用：当前版本明确不实现的能力。

## 3. V0.5.0 文档基线

### TC-050-01 五份文档视角分离

目的：

- 确认产品、架构、路线图、测试和实际实现各自回答不同问题。

预期：

- 01 只做产品 Y/N。
- 02 只做架构与后端 Y/N。
- 03 只做版本拆解与状态。
- 04 只做测试用例与真实结果。
- 05 只说明实际怎样实现及与规划的差异。

实际：

- 五份 Markdown 已按上述视角建立。
- 五份文档均声明为动态工作记忆，不是不可变钢筋标尺。

状态：通过。

### TC-050-02 文档版本一致

预期：

- 五份文档内部当前版本均为 V0.5.5。

实际：

- Markdown 已统一到 V0.5.5。
- Word 在本轮收尾时重新生成。

状态：通过。

## 4. V0.5.1 主机与 DeepSeek Gate

### TC-051-01 目标主机只读检查

步骤：

1. 读取操作系统、CPU、内存、磁盘。
2. 读取 Docker、Compose、现有容器和监听端口。
3. 不停止、不重启、不修改现有容器。

预期：

- 资源足够运行独立演示项目。
- 19080 未占用。
- 现有 Immich 容器不受影响。

实际：

- 主机资源足够。
- 19080 检查时未占用。
- 当时只有 `immich_machine_learning` 在运行并占用 3333。

状态：通过。

### TC-051-02 DeepSeek 非流式三类 Usage

步骤：

- 在目标主机直接调用 `deepseek-v4-flash`。
- 显式开启 thinking 并设置 reasoning effort high。
- 只记录模型、回答长度、三类 Token 和等式结果，不输出思考内容。

预期：

- 返回缓存未命中输入、缓存命中输入和输出 Token。
- `prompt_tokens = miss + hit`。

实际：

- miss：13。
- hit：0。
- completion：38。
- prompt：13。
- 等式成立。

状态：通过。

### TC-051-03 DeepSeek 流式最终 Usage

步骤：

- 使用 SSE 流式调用并设置 `stream_options.include_usage=true`。

预期：

- 最终 Usage chunk 返回三类 Token。
- 回答内容与 Usage 都能取得。

实际：

- miss：13。
- hit：0。
- completion：40。
- prompt：13。
- 等式成立。

状态：通过。

### TC-051-04 模型策略

预期：

- V0.5.0—V0.5.5 不调用 V4-Pro。
- 思考内容不进入页面、数据库和 Trace。

实际：

- 4 条成功 Run 共 8 个 CloudCallSnap，模型全部为 `deepseek-v4-flash`。
- 代码只读取并输出 `content`；`reasoning_content` 被明确忽略。
- Health 返回 `expert_model_enabled_workflows=[]`。

状态：通过。

## 5. V0.5.2 应用骨架与三个 TAB

### TC-052-01 零依赖镜像构建

预期：

- 使用目标机已有 Python 3.12 镜像完成构建。
- 构建不需要 Node、Nginx 和第三方 Python 包。

实际：

- 镜像 `yiai-center-api` 构建成功。
- Python `compileall` 通过。

状态：通过。

### TC-052-02 四条契约单元测试

实际执行：

- 完整 Usage 解析与成本计算。
- 缺失 Usage 不补零、不伪造成本。
- 多 Agent 数组输出被拒绝。
- Usage 缺失时答案继续返回、Run 成本为 null、生成疑似 Badcase。
- 人民币价格快照、历史 USD Snap 兼容换算、历史对话聚合和 Trace 输入／回答证据。

实际：

- 4 条 unittest 全部通过。
- 2026-07-21 回归总耗时约 0.197 秒。

状态：通过。

### TC-052-03 健康检查与容器状态

预期：

- `/api/health` 返回真实数据库和模型配置状态。
- 容器最终为 healthy。

实际：

- Health：ok。
- Database：ok。
- DeepSeek configured：true。
- Default model：deepseek-v4-flash。
- Thinking：enabled／high。
- 容器：healthy。

状态：通过。

### TC-052-04 首页和三个 TAB 结构

预期：

- 首页 HTTP 200。
- 静态页面包含用户、员工、平台管理三个 TAB。
- 不出现登录和身份切换入口。

实际：

- 首页 HTTP 200。
- 已部署 `app.js` 包含用户、员工、平台管理三个顶层 TAB。
- 静态代码包含 Release 和 CloudCallSnap 页面入口。

状态：通过（结构和服务）；视觉与交互体验待产品负责人手动验证。

### TC-052-05 SQLite 持久化

步骤：

1. 先产生真实 Run。
2. 重建应用镜像并重建容器。
3. 再读取 Run 列表和 SQLite 文件。

预期：

- 数据不因容器重建丢失。

实际：

- SQLite 文件存在，大小 110592 字节。
- 容器重建后仍保留 5 条真实 Run。

状态：通过。

## 6. V0.5.3 Release、Run 与 Trace

### TC-053-01 同一旧会话发布前后 Release

测试会话：

- `conv_58a164fdaf824077a71c23f0cdbd3b2b`。

步骤：

1. 在 `V0.5.5-default` 下完成第一轮对话。
2. 创建并发布 `V0.5.5-release-smoke-b`。
3. 在同一旧会话继续发送一条新消息。
4. 读取四条消息的 release_version。

预期：

- 前两条旧气泡保持默认 Release。
- 后两条新气泡使用新 Active Release。

实际：

- 消息 Release 顺序：
  - `V0.5.5-default`。
  - `V0.5.5-default`。
  - `V0.5.5-release-smoke-b`。
  - `V0.5.5-release-smoke-b`。

状态：通过。

### TC-053-02 人工回滚

步骤：

- 将 Active Release 从测试候选回滚到默认 Release。

预期：

- 回滚只影响下一条新消息，不改写历史气泡。

实际：

- Active Release 已恢复为 `V0.5.5-default`。
- 历史测试 Run 仍保留 `V0.5.5-release-smoke-b`。

状态：通过。

### TC-053-03 Trace 唯一终态

预期：

- 每个 Run 恰好一个 done 或 error。

实际：

- 5 条历史 Run 的 terminal 数量均为 1。
- 4 条为 DONE，1 条为 ERROR。

状态：通过。

### TC-053-04 失败证据不删除

实际：

- 保留代理配置修复前的 ERROR Run：
  `run_c8a77c0324a2460e9f45b7b46e048372`。
- 该 Run 的 Trace 记录 Router 外部调用失败、确定性兜底路由、单一垂直 Agent 和最终 URLError。
- 没有为了“全绿”删除数据库记录。

状态：通过。

## 7. V0.5.4 DeepSeek、SSE、Usage 与成本

### TC-054-01 真实 SSE 闭环

代表 Run：

- `run_bf042f987a964d4eacb04bf677591020`。

预期：

- SSE 包含 run_started、route_decision、agent_selected、delta 和 done。
- 回答真实来自 DeepSeek。

实际：

- Run 状态 DONE。
- Release 为 `V0.5.5-default`。
- Agent 为 `general-service`。
- CloudCallSnap 数量为 2。

状态：通过。

### TC-054-02 逐次 CloudCallSnap

预期：

- Router 和主 Agent 各保存一个 Snap。
- 每个 Snap 独立保存模型、延迟、三类 Token、单价和成本。

实际：

- 4 条成功 Run 每条均为 2 个 CloudCallSnap。
- 共 8 个成功 Snap，模型全部为 V4-Flash。
- 所有成功 Snap 的 usage_status 均为 COMPLETE。

状态：通过。

### TC-054-03 Estimated Cost

代表结果：

- `run_bf042f987a964d4eacb04bf677591020` 的 Run Estimated Cost 为 0.00015442 USD。
- 该历史 USD 事实保持不变；按固定演示汇率 7.20 的页面兼容展示为 0.001111824 CNY。

预期：

- 按缓存未命中输入、缓存命中输入、输出三种单价分别计算。
- Run 成本来自 Snap 聚合。

实际：

- 成本由 Provider Token 与单价快照计算。
- 页面不使用字符数估算。
- 新 Snap 直接保存 CNY 单价、官方 USD 原价和 7.20 汇率快照；旧 USD Snap 只读换算展示，不回写原始事实。

状态：通过。

### TC-054-04 Usage 缺失兜底

步骤：

- 使用 Fake Adapter 模拟主 Agent 已返回“答案仍然返回”，但最终 Usage 缺失。

预期：

- 答案仍进入 SSE 和消息历史。
- 三类 Token 为 null。
- 主调用 estimated_cost 为 null。
- Run 总成本为 null，不能只显示 Router 的部分成本。
- 自动生成疑似 Badcase。

实际：

- 上述五项均由 unittest 验证通过。

状态：通过。

## 8. V0.5.5 唯一 Router 与单 Agent

### TC-055-01 一般咨询

- 输入：请简单介绍你能做什么。
- Run：`run_bf042f987a964d4eacb04bf677591020`。
- 实际 Agent：`general-service`。
- agent_selected 次数：1。

状态：通过。

### TC-055-02 投诉

- 输入：我要投诉，刚才的服务体验太差了。
- Run：`run_361b93eb9d11479b87fef99e809c6fd6`。
- 实际 Agent：`complaint-service`。
- agent_selected 次数：1。

状态：通过。

### TC-055-03 工单意图

- 输入：请查询我的工单进度。
- Run：`run_25c70909fdb44cd2ab6534f3403e3554`。
- 实际 Agent：`work-order-service`。
- agent_selected 次数：1。

状态：通过。

### TC-055-04 非法多 Agent 输出

预期：

- `target_agent` 是数组或不在当前 Release 的 Agent 集合中时，契约拒绝。

实际：

- 多 Agent 数组测试抛出 ValueError。
- Runtime 使用唯一确定性兜底，不串行尝试多个 Agent。

状态：通过。

### TC-055-05 历史对话列表

预期：

- `GET /api/conversations` 返回真实 Conversation。
- 每项包含标题、创建时间、最近消息时间和消息数。
- 页面点击历史项后读取原消息，不生成新 Run。

实际：

- 部署后接口返回 8 个历史对话。
- 首项字段实际包含 `id`、`title`、`created_at`、`updated_at` 和 `message_count`。
- 已部署前端只在用户主动发送新消息时调用 `/api/chat/stream`；历史选择只读取消息接口。

状态：通过（API 和静态交互结构）；视觉体验待产品负责人手动验证。

### TC-055-06 消息时间戳与气泡 Run 入口

预期：

- 用户消息和 AI 回答均显示消息时间。
- AI 气泡下方显示 Run 状态、垂直 Agent、Release 和 Run 详情入口。
- 点击后从右侧打开抽屉，并复用权威 Run 详情 API。

实际：

- 消息接口返回 `created_at`、`run_id`、`run_status`、`release_version` 和 `agent_name`。
- 已部署 `app.js` 包含时间格式化、`data-message-run-id` 和 `/api/runs/{run_id}` 调用。
- 已部署 CSS 包含右侧 `.run-drawer`。
- 页面名称已经使用“垂直 Agent”，没有“唯一 Agent”展示文案。

状态：通过（数据与静态结构）；抽屉视觉和点击体验待产品负责人手动验证。

### TC-055-07 Trace 步骤内人民币 CloudCallSnap

预期：

- 每个 `cloud_call_completed` 通过 `cloud_call_id` 关联一个 CloudCallSnap。
- Snap 在对应 Trace 步骤中显示人民币单价、三类 Token、延迟和本步成本。
- Trace 最底部汇总整个 Run 的调用次数、Token、延迟和人民币成本。

实际：

- 新真实 Run `run_4e283b75bca3456cbd436bf2c5d93bf3` 有 2 个 CloudCallSnap。
- 两个 Snap 均返回 `estimated_cost_cny` 和 CNY 单价快照。
- Run 人民币汇总成本为 `0.000732816 CNY`，等于两个 Snap 人民币成本之和。
- 已部署前端按 `cloud_call_id` 把 Snap 嵌入 `cloud_call_completed`，底部单独渲染 Run 汇总。

状态：通过。

### TC-055-08 Trace 输入与客服回答

预期：

- 新 Run 的 Trace 包含完整用户输入。
- 成功 Run 的 Trace 包含完整客服最终回答和垂直 Agent。
- 历史 Run 不补写事件，而是从已保存消息回显输入和回答。

实际：

- 新真实 Run 的事件顺序包含：
  `run_started → user_message_received → release_pinned → … → assistant_response_completed → done`。
- `user_message_received` 内容与实际输入一致。
- `assistant_response_completed` 内容与消息表最终回答一致，回答长度 47 字符。
- 修复前历史 Run 的 `messages.input` 和 `messages.output` 均可读取；历史事件数组没有被改写。

状态：通过。

### TC-055-09 同版本部署回归

实际：

- `app.js` 语法检查通过，共 696 行。
- Python compileall 通过。
- 4 条 unittest 通过。
- `/api/health` 返回 `ok / V0.5.5`。
- 当前数据库有 9 条 Run、8 个 Conversation，未清空历史数据。
- `yiai-center-api-1` 为 `running/healthy`。
- `immich_machine_learning` 仍为 `running`。

状态：通过。

## 9. V0.5.6 自然语言 Skill

### TC-056-01 前向迁移与历史数据

- 预期：第二次真实表结构变更通过前向迁移完成，不删除 SQLite。
- 实际：迁移版本从 1 升到 2；部署前复制 `yiai-center.sqlite.pre-v056-20260721`；迁移后仍保留 9 条历史 Run、8 个 Conversation。
- 状态：通过。

### TC-056-02 Draft、校验、绑定与不可变版本

- 实际：创建 Skill 后为 Draft；绑定一般客服并校验后为 VALIDATED；保存修改会创建新 SkillVersion，已发布版本不原地覆盖；未绑定 Skill 校验失败。
- 证据：7 条 unittest 中 3 条为 Skill 专项契约测试。
- 状态：通过。

### TC-056-03 Candidate 不影响在线与 Release Diff

- 实际：Candidate `rel_9194ba42cc254102b6f46017908f92ca` 创建后 Active 仍为 `V0.5.5-default`；Diff 新增 `skillv_e14783966d0f49ef80dc354faa367082`。
- 状态：通过。

### TC-056-04 发布前后真实 Run

- 发布前：`run_dfe0fa51b40940a187d6fa66ab160267`，没有 `skill_activated`。
- 发布后：同一会话 `run_80e84830fb3b455b839869a6f9a962af`，Release 为 `V0.5.6-skill-demo`，Trace 含 `skill_considered → skill_activated`。
- 回答证据：第一行真实以“结论先行：”开头。
- 模型证据：2 个 V4-Flash CloudCallSnap，人民币总成本 `0.000797328`。
- 状态：通过。

### TC-056-05 页面与脚本边界

- 实际：平台管理新增 Skill 页面，可查看完整正文、编辑、校验、停用和绑定；正文只作为 Prompt 文本注入，不存在脚本执行入口。
- 状态：数据契约与静态结构通过；视觉和点击体验待产品负责人手动验证。

## 10. 部署隔离与 Git

### TC-DEP-01 不影响现有容器

实际：

- YIAI Center 使用独立 Compose project、网络、目录、容器和 19080 端口。
- `immich_machine_learning` 最终状态仍为 running。

状态：通过。

### TC-DEP-02 密钥不进入 Git

步骤：

1. 扫描可提交源码中的 DeepSeek Key、Git Token 和 SSH 密码特征。
2. 使用 Git ignore 检查 `.env` 和 `data/`。
3. 推送后检查工作区状态。

实际：

- 可提交源码扫描无命中。
- `.env` 和 `data/` 被 `.gitignore` 排除。
- Git `main` 与 `origin/main` 同步。

状态：通过。

## 11. 待产品负责人手动验证

### MANUAL-01 三个 TAB 视觉与切换

步骤：

1. 打开 `http://192.168.50.232:19080`。
2. 依次点击用户、员工、平台管理。
3. 确认没有登录、身份切换和行业迹象。

状态：待手动。

### MANUAL-02 流式对话体验

步骤：

1. 在用户 TAB 分别输入一般咨询、投诉和工单问题。
2. 观察回答是否持续生成。
3. 确认用户消息和 AI 回答都有时间戳。
4. 点击 AI 气泡下方“查看 Run 详情”。
5. 确认右侧抽屉展示输入、客服回答、完整 Trace、逐步人民币成本和底部汇总。

状态：待手动。

### MANUAL-03 Release 与 Trace 页面体验

步骤：

1. 在平台管理创建一个候选 Release。
2. 确认创建候选后 Active Release 不变。
3. 人工发布并在用户 TAB 发送新消息。
4. 返回 Run 与 Trace，确认 CloudCallSnap 位于对应云调用 Trace 步骤内。
5. 回滚到需要的历史 Release。

状态：待手动。

## 12. 当前已知问题与说明

- 目标机 Docker Hub 和 PyPI 经现有代理时连接不稳定，因此最终实现主动取消 Node、Nginx、FastAPI 等外部下载依赖。
- 容器访问 DeepSeek 需要使用目标机现有的 7890 HTTPS 代理；该配置只写在本项目 `.env`，未修改系统和其他容器。
- 数据库中保留一次代理修复前的真实 ERROR Run，这是 Trace 和失败治理证据，不是待删除脏数据。
- V0.5.5 没有真实 Skill、RAG、MCP、工单写入、人机共驾、Badcase 页面和成本控制页面；对应测试在后续版本新增。
- UI 没有经过 Codex 浏览器自动化；这是当前演示项目明确的测试边界。

## 13. V0.5.6 自测结论

- V0.5.0—V0.5.6 的后端契约、部署闭环和真实 DeepSeek 主路径通过。
- 当前容器 healthy，Active Release 为 `V0.5.6-skill-demo`。
- 可以交给产品负责人进行浏览器手动体验。
- 手动体验通过前，不把 UI 视觉和交互标记为最终验收完成。
