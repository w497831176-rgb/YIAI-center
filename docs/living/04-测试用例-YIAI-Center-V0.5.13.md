# YIAI Center V0.5.13 测试用例与自测记录

> 文档版本：V0.5.13
> 原版本验收日期：2026-07-21
> 迁移复测日期：2026-07-22
> 当前正式地址：`http://192.168.50.112:19080`
> 原隔离验收地址：`http://192.168.50.232:19081`
> 当前 Active Release：`V0.5.13-unlimited-codrive`

## 1. 结果说明

- 通过：实际结果符合预期，且有测试输出、API 返回、Run、Action 或状态快照作为证据。
- 通过并发生降级：核心业务事实正确完成，外部模型调用失败并按设计降级，Trace 如实记录失败。
- 待人工体验：技术链路已验证，但颜色、间距、卡片密度等主观页面体验未由产品负责人逐项走查。
- 失败：实际结果不符合预期，不能发布。

本轮没有以简单字母代替结果，所有用例均直接写明状态和证据。

## 2. 测试环境

### 隔离环境

- 容器：`yiai-v0513-stage`
- 端口：`19081`
- 数据库：容器内全新临时 SQLite
- DeepSeek：未配置，用于验证确定性 Router 和模型异常降级
- 正式 `19080` 在隔离测试期间保持运行

### 当前正式环境

- 主机：Ubuntu Server 24.04 LTS，`192.168.50.112`
- Compose 项目：`yiai-center-v0513`
- 应用容器：`yiai-center-v0513-api-1`
- 应用网络：`yiai-center-v0513_default`
- 端口：`19080`
- 数据目录：`/home/wang/apps/yiai-center-v0513/data`
- 代码提交：`a50e795`
- DeepSeek：已配置；迁移复测仅执行不含业务内容的鉴权检查，返回 HTTP 200 和 2 个可用模型

### 源端回滚环境

- 主机：`192.168.50.232`
- 原容器：`yiai-center-api-1`，迁移验收后已停止但未删除
- 原数据目录：`D:\Docker\yiai-center\data`
- 一致性备份：`yiai-center-migration-20260722.sqlite`

## 3. 自动回归

### TC-0513-A01 隔离源码完整回归

预期：Agent、Skill、RAG、MCP、成本、工单、Action Gateway 和共驾测试全部通过。

实际：在 `D:\Docker\yiai-center-stage-v0513` 挂载源码，执行 `python -m unittest discover -s tests -v`，共 40 项测试，耗时 7.543 秒，全部通过。

状态：通过。

### TC-0513-A02 正式镜像完整回归

预期：最终构建镜像内的代码和静态资源能够执行同一套测试。

实际：原正式镜像 `yiai-center-api` 内 40 项测试全部通过；迁移后在目标镜像 `yiai-center-v0513-api` 内再次执行同一命令，共 40 项，耗时 2.461 秒，全部通过。测试同时兼容源码目录和镜像内 `/app/static` 布局。

状态：通过。

### TC-0513-A03 共驾 UI 静态契约

预期：员工工作台存在连续员工消息接口和“交还 AI”，不存在结束会话操作按钮。

实际：自动测试确认 `app.js` 包含 `/codrive/messages` 与“交还 AI”，且不存在“结束会话”或“结束共驾”按钮。

状态：通过。

## 4. 迁移与数据保护

### TC-0513-B01 前向迁移

预期：升级创建工单、Action Gateway 和共驾表，不改写旧 Release 与 Run。

实际：迁移 7、8、9 正常执行；服务启动健康。部署前旧数据数量为 Release 9、Run 24、Agent 3、Skill 2、RAG 3、MCP 2；迁移后首次核对数量完全一致。

状态：通过。

### TC-0513-B02 正式备份

预期：重建容器前完成可恢复的数据库备份。

