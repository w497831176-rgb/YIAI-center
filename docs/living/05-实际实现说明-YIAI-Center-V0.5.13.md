# YIAI Center V0.5.13 实际实现说明

> 文档版本：V0.5.13
> 创建日期：2026-07-21
> 更新日期：2026-07-22
> 正式地址：`http://192.168.50.112:19080`
> Active Release：`V0.5.13-unlimited-codrive`
> Active Release ID：`rel_191f4cfd72b14a69ab6969e74c775c68`
> 部署提交：`a50e795`（包含功能提交 `adc7411 feat:work-orders-and-unlimited-codrive`）

## 1. 交付结论

V0.5.10—V0.5.13 已连续完成并部署到正式环境。当前产品能够：

- 从真实数据库查询工单列表和详情。
- 从自然语言生成创建工单草稿，确认后实际写入。
- 通过同一 Action Gateway 更新、关闭和软删除工单。
- 对普通写操作执行一次确认，对软删除执行两次确认。
- 防止重复确认产生重复写入。
- 在同一历史会话中由员工连续回复任意轮。
- 在人工期间让 AI 保持待命且不抢答。
- 通过“交还 AI”恢复 AI 输出权，随后仍能再次进入人工协同。
- 在 Run 详情中保留 Release、Agent、Tool、参数、结果、模型用量和人民币成本。

产品负责人最新决定的“无轮次限制、无完结状态、AI 永远待命”已经作为服务端状态机和员工页面交互的正式规则实现，不是仅靠文案提示。

## 2. 主要代码

### 新增后端模块

- `apps/api/app/work_orders.py`
  - 工单表、演示数据和六个 Tool 定义。
  - 用户/员工范围查询和详情读取。
  - 创建、更新、关闭、软删除执行器。
  - 自然语言读写规划和真实结果格式化。

- `apps/api/app/action_gateway.py`
  - Action 草稿和追加式审计表。
  - Release Tool 绑定校验。
  - 确认令牌哈希、幂等键和状态迁移。
  - 删除双重确认、执行收据和结果未知状态。

- `apps/api/app/codrive.py`
  - 共驾会话、事件和员工消息表。
  - 请求、接受、无限轮员工消息、交还 AI。
  - 乐观版本控制和失败恢复。
  - 仅四种输出权状态，不包含 `CLOSED`。

### 修改后端模块

- `apps/api/app/db.py`
  - 执行迁移 7、8、9。
  - 将六个预置 Tool 接入 Agent 配置和 Release 快照。
  - Release Diff 增加 Tool 变化。
  - 支持按指定 Release 创建 Run。
  - 合并员工消息到会话消息和模型历史。
  - 支持无 AI 输出的 Run 正常结束。

- `apps/api/app/runtime.py`
  - Router 提示与确定性兜底读取 Release Tool 描述。
  - 执行只读 Tool、生成写操作 Action 草稿。
  - Tool 成功、模型失败时返回真实结果并标记降级。
  - 人工承接期间抑制 AI 输出。
  - 交还 AI 时读取人工上下文并使用当前 Release。

- `apps/api/app/main.py`
  - 产品版本升级为 V0.5.13。
  - 新增工单、Action、共驾 API。
  - Action 确认创建独立 Run 和 Trace。
  - “交还 AI”使用 SSE，并在所有结果下恢复 AI 状态。

- `apps/api/app/config.py`
  - 产品版本和配置提示更新到 V0.5.13。

### 前端

- `apps/web/static/app.js`
  - 用户“我的工单”卡片和确认卡。
  - 员工工单工作台、Action 卡片与交接包。
  - 无限轮员工回复和“交还 AI”。
  - 确认令牌只保存在浏览器 localStorage。
  - Agent 页面增加六个预置 Tool 的装配选项。
  - Release Diff 展示 Tool 增减。

- `apps/web/static/styles.css`
  - 工单、Action、共驾、员工消息和响应式布局。

### 测试

