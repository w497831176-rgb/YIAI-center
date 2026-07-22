# YIAI Center V0.5.13 版本规划

> 文档版本：V0.5.13
> 创建日期：2026-07-21
> 更新日期：2026-07-22
> 规划区间：V0.5.10—V0.5.13
> 实施状态：四个版本已按顺序实现、测试、发布，并迁移到 Ubuntu 小主机

## 1. 总目标

本轮用四个连续 Release 完成一条可解释的工单业务路径：

`真实查询 → 创建前确认 → 更新/关闭/软删除 → 无限轮员工与 AI 共驾`

各版本都遵守同一产品边界：能力在垂直 Agent 中装配，Candidate Release 冻结绑定，人工发布后从下一条新消息生效，历史 Run 保留旧快照。

## 2. V0.5.10：只读工单

### 目标

让工单 Agent 能够查询真实工单列表和详情，并在 Run 详情中展示 Tool 参数与结果。

### 已完成

- 新增 `work_orders` 数据表和三条领域无关演示记录。
- 新增 `list_work_orders` 和 `get_work_order`。
- Tool 在工单 Agent 页面装配，不在 Tool 页面反向选择 Agent。
- Candidate Diff 展示 Tool 绑定变化。
- Router 使用 Release 中的 Agent 与 Tool 描述进行选择。
- 主模型异常时根据真实 Tool 结果生成确定性降级回答。

### 正式 Release

- 版本：`V0.5.10-work-order-read`
- Release ID：`rel_92d43c98147844979b5c936a3eb03730`
- 代表 Run：`run_7a9e0856d25b452e8bbe0202704beee6`

## 3. V0.5.11：创建、确认与幂等

### 目标

把“我要创建工单”从流程说明升级为真实写入，同时确保确认前不落库、重复确认不重复创建。

### 已完成

- 新增 `create_work_order`。
- 从自然语言提取主题、描述、类别和优先级。
- 新增 Action Gateway 草稿、确认和收据。
- 一次性确认令牌只在浏览器出现，服务端只保存哈希。
- 幂等键防止重复执行。
- 确认动作创建独立 Run，并固定原 Action 的 Release。

### 正式 Release

- 版本：`V0.5.11-work-order-create`
- Release ID：`rel_98359d126d3f4202b3a0e35bd7c2bcef`
- 草稿 Run：`run_eb63354876194ab599ed4b9ac4dce571`
- 确认 Run：`run_bfb5e4f21ab64a239794db14f4bcf3b6`
- Action：`action_68780600b79a4145ab862c6c8b477656`

## 4. V0.5.12：更新、关闭与软删除

### 目标

将修改类操作统一纳入 Action Gateway，并对删除实施更严格的确认与审计。

### 已完成

- 新增 `update_work_order`。
- 新增 `close_work_order`。
- 新增 `delete_work_order`。
- 更新和关闭展示执行前后差异，确认一次后执行。
- 删除确认两次，第一次不写入，第二次设置 `deleted_at`。
- 普通查询隐藏软删除工单，Action 与审计仍保留前后快照。
- 成功、失败、结果未知和取消使用明确状态，不盲目重试。

### 正式 Release

- 版本：`V0.5.12-work-order-write`
- Release ID：`rel_92335d5414a54eb3aeb561367b0027aa`
- 更新 Action：`action_437409132c60488eb4c2a9adb81cd03e`
- 关闭 Action：`action_b4117f9c8f3a413fb1a672e9b11a1300`
- 删除 Action：`action_e2580af2bb554b7caef8404195a50f5b`

## 5. V0.5.13：无限轮人机共驾

### 最终产品决定

本版不采用旧设想中的“一次人工回复”“一次 AI 返回”和“完结会话”。最终规则是：

- 人工回复不限制轮次。
- 共驾没有完结状态。
- “交还 AI”只改变输出权，不代表事项关闭。
- AI 始终待命，恢复后还能再次请求人工。

### 已完成

