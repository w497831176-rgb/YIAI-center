# YIAI Center 小步迭代版本规划

> 当前版本：V0.5.6  
> 文档视角：产品交付与开发拆解  
> 文档性质：Living Roadmap（动态路线图），不是固定排期承诺  
> 用途：把产品全局 Y/N 和架构全局 Y/N 拆成小功能、小版本和真实验收  
> 状态原则：只有已经得到真实证据的功能才能标记完成  
> 配套文档：01 产品全局 Y/N、02 架构全局 Y/N、04 测试用例与自测记录、05 实际实现说明。

## 0. 五份文档如何协作

每次开发开始前按顺序阅读：

1. 产品全局 Y/N：确认产品做什么、不做什么。
2. 架构全局 Y/N：确认技术必须怎样做、哪些是红线。
3. 版本规划：确认本次只做哪一个小切片。
4. 测试用例与自测记录：确认本版本如何验收、哪些历史问题要回归。
5. 实际实现说明：确认当前代码事实上怎样运行，避免只按规划猜实现。

每次开发结束后：

1. 把真实验收结果写入本文件。
2. 若产品规则变化，先更新产品全局。
3. 若技术权威、契约或模块边界变化，先更新架构全局。
4. 五份文档统一升级为同一个 V0.5.x 版本。
5. 重新生成五份 Word。
6. 没有真实证据时只能标记“进行中”或“阻塞”，不能标记“完成”。

动态调整规则：

- 后续版本编号和顺序是当前规划，不是固定承诺。
- 可以根据验证结果拆分、合并、重排、延期或取消后续小版本。
- 当前只强约束“正在做的版本”和“紧接着的下一个版本”。
- 规划变化时先说明原因，再同步更新产品全局、架构全局和本文件。
- 不为了保持旧路线图而继续开发已经失去价值或被证伪的功能。

## 1. 版本号规则

- `V0.5.0`：三份规划基线。
- `V0.5.1` 至 `V0.5.n`：每完成一个小功能切片递增一次。
- 产品范围或架构方向发生明显变化时进入 `V0.6.0`，不继续堆补丁号。
- 五份文档的版本号必须一致。
- 本文件中列出的 V0.5.1—V0.5.17 是当前建议拆解，允许动态变化。

## 2. 每个小版本的固定开工卡

开发前必须填写：

```text
目标版本：
当前五份文档版本：
本次只完成：
对应产品 Y/N：
对应架构 Y/N：
允许修改：
必须保持：
真实验收：
停止条件：
```

通用停止条件：

- 同一故障连续两次尝试没有新增证据时停止碰运气。
- 需要突破任意全局 `[N]` 时停止编码，请产品负责人确认。
- 需要同时修改三个以上权威模块时停止，先重新拆分。
- 外部依赖缺失时报告单一阻塞点，不用假数据继续。

## 3. 当前总状态

- V0.5.0 三份全局文档基线：已确认并完成。
- V0.5.1—V0.5.6：已完成实现、部署和后端自测；V0.5.6 增加自然语言 Skill 的完整发布闭环。
- 产品代码：已推送到 GitHub `main`；核心实现提交为 `e47ca3f`，Living Docs 在后续提交持续同步。
- Windows 10 Docker 主机：只读检查完成；独立 Compose `yiai-center` 已部署。
- DeepSeek API：V4-Flash 非流式、流式和真实运行 Gate 已通过。
- 当前访问地址：`http://192.168.50.232:19080`。
- 当前 Active Release：`V0.5.6-skill-demo`。
- 远程只读 MCP Server：等待产品负责人提供或选择。
- 三篇通用 RAG 长文档：等待后续专门版本编写。

### 3.1 当前批次和演示边界

- 当前授权批次为 V0.5.0—V0.5.5：文档基线、主机 Gate、三个 TAB、Release／Run／Trace、DeepSeek 对话和唯一 Router。
- 当前批次可以连续实现和自测，不要求每个补丁版本都停下来等待人工确认。
- 全局普通模型为 `deepseek-v4-flash`，开启思考模式。
- 只有显式高级专家工作流允许使用 `deepseek-v4-pro`；首个规划场景是 V0.5.15 Badcase AI Darwin。
- V0.5.0—V0.5.5 不调用 `deepseek-v4-pro`。
- 本项目不建设生产级安全运维、高可用、容灾、监控平台和复杂发布工程。
- 只保留密钥不入 Git、不误删 SQLite／Volume、业务写入确认和幂等这些最小边界。

