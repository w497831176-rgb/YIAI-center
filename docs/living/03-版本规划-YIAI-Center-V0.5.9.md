# YIAI Center V0.5.9 版本规划

> 文档版本：V0.5.9
> 创建日期：2026-07-21
> 本次版本目标：修复 Agent 配置缺失与能力绑定归属错误

## 1. 本次只完成

- 新增垂直 Agent 配置页。
- Agent 内配置名称、说明、System Prompt、Skill、RAG、MCP Tool 与预置 Tool。
- 删除 Skill、RAG、MCP 编辑表单中的 Agent 绑定入口。
- 新增 Agent 草稿数据权威和无损迁移。
- Candidate Release 从 Agent 草稿生成能力绑定快照。
- Release Diff 展示 Agent 与绑定变化。
- Runtime 支持新 MCP Tool 级 Agent 绑定并兼容历史快照。
- 完成部署、后端自测、接口冒烟和文档闭环。

## 2. 本次不扩展

- 不新增第四个 Agent。
- 不开发预置业务 Tool 的真实执行器。
- 不改变唯一 Router 规则。
- 不重写 Skill、RAG、MCP 的内容管理和版本机制。
- 不删除旧绑定字段或重算历史 Release。
- 不增加登录、权限、行业模板和生产级运维功能。
- 不以浏览器自动化代替产品负责人的页面体验。

## 3. 实施顺序

### 阶段 A：文档冻结

- 创建 V0.5.9 产品说明。
- 创建 V0.5.9 架构说明。
- 创建 V0.5.9 版本规划。
- 创建 V0.5.9 测试用例，自测记录先标记待执行。

### 阶段 B：后端与迁移

- 新增第六号迁移和 `agent_configs`。
- 从 Active Release 无损迁移现有绑定。
- 新增 Agent API。
- 调整 Skill、RAG、MCP 校验和只读反向关系。
- 改造 Candidate 与 Release Diff。
- 增加 MCP Tool 级 Agent 校验。

### 阶段 C：前端

- 增加 Agent 导航与配置页面。
- 增加四类能力装配区域。
- 从 Skill、RAG、MCP 表单移除 Agent 复选框。
- 资源卡片显示只读使用关系。

### 阶段 D：测试与部署

- 执行迁移与数据保留测试。
- 执行 Agent API 与 Candidate 快照测试。
- 执行 MCP Tool 粒度绑定测试。
- 执行既有测试回归。
- 部署到 `192.168.50.92:19080`。
- 执行真实 HTTP 冒烟和容器重启持久化检查。

### 阶段 E：文档收尾

- 回填 V0.5.9 测试用例中的自测记录。
- 新建 V0.5.9 实际实现说明。
- 重新生成干净的 Word 文档。
- 提交并推送 GitHub。

## 4. 完成条件

- Agent 页面成为唯一绑定编辑入口。
- 现有资源、绑定和历史证据未丢失。
- 新 Candidate 的绑定来源可以由 Agent 草稿解释。
- 发布后的运行继续满足单 Agent、Release 固定和 Trace 可追溯。
- 新测试用例有真实执行记录；未做的页面体验明确标记待产品负责人验证。
