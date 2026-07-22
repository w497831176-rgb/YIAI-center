# YIAI Center V0.5.13 测试用例与自测记录（全局累计）

> 文档性质：Living Test Doc  
> 当前文档版本：V0.5.13  
> 累计覆盖：V0.5.0—V0.5.13  
> 原 V0.5.13 验收日期：2026-07-21  
> Ubuntu 迁移复测日期：2026-07-22  
> 当前正式地址：http://192.168.50.112:19080  
> 当前 Active Release：V0.5.13-unlimited-codrive

## 1. 文档范围与结果口径

本文件不是只测试 V0.5.13 工单与人机共驾。它按当前开发版本命名，但累计保留 YIAI Center 从 V0.5.0 到 V0.5.13 的测试范围、历史自测结果和代表证据。

结果使用完整文字：

- 通过：实际结果符合预期，且有测试输出、API、数据库、Run、Trace、Release、Action 或状态快照证据。
- 通过并发生降级：核心事实正确完成，外部调用失败后按设计降级，错误和成本如实记录。
- 待人工体验：技术契约已验证，但视觉、间距、卡片密度或操作手感未由产品负责人逐项走查。
- 失败：实际结果不符合预期，保留失败证据，不得发布。
- 阻塞：外部依赖阻止本次路径继续，且没有安全替代验证；不能把阻塞写成通过。

当前是个人演示项目，不建设 Playwright、浏览器容器和大型自动化测试工程。自动测试重点覆盖 Release 固定、单 Agent、能力边界、Trace 终态、Usage、成本、写操作确认、共驾状态和数据持久化；主观页面体验由产品负责人手动验证。

## 2. 测试环境与回归里程碑

### 2.1 当前正式环境

- 主机：192.168.50.112，Ubuntu Server 24.04 LTS。
- Compose 项目：yiai-center-v0513。
- 应用容器：yiai-center-v0513-api-1。
- 应用网络：yiai-center-v0513_default。
- 数据目录：/home/wang/apps/yiai-center-v0513/data。
- 端口：19080。
- 功能代码基线：a50e795。
- DeepSeek：已配置；迁移复测的无业务内容 /models 请求返回 HTTP 200 和 2 个模型。

### 2.2 V0.5.13 隔离环境

- 原隔离容器：yiai-v0513-stage。
- 原隔离端口：19081。
- 使用全新临时 SQLite。
- DeepSeek 未配置，用于验证确定性 Router 和模型异常恢复。
- 隔离测试期间原正式 19080 保持运行。

### 2.3 源端回滚环境

- 源主机：192.168.50.232。
- 原容器：yiai-center-api-1，目标验证后停止但未删除。
- 原数据目录：D:\Docker\yiai-center\data。
- 一致性备份：yiai-center-migration-20260722.sqlite。

### 2.4 自动回归演进

| 里程碑 | 当时回归结果 | 说明 |
| --- | --- | --- |
| V0.5.5 | 4/4 | Runtime、Usage、成本和核心契约 |
| V0.5.6 | 7/7 | 新增 Skill 契约 |
| V0.5.7 | 12/12 | 新增 Git Skill 导入安全 |
| V0.5.8 | 16/16 | 新增 RAG 切片、排序和引用保护 |
| V0.5.9 MCP | 21/21 | 新增 MCP Client、白名单、Schema 和快照 |
| V0.5.9 Agent 配置修复 | 30/30 | 新增 Agent 中心装配、动态 Agent、卡片契约 |
| V0.5.13 隔离源码 | 40/40，7.543 秒 | 新增工单、Action Gateway 和共驾 |
| V0.5.13 原正式镜像 | 40/40，7.374 秒 | 原台式机最终镜像 |
| V0.5.13 Ubuntu 镜像 | 40/40，2.461 秒 | 迁移后的最终镜像复测 |

## 3. V0.5.0 文档基线

### TC-050-01 五份文档职责与全局范围

预期：产品、架构、路线图、测试和实际实现各自回答不同问题；产品、架构和路线图覆盖整体，测试与实现按当前版本命名但累计保留历史。