## 4. V0.5.0——三份全局文档

目标：

- 建立产品、架构和迭代三个不同视角的持续约束。

产品 Y/N：

- [Y] 产品全局只描述产品行为、页面、业务规则和验收。
- [N] 产品全局不混入数据库、接口和代码实现。

架构 Y/N：

- [Y] 架构全局描述唯一权威、契约、状态、数据和技术红线。
- [N] 架构全局不替产品负责人决定页面和业务范围。

验收证据：

- 三份 Markdown。
- 三份可编辑 Word。
- 三份文件版本一致。
- 用户确认分层正确。

当前状态：已完成（2026-07-20）。

真实证据：

- 三份 Markdown 和 Word 已建立。
- 产品负责人确认分层正确；后续扩展为五份文档，并确认它们都是动态工作记忆。

完成后版本：V0.5.0。

## 5. V0.5.1——目标主机只读检查与 DeepSeek Usage Gate

本次只完成：

- 目标主机环境事实。
- DeepSeek 一次普通调用和一次流式调用。
- 三类 Token Usage 证据。
- `deepseek-v4-flash` 思考模式请求与响应证据。

产品 Y/N：

- [Y] 已生成答案可以正常展示。
- [Y] 每次模型调用能够获得缓存未命中输入、缓存命中输入和输出 Token。
- [N] 不伪造 Usage。

架构 Y/N：

- [Y] 只读检查 Docker、WSL2、CPU、内存、磁盘、端口和网络。
- [Y] 流式调用使用 `include_usage`。
- [Y] 请求显式设置 `thinking.type=enabled` 和 `reasoning_effort=high`。
- [Y] 保存 Provider 原始 Usage 样例。
- [N] 不安装正式应用。
- [N] 不修改既有容器。

真实验收：

- 主机事实记录。
- DeepSeek 非流式响应。
- DeepSeek 流式最终 usage chunk。
- 三类 Token 等式校验。

不在本版本：

- 页面。
- Router。
- RAG。
- MCP。
- 工单。

当前状态：已完成（2026-07-20）。

真实证据：

- 目标机为 Windows 10 专业版、Docker Desktop 4.73.1、Docker Engine 29.4.3、Compose 5.1.3。
- 非流式 Gate：三类 Token 均返回，输入 Token 等式成立。
- 流式 Gate：最终 Usage chunk 返回三类 Token，输入 Token 等式成立。
- 两次 Gate 均为 `deepseek-v4-flash`，思考模式实际返回 reasoning_content，但系统未保存其内容。

## 6. V0.5.2——应用骨架与三个 TAB

本次只完成：

- Web、API、SQLite 和 Compose 骨架。
- 用户、员工、平台管理三个顶层 TAB。
- 健康检查。

产品 Y/N：

- [Y] 三个 TAB 无登录直接切换。
- [N] 不出现身份切换和权限页面。
- [N] 不出现行业迹象。

架构 Y/N：

- [Y] 模块化单体。
- [Y] 独立 Compose project、端口和持久化目录。
- [Y] SQLite WAL 和迁移。
- [N] 不实现业务功能。

真实验收：

- 三个 TAB 可打开。
- `/api/health` 返回真实依赖状态。
- 容器重启后 SQLite 文件仍存在。

当前状态：已完成（2026-07-20）。

真实证据：

- `yiai-center-api-1` 容器 healthy。
- 首页 HTTP 200，静态代码包含用户、员工、平台管理三个 TAB。
- `/api/health` 返回数据库、DeepSeek 配置、默认模型和思考模式真实状态。
- 容器重建后 SQLite 仍存在，5 条真实 Run 保留。

## 7. V0.5.3——Release、Run 和 Trace 骨架

本次只完成：

- Workspace Active Release。
- 不可变 Release。
- 每条消息创建 Run。
- 基础 Trace 终态。

产品 Y/N：

- [Y] 发布影响之后的新消息。
- [Y] 旧会话新消息使用新 Release。
- [Y] 旧气泡保持旧 Release。

架构 Y/N：