- 新增共驾会话、事件和员工消息数据表。
- 新增请求、接受、员工连续回复和交还 AI 接口。
- 人工承接期间阻止 AI 输出，但继续记录用户消息。
- 使用乐观版本拒绝并发旧回复。
- 交还 AI 后读取员工消息与摘要，用当前 Active Release 继续承接。
- 模型失败时仍恢复 `AI_ACTIVE`。
- 员工工作台只提供“交还 AI”，不提供结束按钮。

### 正式 Release

- 版本：`V0.5.13-unlimited-codrive`
- Release ID：`rel_191f4cfd72b14a69ab6969e74c775c68`
- 会话：`conv_e4647f87c1d045c38c7c53dc14f9963a`
- 人工期间抑制 AI 的 Run：`run_76fd4048cc1e4c689b9d3425bd4d12cf`
- 第一次交还 AI Run：`run_7d72c0f4fb3a4855b96a7923dcc090e8`
- 第二次交还 AI Run：`run_86063811b4fa43a8a7e5b05584988490`

## 6. 实施顺序

本轮实际按以下顺序完成：

1. 从 V0.5.9 五份文档与补充要求冻结产品边界。
2. 新增工单、Action Gateway 和共驾前向迁移。
3. 实现后端服务、API、Runtime、Trace 和成本规则。
4. 实现用户卡片、员工工作台、Agent Tool 装配和 Release Diff。
5. 在 `19081` 隔离容器创建四个 Release 并执行真实 API 验收。
6. 将回归补充到 40 项测试，隔离源码环境全部通过。
7. 备份正式 SQLite，构建并部署到源环境 `19080`。
8. 在正式环境按 V0.5.10、V0.5.11、V0.5.12、V0.5.13 顺序发布。
9. 对只读查询、创建确认、幂等、更新、关闭、双确认删除和两轮共驾循环执行真实验证。
10. 用最终正式镜像再执行 40 项测试并回填五份文档。
11. 将固定提交 `a50e795`、SQLite 数据和必要配置迁移到 Ubuntu 小主机 `192.168.50.112`。
12. 在目标镜像内重新执行 40 项测试，核对全表数量、Active Release、MCP 和 DeepSeek 连通性，再停止源端 YIAI API。

## 7. 本轮不扩展

- 不增加登录和角色权限系统。
- 不实现真正的多用户隔离，仍使用固定演示用户。
- 不建设员工排队、抢单、会话分配和绩效指标。
- 不增加附件、通知、SLA 或外部工单系统集成。
- 不增加共驾“结束”状态。
- 不让业务页面反向拥有 Agent 绑定编辑权。
- 不为了测试方便而删除历史 Run、Release、Action 或审计事件。

## 8. 后续建议

下一阶段如果继续开发，优先顺序建议为：

1. 引入演示级登录与用户/员工身份，替换固定演示用户。
2. 为 Action Gateway 增加权限策略和操作影响级别，而不是在每个 Tool 内重复实现。
3. 增加员工工作台筛选和未处理提示，但仍保持共驾没有完结状态。
4. 将预置 Tool 注册改为插件化目录，保持 Agent 装配和 Release 发布机制不变。
5. 对真实浏览器的卡片布局、移动端和长消息体验做人工走查。

## 9. 回滚策略

- 代码回滚：目标机当前固定为 Git 提交 `a50e795`；需要产品版本回滚时使用 Git 历史选择目标提交，再重建项目 `api` 服务。
- Release 回滚：平台选择旧 Release 并人工回滚，下一条新消息使用旧快照。
- 数据恢复：目标数据库位于 `/home/wang/apps/yiai-center-v0513/data/yiai-center.sqlite`；源机原数据库和 `D:\Docker\yiai-center\data\yiai-center-migration-20260722.sqlite` 均保留。
- 主机回滚：如目标机出现不可恢复故障，可先停止目标 Compose 项目，再在确认数据版本后重新启动源机 YIAI API；不得让两个实例同时接受写入。
- 前向表保留不会影响旧 Runtime；禁止直接删除业务卷或覆盖历史 Release。