实际：五份 V0.5.13 文档已按全局累计口径重写；不再把产品、架构和版本规划缩成 V0.5.13 专题，也不强行使用 Y/N 表述。

状态：通过。

### TC-050-02 文档版本一致

预期：五份当前文件均为 V0.5.13，互相引用的地址、Active Release 和版本状态一致。

实际：五份 Markdown 与五份 Word 使用统一 V0.5.13 文件名；当前地址为 192.168.50.112:19080，Active Release 为 V0.5.13-unlimited-codrive。

状态：通过。

## 4. V0.5.1 主机与 DeepSeek Gate

### TC-051-01 目标主机只读检查

预期：确认主机、Docker、端口、现有容器和持久化边界，不破坏其他服务。

历史实际：主机检查完成，YIAI Center 使用独立目录、容器、端口和数据文件；现有 immich_machine_learning 未被替换或停止。

状态：通过。

### TC-051-02 DeepSeek 非流式 Usage

预期：非流式调用能取得输入、缓存输入和输出 Usage，并可映射价格。

历史实际：三类 Usage 成功返回并进入模型策略验证。

状态：通过。

### TC-051-03 DeepSeek 流式最终 Usage

预期：流式回答的最终事件能取得完整 Usage，而不是按字符估算 Token。

历史实际：流式最终 Usage 验证通过。

状态：通过。

### TC-051-04 模型策略

历史实际：4 条成功 Run 共形成 8 个 CloudCallSnap，模型均为 deepseek-v4-flash。

状态：通过。

## 5. V0.5.2 应用骨架与三个端

### TC-052-01 零依赖镜像与语法

预期：不依赖临时外部前端或 Python 包下载即可构建运行。

历史实际：Python compileall 通过，零第三方运行依赖镜像构建成功。

状态：通过。

### TC-052-02 核心契约单元测试

预期：Release 固定、单 Agent、Trace 终态、Usage 缺失和成本诚实等契约可自动验证。

历史实际：当时 4 条 unittest 全部通过；Usage 缺失时回答继续返回、Run 成本为未知并生成疑似 Badcase 线索。

状态：通过。

### TC-052-03 健康检查与持久化

预期：健康接口、数据库和容器正常；重建容器后历史 Run 保留。

历史实际：容器健康，SQLite 文件持久化；重建后 5 条真实 Run 仍存在。

状态：通过。

### TC-052-04 三个端页面结构

预期：用户、员工和平台管理入口存在，平台管理含 Release 与 Run/Trace。

历史实际：页面结构和服务通过；当时视觉与交互留给产品负责人手动验证。

状态：通过；视觉体验为人工项。

## 6. V0.5.3 Release、Run 与 Trace

### TC-053-01 同一历史会话发布前后

预期：发布只影响下一条新消息，旧消息保持原 Release。

历史实际：同一会话前两条气泡保持默认 Release，发布后两条使用 V0.5.5-release-smoke-b。

状态：通过。

### TC-053-02 人工回滚

预期：回滚改变后续 Active Release，不改写历史 Run。

历史实际：Active Release 恢复 V0.5.5-default，测试 Run 仍保存 V0.5.5-release-smoke-b。

状态：通过。

### TC-053-03 Trace 唯一终态

预期：每个 Run 恰好一个 done 或 error。

历史实际：5 条历史 Run 的 terminal 数量均为 1。

状态：通过。

### TC-053-04 失败证据保留

历史实际：错误 Run run_c8a77c0324a2460e9f45b7b46e048372 保留 Router 外部调用失败、确定性兜底、唯一 Agent 和最终 URLError，没有被删除。

状态：通过。

## 7. V0.5.4 DeepSeek、SSE、Usage 与成本

### TC-054-01 真实 SSE 闭环

代表 Run：run_bf042f987a964d4eacb04bf677591020。

实际：SSE 包含 run_started、route_decision、agent_selected、delta 和 done；Run 状态 DONE，Release 为 V0.5.5-default。