- [Y] Run 启动固定 release_id。
- [Y] conversation 不永久固定 Release。
- [Y] Trace 只追加并结束于 done 或 error。
- [N] 不接入 Agent 和模型。

真实验收：

- Release A 下创建 Run A。
- 发布 Release B。
- 同一旧会话的新消息创建 Run B 并固定 Release B。
- Run A 的历史记录仍是 Release A。

当前状态：已完成（2026-07-20）。

真实证据：

- 同一旧会话前两条气泡保持 `V0.5.5-default`。
- 发布 `V0.5.5-release-smoke-b` 后，同一会话新增两条气泡使用新 Release。
- 回滚后 Active Release 恢复为 `V0.5.5-default`。
- 所有历史 Run 的 Trace 都只有一个 done 或 error 终态。

## 8. V0.5.4——DeepSeek 对话与逐次 CloudCallSnap

本次只完成：

- 一次真实 AI 对话。
- SSE。
- 每次 DeepSeek 调用独立 Snap。
- 基础 Estimated Cost。
- 所有调用固定使用 `deepseek-v4-flash` 思考模式。

产品 Y/N：

- [Y] 用户看到真实流式回答。
- [Y] 本轮运行卡显示三类 Token、延迟和 Estimated Cost。
- [Y] Usage 异常时答案继续显示并明确标错。

架构 Y/N：

- [Y] 统一 DeepSeek Adapter。
- [Y] 每次调用保存 CloudCallSnap。
- [Y] 缺失 Usage 保持 null并创建 Candidate。
- [N] 不用字符估算冒充 Provider Usage。

真实验收：

- 一条真实消息的 SSE。
- 对应 CloudCallSnap。
- 三类 Token 和费用计算。
- 模拟 Usage 缺失时答案仍返回、字段为 null。

当前状态：已完成（2026-07-20）。

真实证据：

- 4 条真实 DONE Run 均通过 SSE 返回答案。
- 每条成功 Run 各有 Router 和主 Agent 两个 CloudCallSnap。
- 所有真实 CloudCallSnap 都返回三类 Token，Usage 状态为 COMPLETE。
- Run 卡和 Trace 可查看延迟、单价快照和 Estimated Cost。
- 自动测试证明 Usage 缺失时答案仍返回、缺失字段与 Run 总成本为 null，并生成疑似 Badcase。

## 9. V0.5.5——唯一 Router 与单 Agent

本次只完成：

- 唯一 Router。
- 三个默认垂直 Agent。
- 一个 Run 只能选择一个 Agent。

产品 Y/N：

- [Y] 普通咨询、投诉和工单请求命中不同 Agent。
- [Y] 低置信度时澄清或建议人工。
- [N] 不做多 Agent 协作。

架构 Y/N：

- [Y] RouteDecision 结构化。
- [Y] target_agent 最多一个。
- [Y] Router 只选择当前 Release 中的 Agent。

真实验收：

- 三条真实请求的 route_decision。
- 每条只有一个 agent_selected。
- 非法多 Agent 输出被契约拒绝。

当前状态：已完成（2026-07-20）。

真实证据：

- 一般咨询命中 `general-service`。
- 明确投诉命中 `complaint-service`。
- 工单查询命中 `work-order-service`。
- 4 条成功 Run 的 `agent_selected` 均恰好一次。
- 契约测试证明数组形式的多 Agent 输出会被拒绝。

### 9.1 V0.5.5 同版本体验与证据链纠偏

版本处理：

- 不创建 V0.5.6，不改变 Active Release `V0.5.5-default`。
- 这是产品负责人手动体验 V0.5.5 后发现的阻塞问题修复，仍归入 V0.5.5。

本次只完成：

- 用户页面增加历史对话列表和最近消息时间。
- 所有消息气泡增加时间戳。
- AI 气泡下方增加 Run 状态、垂直 Agent、Release 和 Run 详情入口。
- Run 详情从气泡右侧抽屉打开。
- Trace 增加用户输入与客服最终回答事件。
- 每个云调用 Snap 嵌入对应 Trace 步骤，人民币显示该步成本。
- Trace 底部增加 Run 人民币成本与 Usage 汇总。
- 页面显示名由“唯一 Agent”统一改为“垂直 Agent”，单 Agent 约束不变。

产品 Y/N：