实际：迁移前通过 SQLite 在线备份接口生成 `yiai-center-migration-20260722.sqlite`。备份大小为 2,461,696 字节，完整性检查为 `ok`，SHA-256 为 `1d364115d403fa07d9b699eb6d21dd21e4ce2730b0b888b2f78b78449cf4d4e5`。

状态：通过。

### TC-0513-B03 最终数据数量

预期：四个新 Release 和自测 Run 只增加记录，不减少旧数据；自测工单完成软删除后不出现在普通列表。

实际：最终数量为 Release 13、Run 35、Agent 3、Skill 2、RAG 3、MCP 2、可见工单 3。旧能力数量未减少；自测工单不再出现在普通列表，Action 审计仍保留。

状态：通过。

### TC-0513-B04 Ubuntu 迁移与全表对账

预期：目标机启动后数据库完整，全部历史数据不减少；源端只在目标验证完成后停止并保留回滚数据。

实际：目标数据库完整性检查为 `ok`，迁移前后所有业务表数量逐项一致。关键数量为 Release 13、Run 35、Trace 481、Agent 3、Skill 2、RAG 3、MCP 2、Release 绑定 67、Action 4、共驾会话 4。目标健康检查、首页、两个 MCP 初始化与 Tool List、两个只读 Tool 实际调用均成功。目标验证完成后只停止源端 YIAI API，源数据库、容器和一致性备份均保留。

状态：通过。

## 5. V0.5.10 只读工单

### TC-0510-C01 Agent 中装配 Tool

预期：`list_work_orders` 和 `get_work_order` 从工单 Agent 草稿进入 Candidate，不在 Tool 页面反向绑定。

实际：工单 Agent 同时保留原 RAG `ragdoc_49f2582565aa4ad8ac80a57f3b5e5c19`，并新增两个只读 Tool；Candidate 成功发布。

状态：通过。

### TC-0510-C02 正式只读 Run

输入：“请查询我的工单进度”。

预期：Router 只选择一个工单 Agent，调用 `list_work_orders`，返回固定演示用户的真实记录。

实际：Run `run_7a9e0856d25b452e8bbe0202704beee6` 使用 Release `rel_92d43c98147844979b5c936a3eb03730`。Router 选择 `work-order-service`，置信度 0.95；Tool 参数为 `{"scope":"USER"}`，返回 2 条真实工单，Tool 延迟 13 毫秒，结果长度 689，Tool 模型成本为 0。

状态：通过。

### TC-0510-C03 主模型异常降级

预期：Tool 成功但主模型异常时，回答仍以真实结果为准，Trace 明确记录降级。

实际：同一 Run 的 Router DeepSeek 调用成功；主回答调用出现 `URLError`。系统输出两条真实工单，Run 为 `DONE`，并写入 `degraded_reason=main_agent_model_unavailable` 和 `fallback=deterministic_preset_tool_answer`。

Router 真实用量：缓存未命中输入 266、缓存命中输入 0、输出 103，人民币估算成本 `0.000475776`。失败的主模型调用没有虚构 Token。

状态：通过并发生降级。

### TC-0510-C04 模型完全不可用时 Router 兜底

预期：不能按 Agent 顺序盲选，应根据当前 Release 已绑定 Tool 的描述选择 Agent。

实际：隔离环境未配置 DeepSeek，Router 仍选择工单 Agent，并说明与“已发布 Tool 能力匹配”；真实查询完成。对应自动测试覆盖首个 Agent 并非目标 Agent 的场景。

状态：通过。

## 6. V0.5.11 创建与确认

### TC-0511-D01 自然语言生成草稿

输入：“创建工单：主题=测试登录问题；描述=无法进入演示页面；类别=账号支持；优先级=高”。

预期：只生成草稿，不提前写入。

实际：Run `run_eb63354876194ab599ed4b9ac4dce571` 生成 Action `action_68780600b79a4145ab862c6c8b477656`，状态为 `AWAITING_CONFIRMATION`；确认前正式工单总数仍为 3。