状态：通过。

### TC-054-02 调用级 CloudCallSnap

历史实际：4 条成功 Run 每条均形成 Router 和主回答两个 CloudCallSnap。

状态：通过。

### TC-054-03 Estimated Cost

历史实际：代表 Run 的 USD 成本为 0.00015442，来自调用快照聚合；后续页面同时展示人民币价格快照与汇总。

状态：通过。

### TC-054-04 Usage 缺失兜底

预期：任一必要调用缺失 Usage 时，Run 总成本不能只显示部分成本。

历史实际：自动测试覆盖调用缺失 Usage、Snap 状态、Run 成本未知和错误 Trace，全部通过。

状态：通过。

## 8. V0.5.5 唯一 Router 与单 Agent

### TC-055-01 三类真实意图

历史代表 Run：

- 一般咨询：run_bf042f987a964d4eacb04bf677591020。
- 投诉：run_361b93eb9d11479b87fef99e809c6fd6。
- 工单：run_25c70909fdb44cd2ab6534f3403e3554。

实际：三类输入均只选择一个匹配 Agent。

状态：通过。

### TC-055-02 非法多 Agent 输出

预期：target_agent 为数组、未知 ID 或多个 Agent 时拒绝。

历史实际：数组契约抛出 ValueError；Runtime 使用唯一确定性兜底，不串行尝试多个 Agent。

状态：通过。

### TC-055-03 历史会话与气泡 Run 入口

预期：读取历史会话不创建新 Run；AI 气泡显示时间、Run、Agent、Release 和详情入口。

历史实际：API 与静态交互结构通过，Run 抽屉复用权威详情 API。

状态：通过；主观视觉为人工项。

### TC-055-04 Trace 内人民币调用快照

历史实际：Run run_4e283b75bca3456cbd436bf2c5d93bf3 有 2 个 CloudCallSnap；人民币汇总 0.000732816 CNY，等于调用快照之和。

状态：通过。

## 9. V0.5.6 自然语言 Skill

### TC-056-01 前向迁移与历史数据

实际：迁移版本 1 → 2；部署前保存 yiai-center.sqlite.pre-v056-20260721；迁移后 9 条历史 Run、8 个 Conversation 保留。

状态：通过。

### TC-056-02 草稿、校验、版本和绑定

预期：Skill 可编辑草稿，校验后生成不可变版本；只有 Agent 绑定进入 Candidate 才能上线。

实际：7 条当时回归测试全部通过，其中 3 条为 Skill 专项契约。

状态：通过。

### TC-056-03 Candidate 与真实 Run

预期：Candidate 不改变在线；发布后新 Run 才激活 Skill。

实际：Run run_80e84830fb3b455b839869a6f9a962af 使用 V0.5.6-skill-demo，Trace 含 skill_considered → skill_activated。

状态：通过。

## 10. V0.5.7 Git Skill 安全导入

### TC-057-01 凭据边界

实际：包含凭据的 Git URL 被契约拒绝。

状态：通过。

### TC-057-02 纯文本仓库与脚本仓库

预期：纯文本 Skill 可导入；含脚本或可执行内容的仓库拒绝。

实际：两个真实分支分别完成允许和拒绝验证。

状态：通过。

### TC-057-03 不执行、不绑定、不发布

实际：导入成功后仍为未绑定 Draft，Active Release 保持 V0.5.6-skill-demo；没有执行代码、安装依赖或泄露凭据。

状态：通过。

### TC-057-04 回归与部署

实际：12 条 unittest 全部通过；Health 返回 V0.5.7；迁移版本为 3。

状态：通过。

## 11. V0.5.8 RAG 混合检索

### TC-058-01 确定性切片与技术披露

实际：三篇 Markdown 文档分别生成 5、5、6 个 Chunk；相同输入重复预览一致。API 如实返回 markdown-paragraph-v1、sqlite-fts5-bm25、local-tfidf-lsa-v1 和 weighted-rrf。

状态：通过。

### TC-058-02 三路检索