- `apps/api/tests/test_work_orders_actions_codrive.py`
  - 真实查询范围、Router Tool 能力兜底、确认幂等。
  - 更新、关闭、双确认软删除和审计。
  - 未发布 Tool 拒绝。
  - 五轮员工消息、重复共驾、并发冲突、AI 抑制。
  - 员工页面只有“交还 AI”的静态契约。

- `apps/api/tests/test_agent_config.py`
  - 迁移 7—9 和六个预置 Tool 的 Agent/Release 快照回归。

## 3. 数据库实现

### `work_orders`

保存真实工单事实。删除使用 `deleted_at`，普通列表和详情默认排除软删除记录。

### `action_requests`

保存 Action 的 Tool、参数、执行前快照、确认步骤、状态、结果、收据、Release、来源 Run 和确认 Run。

### `action_audit_events`

每次状态变化新增一条事件，不覆盖旧事件。软删除自测 Action 保留了草稿、请求确认、第一次确认、已确认、开始执行和执行成功等事件。

### `codrive_sessions`

每个会话一条当前状态，`version` 用于员工并发保护。`ai_standby` 是对外计算字段，在所有状态下都为真。

### `codrive_events` 与 `human_messages`

分别保存状态变化和员工回复。员工消息进入历史会话展示和交还 AI 的模型上下文。

## 4. 正式 Release 记录

### V0.5.10

- Release：`rel_92d43c98147844979b5c936a3eb03730`
- 工单 Agent：保留“通用工单规则”RAG。
- 新增 Tool：`list_work_orders`、`get_work_order`。

### V0.5.11

- Release：`rel_98359d126d3f4202b3a0e35bd7c2bcef`
- 新增 Tool：`create_work_order`。

### V0.5.12

- Release：`rel_92335d5414a54eb3aeb561367b0027aa`
- 新增 Tool：`update_work_order`、`close_work_order`、`delete_work_order`。

### V0.5.13

- Release：`rel_191f4cfd72b14a69ab6969e74c775c68`
- Tool 绑定保持完整。
- 发布无限轮共驾的状态规则、员工工作台和运行链路。

最终正式 Release 数量由 9 增加到 13，发布顺序符合版本顺序。

## 5. 正式运行记录

### 只读查询

- Run：`run_7a9e0856d25b452e8bbe0202704beee6`
- Router：DeepSeek 成功，选择唯一 `work-order-service`。
- Tool：`list_work_orders`，参数 `scope=USER`。
- 结果：2 条真实工单，Tool 延迟 13 毫秒，Tool 模型成本 0。
- 主回答模型：发生 `URLError`，使用真实 Tool 结果确定性降级。
- Router 成本：人民币 `0.000475776`。

### 创建与幂等

- 草稿 Run：`run_eb63354876194ab599ed4b9ac4dce571`
- Action：`action_68780600b79a4145ab862c6c8b477656`
- 确认 Run：`run_bfb5e4f21ab64a239794db14f4bcf3b6`
- 创建编号：`WO-20260721-003`
- 确认前数量：3；确认后仅增加 1；重复确认返回幂等重放。

### 更新、关闭与删除

- 更新：`action_437409132c60488eb4c2a9adb81cd03e` / `run_f66cb54e6b654d748874787e2c507c0d`
- 关闭：`action_b4117f9c8f3a413fb1a672e9b11a1300` / `run_5c4584e4af6d449295cc5964a66caff5`
- 删除：`action_e2580af2bb554b7caef8404195a50f5b`
- 第一次删除确认：`run_8e657f62ecc94257982b5034b733aed7`
- 第二次删除确认：`run_4145c1810a0140249aefef4354cb667d`
- 最终：自测工单已软删除，可见工单恢复为 3，审计和前后快照仍保留。

### 无限轮共驾