- [Y] 历史对话可恢复。
- [Y] 时间、输入、回答和 Run 证据可见。
- [Y] 价格和成本统一以人民币展示。
- [N] 不借此提前实现 Skill、RAG、MCP、工单、人机共驾或成本策略页面。

架构 Y/N：

- [Y] 气泡抽屉与平台管理复用 `GET /api/runs/{run_id}`。
- [Y] 新 Run 追加 `user_message_received` 与 `assistant_response_completed`。
- [Y] 历史 Run 只从消息事实回显输入／输出，不补写历史 Trace。
- [Y] 官方 USD 原价、7.20 固定演示汇率和人民币单价进入新 Snap 快照。
- [Y] 旧 USD Snap 通过只读兼容字段显示人民币，不修改原始记录。

真实验收：

- 4 条标准库 unittest 全部通过。
- `app.js` 语法检查通过。
- 目标容器重建后为 healthy，Immich 容器仍为 running。
- `GET /api/conversations` 返回历史会话标题、创建时间、最近消息时间和消息数。
- 历史 Run 能从既有消息记录回显输入和客服回答，并把旧 USD Snap 转为人民币展示字段。
- 新真实 Run `run_4e283b75bca3456cbd436bf2c5d93bf3` 状态 DONE，Trace 包含输入与客服回答，两个 CloudCallSnap 均有人民币成本，Run 汇总成本为 `0.000732816 CNY`。

当前状态：后端、部署与静态结构自测通过；浏览器视觉和抽屉交互待产品负责人手动体验。

## 10. V0.5.6——自然语言 Skill 编辑与发布

本次只完成：

- 页面创建、编辑、校验、绑定和发布自然语言 Skill。

产品 Y/N：

- [Y] Skill 全文可读可改。
- [Y] 未绑定 Skill 不参加运行。
- [Y] 发布后新消息可激活。

架构 Y/N：

- [Y] SkillVersion 不可变。
- [Y] 激活记录版本和原因。
- [N] 不执行脚本。

真实验收：

- 未绑定时不激活。
- 绑定并发布后激活。
- 历史 Run 保留旧 SkillVersion。

当前状态：已完成（2026-07-21）。

真实证据：

- 第二号前向迁移在保留 9 条历史 Run 和 8 个 Conversation 的 SQLite 上成功应用。
- 7 条标准库契约测试通过；其中 3 条专门覆盖 Skill 发布边界。
- Skill `skill_029d70e05b8146b68eed17a1107e8845` 校验为 `VALIDATED`，不可变版本为 `skillv_e14783966d0f49ef80dc354faa367082`。
- Candidate `rel_9194ba42cc254102b6f46017908f92ca` 创建后 Active 仍为 `V0.5.5-default`，Diff 显示新增上述 SkillVersion。
- 发布前 Run `run_dfe0fa51b40940a187d6fa66ab160267` 没有 `skill_activated`；发布后同一会话 Run `run_80e84830fb3b455b839869a6f9a962af` 固定 `V0.5.6-skill-demo` 并记录唯一 `skill_activated`。
- 发布后真实回答按 Skill 要求以“结论先行：”开头；该 Run 有 2 个真实 V4-Flash Snap，人民币成本 `0.000797328`。

未完成：浏览器视觉与表单交互体验交由产品负责人手动验证。

## 11. V0.5.7——Git Skill 安全导入

本次只完成：

- 公开 Git URL 导入纯文本 Skill。
- 脚本扫描和拒绝。

产品 Y/N：

- [Y] 展示 commit、SKILL.md、文件清单和检查结果。
- [Y] 无脚本 Skill 可以导入。
- [Y] 有脚本 Skill 明确拒绝。

架构 Y/N：

- [Y] 临时隔离目录。
- [Y] 固定 commit。
- [Y] 可执行扩展名和脚本要求扫描。
- [N] 不执行仓库内容和 Git hook。

真实验收：

- 一个纯文本测试仓库导入成功。
- 一个包含脚本的测试仓库被拒绝。
- 失败原因可见。

当前状态：进行中（2026-07-21；正在实现公开 GitHub URL 固定 commit、隔离扫描、拒绝记录与 Draft 导入）。

## 12. V0.5.8——RAG 引擎与三篇通用长文档

本次只完成：

