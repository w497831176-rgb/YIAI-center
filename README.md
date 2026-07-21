# YIAI Center

领域无关的 AI 能力装配、运行解释、质量治理和成本治理演示平台。

当前版本：V0.5.9

已经实现：

- 用户、员工、平台管理三个顶层 TAB，无登录和身份系统。
- 不可变 Release、Active Release、Run 固定和只追加 Trace。
- DeepSeek V4-Flash 思考模式流式对话。
- 历史对话、消息时间戳，以及 AI 气泡下方可打开的右侧 Run 详情抽屉。
- Trace 记录用户输入和客服最终回答；每次云调用独立记录三类 Token、延迟、人民币单价快照和人民币 Estimated Cost。
- CloudCallSnap 嵌入对应 Trace 步骤，Run 底部提供人民币汇总。
- 唯一 Router，每个 Run 只选择一个垂直 Agent。
- 一般客服、投诉客服、工单处理三个默认 Agent。
- 自然语言 Skill 的完整创建、编辑、校验、停用、Agent 绑定、不可变 SkillVersion、Release Diff 与运行 Trace。
- 公开 GitHub URL 导入纯文本 Skill：固定 commit、隔离扫描、脚本/可执行内容拒绝，成功后仍是未绑定 Draft。
- RAG 文档粘贴、确定性 Markdown 切片、不可变 RAGVersion、SQLite FTS5/BM25 关键词检索、本地 TF-IDF/LSA 潜语义向量、加权 RRF 混合检索、真实引用、Agent 绑定、Release Diff 与历史 Trace 快照。
- 远程 Streamable HTTP MCP 的连接测试、Tool 清单与读写校验、只读白名单、Agent 绑定、Release 热切换、真实调用、MCP Snap 和历史快照。

尚未实现的后续能力会在页面中明确标为“后续版本”，不会用假功能占位。

## 演示部署

1. 复制 `.env.example` 为 `.env`，填写 `DEEPSEEK_API_KEY`。
2. 运行 `docker compose -p yiai-center up -d --build`。
3. 打开 `http://主机地址:19080`。

项目是个人面试演示，不建设生产级权限、高可用、监控平台和复杂发布工程。密钥不得提交到 Git，演示数据库保存在 `data/`。

V0.5 使用 Python 标准库单容器同时提供 API 与原生静态页面，运行时零第三方依赖，减少演示环境的镜像和下载数量。

独立 MCP Server 不进入 YIAI Center 应用容器或 Compose project。`deployments/mcp/` 仅保存可复现的独立部署材料，平台本身只连接已运行的远程 Endpoint。

## Living Docs

开发前按顺序阅读 `docs/living/` 中的五份动态文档：

1. 产品全局 Y/N。
2. 架构全局 Y/N。
3. 版本规划。
4. 测试用例与自测记录。
5. 实际实现说明。

它们用于防止上下文变长后方向漂移，会随版本和真实验证结果更新。