查询“登录失败后怎样重置密码并完成身份核验？”时：

- BM25 首条分数 12.252185315657858。
- LSA 首条余弦分数 0.9745432893590202。
- RRF 首条分数 0.01639344262295082。
- 三路均命中身份与信息最小化 Chunk。

当时 16 条 unittest 全部通过，其中 4 条覆盖 RAG。

状态：通过。

### TC-058-03 无召回与引用保护

实际：词表外查询 zzqv987654321 的三路结果均为 0；模型输出中的未知 Citation 在发送前移除。

状态：通过。

### TC-058-04 Release 与历史快照

- Release：rel_829f57da467c4cc59d4693cd3acbcfcf / V0.5.8-rag-demo。
- 发布前 Run：run_10cacdd225e644f78fe9e225879f9b00，0 条证据。
- 发布后 Run：run_1a2a5d2a4b5f4e81b8d776c939f3565，召回 4 个 Chunk、使用 2 个合法 Citation、注入 1408 字符。
- 历史 Run 仍显示旧 Release 和 0 个绑定。

状态：通过。

### TC-058-05 Trace 与成本

实际：Trace 包含 rag_retrieval_requested、rag_retrieval_completed 和 rag_citation_validation；RAG 本地成本 0，Router/主 Agent 保存真实 Usage，Run 总成本 0.002268 CNY。

状态：通过。

## 12. V0.5.9 远程只读 MCP

### TC-059-01 独立部署与版本固定

实际：命语来源 https://github.com/Brhiza/mingyu，固定 commit 8e24d474d25d52d8b33533fe6e4dbc50aae6d9c8；独立目录、Compose 和端口 19120；上游 stdio 经独立 Adapter 转 Streamable HTTP，不复制算法。

状态：通过。

### TC-059-02 initialize、Tool List 与页面字段

历史实际：

- 命语 initialize 返回 mingyu-mcp-server / 0.1.0+8e24d47，Tool List 56 个，测试耗时 32 ms。
- 官方文档返回 Model Context Protocol / 1.0.0，Tool List 3 个；一次成功耗时 986 ms。
- API 与页面保存 Git、版本、Endpoint、Transport、鉴权、状态、最近测试、Schema/hash、读写属性、白名单、拒绝项、Agent 与 Release。

状态：通过。

### TC-059-03 Tool 白名单

实际：命语只允许 ziwei_calculate，其他 55 个 Tool 全部拒绝；官方文档只允许 search_model_context_protocol，另外 2 个未开放。Runtime 再次校验 Release 白名单和 Schema。

状态：通过。

### TC-059-04 命语核心真实 Run

输入：“我是女性，阳历1992年8月21日7点35分出生，不使用真太阳时，请给我做紫微斗数排盘。”

证据：

- Release：rel_8e71df9301be4b7e936941ceda531bb4。
- Run：run_c6a864bd64d04ed3b6d124fd6623dc78。
- 唯一 Agent：general-service。
- 唯一 MCP Tool：ziwei_calculate。
- 参数：gender=female、dateType=solar、year=1992、month=8、day=21、timeIndex=4、useTrueSolarTime=false、isLeapMonth=false、promptScope=full。
- 历史 MCP 结果长度 3,642,960，延迟 3,563 ms，MCP 模型成本 0。
- DeepSeek 主回答输入未命中 144、缓存命中 4,096、输出 1,313 Token，成本 0.00287473536 CNY；Run 总成本 0.00302549184 CNY。

状态：通过。

### TC-059-05 信息不足集中追问

实际：Run run_312f2d79fc564ae4bb8a547e5cf6f38a 未调用 MCP，只集中追问性别、历法和可选真太阳时信息，没有自行猜测。

状态：通过。

### TC-059-06 MCP A→B 热切换

实际：