- 文本切分。
- FTS5／BM25。
- 本地向量检索。
- 混合召回。
- 三篇领域无关长文档。

产品 Y/N：

- [Y] 页面展示切分和索引技术信息。
- [Y] 检索测试显示片段、分数和引用。
- [Y] 三篇文档无行业迹象。

架构 Y/N：

- [Y] RagVersion 固定原文、Chunk、模型和索引。
- [Y] Gate 0 确认 Embedding 资源。
- [N] 不支持文件和网页数据源。

真实验收：

- 三篇文档均完成切分和索引。
- 每篇至少一条命中测试。
- AI 回答引用真实 Chunk。
- 无命中时不生成假引用。

当前状态：待开始。

## 13. V0.5.9——远程只读 MCP

本次只完成：

- 一个已部署远程 MCP Server。
- initialize、tools/list、单 Tool 测试、绑定和调用。

产品 Y/N：

- [Y] 平台管理只填写 Endpoint，不提交源码。
- [Y] Tool 说明和参数可读。
- [Y] 只有白名单 Tool 可用。

架构 Y/N：

- [Y] Streamable HTTP。
- [Y] Schema hash 随 Release 固定。
- [Y] 调用生成外部 Snap。
- [N] 不运行 Git MCP 和 stdio。
- [N] 不接动态写 Tool。

真实验收：

- 连接测试。
- tools/list。
- 单 Tool 测试。
- 对话中真实调用和 Trace。
- 未绑定 Tool 无法调用。

当前状态：待开始。

## 14. V0.5.10——工单只读

本次只完成：

- 工单数据。
- list_work_orders。
- get_work_order。
- 用户和员工页面列表。

产品 Y/N：

- [Y] 用户查看演示工单。
- [Y] 员工查看全部演示工单。
- [Y] 工单 Agent 可查询列表和详情。

架构 Y/N：

- [Y] 工单逻辑只在 work_orders 模块。
- [Y] Tool 调用进入 Trace。
- [N] 本版本不写工单。

真实验收：

- 列表查询。
- 详情查询。
- AI 对话真实返回 Tool 数据。

当前状态：待开始。

## 15. V0.5.11——创建工单确认写入

本次只完成：

- create_work_order 草稿、确认、幂等和回执。

产品 Y/N：

- [Y] AI 先展示草稿。
- [Y] 用户确认或取消。
- [Y] 成功后显示工单编号。
- [N] 未确认不写入。

架构 Y/N：

- [Y] Action Gateway。
- [Y] 一次性 token。
- [Y] idempotency key。
- [Y] SUCCEEDED／FAILED／INDETERMINATE。

真实验收：

- 未确认数据库不增加。
- 确认后只增加一条。
- 重复确认不重复创建。

当前状态：待开始。

## 16. V0.5.12——更新、关闭和删除工单

本次只完成：

- update_work_order。
- close_work_order。
- delete_work_order。

产品 Y/N：

- [Y] 三种操作分别展示差异或影响确认卡。
- [Y] 删除使用二次确认。
- [Y] 每次执行显示回执。

架构 Y/N：

- [Y] 复用 Action Gateway，不建设第二套状态机。
- [Y] delete 软删除。
- [Y] 所有操作幂等并保留审计。

真实验收：

- 更新前后差异。
- 关闭状态。
- 删除后页面不可见但审计仍存在。
- 重复执行不产生二次副作用。

当前状态：待开始。

## 17. V0.5.13——人机共驾一个来回

本次只完成：

- 用户或 AI 发起。
- 员工回复。
- 交给 AI 继续或结束。

产品 Y/N：

- [Y] 员工看到交接包。
- [Y] AI 恢复读取人工消息。
- [N] 不做队列和坐席系统。

架构 Y/N：

- [Y] 单一输出权状态机。
- [Y] AI_RESUMING 创建新 Run并使用当前 Active Release。
- [N] HUMAN_ACTIVE 时 AI 不回复。

真实验收：

- 一次人工回复。
- 一次 AI 恢复。
- 一次人工直接结束。
- 并发回复被拒绝。

当前状态：待开始。

## 18. V0.5.14——疑似 Badcase 与两级分类

本次只完成：

- 自动抓捕规则。
- Candidate 列表。
- 一级和二级分类建议。
- 人工确认或排除。