- 会话：`conv_e4647f87c1d045c38c7c53dc14f9963a`
- 连续员工回复：3 轮，状态保持 `HUMAN_ACTIVE`。
- 并发旧版本：HTTP 409。
- 人工期间用户补充 Run：`run_76fd4048cc1e4c689b9d3425bd4d12cf`，没有 AI `delta`。
- 第一次交还 Run：`run_7d72c0f4fb3a4855b96a7923dcc090e8`。
- 第一次交还成本：人民币 `0.001877904`，输入 1,461，缓存命中 0，输出 201。
- 第二次交还 Run：`run_86063811b4fa43a8a7e5b05584988490`。
- 第二次交还成本：人民币 `0.003612672`，输入 1,542，缓存命中 0，输出 594。
- 最终状态：version 12、`AI_ACTIVE`、`ai_standby=true`、`can_request_human=true`。

## 6. 测试结果

- 隔离源码回归：40/40 通过，7.543 秒。
- 原正式最终镜像回归：40/40 通过，7.374 秒。
- Ubuntu 目标镜像 `yiai-center-v0513-api` 回归：40/40 通过，2.461 秒。
- 正式首页：GET 返回 HTTP 200。
- 正式健康：`status=ok`、`version=V0.5.13`、`database=ok`、`deepseek_configured=true`。
- 部署前后旧数据数量：Release、Run、Agent、Skill、RAG、MCP 均无减少。
- 最终数据：Release 13、Run 35、Agent 3、Skill 2、RAG 3、MCP 2、可见工单 3。
- 完整全表对账：Trace 481、Release 绑定 67、Action 4、共驾会话 4，迁移前后逐项一致。
- MCP 复测：官方文档 MCP 与命语 MCP 均初始化成功、Tool List 成功；白名单 Tool 实际调用成功。
- DeepSeek 复测：不发送业务内容的 `/models` 鉴权请求返回 HTTP 200，模型数量为 2。

## 7. 部署记录

- 目标主机：Ubuntu Server 24.04 LTS，`192.168.50.112`
- 代码目录：`/home/wang/apps/yiai-center-v0513`
- 固定提交：`a50e795`
- Compose 项目：`yiai-center-v0513`
- 应用容器：`yiai-center-v0513-api-1`
- 应用网络：`yiai-center-v0513_default`
- 数据库：`/home/wang/apps/yiai-center-v0513/data/yiai-center.sqlite`
- 项目代理桥接：`yiai-center-v0513-proxy-host` 与 `yiai-center-v0513-proxy-bridge`
- 网络适配：通过共享 Unix Socket 使用主机回环上的 Mihomo，不开放新局域网端口，不修改 Mihomo、UFW、DNS、TUN 或其他 Docker 项目。
- 源端备份：`D:\Docker\yiai-center\data\yiai-center-migration-20260722.sqlite`
- 源端状态：`yiai-center-api-1` 已停止；容器、原数据库与备份保留，可回滚。

## 8. 已知情况

- 正式只读 Run 中，Router 的 DeepSeek 调用成功，但主回答调用出现一次网络 `URLError`。系统按设计用真实 Tool 结果降级，用户仍得到正确工单事实；错误和成本均如实记录。
- 两次正式“交还 AI”的 DeepSeek 主调用成功，证明模型与成本链路可用。网络仍可能偶发失败，因此保留失败恢复和确定性降级是必要设计。
- 当前是个人演示系统，工单范围使用固定演示用户，没有登录、权限和多租户隔离。
- 员工工作台不包含排队、抢单、结束会话或绩效功能。
- 按产品负责人“先不细测”的决定，本轮没有执行浏览器自动化或主观视觉验收；API、SSE、静态契约、正式镜像和真实业务闭环已经完成。

## 9. 最终状态

V0.5.13 已在 `http://192.168.50.112:19080` 正式运行。AI 与员工的关系是可反复切换的输出权协同，不是一次性的人工接管流程；员工交还 AI 之后，AI 继续待命，事项也不会因为 AI 承接而自动完结。迁移没有改变 Active Release、历史 Run 或业务数据，源端回滚副本仍安全保留。