- A Release rel_8e71df9301be4b7e936941ceda531bb4 绑定命语。
- B Release rel_da9c4e8d8eb540ed89c6738bdc7b9252 移除命语并绑定官方文档。
- 同一 Conversation conv_98cad63e288b4cd6abb1c759ee744399 的旧 Run 保留命语快照；新 Run run_fccbf50fe28c4fbba496114ddf4102f9 调用官方文档。
- B 发布后 Run run_be2cd695fba14a959f4121165cacff86 再请求命语时 MCP Snap 数为 0。
- 切换没有修改聊天代码或重建 YIAI Center 容器。

状态：通过。

### TC-059-07 异常降级与回归

实际：官方 Endpoint 失败 Run run_3bcc57cf46834e5b99f27dcfc423a432 保留 FAILED MCP Snap 和 URLError；后续成功 Run 不覆盖失败证据。当时 21/21 MCP 回归通过。

状态：通过。

## 13. V0.5.9 Agent 中心配置与卡片 UI 修复

### TC-059A-01 第六号迁移与旧绑定

实际：迁移版本为 1—6，agent_configs=3。迁移前 8 个 Release、23 个 Run、351 个 Trace、2 个 Skill、3 个 RAG、2 个 MCP、6 个 MCPCallSnap；迁移后在新增测试证据前数量完全不变，历史 Release 不重写。

状态：通过。

### TC-059A-02 Agent 是唯一装配入口

预期：Skill、RAG、MCP 页面不再反向勾选 Agent；Agent 页面装配四类能力。

实际：资源表单删除 Agent 复选框，API 只读返回 bound_agent_ids 或 tool_agent_ids；保存 Agent 草稿不改变 Active Release。

状态：通过。

### TC-059A-03 Candidate、Diff 与 Tool 粒度

实际：Candidate 从 Agent 草稿构建；MCP Tool 可按 Tool 映射不同 Agent；Diff 返回 Agent 基础信息、能力变化和完整绑定快照。

状态：通过。

### TC-059A-04 动态新增 Agent

实际：部署环境临时创建 agent_65e4d80942894573b39852e2d7fdbc4e，Agent 数量 3 → 4；随后删除草稿恢复 3，响应 active_release_unchanged=true。自动测试验证新 Agent 可进入 Candidate 并被 Router 接受。

状态：通过。

### TC-059A-05 卡片式平台管理

预期：Agent、Release、Skill、RAG、MCP、Run 以卡片展示，右上角新增或导入，对象操作从卡片进入。

实际：静态契约与页面结构通过；最终卡片密度和操作感受留给产品负责人手动验收。

状态：通过；主观视觉为人工项。

### TC-059A-06 回归

实际：当时 30/30 unittest 通过，耗时 4.103 秒；容器健康。

状态：通过。

## 14. V0.5.10 只读工单

### TC-0510-01 Agent 装配与发布

实际：work-order-service 保留原 RAG，并绑定 list_work_orders、get_work_order；Candidate 发布为 rel_92d43c98147844979b5c936a3eb03730。

状态：通过。

### TC-0510-02 正式只读 Run

输入：“请查询我的工单进度”。

实际：Run run_7a9e0856d25b452e8bbe0202704beee6 只选择 work-order-service；list_work_orders 参数 scope=USER，返回 2 条真实工单，延迟 13 ms，结果长度 689，Tool 模型成本 0。

状态：通过。

### TC-0510-03 主模型失败降级

实际：Router DeepSeek 成功；主回答发生 URLError。系统仍以真实 Tool 结果输出并标记 degraded_reason=main_agent_model_unavailable、fallback=deterministic_preset_tool_answer。Router 成本 0.000475776 CNY，失败主调用未虚构 Token。

状态：通过并发生降级。

### TC-0510-04 模型完全不可用时 Router 兜底

实际：隔离环境未配置 DeepSeek，Router 仍根据 Release Tool 描述选择工单 Agent，而不是盲选第一个 Agent。

状态：通过。

## 15. V0.5.11 创建与确认

### TC-0511-01 只生成草稿

实际：Run run_eb63354876194ab599ed4b9ac4dce571 生成 Action action_68780600b79a4145ab862c6c8b477656，状态 AWAITING_CONFIRMATION；确认前正式工单数量不变。