产品 Y/N：

- [Y] 产品全局列出的自动条件都能生成 Candidate。
- [Y] 人工确认后才成为正式 Badcase。
- [Y] 用户主动请求人工不自动成为 Badcase。

架构 Y/N：

- [Y] run_id + rule_code 去重。
- [Y] Candidate 保存证据事件。
- [N] 自动分类不直接成为正式根因。

真实验收：

- error、低路由、Tool 失败、点踩、Usage 缺失和成本异常样例。
- 重复事件不生成重复 Candidate。
- 人工确认和排除。

当前状态：待开始。

## 19. V0.5.15——Darwin 与按需 Evaluation

本次只完成：

- Darwin 诊断草稿。
- Eval Case 草稿。
- 基准与候选 Release 回放。
- 原案例复验。

产品 Y/N：

- [Y] 人工确认根因和关闭。
- [Y] Evaluation 比较质量、Token、延迟和成本。
- [N] 不自动改配置和发布。

架构 Y/N：

- [Y] Darwin 和 Evaluation 的每次云调用也生成 CloudCallSnap。
- [Y] Darwin 作为显式高级专家工作流，可以使用 `deepseek-v4-pro` 思考模式。
- [Y] EvalRun 与真实 Run 分开标识。
- [Y] 回放使用固定输入和上下文。

真实验收：

- 一个真实 Badcase 完成全闭环。
- 新旧 Release 对比结果。
- 发布后原案例复验。

当前状态：待开始。

## 20. V0.5.16——成本页面与控制策略

本次只完成：

- 成本汇总页面。
- CostPolicy 编辑、发布和限制。
- 预警。

产品 Y/N：

- [Y] 按时间、Run、Release、Agent 和模型查看。
- [Y] 展示每次云调用 Snap。
- [Y] 演示一次硬限制和一次金额预警。
- [N] 不自动切模型和发布。

架构 Y/N：

- [Y] Run 汇总只来自 CloudCallSnap。
- [Y] CostPolicyVersion 随 Release 固定。
- [Y] Guardrail 服务端执行并进入 Trace。
- [Y] 缺失 Usage 时成本为 null。

真实验收：

- 成本聚合与原始 Snap 对账。
- max_output_tokens 实际生效。
- RAG 或 MCP 长度限制实际生效。
- 金额预警显示但不阻塞服务。

当前状态：待开始。

## 21. V0.5.17——四个面试故事最终串联

本次只完成：

- 清理演示阻塞问题。
- 完成四个故事的顺序演示。
- 更新最终文档和部署状态。

故事一：

- 可解释运行。

故事二：

- 修改能力并发布，旧气泡不变，新消息使用新 Release。

故事三：

- Badcase → Darwin → Evaluation → 发布 → 原案例复验。

故事四：

- 找到高成本 Run → 调整 Cost Policy → 比较质量和成本 → 人工发布。

架构 Y/N：

- [Y] 只修复阻塞四个故事的问题。
- [N] 不在最终串联阶段新增大功能。

真实验收：

- 四个故事各有真实 Run、Trace 和截图或用户手动验证结果。
- 五份文档统一到最终 V0.5.x。
- CURRENT-STATE 只记录已验证事实。

当前状态：待开始。

## 22. 每个版本完成后的更新模板

```text
版本：
完成日期：
状态：完成／进行中／阻塞

已完成：

未完成：

产品 Y/N 变化：
无／具体条目

架构 Y/N 变化：
无／具体条目

真实证据：

已知问题：

下一小版本：
```

## 23. 当前下一步

当前下一步：

1. 产品负责人手动打开 `http://192.168.50.232:19080`，体验历史对话、消息时间戳、AI 气泡下的 Run 入口、右侧详情抽屉、Trace 输入／回答和人民币逐步成本。
2. 若手动体验仍发现阻塞 V0.5.5 的问题，继续作为 V0.5.5 同版本纠偏并回归 04 文档中的相关测试。
3. 若 V0.5.5 手动体验通过，再从 V0.5.6 自然语言 Skill 开始下一批次。
4. FastGPT 继续只作为可选 Gate 判断，不安装、不修改其内部数据库，也不阻塞直接 DeepSeek 主路径。
5. 下一批开发前重新阅读并按事实更新五份 Living Docs。