状态：通过。

### TC-0511-D02 确认后创建

预期：一次确认后写入，并返回真实编号和收据。

实际：确认 Run `run_bfb5e4f21ab64a239794db14f4bcf3b6` 成功，创建 `WO-20260721-003`，Action 为 `SUCCEEDED`，收据包含 Action、Tool、执行时间与工单编号。

状态：通过。

### TC-0511-D03 重复确认幂等

预期：重复提交同一确认不创建第二条记录。

实际：重复确认返回 `idempotent_replay=true`，仍引用 `WO-20260721-003`，没有增加第二条工单。

状态：通过。

### TC-0511-D04 未发布写 Tool

预期：不在指定 Release 的写 Tool 不能生成 Action。

实际：自动测试在未发布 `delete_work_order` 的 Release 中创建删除草稿，服务端拒绝。

状态：通过。

## 7. V0.5.12 更新、关闭与删除

### TC-0512-E01 更新前后快照

预期：优先级从 HIGH 改为 URGENT，确认前不变，确认后保存前后快照。

实际：Action `action_437409132c60488eb4c2a9adb81cd03e`，确认 Run `run_f66cb54e6b654d748874787e2c507c0d`；`before.priority=HIGH`，`result.priority=URGENT`。

状态：通过。

### TC-0512-E02 关闭与处理结果

预期：确认后状态为关闭，并保存处理结果。

实际：Action `action_b4117f9c8f3a413fb1a672e9b11a1300`，确认 Run `run_5c4584e4af6d449295cc5964a66caff5`；最终 `status=CLOSED`，结果为“V0.5.12 正式自测完成”。

状态：通过。

### TC-0512-E03 删除第一次确认

预期：第一次确认只记录意图，工单仍可读取。

实际：Action `action_e2580af2bb554b7caef8404195a50f5b` 第一次确认 Run 为 `run_8e657f62ecc94257982b5034b733aed7`；状态仍为 `AWAITING_CONFIRMATION`、剩余一次；随后读取工单成功，`deleted_at=null`。

状态：通过。

### TC-0512-E04 删除第二次确认与审计

预期：第二次确认后软删除，普通接口不可见，Action 审计保留。

实际：第二次确认 Run `run_4145c1810a0140249aefef4354cb667d`；`deleted_at=2026-07-21T10:50:53.496547+00:00`。Action 结果和执行前快照仍存在；自动测试确认删除 Action 至少包含草稿、请求确认、第一次确认、已确认、开始执行、执行成功六个事件。

状态：通过。

## 8. V0.5.13 无限轮人机共驾

### TC-0513-F01 历史会话进入新 Release 共驾

预期：在 V0.5.11 创建的历史会话中发起人工协同，新状态使用 V0.5.13，不改写旧 Run。

实际：会话 `conv_e4647f87c1d045c38c7c53dc14f9963a` 保留 V0.5.11 草稿和确认 Run；发布 V0.5.13 后进入 `HANDOFF_REQUESTED`，员工接受后为 `HUMAN_ACTIVE`。

状态：通过。

### TC-0513-F02 连续三轮员工回复

预期：员工回复不限制轮次，不自动完结。

实际：连续写入 3 条员工消息，session version 从 3 递增到 6，每次状态仍为 `HUMAN_ACTIVE`，`ai_standby=true`，`can_return_to_ai=true`。

状态：通过。

### TC-0513-F03 并发旧版本

预期：使用旧 `expected_version` 的员工回复被拒绝。

实际：正式接口返回 HTTP 409，提示“已有其他回复或状态变化，请刷新后重试”。

状态：通过。

### TC-0513-F04 人工期间 AI 不抢答

输入：“我补充一个信息，请员工继续处理。”

预期：记录用户消息和 Run，但不产生 AI `delta`。