状态：通过。

### TC-0511-02 确认创建与收据

实际：确认 Run run_bfb5e4f21ab64a239794db14f4bcf3b6 创建 WO-20260721-003，Action SUCCEEDED，收据包含 Action、Tool、执行时间和工单编号。

状态：通过。

### TC-0511-03 重复确认幂等

实际：重复确认返回 idempotent_replay=true，仍引用同一工单，没有第二次写入。

状态：通过。

### TC-0511-04 未发布写 Tool 拒绝

实际：在未发布 delete_work_order 的 Release 中创建删除草稿被服务端拒绝。

状态：通过。

## 16. V0.5.12 更新、关闭与删除

### TC-0512-01 更新前后快照

实际：Action action_437409132c60488eb4c2a9adb81cd03e / Run run_f66cb54e6b654d748874787e2c507c0d，将 priority 从 HIGH 更新为 URGENT，确认前不写入。

状态：通过。

### TC-0512-02 关闭与处理结果

实际：Action action_b4117f9c8f3a413fb1a672e9b11a1300 / Run run_5c4584e4af6d449295cc5964a66caff5，最终 status=CLOSED，保留处理结果。

状态：通过。

### TC-0512-03 软删除双确认

实际：Action action_e2580af2bb554b7caef8404195a50f5b 第一次确认 Run run_8e657f62ecc94257982b5034b733aed7 后仍可读取；第二次确认 Run run_4145c1810a0140249aefef4354cb667d 后写入 deleted_at。普通列表不可见，执行前快照和审计保留。

状态：通过。

## 17. V0.5.13 无限轮人机共驾

### TC-0513-01 历史会话进入新 Release

实际：Conversation conv_e4647f87c1d045c38c7c53dc14f9963a 保留 V0.5.11 历史 Run；发布 V0.5.13 后进入 HANDOFF_REQUESTED，员工接受后为 HUMAN_ACTIVE。

状态：通过。

### TC-0513-02 连续员工回复无限轮

实际：连续写入 3 条员工消息，session version 3 → 6，每次仍为 HUMAN_ACTIVE、ai_standby=true、can_return_to_ai=true。自动测试另覆盖五轮回复。

状态：通过。

### TC-0513-03 并发旧版本

实际：使用旧 expected_version 回复返回 HTTP 409，并提示刷新重试。

状态：通过。

### TC-0513-04 人工期间 AI 不抢答

实际：Run run_76fd4048cc1e4c689b9d3425bd4d12cf 只有 run_started、human_active、done，没有 AI delta；状态仍 HUMAN_ACTIVE。

状态：通过。

### TC-0513-05 第一次交还 AI

实际：Run run_7d72c0f4fb3a4855b96a7923dcc090e8 使用 V0.5.13-unlimited-codrive，DeepSeek 成功续接；最终 AI_ACTIVE、ai_standby=true、can_request_human=true。输入 1,461、输出 201，成本 0.001877904 CNY。

状态：通过。

### TC-0513-06 第二轮循环

实际：再次请求人工、接受并交还，Run run_86063811b4fa43a8a7e5b05584988490；最终 version 12、AI_ACTIVE、ai_standby=true。输入 1,542、输出 594，成本 0.003612672 CNY。

状态：通过。

### TC-0513-07 模型失败恢复输出权

实际：隔离环境交还 AI 时模型失败，随后状态仍恢复 AI_ACTIVE、ai_standby=true、can_request_human=true，没有停留在 AI_RESUMING。

状态：通过。

### TC-0513-08 UI 静态契约

实际：app.js 包含 /codrive/messages 和“交还 AI”，不存在“结束会话”或“结束共驾”按钮。

状态：通过。

## 18. Release 顺序、数据保护与 Ubuntu 迁移

### TC-GLOBAL-01 V0.5.10—V0.5.13 顺序发布

实际 Release 顺序：

