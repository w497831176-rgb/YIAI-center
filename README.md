# YIAI Center

领域无关的 AI 能力装配、运行解释、质量治理和成本治理演示平台。

当前版本：V0.5.5

已经实现：

- 用户、员工、平台管理三个顶层 TAB，无登录和身份系统。
- 不可变 Release、Active Release、Run 固定和只追加 Trace。
- DeepSeek V4-Flash 思考模式流式对话。
- 每次云调用独立记录三类 Token、延迟、单价快照和 Estimated Cost。
- 唯一 Router，每个 Run 只选择一个垂直 Agent。
- 一般客服、投诉客服、工单处理三个默认 Agent。

尚未实现的后续能力会在页面中明确标为“后续版本”，不会用假功能占位。

## 演示部署

1. 复制 `.env.example` 为 `.env`，填写 `DEEPSEEK_API_KEY`。
2. 运行 `docker compose -p yiai-center up -d --build`。
3. 打开 `http://主机地址:19080`。

项目是个人面试演示，不建设生产级权限、高可用、监控平台和复杂发布工程。密钥不得提交到 Git，演示数据库保存在 `data/`。

V0.5 使用 Python 标准库单容器同时提供 API 与原生静态页面，运行时零第三方依赖，减少演示环境的镜像和下载数量。