实际：Run `run_76fd4048cc1e4c689b9d3425bd4d12cf` 只返回 `run_started`、`human_active` 和 `done`，没有 AI 文本输出，状态仍为 `HUMAN_ACTIVE`。

状态：通过。

### TC-0513-F05 第一次交还 AI

预期：交还后 AI 读取人工上下文，使用当前 V0.5.13 Release 回答，状态恢复为 `AI_ACTIVE`。

实际：Run `run_7d72c0f4fb3a4855b96a7923dcc090e8` 使用 `V0.5.13-unlimited-codrive`，DeepSeek 主调用成功并输出续接回答；最终 version 8、`AI_ACTIVE`、`ai_standby=true`、`can_request_human=true`。

真实用量：缓存未命中输入 1,461、缓存命中输入 0、输出 201；人民币估算成本 `0.001877904`。

状态：通过。

### TC-0513-F06 第二轮循环

预期：第一次交还后仍能再次请求人工、接受并再次交还。

实际：version 8 再次请求人工，进入 version 9；员工接受进入 version 10；再次交还产生 Run `run_86063811b4fa43a8a7e5b05584988490`，最终 version 12、`AI_ACTIVE`、`ai_standby=true`。

第二次交还的真实 DeepSeek 用量为缓存未命中输入 1,542、缓存命中输入 0、输出 594，人民币估算成本 `0.003612672`。

状态：通过。

### TC-0513-F07 模型失败仍恢复输出权

预期：交还 AI 过程出现模型异常时，不停留在 `AI_RESUMING`。

实际：隔离环境没有 DeepSeek，交还 Run 返回错误，但随后 `codrive` 事件显示 `AI_ACTIVE`、`ai_standby=true`、`can_request_human=true`。自动测试同样覆盖失败恢复路径。

状态：通过。

## 9. Release 与历史快照

### TC-0513-G01 四个版本顺序发布

预期：按 V0.5.10、V0.5.11、V0.5.12、V0.5.13 顺序发布。

实际：正式 Release ID 依次为：

1. `rel_92d43c98147844979b5c936a3eb03730`
2. `rel_98359d126d3f4202b3a0e35bd7c2bcef`
3. `rel_92335d5414a54eb3aeb561367b0027aa`
4. `rel_191f4cfd72b14a69ab6969e74c775c68`

状态：通过。

### TC-0513-G02 下一条新消息生效

预期：发布后才影响新消息，Action 确认仍固定创建草稿时的 Release。

实际：V0.5.10 Run 固定只读 Release；V0.5.11 创建确认 Run 仍固定 V0.5.11；V0.5.13 共驾交还 Run 使用当时 Active Release。各 Run 的 Release ID 未被后续发布改写。

状态：通过。

## 10. 页面与部署冒烟

### TC-0513-H01 页面入口

预期：正式首页能够加载。

实际：从当前电脑访问 `http://192.168.50.112:19080/` 返回 HTTP 200；`GET /api/health` 返回 `status=ok`、`version=V0.5.13`、`database=ok`、`deepseek_configured=true`。三个项目容器均为 `healthy`。

状态：通过。

### TC-0513-H02 主观视觉体验

预期：产品负责人有空时检查员工工作台、工单卡片、确认卡和共驾交接包的可读性。

实际：本轮按产品负责人“先不细测”的要求，没有执行浏览器自动化或代替产品负责人做主观视觉判断。静态契约、真实接口、正式 GET、SSE 和业务闭环均已验证。

状态：待人工体验，不阻塞本次技术发布。

## 11. 最终结论

V0.5.10—V0.5.13 的后端、Release、真实业务数据、正式 DeepSeek 调用、成本、共驾循环、Ubuntu 迁移和部署链路均通过。迁移后测试仍为 40/40，Active Release 仍为 `V0.5.13-unlimited-codrive`，迁移前后数据无减少。唯一保留项是产品负责人之后对页面视觉密度与操作手感的主观走查；它不影响当前正式环境的业务可用性和证据完整性。