1. rel_92d43c98147844979b5c936a3eb03730。
2. rel_98359d126d3f4202b3a0e35bd7c2bcef。
3. rel_92335d5414a54eb3aeb561367b0027aa。
4. rel_191f4cfd72b14a69ab6969e74c775c68。

状态：通过。

### TC-GLOBAL-02 前向迁移 7—9

实际：升级创建工单、Action 和共驾表；迁移前 Release 9、Run 24、Agent 3、Skill 2、RAG 3、MCP 2，迁移后首次核对完全一致。

状态：通过。

### TC-GLOBAL-03 一致性备份

实际：SQLite 在线备份 yiai-center-migration-20260722.sqlite，大小 2,461,696 字节，integrity_check=ok，SHA-256 为 1d364115d403fa07d9b699eb6d21dd21e4ce2730b0b888b2f78b78449cf4d4e5。

状态：通过。

### TC-GLOBAL-04 迁移前后全表对账

实际关键数量一致：

| 数据 | 源端 | 目标端 |
| --- | ---: | ---: |
| Release | 13 | 13 |
| Run | 35 | 35 |
| Trace Event | 481 | 481 |
| Release Binding | 67 | 67 |
| Agent Config | 3 | 3 |
| Skill | 2 | 2 |
| RAG Document | 3 | 3 |
| RAG Chunk | 16 | 16 |
| MCP Server | 2 | 2 |
| MCP Call Snap | 6 | 6 |
| Cloud Call Snap | 49 | 49 |
| Action Request | 4 | 4 |
| Action Audit Event | 21 | 21 |
| Codrive Session | 4 | 4 |
| Codrive Event | 12 | 12 |
| Human Message | 3 | 3 |
| Conversation | 21 | 21 |
| Message | 65 | 65 |
| Work Order | 4 | 4 |

普通接口可见工单为 3，另 1 条为保留审计的软删除自测工单。

状态：通过。

### TC-GLOBAL-05 目标健康与外部依赖

实际：

- 首页 HTTP 200。
- /api/health 返回 status=ok、version=V0.5.13、database=ok、deepseek_configured=true。
- 官方文档 MCP 与命语 MCP 均 initialize、Tool List 和白名单 Tool 实际调用成功。
- 迁移后命语 ziwei_calculate 结果长度 447,167；官方文档 search_model_context_protocol 结果长度 11,571。
- 最终镜像 40/40 通过。
- Active Release 仍为 V0.5.13-unlimited-codrive。

状态：通过。

### TC-GLOBAL-06 源端回滚保护

实际：目标验证完成后只停止源端 YIAI API；源容器、数据库、原目录和一致性备份均保留，没有删除 Volume 或执行全局 Docker 清理。

状态：通过。

## 19. 待产品负责人手动体验

以下不是当前技术阻塞，但仍需要产品负责人有空时走查：

- 用户、员工、平台管理三个端的视觉一致性。
- 管理卡片的信息密度、右上角新增入口和卡片菜单是否顺手。
- Agent 装配 Skill、RAG、MCP Tool、预置 Tool 的理解成本。
- 工单确认卡、Action 收据和共驾交接包的可读性。
- 连续员工回复与“交还 AI”的操作手感。
- Run 抽屉在长 Trace、长 MCP 结果摘要和成本明细下的阅读体验。

本轮按产品负责人“先不细测”的要求，没有执行浏览器自动化或替代产品负责人作主观视觉判断。

## 20. 当前自测结论

V0.5.0—V0.5.13 的文档基线、模型 Gate、应用骨架、Release/Run/Trace、SSE 与成本、唯一 Router、Skill、Git 导入、RAG、远程只读 MCP、Agent 中心配置、卡片管理、工单、Action Gateway、无限轮共驾和 Ubuntu 迁移均有累计测试证据。

当前最终镜像 40/40 通过，Active Release 为 V0.5.13-unlimited-codrive，迁移前后数据没有减少，两个 MCP 仍可连接和真实调用，源端回滚数据安全保留。当前唯一未完成项是产品负责人之后对页面视觉密度和操作手感的主观走查。
