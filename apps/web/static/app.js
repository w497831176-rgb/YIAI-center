const state = {
  tab: "user",
  userSection: "chat",
  employeeSection: "handoff",
  platformSection: "agents",
  workspace: null,
  messages: [],
  conversations: [],
  conversationId: localStorage.getItem("yiai-conversation-id"),
  userWorkOrders: [],
  employeeWorkOrders: [],
  actions: [],
  employeeActions: [],
  actionTokens: JSON.parse(localStorage.getItem("yiai-action-tokens") || "{}"),
  codriveSession: null,
  codriveSessions: [],
  selectedCodrive: null,
  employeeConversationMessages: [],
  sending: false,
  streamTerminal: null,
  run: null,
  releases: [],
  selectedRelease: null,
  releaseEditorOpen: false,
  agents: [],
  editingAgent: null,
  agentEditorOpen: false,
  skills: [],
  skillImports: [],
  editingSkill: null,
  skillEditorOpen: false,
  skillImportOpen: false,
  ragDocuments: [],
  editingRag: null,
  ragEditorOpen: false,
  testingRag: null,
  ragPreview: null,
  ragQueryResult: null,
  ragDraft: { name: "", tags: ["服务", "规则"], version_note: "", content: "" },
  mcpServers: [],
  editingMcp: null,
  mcpEditorOpen: false,
  testingMcp: null,
  mcpToolResult: null,
  runs: [],
  selectedRun: null,
  drawerRun: null,
  citationOpen: null,
  notice: "",
};

const root = document.querySelector("#root");
const escapeHtml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function formatTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}

function formatCny(value) {
  return typeof value === "number" ? `¥${value.toFixed(8)}` : "用量异常，成本未知";
}

function displayToken(value) {
  return Number.isInteger(value) ? String(value) : "null";
}

function agentName(id, fallback) {
  if (fallback) return fallback;
  const configured = state.agents.find((item) => item.id === id);
  if (configured?.name) return configured.name;
  return (
    {
      "general-service": "一般客服",
      "complaint-service": "投诉客服",
      "work-order-service": "工单处理",
    }[id] ||
    id ||
    "路由中"
  );
}

function fact(label, value) {
  return `<div class="fact"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function panelHeading(eyebrow, title, description, actions = "") {
  return `<div class="section-heading compact platform-heading">
    <div><span class="eyebrow">${escapeHtml(eyebrow)}</span><h1>${escapeHtml(title)}</h1><p>${escapeHtml(description)}</p></div>
    ${actions ? `<div class="heading-actions">${actions}</div>` : ""}
  </div>`;
}

function editorDialog(title, description, body, closeAction, wide = false) {
  return `<div class="editor-backdrop" role="presentation">
    <section class="editor-dialog ${wide ? "wide" : ""}" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}">
      <div class="editor-dialog-head"><div><h2>${escapeHtml(title)}</h2><p>${escapeHtml(description)}</p></div><button type="button" class="icon-button" data-action="${escapeHtml(closeAction)}" aria-label="关闭">×</button></div>
      <div class="editor-dialog-body">${body}</div>
    </section>
  </div>`;
}

function cardIcon(label, tone = "green") {
  return `<span class="management-card-icon ${escapeHtml(tone)}">${escapeHtml(label)}</span>`;
}

function shortText(value, maximum = 120) {
  const text = String(value || "");
  return text.length > maximum ? `${text.slice(0, maximum)}…` : text;
}

function persistActionToken(action) {
  if (action?.confirmation_token) {
    state.actionTokens[action.id] = action.confirmation_token;
  } else if (action && action.status !== "AWAITING_CONFIRMATION") {
    delete state.actionTokens[action.id];
  }
  localStorage.setItem("yiai-action-tokens", JSON.stringify(state.actionTokens));
}

function workOrderStatus(value) {
  return ({ OPEN: "待处理", IN_PROGRESS: "处理中", CLOSED: "已关闭" })[value] || value;
}

function workOrderTable(orders, employee = false) {
  if (!orders.length) return `<div class="run-empty">当前没有可见工单。</div>`;
  return `<div class="table-shell"><table class="data-table work-order-table">
    <thead><tr><th>工单</th><th>状态</th><th>类别 / 优先级</th><th>当前说明</th><th>更新时间</th>${employee ? "<th>操作</th>" : ""}</tr></thead>
    <tbody>${orders.map((order) => `<tr>
      <td><strong>${escapeHtml(order.subject)}</strong><small>${escapeHtml(order.id)}</small></td>
      <td><span class="status ${order.status === "CLOSED" ? "done" : "running"}">${escapeHtml(workOrderStatus(order.status))}</span></td>
      <td>${escapeHtml(order.category)}<small>${escapeHtml(order.priority)}</small></td>
      <td><span class="cell-clamp">${escapeHtml(order.result || order.description || "暂无")}</span></td>
      <td>${formatTime(order.updated_at)}</td>
      ${employee ? `<td><div class="row-actions">${order.status !== "CLOSED" ? `<button class="secondary" data-work-order-action="update" data-work-order-id="${escapeHtml(order.id)}">更新</button><button class="secondary" data-work-order-action="close" data-work-order-id="${escapeHtml(order.id)}">关闭</button>` : ""}<button class="danger-button" data-work-order-action="delete" data-work-order-id="${escapeHtml(order.id)}">删除</button></div></td>` : ""}
    </tr>`).join("")}</tbody>
  </table></div>`;
}

function actionCard(action) {
  const hasToken = Boolean(state.actionTokens[action.id]);
  const confirmLabel = action.tool_name === "delete_work_order"
    ? (action.confirmation_step === 0 ? "第一次确认删除" : "第二次确认并软删除")
    : "确认执行";
  return `<article class="action-card">
    <div class="management-card-top">${cardIcon("✓", action.status === "SUCCEEDED" ? "green" : action.status === "FAILED" ? "red" : "orange")}<span class="status ${action.status.toLowerCase()}">${escapeHtml(action.status)}</span></div>
    <div class="management-card-title"><h3>${escapeHtml(action.tool_name)}</h3><small>${escapeHtml(action.id)}</small></div>
    <div class="action-diff"><span>执行参数</span><pre>${escapeHtml(JSON.stringify(action.payload, null, 2))}</pre>${action.before ? `<span>执行前快照</span><pre>${escapeHtml(JSON.stringify(action.before, null, 2))}</pre>` : ""}</div>
    ${action.receipt ? `<div class="notice">${escapeHtml(action.receipt.message)} ${escapeHtml(action.receipt.work_order_id || "")}</div>` : ""}
    ${action.status === "AWAITING_CONFIRMATION" ? `<p class="section-note">还需确认 ${action.remaining_confirmations} 次。确认令牌只保存在当前浏览器，不进入 Trace 或文档。</p><div class="card-actions"><button data-action-confirm="${escapeHtml(action.id)}" data-action-version="${action.version}" ${hasToken ? "" : "disabled"}>${confirmLabel}</button><button class="secondary" data-action-cancel="${escapeHtml(action.id)}" data-action-version="${action.version}">取消</button></div>${hasToken ? "" : `<p class="validation-errors">当前浏览器没有该草稿的一次性令牌，请取消后重新生成。</p>`}` : ""}
  </article>`;
}

function codriveBanner() {
  const session = state.codriveSession;
  if (!state.conversationId) return `<div class="codrive-banner"><div><strong>人机共驾</strong><p>开始一段对话后，可以随时邀请员工协助。</p></div></div>`;
  if (!session || session.state === "AI_ACTIVE") {
    return `<div class="codrive-banner ai-active"><div><strong>AI 承接中 · 持续待命</strong><p>可以反复进入人机共驾；这里没有“完结”状态。</p></div><button class="secondary" data-action="request-human">邀请员工协助</button></div>`;
  }
  if (session.state === "HANDOFF_REQUESTED") {
    return `<div class="codrive-banner waiting"><div><strong>等待员工接受</strong><p>AI 保持待命，不与员工并发输出；你仍可以继续补充消息。</p></div></div>`;
  }
  if (session.state === "HUMAN_ACTIVE") {
    return `<div class="codrive-banner human-active"><div><strong>员工协同中</strong><p>AI 保持待命。只有员工点击“交还 AI”后，AI 才重新承接。</p></div></div>`;
  }
  return `<div class="codrive-banner waiting"><div><strong>正在交还 AI</strong><p>AI 正读取人工回复和处置摘要，恢复后继续待命。</p></div></div>`;
}

function shell(content) {
  return `
    <div class="app-shell">
      <header class="topbar">
        <div class="brand">
          <span class="brand-mark">Y</span>
          <div><strong>YIAI Center</strong><small>AI 能力装配与运行治理演示</small></div>
        </div>
        <div class="release-pill">
          <span>Active Release</span>
          <strong>${escapeHtml(state.workspace?.active_release_version || "读取中")}</strong>
        </div>
      </header>
      <nav class="tabs" aria-label="顶层导航">
        ${[
          ["user", "用户"],
          ["employee", "员工"],
          ["platform", "平台管理"],
        ]
          .map(
            ([key, label]) =>
              `<button data-tab="${key}" class="${state.tab === key ? "active" : ""}">${label}</button>`,
          )
          .join("")}
      </nav>
      <main>${content}</main>
      ${state.drawerRun ? runDrawer(state.drawerRun) : ""}
      ${citationDialog()}
    </div>`;
}

function conversationList() {
  return `<aside class="conversation-panel">
    <div class="conversation-heading">
      <div><span class="eyebrow">HISTORY</span><h2>历史对话</h2></div>
      <button class="icon-button" data-action="new-conversation" title="新对话">＋</button>
    </div>
    <div class="conversation-list">
      ${
        state.conversations.length
          ? state.conversations
              .map(
                (conversation) => `<button
                  data-conversation-id="${escapeHtml(conversation.id)}"
                  class="${state.conversationId === conversation.id ? "active" : ""}">
                  <strong>${escapeHtml(conversation.title)}</strong>
                  <span>${formatTime(conversation.updated_at)}</span>
                  <small>${conversation.message_count} 条消息</small>
                </button>`,
              )
              .join("")
          : `<div class="history-empty">还没有历史对话</div>`
      }
    </div>
  </aside>`;
}

function citationTags(message) {
  const citations = message.capability_summary?.rag?.citations || [];
  if (!citations.length) return "";
  return `<div class="citation-tags" aria-label="本回答引用的知识切片">
    ${citations.map((item) => `<button type="button" data-citation-run-id="${escapeHtml(message.run_id)}" data-citation-chunk-id="${escapeHtml(item.chunk_id)}" title="打开引用切片：${escapeHtml(item.heading || item.chunk_id)}">${escapeHtml(item.citation)}</button>`).join("")}
  </div>`;
}

function hitChip(tone, label, value, title = "") {
  if (value == null || value === "") return "";
  const full = `${label}：${value}`;
  return `<span class="hit-chip ${escapeHtml(tone)}" title="${escapeHtml(title || full)}"><b>${escapeHtml(label)}</b>${escapeHtml(value)}</span>`;
}

function capabilityHitStrip(message) {
  const summary = message.capability_summary;
  if (!summary) return "";
  const route = summary.route || {};
  const usage = summary.usage || {};
  const skills = summary.skills || [];
  const ragDocuments = summary.rag?.documents || [];
  const mcpCalls = summary.mcp_calls || [];
  const presetTools = summary.preset_tools || [];
  const badcases = summary.badcases || [];
  const evaluation = summary.evaluation;
  const chips = [
    hitChip("agent", "Agent", summary.agent?.name || message.agent_name || message.agent_id),
    hitChip("route", "Router", shortText(route.reason || "已选择唯一垂直 Agent", 46), route.reason),
    ...skills.map((item) => hitChip("skill", "Skill", item.name)),
    ...ragDocuments.map((item) => hitChip("rag", "RAG", item.document_name || item.document_id)),
    ...mcpCalls.map((item) => hitChip("mcp", "MCP", `${item.server_name || item.server_id} / ${item.tool_name} · ${item.status}`)),
    ...presetTools.map((item) => hitChip("tool", "Tool", `${item.tool_name} · ${item.status || "已调用"}`)),
    summary.codrive?.triggered ? hitChip("human", "人机协同", `${summary.codrive.source} · ${shortText(summary.codrive.reason, 30)}`, summary.codrive.reason) : "",
    ...badcases.map((item) => hitChip("badcase", "Badcase", `${item.rule_code} · ${item.status}`)),
    evaluation ? hitChip(evaluation.status === "PASS" ? "evaluation-pass" : "evaluation-warn", "Evaluation", `${evaluation.status} / ${evaluation.score}`) : "",
    hitChip("token-miss", "未命中输入", String(usage.prompt_cache_miss_tokens ?? 0)),
    hitChip("token-hit", "缓存输入", String(usage.prompt_cache_hit_tokens ?? 0)),
    hitChip("token-output", "输出", String(usage.completion_tokens ?? 0)),
    hitChip("cost", "成本", formatCny(summary.estimated_cost_cny)),
    hitChip("release", "Release", message.release_version),
  ].filter(Boolean);
  return `<div class="capability-hit-strip" aria-label="本次回答实际命中的 AI 技术栈">${chips.join("")}</div>`;
}

function citationDialog() {
  const item = state.citationOpen;
  if (!item) return "";
  return editorDialog(
    `RAG 引用切片 · ${item.document_name || item.document_id}`,
    `${item.citation} · ${item.chunk_id} · 不可变版本 ${item.rag_version_id || "—"}`,
    `<section class="citation-detail"><div class="trace-summary">${fact("切片标题", item.heading || "未命名切片")}${fact("混合检索分数", item.hybrid_score ?? "—")}${fact("内容哈希", item.content_hash || "—")}</div><pre>${escapeHtml(item.content || "该历史 Run 未保存切片正文。")}</pre></section>`,
    "close-citation",
    true,
  );
}

function messageMeta(message) {
  const timestamp = `<time>${formatTime(message.created_at)}</time>`;
  if (message.role !== "assistant") {
    return `<div class="bubble-meta">${timestamp}</div>`;
  }
  const runId = message.run_id;
  const status = message.run_status
    ? `<span class="status ${message.run_status.toLowerCase()}">${escapeHtml(message.run_status)}</span>`
    : "";
  const detail = runId
    ? `<button class="run-detail-link" data-message-run-id="${escapeHtml(runId)}">查看 Run 详情 →</button>`
    : "";
  return `<div class="bubble-meta">${timestamp}${status}${detail}</div>`;
}

function messageList() {
  if (state.messages.length === 0) {
    return `<div class="empty-state">
      <div class="empty-icon">AI</div>
      <strong>真实能力，从一条消息开始</strong>
      <p>试试一般咨询、明确投诉，或询问工单处理。</p>
      <div class="suggestions">
        ${["帮我解释一下这个平台", "我要投诉服务体验", "查询我的工单进度"]
          .map(
            (item) =>
              `<button data-suggestion="${escapeHtml(item)}">${escapeHtml(item)}</button>`,
          )
          .join("")}
      </div>
    </div>`;
  }
  return state.messages
    .map(
      (message) => `<article class="message ${message.role}">
        <span class="message-role">${message.role === "user" ? "你" : "AI"}</span>
        <div class="message-body">
          <p>${escapeHtml(message.content || (state.sending ? "正在生成回答…" : ""))}</p>
          ${message.role === "assistant" ? citationTags(message) : ""}
          ${message.role === "assistant" ? capabilityHitStrip(message) : ""}
          ${messageMeta(message)}
        </div>
      </article>`,
    )
    .join("");
}

function roleSubnav(role) {
  const items = role === "user"
    ? [["chat", "AI 对话"], ["workorders", "我的工单"]]
    : [["handoff", "人工接管"], ["workorders", "我的工单"]];
  const current = role === "user" ? state.userSection : state.employeeSection;
  return `<nav class="secondary-nav" aria-label="${role === "user" ? "用户" : "员工"}二级菜单">${items.map(([key, label]) => `<button data-${role}-section="${key}" class="${current === key ? "active" : ""}">${label}</button>`).join("")}</nav>`;
}

function userPage() {
  if (state.userSection === "workorders") {
    return `<section class="role-workspace">${roleSubnav("user")}${panelHeading("MY WORK ORDERS", "我的工单", "以列表查看当前用户可见的真实工单记录。")}${workOrderTable(state.userWorkOrders)}</section>`;
  }
  return `<section class="role-workspace">
    ${roleSubnav("user")}
    <section class="chat-layout">
      ${conversationList()}
      <div class="chat-panel">
        <div class="section-heading">
          <div><span class="eyebrow">AI CONVERSATION</span><h1>今天想处理什么？</h1><p>每条消息固定一个 Release，经 Router 只选择一个垂直 Agent。</p></div>
          <button class="ghost-button" data-action="new-conversation">新对话</button>
        </div>
        ${codriveBanner()}
        <div class="message-list">${messageList()}</div>
        ${state.actions.length ? `<section class="inline-business-section"><div class="subsection-heading"><div><span class="eyebrow">CONFIRM BEFORE WRITE</span><h2>待确认操作</h2></div></div><div class="business-grid">${state.actions.map(actionCard).join("")}</div></section>` : ""}
        <form class="composer" id="chat-form"><textarea id="chat-input" placeholder="输入你的问题…" rows="2" ${state.sending ? "disabled" : ""}></textarea><button ${state.sending ? "disabled" : ""}>${state.sending ? "运行中" : "发送"}</button></form>
        <p class="privacy-note">隐藏思考内容不展示、不保存；气泡摘要和 Run 详情只显示可核对的运行事实。</p>
      </div>
    </section>
  </section>`;
}

function codriveTable() {
  if (!state.codriveSessions.length) return `<div class="run-empty">当前没有人机共驾记录。</div>`;
  return `<div class="table-shell"><table class="data-table"><thead><tr><th>会话</th><th>状态</th><th>请求原因</th><th>最近 Agent</th><th>员工消息</th><th>更新时间</th><th>操作</th></tr></thead><tbody>${state.codriveSessions.map((session) => `<tr>
    <td><strong>${escapeHtml(shortText(session.title || "未命名对话", 42))}</strong><small>${escapeHtml(session.conversation_id)}</small></td>
    <td><span class="status ${session.state.toLowerCase()}">${escapeHtml(session.state)}</span></td>
    <td><span class="cell-clamp">${escapeHtml(session.request_reason || "AI 已承接并持续待命")}</span></td>
    <td>${escapeHtml(agentName(session.last_agent_id))}</td><td>${session.staff_message_count || 0} 条</td><td>${formatTime(session.updated_at)}</td>
    <td><div class="row-actions"><button class="secondary" data-codrive-open="${escapeHtml(session.conversation_id)}">交接包</button>${session.state === "HANDOFF_REQUESTED" ? `<button data-codrive-accept="${escapeHtml(session.conversation_id)}" data-codrive-version="${session.version}">接受</button>` : ""}</div></td>
  </tr>`).join("")}</tbody></table></div>`;
}

function employeePage() {
  const selected = state.selectedCodrive;
  if (state.employeeSection === "workorders") {
    return `<section class="role-workspace">${roleSubnav("employee")}${panelHeading("EMPLOYEE WORK ORDERS", "我的工单", "以列表查看和发起工单操作；写操作仍需统一确认。")}${state.notice ? `<div class="notice">${escapeHtml(state.notice)}</div>` : ""}${workOrderTable(state.employeeWorkOrders, true)}${state.employeeActions.length ? `<section class="employee-section"><div class="subsection-heading"><div><h2>工单操作与回执</h2><p>所有写操作统一进入 Action Gateway。</p></div></div><div class="business-grid">${state.employeeActions.map(actionCard).join("")}</div></section>` : ""}</section>`;
  }
  return `<section class="role-workspace employee-workspace">
    ${roleSubnav("employee")}
    ${panelHeading("HUMAN + AI CO-DRIVING", "人工接管", "列表展示待接管和协同中的会话；人工可多轮回复，交还 AI 不代表完结。")}
    ${state.notice ? `<div class="notice">${escapeHtml(state.notice)}</div>` : ""}
    ${codriveTable()}
    ${selected ? `<section class="codrive-detail">
      <div class="subsection-heading"><div><h2>交接包</h2><p>${escapeHtml(selected.conversation_id)} · ${escapeHtml(selected.state)}</p></div><button class="secondary" data-action="close-codrive-detail">收起</button></div>
      <div class="handoff-facts">${fact("请求方", selected.requested_by || "—")}${fact("请求原因", selected.request_reason || "—")}${fact("处置摘要", selected.handoff_summary || "暂无")}${fact("AI 状态", "始终待命")}</div>
      <div class="handoff-messages">${state.employeeConversationMessages.map((message) => `<article class="message ${message.role}"><span class="message-role">${message.role === "staff" ? "员工" : message.role === "user" ? "用户" : "AI"}</span><div class="message-body"><p>${escapeHtml(message.content)}</p><div class="bubble-meta"><time>${formatTime(message.created_at)}</time></div></div></article>`).join("")}</div>
      ${selected.state === "HUMAN_ACTIVE" ? `<form class="staff-reply-form" id="staff-reply-form" data-conversation-id="${escapeHtml(selected.conversation_id)}" data-version="${selected.version}"><textarea name="content" rows="3" placeholder="员工可以连续回复多轮…" required></textarea><button>发送员工回复</button></form><form class="return-ai-form" id="return-ai-form" data-conversation-id="${escapeHtml(selected.conversation_id)}" data-version="${selected.version}"><textarea name="summary" rows="2" placeholder="处置摘要（可选，AI 会同时读取完整人工消息）"></textarea><button>交还 AI</button></form><p class="section-note">没有“结束会话”按钮。交还后 AI 恢复承接并继续待命，之后仍可再次进入人机共驾。</p>` : ""}
    </section>` : ""}
  </section>`;
}

function releasePanel() {
  return `<div class="platform-content">
    ${panelHeading("VERSIONED CHANGE", "Release 管理", "先查看 Agent 级变化，再展开该 Agent 下 Skill、RAG、MCP 与 Tool 的前后差异。", `<button class="primary-button" data-action="new-release">＋ 创建候选版本</button>`)}
    ${state.notice ? `<div class="notice">${escapeHtml(state.notice)}</div>` : ""}
    <div class="table-shell"><table class="data-table"><thead><tr><th>Release</th><th>状态</th><th>变更说明</th><th>创建 / 发布</th><th>操作</th></tr></thead><tbody>${state.releases.map((release) => `<tr>
      <td><strong>${escapeHtml(release.version)}</strong><small>${escapeHtml(release.id)}</small></td>
      <td><span class="status ${release.status.toLowerCase()}">${release.status}</span></td>
      <td><span class="cell-clamp">${escapeHtml(release.change_summary)}</span></td>
      <td>${formatTime(release.created_at)}<small>${release.published_at ? `发布：${formatTime(release.published_at)}` : "尚未发布"}</small></td>
      <td><div class="row-actions"><button class="secondary" data-release-detail-id="${release.id}">查看分层 Diff</button>${release.status === "ACTIVE" ? "" : `<button class="secondary" data-release-id="${release.id}" data-release-action="${release.status === "CANDIDATE" ? "publish" : "rollback"}">${release.status === "CANDIDATE" ? "人工发布" : "回滚"}</button>`}</div></td>
    </tr>`).join("")}</tbody></table></div>
    ${state.releaseEditorOpen ? editorDialog("创建候选 Release", "复制当前 Active 配置并固定本次 Agent 与能力快照。", `<form class="release-form modal-form" id="release-form"><label><span>候选版本名</span><input name="version" placeholder="例如 V0.5.9-next" required /></label><label><span>变更说明</span><textarea name="summary" rows="4" placeholder="说明本次变更内容" required></textarea></label><div class="form-actions"><button>创建候选版本</button><button type="button" class="secondary" data-action="close-release-editor">取消</button></div></form>`, "close-release-editor") : ""}
    ${releaseDiff()}
  </div>`;
}

function releaseDiff() {
  const detail = state.selectedRelease;
  if (!detail) return "";
  const diff = detail.diff || {};
  const capabilityLabel = { skills: "Skill", rag: "RAG", mcp_tools: "MCP Tool", tools: "预置 Tool" };
  const capabilityDiff = (changes) => Object.entries(changes || {}).map(([key, value]) => `<div class="capability-diff-row"><strong>${capabilityLabel[key] || key}</strong><div class="before-after"><div><span>变更前</span>${(value.before || []).length ? value.before.map((item) => `<code>${escapeHtml(item.name)}<small>${escapeHtml(item.id)}</small></code>`).join("") : `<em>无</em>`}</div><div><span>变更后</span>${(value.after || []).length ? value.after.map((item) => `<code>${escapeHtml(item.name)}<small>${escapeHtml(item.id)}</small></code>`).join("") : `<em>无</em>`}</div></div></div>`).join("");
  const body = `<section class="detail-card embedded-detail release-diff"><div class="trace-summary">${fact("变更前 Active", diff.base_release_id || "—")}${fact("变更后 Release", detail.id)}${fact("Agent 总数", String((diff.agent_changes || []).length))}</div>
    <div class="agent-diff-list">${(diff.agent_changes || []).map((item) => `<details class="agent-diff" ${item.change_type !== "UNCHANGED" ? "open" : ""}><summary><div><strong>${escapeHtml(item.agent_name)}</strong><small>${escapeHtml(item.agent_id)}</small></div><span class="diff-state ${item.change_type.toLowerCase()}">${escapeHtml(item.change_type)}</span></summary><div class="agent-before-after"><div><span>Agent 变更前</span><pre>${escapeHtml(JSON.stringify(item.before || "无", null, 2))}</pre></div><div><span>Agent 变更后</span><pre>${escapeHtml(JSON.stringify(item.after || "无", null, 2))}</pre></div></div><h4>该 Agent 下的能力变化</h4>${capabilityDiff(item.capabilities)}</details>`).join("")}</div>
  </section>`;
  return editorDialog(`${detail.version} · Agent 分层 Diff`, "一级对比 Agent；展开后查看该 Agent 下各类能力的变更前后。", body, "close-release-detail", true);
}

function agentPanel() {
  const current = state.editingAgent;
  const skillIds = new Set(current?.skill_ids || []);
  const ragIds = new Set(current?.rag_document_ids || []);
  const mcpBindings = new Set(
    (current?.mcp_tool_bindings || []).map((item) => `${item.server_id}::${item.tool_name}`),
  );
  const toolIds = new Set(current?.tool_ids || []);
  const validSkills = state.skills.filter((item) => item.status === "VALIDATED");
  const validRag = state.ragDocuments.filter((item) => item.status === "VALIDATED");
  const connectedMcp = state.mcpServers.filter((item) => item.status === "CONNECTED");
  const presetTools = current?.available_preset_tools || [];
  return `<div class="platform-content">
    ${panelHeading("VERTICAL AGENT ASSEMBLY", "垂直 Agent", "每张卡片代表一个可独立发布的业务 Agent。Skill、RAG、MCP Tool 和预置 Tool 都在 Agent 内装配。", `<button class="primary-button" data-action="new-agent">＋ 新增 Agent</button>`)}
    ${state.notice ? `<div class="notice">${escapeHtml(state.notice)}</div>` : ""}
    <div class="management-grid">
      ${state.agents.length ? state.agents.map(agentCard).join("") : `<div class="run-empty">还没有垂直 Agent，请点击右上角新增。</div>`}
    </div>
    ${state.agentEditorOpen ? editorDialog(current ? `配置·${current.name}` : "新增垂直 Agent", "保存的是草稿；创建候选 Release 并人工发布后才影响新消息。", `<form class="capability-form modal-capability-form" id="agent-form" data-agent-id="${escapeHtml(current?.id || "")}">
      <label><span>Agent 名称</span><input name="name" maxlength="80" value="${escapeHtml(current?.name || "")}" required /></label>
      <label><span>稳定 ID</span><input value="${escapeHtml(current?.id || "创建后自动生成")}" disabled /></label>
      <label class="full"><span>业务说明</span><textarea name="description" rows="3" maxlength="500" required>${escapeHtml(current?.description || "")}</textarea></label>
      <label class="full"><span>System Prompt</span><textarea name="system_prompt" rows="8" maxlength="20000" required>${escapeHtml(current?.system_prompt || "")}</textarea></label>
      <fieldset class="full binding-group"><legend>Skill</legend>
        <p>只显示已经校验通过的 Skill；具体不可变版本在创建 Candidate 时固定。</p>
        ${validSkills.length ? validSkills.map((skill) => `<label><input type="checkbox" name="skill_ids" value="${escapeHtml(skill.id)}" ${skillIds.has(skill.id) ? "checked" : ""} /> <strong>${escapeHtml(skill.name)}</strong><small>${escapeHtml(skill.current_version.id)}</small></label>`).join("") : `<div class="run-empty">暂无已校验 Skill。请先在 Skill 页面创建并校验。</div>`}
      </fieldset>
      <fieldset class="full binding-group"><legend>RAG</legend>
        <p>只显示已经校验通过的 RAG 文档。</p>
        ${validRag.length ? validRag.map((document) => `<label><input type="checkbox" name="rag_document_ids" value="${escapeHtml(document.id)}" ${ragIds.has(document.id) ? "checked" : ""} /> <strong>${escapeHtml(document.name)}</strong><small>${escapeHtml(document.current_version.id)}</small></label>`).join("") : `<div class="run-empty">暂无已校验 RAG 文档。请先在 RAG 页面创建并校验。</div>`}
      </fieldset>
      <fieldset class="full binding-group"><legend>MCP Tool</legend>
        <p>按 Tool 绑定，而不是把整个 Server 的所有 Tool 一次性交给 Agent。</p>
        ${connectedMcp.length ? connectedMcp.map((server) => `<div class="binding-server"><strong>${escapeHtml(server.name)}</strong><small>${escapeHtml(server.endpoint)}</small>${(server.allowed_tools || []).map((toolName) => { const key = `${server.id}::${toolName}`; return `<label><input type="checkbox" name="mcp_tool_bindings" value="${escapeHtml(key)}" ${mcpBindings.has(key) ? "checked" : ""} /> ${escapeHtml(toolName)}</label>`; }).join("") || `<div class="run-empty">没有可绑定的只读 Tool。</div>`}</div>`).join("") : `<div class="run-empty">暂无已连接的远程 MCP Server。</div>`}
      </fieldset>
      <fieldset class="full binding-group"><legend>预置 Tool</legend>
        ${presetTools.length ? presetTools.map((tool) => `<label><input type="checkbox" name="tool_ids" value="${escapeHtml(tool.id)}" ${toolIds.has(tool.id) ? "checked" : ""} /> <strong>${escapeHtml(tool.name)}</strong><small>${tool.read_only ? "只读" : "写操作 · 必须确认"} · ${escapeHtml(tool.id)}</small></label>`).join("") : `<div class="run-empty">当前版本没有已登记的预置 Tool，不使用占位 Tool 冒充真实能力。</div>`}
      </fieldset>
      <div class="form-actions full"><button>保存 Agent 草稿</button></div>
    </form>`, "close-agent-editor", true) : ""}
  </div>`;
}

function agentCard(agent) {
  const bindings = agent.bindings || {};
  const capabilities = [
    ...(bindings.skills || []).map((item) => item.name),
    ...(bindings.rag_documents || []).map((item) => item.name),
    ...(bindings.mcp_tools || []).map((item) => `${item.server_name} / ${item.tool_name}`),
    ...(bindings.preset_tools || []).map((item) => item.name),
  ];
  return `<article class="management-card agent-management-card">
    <div class="management-card-top">${cardIcon("A", "purple")}<span class="status draft">配置草稿</span></div>
    <div class="management-card-title"><h3>${escapeHtml(agent.name)}</h3><small>${escapeHtml(agent.id)}</small></div>
    <p>${escapeHtml(shortText(agent.description, 150))}</p>
    <div class="capability-counts"><span><strong>${(agent.skill_ids || []).length}</strong> Skill</span><span><strong>${(agent.rag_document_ids || []).length}</strong> RAG</span><span><strong>${(agent.mcp_tool_bindings || []).length}</strong> MCP Tool</span><span><strong>${(agent.tool_ids || []).length}</strong> Tool</span></div>
    <div class="card-chip-list">${capabilities.length ? capabilities.slice(0, 5).map((item) => `<span>${escapeHtml(item)}</span>`).join("") : `<span class="muted-chip">尚未装配能力</span>`}</div>
    <div class="management-card-meta"><span>更新时间</span><strong>${formatTime(agent.updated_at)}</strong></div>
    <div class="card-actions"><button class="secondary" data-agent-action="edit" data-agent-id="${escapeHtml(agent.id)}">配置</button><button class="danger-button" data-agent-action="delete" data-agent-id="${escapeHtml(agent.id)}">删除草稿</button></div>
  </article>`;
}

function skillPanel() {
  const current = state.editingSkill;
  const version = current?.current_version || {};
  return `<div class="platform-content">
    ${panelHeading("NATURAL LANGUAGE CAPABILITY", "Skill 管理", "创建、导入和校验自然语言能力。校验通过后，再到 Agent 卡片内装配。", `<button class="ghost-button" data-action="open-skill-import">⇧ 从 GitHub 导入</button><button class="primary-button" data-action="new-skill">＋ 新增 Skill</button>`)}
    ${state.notice ? `<div class="notice">${escapeHtml(state.notice)}</div>` : ""}
    ${skillTable()}
    ${state.skillEditorOpen ? editorDialog(current ? `编辑·${current.name}` : "新增 Skill", "编辑已有 Skill 会生成新的不可变版本，不覆盖历史。", `<form class="capability-form modal-capability-form" id="skill-form">
      <label><span>名称</span><input name="name" maxlength="80" value="${escapeHtml(current?.name || "")}" required /></label>
      <label><span>说明</span><input name="description" maxlength="500" value="${escapeHtml(current?.description || "")}" required /></label>
      <label><span>适用条件</span><textarea name="applicability" rows="2" required>${escapeHtml(version.applicability || current?.applicability || "")}</textarea></label>
      <label><span>不适用条件</span><textarea name="non_applicability" rows="2" required>${escapeHtml(version.non_applicability || current?.non_applicability || "")}</textarea></label>
      <label class="full"><span>Skill 正文（完整可读、可编辑）</span><textarea name="content" rows="10" required>${escapeHtml(version.content || "")}</textarea></label>
      <label class="full"><span>输出要求</span><textarea name="output_requirements" rows="3" required>${escapeHtml(version.output_requirements || current?.output_requirements || "")}</textarea></label>
      <div class="form-actions full"><button>${current ? "保存为新版本" : "创建 Skill 草稿"}</button><button type="button" class="secondary" data-action="close-skill-editor">取消</button></div>
    </form>`, "close-skill-editor", true) : ""}
    ${state.skillImportOpen ? editorDialog("从 GitHub 导入 Skill", "系统会固定 commit、扫描文件并保留导入或拒绝记录。", `<form class="import-form modal-form" id="skill-import-form"><label><span>公开 GitHub Skill URL</span><input name="url" type="url" placeholder="https://github.com/owner/repo/tree/main/path" required /></label><button>固定 commit 并安全扫描</button></form>${skillImportAttempts()}`, "close-skill-import", true) : ""}
  </div>`;
}

function skillTable() {
  if (!state.skills.length) return `<div class="run-empty">还没有 Skill，请点击右上角新增或导入。</div>`;
  return `<div class="table-shell"><table class="data-table"><thead><tr><th>Skill</th><th>状态</th><th>适用条件</th><th>装配 Agent</th><th>版本 / 更新</th><th>操作</th></tr></thead><tbody>${state.skills.map((skill) => `<tr>
    <td><strong>${escapeHtml(skill.name)}</strong><small>${escapeHtml(skill.description)}</small></td>
    <td><span class="status ${skill.status.toLowerCase()}">${escapeHtml(skill.status)}</span></td>
    <td><span class="cell-clamp">${escapeHtml(skill.current_version.applicability)}</span></td>
    <td>${(skill.bound_agent_ids || []).map((id) => agentName(id)).join("、") || "暂无"}</td>
    <td>v${skill.current_version.version_number}<small>${formatTime(skill.updated_at)}</small></td>
    <td><div class="row-actions"><button class="secondary" data-skill-action="edit" data-skill-id="${skill.id}">编辑</button><button class="secondary" data-skill-action="validate" data-skill-id="${skill.id}">校验</button><button class="secondary" data-skill-action="disable" data-skill-id="${skill.id}">停用</button></div></td>
  </tr>`).join("")}</tbody></table></div>`;
}

function skillImportAttempts() {
  if (!state.skillImports.length) return "";
  return `<section class="import-results"><h3>最近导入与拒绝记录</h3>${state.skillImports
    .map(
      (item) => `<article>
        <div><span class="status ${item.status.toLowerCase()}">${escapeHtml(item.status)}</span><strong>${escapeHtml(item.repo_url)}</strong></div>
        <p>commit：${escapeHtml(item.commit_sha || "未解析")} · SKILL.md：${escapeHtml(item.skill_path || "未找到")}</p>
        <details><summary>文件清单（${item.file_list.length}）</summary><pre>${escapeHtml(item.file_list.join("\n") || "无")}</pre></details>
        <p>${escapeHtml(item.reason || "扫描通过，已导入为 Draft；校验后请从 Agent 页面装配。")}</p>
      </article>`,
    )
    .join("")}</section>`;
}

function skillCard(skill) {
  const version = skill.current_version;
  return `<article class="management-card">
    <div class="management-card-top">${cardIcon("S", "green")}<span class="status ${skill.status.toLowerCase()}">${escapeHtml(skill.status)}</span></div>
    <div class="management-card-title"><h3>${escapeHtml(skill.name)}</h3><small>v${version.version_number}</small></div>
    <p>${escapeHtml(shortText(skill.description, 150))}</p>
    <div class="card-highlight">${escapeHtml(shortText(version.applicability, 120))}</div>
    <div class="management-card-meta"><span>使用该 Skill 的 Agent</span><strong>${(skill.bound_agent_ids || []).map((id) => agentName(id)).join("、") || "暂无"}</strong><span>版本 / 更新</span><strong>${skill.versions.length} 个版本 · ${formatTime(skill.updated_at)}</strong></div>
    ${skill.validation_errors.length ? `<div class="validation-errors">${skill.validation_errors.map((item) => `<p>${escapeHtml(item)}</p>`).join("")}</div>` : ""}
    <details><summary>查看完整正文与版本信息</summary><pre>${escapeHtml(version.content)}</pre><code>${escapeHtml(version.id)} · ${escapeHtml(version.content_hash)}</code></details>
    <div class="card-actions">
      <button class="secondary" data-skill-action="edit" data-skill-id="${skill.id}">编辑</button>
      <button class="secondary" data-skill-action="validate" data-skill-id="${skill.id}">校验</button>
      <button class="secondary" data-skill-action="disable" data-skill-id="${skill.id}">停用</button>
    </div>
  </article>`;
}

function ragPanel() {
  const preview = state.ragPreview;
  const tested = state.ragQueryResult;
  const draft = state.ragDraft;
  return `<div class="platform-content">
    ${panelHeading("RETRIEVAL AUGMENTED GENERATION", "RAG 知识库", "知识文档适合列表比较；编辑、校验和检索测试从每行操作进入。", `<button class="primary-button" data-action="new-rag">＋ 新增知识文档</button>`)}
    ${state.notice ? `<div class="notice">${escapeHtml(state.notice)}</div>` : ""}
    ${ragTable()}
    ${state.ragEditorOpen ? editorDialog(state.editingRag ? `编辑·${state.editingRag.name}` : "新增 RAG 知识文档", "先预览切片，确认后保存并建立真实本地索引。", `<form class="capability-form modal-capability-form" id="rag-form" data-rag-id="${escapeHtml(state.editingRag?.id || "")}">
      <label><span>文档名称</span><input name="name" maxlength="100" value="${escapeHtml(draft.name)}" required /></label>
      <label><span>标签（逗号分隔）</span><input name="tags" value="${escapeHtml(draft.tags.join(","))}" required /></label>
      <label class="full"><span>版本说明</span><input name="version_note" maxlength="300" value="${escapeHtml(draft.version_note)}" required /></label>
      <label class="full"><span>原始纯文本 / Markdown</span><textarea name="content" rows="14" minlength="500" required>${escapeHtml(draft.content)}</textarea></label>
      <div class="form-actions full"><button>${state.editingRag ? "保存为新版本" : "保存并建立索引"}</button><button type="button" class="secondary" data-action="preview-rag">预览切片</button><button type="button" class="secondary" data-action="close-rag-editor">取消</button></div>
    </form>
    ${preview ? `<section class="detail-card"><h3>切片预览 · ${preview.chunk_count} 段</h3>
      <p>${escapeHtml(preview.keyword_engine)} · ${escapeHtml(preview.embedding_model)} · ${escapeHtml(preview.fusion.name)}</p>
      ${preview.chunks.map((item) => `<details><summary>#${item.ordinal} ${escapeHtml(item.heading)} · ${item.char_count} 字</summary><pre>${escapeHtml(item.content)}</pre></details>`).join("")}</section>` : ""}`, "close-rag-editor", true) : ""}
    ${state.testingRag ? editorDialog(`检索测试·${state.testingRag.name}`, "同时执行 BM25、本地 LSA 向量和加权 RRF 混合检索。", `<form class="import-form modal-form rag-query-form" data-rag-version-id="${escapeHtml(state.testingRag.current_version.id)}"><label><span>可人工核对的问题</span><input name="query" required placeholder="输入检索问题" /></label><button>开始测试</button></form>${tested ? `<section class="detail-card embedded-detail"><h3>真实混合检索结果</h3>
      <p>${escapeHtml(tested.technology.keyword_engine)} · ${escapeHtml(tested.technology.embedding_model)} · ${escapeHtml(tested.technology.fusion.name)}</p>
      ${ragResultColumn("关键词 BM25", tested.keyword_results)}
      ${ragResultColumn("本地 LSA 向量", tested.vector_results)}
      ${ragResultColumn("加权 RRF 混合", tested.hybrid_results)}
    </section>` : ""}`, "close-rag-test", true) : ""}
  </div>`;
}

function ragTable() {
  if (!state.ragDocuments.length) return `<div class="run-empty">还没有 RAG 知识文档，请点击右上角新增。</div>`;
  return `<div class="table-shell"><table class="data-table"><thead><tr><th>知识文档</th><th>状态</th><th>标签</th><th>装配 Agent</th><th>索引</th><th>操作</th></tr></thead><tbody>${state.ragDocuments.map((document) => `<tr>
    <td><strong>${escapeHtml(document.name)}</strong><small>v${document.current_version.version_number} · ${escapeHtml(document.current_version.version_note)}</small></td>
    <td><span class="status ${document.status.toLowerCase()}">${escapeHtml(document.status)}</span></td>
    <td><div class="card-chip-list">${document.tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}</div></td>
    <td>${(document.bound_agent_ids || []).map((id) => agentName(id)).join("、") || "暂无"}</td>
    <td>${document.current_version.chunks.length} 个切片<small>${escapeHtml(document.current_version.keyword_engine)} + ${escapeHtml(document.current_version.embedding_model)}</small></td>
    <td><div class="row-actions"><button class="secondary" data-rag-action="edit" data-rag-id="${document.id}">编辑</button><button class="secondary" data-rag-action="test" data-rag-id="${document.id}">检索测试</button><button class="secondary" data-rag-action="validate" data-rag-id="${document.id}">校验</button><button class="secondary" data-rag-action="disable" data-rag-id="${document.id}">停用</button></div></td>
  </tr>`).join("")}</tbody></table></div>`;
}

function ragResultColumn(title, items) {
  return `<div class="import-results"><h3>${escapeHtml(title)}</h3>${items.length ? items.map((item) => `<article>
    <strong>${escapeHtml(item.heading)} · ${escapeHtml(item.chunk_id)}</strong>
    <p>BM25=${item.keyword_score ?? "—"} · Vector=${item.vector_score ?? "—"} · Hybrid=${item.hybrid_score ?? "—"}</p>
    <p>${escapeHtml(item.content)}</p><code>${escapeHtml(item.citation)}</code>
  </article>`).join("") : `<p>无召回；系统不会生成引用。</p>`}</div>`;
}

function ragCard(document) {
  const version = document.current_version;
  return `<article class="management-card">
    <div class="management-card-top">${cardIcon("R", "blue")}<span class="status ${document.status.toLowerCase()}">${escapeHtml(document.status)}</span></div>
    <div class="management-card-title"><h3>${escapeHtml(document.name)}</h3><small>v${version.version_number}</small></div>
    <div class="card-chip-list">${document.tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}</div>
    <div class="card-highlight">${escapeHtml(shortText(version.version_note, 120))}</div>
    <div class="management-card-meta"><span>使用该 RAG 的 Agent</span><strong>${(document.bound_agent_ids || []).map((id) => agentName(id)).join("、") || "暂无"}</strong><span>索引</span><strong>${version.chunks.length} 个切片 · ${escapeHtml(version.keyword_engine)} + ${escapeHtml(version.embedding_model)}</strong></div>
    ${document.validation_errors.length ? `<div class="validation-errors">${document.validation_errors.map((item) => `<p>${escapeHtml(item)}</p>`).join("")}</div>` : ""}
    <details><summary>查看原文与索引快照</summary><pre>${escapeHtml(version.original_content)}</pre><code>${escapeHtml(version.id)} · ${escapeHtml(version.original_content_hash)}</code></details>
    <div class="card-actions"><button class="secondary" data-rag-action="edit" data-rag-id="${document.id}">编辑</button><button class="secondary" data-rag-action="test" data-rag-id="${document.id}">检索测试</button><button class="secondary" data-rag-action="validate" data-rag-id="${document.id}">校验</button><button class="secondary" data-rag-action="disable" data-rag-id="${document.id}">停用</button></div>
  </article>`;
}

function mcpPanel() {
  const current = state.editingMcp;
  const runtimeConfig = current?.runtime_config || {
    activation_keywords: [], business_instructions: "", required_fields: [],
    clarification_prompt: "", default_arguments: {}, result_paths: [],
  };
  return `<div class="platform-content">
    ${panelHeading("REMOTE READ-ONLY TOOLS", "MCP Server", "Server 数量与连接状态适合列表比较；Tool 与 Agent 的装配仍只在 Agent 内完成。", `<button class="primary-button" data-action="new-mcp">＋ 新增 MCP Server</button>`)}
    ${state.notice ? `<div class="notice">${escapeHtml(state.notice)}</div>` : ""}
    ${mcpTable()}
    ${state.mcpEditorOpen ? editorDialog(current ? `编辑·${current.name}` : "新增 MCP Server", "保存远程 Endpoint 和只读白名单；连接测试通过前不会进入 Release。", `<form class="capability-form modal-capability-form" id="mcp-form">
      <label><span>MCP 名称</span><input name="name" maxlength="120" value="${escapeHtml(current?.name || "")}" required /></label>
      <label><span>Git 源地址</span><input name="git_url" type="url" value="${escapeHtml(current?.git_url || "")}" required /></label>
      <label><span>固定 Commit / Tag / 镜像版本</span><input name="version_ref" value="${escapeHtml(current?.version_ref || "")}" required /></label>
      <label><span>Endpoint</span><input name="endpoint" type="url" value="${escapeHtml(current?.endpoint || "")}" required /></label>
      <label><span>Transport</span><select name="transport"><option value="STREAMABLE_HTTP">STREAMABLE_HTTP</option></select></label>
      <label><span>鉴权类型</span><select name="auth_type"><option value="NONE" ${current?.auth_type === "BEARER" ? "" : "selected"}>NONE</option><option value="BEARER" ${current?.auth_type === "BEARER" ? "selected" : ""}>BEARER</option></select></label>
      <label class="full"><span>Bearer Secret（仅服务端保存，不回显）</span><input name="auth_value" type="password" autocomplete="new-password" /></label>
      <label><span>允许绑定的只读 Tool（逗号或换行）</span><textarea name="allowed_tools" rows="4" required>${escapeHtml((current?.allowed_tools || []).join("\n"))}</textarea></label>
      <label><span>显式只读声明（逗号或换行）</span><textarea name="declared_read_only_tools" rows="4" required>${escapeHtml((current?.declared_read_only_tools || []).join("\n"))}</textarea></label>
      <label class="full"><span>通用运行配置 JSON</span><textarea name="runtime_config" rows="12" required>${escapeHtml(JSON.stringify(runtimeConfig, null, 2))}</textarea></label>
      <div class="form-actions full"><button>${current ? "保存配置" : "创建 MCP 草稿"}</button><button type="button" class="secondary" data-action="close-mcp-editor">取消</button></div>
    </form>`, "close-mcp-editor", true) : ""}
    ${state.testingMcp ? editorDialog(`Tool 测试·${state.testingMcp.name}`, "只能选择白名单内的只读 Tool；本次调用不改变 Release。", `<form class="capability-form modal-capability-form mcp-tool-test-form" data-mcp-id="${escapeHtml(state.testingMcp.id)}"><label><span>白名单 Tool</span><select name="tool_name">${(state.testingMcp.allowed_tools || []).map((name) => `<option>${escapeHtml(name)}</option>`).join("")}</select></label><label class="full"><span>参数 JSON</span><textarea name="arguments" rows="8">{}</textarea></label><div class="form-actions full"><button>实际调用</button></div></form>${state.mcpToolResult ? `<section class="detail-card embedded-detail"><h3>实际调用结果</h3><pre>${escapeHtml(JSON.stringify(state.mcpToolResult, null, 2))}</pre></section>` : ""}`, "close-mcp-test", true) : ""}
  </div>`;
}

function mcpTable() {
  if (!state.mcpServers.length) return `<div class="run-empty">还没有 MCP Server，请点击右上角新增。</div>`;
  return `<div class="table-shell"><table class="data-table"><thead><tr><th>MCP Server</th><th>状态</th><th>Endpoint / 版本</th><th>只读白名单</th><th>装配 Agent</th><th>最近测试</th><th>操作</th></tr></thead><tbody>${state.mcpServers.map((server) => `<tr>
    <td><strong>${escapeHtml(server.name)}</strong><small>${escapeHtml(server.transport)}</small></td>
    <td><span class="status ${server.status.toLowerCase()}">${escapeHtml(server.status)}</span></td>
    <td><span class="cell-clamp">${escapeHtml(server.endpoint)}</span><small>${escapeHtml(server.version_ref)}</small></td>
    <td><div class="card-chip-list">${(server.allowed_tools || []).map((name) => `<span>${escapeHtml(name)}</span>`).join("") || `<span class="muted-chip">无</span>`}</div></td>
    <td>${(server.bound_agent_ids || []).map((id) => agentName(id)).join("、") || "暂无"}</td>
    <td>${formatTime(server.last_test_at)}<small>${server.last_test?.latency_ms != null ? `${server.last_test.latency_ms} ms` : "未测试"}</small></td>
    <td><div class="row-actions"><button class="secondary" data-mcp-action="edit" data-mcp-id="${server.id}">编辑</button><button class="secondary" data-mcp-action="test" data-mcp-id="${server.id}">连接</button><button class="secondary" data-mcp-action="tool" data-mcp-id="${server.id}">Tool</button><button class="secondary" data-mcp-action="disable" data-mcp-id="${server.id}">停用</button></div></td>
  </tr>`).join("")}</tbody></table></div>`;
}

function mcpCard(server) {
  const test = server.last_test || {};
  return `<article class="management-card">
    <div class="management-card-top">${cardIcon("M", "orange")}<span class="status ${server.status.toLowerCase()}">${escapeHtml(server.status)}</span></div>
    <div class="management-card-title"><h3>${escapeHtml(server.name)}</h3><small>${escapeHtml(server.transport)}</small></div>
    <p class="endpoint-line">${escapeHtml(server.endpoint)}</p>
    <div class="card-chip-list">${(server.allowed_tools || []).length ? (server.allowed_tools || []).map((name) => `<span>${escapeHtml(name)}</span>`).join("") : `<span class="muted-chip">暂无可用 Tool</span>`}</div>
    <div class="management-card-meta"><span>固定版本</span><strong>${escapeHtml(server.version_ref)}</strong><span>使用该 Server 的 Agent</span><strong>${(server.bound_agent_ids || []).map((id) => agentName(id)).join("、") || "暂无"}</strong><span>最近测试</span><strong>${formatTime(server.last_test_at)}${test.latency_ms != null ? ` · ${test.latency_ms} ms` : ""}</strong></div>
    <details><summary>Tool 与 Agent 使用关系（只读）</summary><pre>${escapeHtml(JSON.stringify(server.tool_agent_ids || {}, null, 2))}</pre></details>
    ${test.error ? `<div class="validation-errors"><p>${escapeHtml(test.error)}</p></div>` : ""}
    <details><summary>Tool 清单与读写属性</summary><pre>${escapeHtml(JSON.stringify(server.tools || [], null, 2))}</pre></details>
    <details><summary>被拒绝的 Tool（${(server.rejected_tools || []).length}）</summary><pre>${escapeHtml(JSON.stringify(server.rejected_tools || [], null, 2))}</pre></details>
    <details><summary>连接测试完整结果</summary><pre>${escapeHtml(JSON.stringify(test, null, 2))}</pre></details>
    <div class="card-actions"><button class="secondary" data-mcp-action="edit" data-mcp-id="${server.id}">编辑</button><button class="secondary" data-mcp-action="test" data-mcp-id="${server.id}">连接测试</button><button class="secondary" data-mcp-action="tool" data-mcp-id="${server.id}">Tool 测试</button><button class="secondary" data-mcp-action="disable" data-mcp-id="${server.id}">停用</button></div>
  </article>`;
}

const eventLabels = {
  run_started: "Run 开始",
  user_message_received: "收到用户请求",
  release_pinned: "固定 Release",
  cloud_call_started: "云 API 调用开始",
  cloud_call_completed: "云 API 调用完成",
  router_fallback: "Router 兜底",
  route_decision: "Router 决策",
  agent_selected: "选择垂直 Agent",
  skill_considered: "检查已发布 Skill",
  skill_activated: "激活 SkillVersion",
  skill_skipped: "跳过不适用 Skill",
  rag_retrieval_requested: "RAG 检索请求",
  rag_retrieval_completed: "RAG 关键词 / 向量 / 混合召回",
  rag_citation_validation: "RAG 引用校验",
  mcp_input_completeness_check: "MCP 信息完整性检查",
  mcp_input_completeness_completed: "MCP 信息完整性检查完成",
  mcp_input_completeness_failed: "MCP 信息完整性检查失败",
  mcp_clarification_requested: "MCP 集中追问",
  mcp_tool_selected: "MCP Tool 选择",
  mcp_parameters_extracted: "MCP 参数提取",
  mcp_request: "MCP 请求",
  mcp_response: "MCP 响应",
  mcp_binding_rejected: "MCP 绑定拒绝",
  preset_tool_selected: "选择预置 Tool",
  preset_tool_request: "预置 Tool 请求",
  preset_tool_response: "预置 Tool 响应",
  action_draft_information_incomplete: "工单草稿信息检查",
  action_draft_created: "创建工单操作草稿",
  action_confirmation_received: "收到操作确认",
  action_cancel_received: "收到操作取消",
  action_gateway_completed: "Action Gateway 回执",
  codrive_handoff_requested: "发起人机共驾",
  codrive_policy_evaluated: "AI 转人工策略判断",
  codrive_ai_suppressed: "员工持有输出权，AI 待命",
  badcase_detected: "自动捕获 Badcase 候选",
  evaluation_completed: "本 Run 即时 Evaluation",
  cloud_call_failed: "云 API 调用失败并降级",
  assistant_response_completed: "客服回答完成",
  done: "Run 完成",
  error: "Run 失败",
};

function priceLine(pricing) {
  if (!pricing) return "价格快照不可用";
  return `未命中 ¥${Number(pricing.cache_miss_input || 0).toFixed(4)} · 命中 ¥${Number(
    pricing.cache_hit_input || 0,
  ).toFixed(4)} · 输出 ¥${Number(pricing.output || 0).toFixed(4)} / 百万 Token`;
}

function snapCard(snap) {
  const pricing = snap.price_snapshot_cny;
  const rate = pricing?.exchange_rate_snapshot?.rate;
  return `<div class="snap-card">
    <div class="snap-title">
      <strong>CloudCallSnap · ${escapeHtml(snap.phase)}</strong>
      <span class="status ${snap.status === "SUCCEEDED" ? "done" : "error"}">${escapeHtml(
        snap.status,
      )}</span>
    </div>
    <div class="snap-grid">
      ${fact("Provider / 模型", `${snap.provider} / ${snap.model}`)}
      ${fact("调用时间", `${formatTime(snap.request_started_at)} → ${formatTime(snap.response_finished_at)}`)}
      ${fact("输入未命中", displayToken(snap.prompt_cache_miss_tokens))}
      ${fact("输入命中", displayToken(snap.prompt_cache_hit_tokens))}
      ${fact("输出 Token", displayToken(snap.completion_tokens))}
      ${fact("本步延迟", `${snap.latency_ms} ms`)}
      ${fact("本步成本", formatCny(snap.estimated_cost_cny))}
      ${fact("Usage", snap.usage_status)}
    </div>
    <p class="price-snapshot">${escapeHtml(priceLine(pricing))}${
      rate ? ` · 演示汇率快照 1 USD = ${escapeHtml(rate)} CNY` : ""
    }</p>
  </div>`;
}

function mcpSnapCard(snap) {
  return `<div class="snap-card">
    <div class="snap-title"><strong>MCPCallSnap · ${escapeHtml(snap.server_name)}</strong><span class="status ${snap.status === "SUCCESS" ? "done" : "error"}">${escapeHtml(snap.status)}</span></div>
    <div class="snap-grid">
      ${fact("Server / Tool", `${snap.server_name} / ${snap.tool_name}`)}
      ${fact("Git 版本", `${snap.git_url} @ ${snap.version_ref}`)}
      ${fact("Endpoint", snap.endpoint)}${fact("Transport", snap.transport)}
      ${fact("调用时间", `${formatTime(snap.started_at)} → ${formatTime(snap.finished_at)}`)}
      ${fact("延迟", `${snap.latency_ms} ms`)}${fact("结果长度", String(snap.result_length))}
      ${fact("模型 API 成本", formatCny(snap.model_api_cost))}${fact("Release", snap.release_id)}
    </div>
    ${snap.error_message ? `<div class="validation-errors"><p>${escapeHtml(snap.error_message)}</p></div>` : ""}
    <details><summary>请求参数</summary><pre>${escapeHtml(JSON.stringify(snap.request_args, null, 2))}</pre></details>
    <details><summary>返回结果摘要</summary><pre>${escapeHtml(JSON.stringify(snap.result_summary, null, 2))}</pre></details>
  </div>`;
}

function eventPayload(event) {
  const payload = event.payload || {};
  if (event.event_type === "user_message_received") {
    return `<div class="trace-message user-trace"><span>用户输入</span><p>${escapeHtml(
      payload.content,
    )}</p></div>`;
  }
  if (event.event_type === "assistant_response_completed") {
    return `<div class="trace-message assistant-trace"><span>${escapeHtml(
      payload.agent_name || "垂直 Agent",
    )}回答</span><p>${escapeHtml(payload.content)}</p></div>`;
  }
  return `<code>${escapeHtml(JSON.stringify(payload))}</code>`;
}

function messageEvidence(detail) {
  const input = detail.messages?.input;
  const output = detail.messages?.output;
  return `<section class="message-evidence">
    <h3>本次 Run 的输入与输出</h3>
    <p class="section-note">历史 Run 从已保存消息回显；新 Run 同时写入下方 Trace 事件。</p>
    <article>
      <strong>用户输入</strong><time>${formatTime(input?.created_at)}</time>
      <p>${escapeHtml(input?.content || "未找到输入消息")}</p>
    </article>
    <article>
      <strong>${escapeHtml(agentName(output?.agent_id, detail.run.agent_name))}回答</strong>
      <time>${formatTime(output?.created_at)}</time>
      <p>${escapeHtml(output?.content || (detail.run.status === "ERROR" ? "本次 Run 未生成完整回答" : "未找到回答消息"))}</p>
    </article>
  </section>`;
}

function runSummary(detail) {
  const snaps = detail.cloud_call_snaps || [];
  const mcpSnaps = detail.mcp_call_snaps || [];
  const totals = snaps.reduce(
    (sum, snap) => ({
      miss: sum.miss + (Number.isInteger(snap.prompt_cache_miss_tokens) ? snap.prompt_cache_miss_tokens : 0),
      hit: sum.hit + (Number.isInteger(snap.prompt_cache_hit_tokens) ? snap.prompt_cache_hit_tokens : 0),
      output: sum.output + (Number.isInteger(snap.completion_tokens) ? snap.completion_tokens : 0),
    }),
    { miss: 0, hit: 0, output: 0 },
  );
  const capabilitySummary = detail.capability_summary || {};
  const evaluation = capabilitySummary.evaluation;
  return `<section class="run-total">
    <h3>Run 汇总</h3>
    ${capabilityHitStrip({ capability_summary: capabilitySummary, agent_id: detail.run.agent_id, agent_name: capabilitySummary.agent?.name, release_version: detail.run.release_version })}
    <div class="trace-summary">
      ${fact("垂直 Agent", agentName(detail.run.agent_id))}
      ${fact("云 API 调用", String(snaps.length))}
      ${fact("MCP Tool 调用", String(mcpSnaps.length))}
      ${fact("输入未命中", String(totals.miss))}
      ${fact("输入命中", String(totals.hit))}
      ${fact("输出 Token", String(totals.output))}
      ${fact("总延迟", detail.run.latency_ms ? `${detail.run.latency_ms} ms` : "—")}
      ${fact("人民币总成本", formatCny(detail.run.estimated_cost_cny))}
      ${fact("完成时间", formatTime(detail.run.finished_at))}
    </div>
    ${evaluation ? `<section class="evaluation-summary"><div class="subsection-heading"><div><h3>即时 Evaluation · ${escapeHtml(evaluation.status)} / ${evaluation.score}</h3><p>只评估本次 Run 的可观测证据，不包含目标 3 的生命周期闭环。</p></div></div><div class="evaluation-checks">${(evaluation.checks || []).map((item) => `<article><span class="status ${item.status === "PASS" ? "done" : item.status === "FAIL" ? "error" : "running"}">${escapeHtml(item.status)}</span><div><strong>${escapeHtml(item.code)}</strong><p>${escapeHtml(item.explanation)}</p></div></article>`).join("")}</div></section>` : ""}
    ${(capabilitySummary.badcases || []).length ? `<section class="badcase-summary"><h3>本 Run 自动捕获的 Badcase 候选</h3>${capabilitySummary.badcases.map((item) => `<article><strong>${escapeHtml(item.rule_code)}</strong><span class="status running">${escapeHtml(item.status)}</span><pre>${escapeHtml(JSON.stringify(item.evidence, null, 2))}</pre></article>`).join("")}</section>` : ""}
  </section>`;
}

function runDetailContent(detail) {
  const snapById = new Map(
    (detail.cloud_call_snaps || []).map((snap) => [snap.cloud_call_id, snap]),
  );
  return `<div class="run-detail">
    <div class="run-detail-head">
      <div>
        <span class="eyebrow">TRACEABLE RUN</span>
        <h2>${escapeHtml(detail.run.id)}</h2>
        <p>${escapeHtml(detail.run.release_version)} · 开始于 ${formatTime(detail.run.started_at)}</p>
      </div>
      <span class="status ${detail.run.status.toLowerCase()}">${escapeHtml(detail.run.status)}</span>
    </div>
    ${messageEvidence(detail)}
    <section class="trace-section">
      <h3>Trace 执行路径</h3>
      <ol class="trace-list">
        ${detail.trace_events
          .map((event) => {
            const snap = snapById.get(event.payload?.cloud_call_id);
            return `<li>
              <span>${event.sequence}</span>
              <div class="trace-event">
                <div class="trace-event-title">
                  <strong>${escapeHtml(eventLabels[event.event_type] || event.event_type)}</strong>
                  <time>${formatTime(event.created_at)}</time>
                </div>
                ${eventPayload(event)}
                ${snap ? snapCard(snap) : ""}
              </div>
            </li>`;
          })
          .join("")}
      </ol>
    </section>
    ${(detail.mcp_call_snaps || []).length ? `<section class="trace-section"><h3>MCP 调用快照</h3>${detail.mcp_call_snaps.map(mcpSnapCard).join("")}</section>` : ""}
    ${runSummary(detail)}
  </div>`;
}

function runDrawer(detail) {
  return `<div class="drawer-backdrop" data-action="close-drawer"></div>
    <aside class="run-drawer" aria-label="Run 详情">
      <button class="drawer-close" data-action="close-drawer">关闭 ×</button>
      ${runDetailContent(detail)}
    </aside>`;
}

function runsPanel() {
  const detail = state.selectedRun;
  return `<div class="platform-content">
    ${panelHeading("RUNTIME EVIDENCE", "Run 与 Trace", "按时间列表比较每次真实运行的 Agent、能力命中、Evaluation、Token 与成本。")}
    ${state.runs.length ? `<div class="table-shell"><table class="data-table"><thead><tr><th>Run</th><th>Agent / Release</th><th>状态 / Evaluation</th><th>能力命中</th><th>三类 Token</th><th>成本 / 延迟</th><th>操作</th></tr></thead><tbody>${state.runs.map((run) => { const summary = run.capability_summary || {}; const usage = summary.usage || {}; return `<tr>
      <td><strong>${formatTime(run.started_at)}</strong><small>${escapeHtml(run.id)}</small></td>
      <td>${escapeHtml(agentName(run.agent_id))}<small>${escapeHtml(run.release_version)}</small></td>
      <td><span class="status ${run.status.toLowerCase()}">${escapeHtml(run.status)}</span><small>${summary.evaluation ? `${summary.evaluation.status} / ${summary.evaluation.score}` : "尚未评估"}</small></td>
      <td><div class="card-chip-list"><span>${(summary.skills || []).length} Skill</span><span>${summary.rag?.evidence_count || 0} RAG</span><span>${(summary.mcp_calls || []).length} MCP</span><span>${(summary.preset_tools || []).length} Tool</span></div></td>
      <td>未命中 ${usage.prompt_cache_miss_tokens ?? 0}<small>命中 ${usage.prompt_cache_hit_tokens ?? 0} · 输出 ${usage.completion_tokens ?? 0}</small></td>
      <td>${formatCny(run.estimated_cost_cny)}<small>${run.latency_ms == null ? "运行中" : `${run.latency_ms} ms`}</small></td>
      <td><button class="secondary" data-run-id="${escapeHtml(run.id)}">完整 Trace</button></td>
    </tr>`; }).join("")}</tbody></table></div>` : `<div class="run-empty">还没有真实 Run。</div>`}
    ${detail ? editorDialog(`Run 详情·${detail.run.id}`, "展示该次运行固定的 Release、Agent、输入输出、Trace 和成本快照。", runDetailContent(detail), "close-run-detail", true) : ""}
  </div>`;
}

function platformPage() {
  return `<section class="platform-layout">
    <aside class="side-nav">
      <span class="eyebrow">CONTROL PLANE</span>
      <button data-platform-section="agents" class="${
        state.platformSection === "agents" ? "active" : ""
      }">Agent</button>
      <button data-platform-section="release" class="${
        state.platformSection === "release" ? "active" : ""
      }">Release</button>
      <button data-platform-section="skills" class="${
        state.platformSection === "skills" ? "active" : ""
      }">Skill</button>
      <button data-platform-section="rag" class="${
        state.platformSection === "rag" ? "active" : ""
      }">RAG</button>
      <button data-platform-section="mcp" class="${
        state.platformSection === "mcp" ? "active" : ""
      }">MCP</button>
      <button data-platform-section="runs" class="${
        state.platformSection === "runs" ? "active" : ""
      }">Run 与 Trace</button>
      <div class="later-list">
        <span>已并入单次 Run</span>
        <p>Badcase 候选 · Evaluation · Trace · 三类 Token · 人民币成本</p>
      </div>
    </aside>
    ${state.platformSection === "agents" ? agentPanel() : state.platformSection === "release" ? releasePanel() : state.platformSection === "skills" ? skillPanel() : state.platformSection === "rag" ? ragPanel() : state.platformSection === "mcp" ? mcpPanel() : runsPanel()}
  </section>`;
}

function render() {
  const content =
    state.tab === "user"
      ? userPage()
      : state.tab === "employee"
        ? employeePage()
        : platformPage();
  root.innerHTML = shell(content);
  bindEvents();
}

function startNewConversation() {
  localStorage.removeItem("yiai-conversation-id");
  state.conversationId = null;
  state.messages = [];
  state.run = null;
  state.drawerRun = null;
  state.actions = [];
  state.codriveSession = null;
  render();
}

async function selectConversation(conversationId) {
  state.conversationId = conversationId;
  localStorage.setItem("yiai-conversation-id", conversationId);
  state.messages = await api(`/api/conversations/${conversationId}/messages`);
  await loadUserData();
  state.drawerRun = null;
  render();
}

async function openRunDrawer(runId) {
  state.drawerRun = await api(`/api/runs/${runId}`);
  render();
}

function bindEvents() {
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.tab = button.dataset.tab;
      if (state.tab === "platform") await loadPlatform();
      if (state.tab === "user") {
        await loadConversations();
        await loadUserData();
      }
      if (state.tab === "employee") await loadEmployeeData();
      render();
    });
  });

  document.querySelectorAll("[data-user-section]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.userSection = button.dataset.userSection;
      await loadUserData();
      render();
    });
  });
  document.querySelectorAll("[data-employee-section]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.employeeSection = button.dataset.employeeSection;
      await loadEmployeeData();
      render();
    });
  });

  document.querySelectorAll("[data-action='new-conversation']").forEach((button) => {
    button.addEventListener("click", startNewConversation);
  });
  document.querySelectorAll("[data-action='close-drawer']").forEach((button) => {
    button.addEventListener("click", () => {
      state.drawerRun = null;
      render();
    });
  });
  document.querySelectorAll("[data-conversation-id]").forEach((button) => {
    button.addEventListener("click", () => selectConversation(button.dataset.conversationId));
  });
  document.querySelectorAll("[data-message-run-id]").forEach((button) => {
    button.addEventListener("click", () => openRunDrawer(button.dataset.messageRunId));
  });
  document.querySelectorAll("[data-citation-run-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const message = state.messages.find((item) => item.run_id === button.dataset.citationRunId);
      state.citationOpen = (message?.capability_summary?.rag?.citations || []).find(
        (item) => item.chunk_id === button.dataset.citationChunkId,
      ) || null;
      render();
    });
  });
  document.querySelector("[data-action='close-citation']")?.addEventListener("click", () => {
    state.citationOpen = null;
    render();
  });
  document.querySelectorAll("[data-suggestion]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelector("#chat-input").value = button.dataset.suggestion;
      document.querySelector("#chat-input").focus();
    });
  });
  document.querySelector("#chat-input")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      document.querySelector("#chat-form").requestSubmit();
    }
  });
  document.querySelector("#chat-form")?.addEventListener("submit", sendChat);
  document.querySelector("[data-action='request-human']")?.addEventListener("click", requestHuman);
  document.querySelectorAll("[data-action-confirm]").forEach((button) => {
    button.addEventListener("click", () => performAction(button.dataset.actionConfirm, "confirm", Number(button.dataset.actionVersion)));
  });
  document.querySelectorAll("[data-action-cancel]").forEach((button) => {
    button.addEventListener("click", () => performAction(button.dataset.actionCancel, "cancel", Number(button.dataset.actionVersion)));
  });
  document.querySelectorAll("[data-codrive-open]").forEach((button) => {
    button.addEventListener("click", () => openCodrive(button.dataset.codriveOpen));
  });
  document.querySelectorAll("[data-codrive-accept]").forEach((button) => {
    button.addEventListener("click", () => acceptCodrive(button.dataset.codriveAccept, Number(button.dataset.codriveVersion)));
  });
  document.querySelector("[data-action='close-codrive-detail']")?.addEventListener("click", () => {
    state.selectedCodrive = null;
    state.employeeConversationMessages = [];
    render();
  });
  document.querySelector("#staff-reply-form")?.addEventListener("submit", sendStaffReply);
  document.querySelector("#return-ai-form")?.addEventListener("submit", returnToAi);
  document.querySelectorAll("[data-work-order-action]").forEach((button) => {
    button.addEventListener("click", () => createEmployeeAction(button.dataset.workOrderId, button.dataset.workOrderAction));
  });

  document.querySelectorAll("[data-platform-section]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.platformSection = button.dataset.platformSection;
      await loadPlatform();
      render();
    });
  });
  document.querySelector("#release-form")?.addEventListener("submit", createCandidate);
  document.querySelector("#agent-form")?.addEventListener("submit", saveAgent);
  document.querySelector("[data-action='new-agent']")?.addEventListener("click", () => {
    state.editingAgent = null;
    state.agentEditorOpen = true;
    render();
  });
  document.querySelector("[data-action='close-agent-editor']")?.addEventListener("click", () => {
    state.agentEditorOpen = false;
    state.editingAgent = null;
    render();
  });
  document.querySelectorAll("[data-agent-action]").forEach((button) => {
    button.addEventListener("click", () => agentAction(button.dataset.agentId, button.dataset.agentAction));
  });
  document.querySelector("#skill-form")?.addEventListener("submit", saveSkill);
  document.querySelector("#skill-import-form")?.addEventListener("submit", importSkill);
  document.querySelector("#rag-form")?.addEventListener("submit", saveRagDocument);
  document.querySelector("[data-action='preview-rag']")?.addEventListener("click", previewRagDocument);
  document.querySelectorAll("[data-rag-action]").forEach((button) => {
    button.addEventListener("click", () => ragAction(button.dataset.ragId, button.dataset.ragAction));
  });
  document.querySelectorAll(".rag-query-form").forEach((form) => {
    form.addEventListener("submit", testRagRetrieval);
  });
  document.querySelector("#mcp-form")?.addEventListener("submit", saveMcpServer);
  document.querySelectorAll("[data-mcp-action]").forEach((button) => {
    button.addEventListener("click", () => mcpAction(button.dataset.mcpId, button.dataset.mcpAction));
  });
  document.querySelectorAll(".mcp-tool-test-form").forEach((form) => {
    form.addEventListener("submit", testMcpTool);
  });
  document.querySelector("[data-action='new-mcp']")?.addEventListener("click", () => {
    state.editingMcp = null;
    state.mcpEditorOpen = true;
    render();
  });
  document.querySelector("[data-action='close-mcp-editor']")?.addEventListener("click", () => {
    state.editingMcp = null;
    state.mcpEditorOpen = false;
    render();
  });
  document.querySelector("[data-action='close-mcp-test']")?.addEventListener("click", () => {
    state.testingMcp = null;
    state.mcpToolResult = null;
    render();
  });
  document.querySelector("[data-action='new-release']")?.addEventListener("click", () => {
    state.releaseEditorOpen = true;
    render();
  });
  document.querySelector("[data-action='close-release-editor']")?.addEventListener("click", () => {
    state.releaseEditorOpen = false;
    render();
  });
  document.querySelectorAll("[data-release-id]").forEach((button) => {
    button.addEventListener("click", () =>
      changeActive(button.dataset.releaseId, button.dataset.releaseAction),
    );
  });
  document.querySelectorAll("[data-release-detail-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedRelease = await api(`/api/releases/${button.dataset.releaseDetailId}`);
      render();
    });
  });
  document.querySelector("[data-action='close-release-detail']")?.addEventListener("click", () => {
    state.selectedRelease = null;
    render();
  });
  document.querySelectorAll("[data-skill-action]").forEach((button) => {
    button.addEventListener("click", () => skillAction(button.dataset.skillId, button.dataset.skillAction));
  });
  document.querySelector("[data-action='new-skill']")?.addEventListener("click", () => {
    state.editingSkill = null;
    state.skillEditorOpen = true;
    render();
  });
  document.querySelector("[data-action='close-skill-editor']")?.addEventListener("click", () => {
    state.editingSkill = null;
    state.skillEditorOpen = false;
    render();
  });
  document.querySelector("[data-action='open-skill-import']")?.addEventListener("click", () => {
    state.skillImportOpen = true;
    render();
  });
  document.querySelector("[data-action='close-skill-import']")?.addEventListener("click", () => {
    state.skillImportOpen = false;
    render();
  });
  document.querySelector("[data-action='new-rag']")?.addEventListener("click", () => {
    state.editingRag = null;
    state.ragDraft = { name: "", tags: ["服务", "规则"], version_note: "", content: "" };
    state.ragPreview = null;
    state.ragEditorOpen = true;
    render();
  });
  document.querySelector("[data-action='close-rag-editor']")?.addEventListener("click", () => {
    state.editingRag = null;
    state.ragEditorOpen = false;
    state.ragPreview = null;
    render();
  });
  document.querySelector("[data-action='close-rag-test']")?.addEventListener("click", () => {
    state.testingRag = null;
    state.ragQueryResult = null;
    render();
  });
  document.querySelectorAll("[data-run-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedRun = await api(`/api/runs/${button.dataset.runId}`);
      render();
    });
  });
  document.querySelector("[data-action='close-run-detail']")?.addEventListener("click", () => {
    state.selectedRun = null;
    render();
  });
}

async function loadConversations() {
  state.conversations = await api("/api/conversations");
}

async function loadUserData() {
  state.userWorkOrders = await api("/api/work-orders?scope=USER");
  if (!state.conversationId) {
    state.actions = [];
    state.codriveSession = null;
    return;
  }
  [state.actions, state.codriveSession] = await Promise.all([
    api(`/api/actions?conversation_id=${encodeURIComponent(state.conversationId)}`),
    api(`/api/conversations/${encodeURIComponent(state.conversationId)}/codrive`),
  ]);
}

async function loadEmployeeData() {
  [state.employeeWorkOrders, state.codriveSessions, state.employeeActions] = await Promise.all([
    api("/api/work-orders?scope=EMPLOYEE"),
    api("/api/codrive/sessions?include_ai_active=true"),
    api("/api/actions"),
  ]);
  if (state.selectedCodrive) {
    await openCodrive(state.selectedCodrive.conversation_id, false);
  }
}

async function requestHuman() {
  if (!state.conversationId) return;
  state.codriveSession = await api(`/api/conversations/${encodeURIComponent(state.conversationId)}/codrive/request`, {
    method: "POST",
    body: JSON.stringify({
      actor: "USER",
      reason: "用户在对话页面点击邀请员工协助",
      summary: "请阅读完整对话、最近 Run 和未完成操作。",
      expected_version: state.codriveSession?.version,
    }),
  });
  state.notice = "已发起人机共驾；AI 保持待命，员工接受后可以持续多轮回复。";
  render();
}

async function performAction(actionId, operation, version) {
  const body = { expected_version: version };
  if (operation === "confirm") body.confirmation_token = state.actionTokens[actionId] || "";
  const response = await api(`/api/actions/${encodeURIComponent(actionId)}/${operation}`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  persistActionToken(response.action);
  state.notice = response.message;
  if (state.tab === "user") {
    if (state.conversationId) state.messages = await api(`/api/conversations/${state.conversationId}/messages`);
    await loadUserData();
    await loadConversations();
  } else {
    await loadEmployeeData();
  }
  render();
}

async function openCodrive(conversationId, rerender = true) {
  [state.selectedCodrive, state.employeeConversationMessages] = await Promise.all([
    api(`/api/conversations/${encodeURIComponent(conversationId)}/codrive`),
    api(`/api/conversations/${encodeURIComponent(conversationId)}/messages`),
  ]);
  if (rerender) render();
}

async function acceptCodrive(conversationId, version) {
  await api(`/api/conversations/${encodeURIComponent(conversationId)}/codrive/accept`, {
    method: "POST",
    body: JSON.stringify({ expected_version: version }),
  });
  state.notice = "员工已接受协同；现在可以连续回复多轮，AI 保持待命。";
  await loadEmployeeData();
  await openCodrive(conversationId, false);
  render();
}

async function sendStaffReply(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const conversationId = event.currentTarget.dataset.conversationId;
  await api(`/api/conversations/${encodeURIComponent(conversationId)}/codrive/messages`, {
    method: "POST",
    body: JSON.stringify({
      content: form.get("content"),
      expected_version: Number(event.currentTarget.dataset.version),
    }),
  });
  state.notice = "员工回复已保存。可以继续回复，不受轮次限制。";
  await loadEmployeeData();
  await openCodrive(conversationId, false);
  render();
}

async function returnToAi(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const conversationId = event.currentTarget.dataset.conversationId;
  const response = await fetch(`/api/conversations/${encodeURIComponent(conversationId)}/codrive/return-ai/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      summary: form.get("summary"),
      expected_version: Number(event.currentTarget.dataset.version),
    }),
  });
  if (!response.ok || !response.body) throw new Error(await response.text());
  const reader = response.body.getReader();
  while (!(await reader.read()).done) {}
  state.notice = "已交还 AI。AI 已恢复承接并继续待命；之后仍可再次进入人机共驾。";
  await loadEmployeeData();
  await openCodrive(conversationId, false);
  render();
}

async function createEmployeeAction(workOrderId, operation) {
  const order = state.employeeWorkOrders.find((item) => item.id === workOrderId);
  if (!order) return;
  let toolName;
  let payload;
  if (operation === "update") {
    const description = window.prompt("填写要更新的工单描述（只生成草稿，确认后才写入）", order.description);
    if (description == null || !description.trim()) return;
    toolName = "update_work_order";
    payload = { work_order_id: workOrderId, changes: { description: description.trim() } };
  } else if (operation === "close") {
    const result = window.prompt("填写关闭处理结果（只生成草稿，确认后才写入）", order.result || "问题已处理");
    if (result == null || !result.trim()) return;
    toolName = "close_work_order";
    payload = { work_order_id: workOrderId, result: result.trim() };
  } else {
    if (!window.confirm(`为工单 ${workOrderId} 生成软删除草稿吗？生成草稿不会删除，执行仍需两次确认。`)) return;
    toolName = "delete_work_order";
    payload = { work_order_id: workOrderId };
  }
  const action = await api("/api/actions/drafts", {
    method: "POST",
    body: JSON.stringify({
      tool_name: toolName,
      payload,
      release_id: state.workspace.active_release_id,
      idempotency_key: `employee-${toolName}-${workOrderId}-${Date.now()}`,
      actor: "STAFF",
    }),
  });
  persistActionToken(action);
  state.notice = "操作草稿已生成，尚未写入。请在下方确认卡核对。";
  await loadEmployeeData();
  render();
}

async function loadPlatform() {
  if (state.platformSection === "agents") {
    [state.agents, state.skills, state.ragDocuments, state.mcpServers] = await Promise.all([
      api("/api/agents"), api("/api/skills"), api("/api/rag/documents"), api("/api/mcp/servers"),
    ]);
    const editingId = state.editingAgent?.id;
    state.editingAgent = state.agents.find((item) => item.id === editingId) || null;
  } else if (state.platformSection === "release") {
    [state.releases, state.agents] = await Promise.all([
      api("/api/releases"), api("/api/agents"),
    ]);
  } else if (state.platformSection === "skills") {
    [state.skills, state.skillImports] = await Promise.all([
      api("/api/skills"),
      api("/api/skill-imports"),
    ]);
  } else if (state.platformSection === "rag") {
    state.ragDocuments = await api("/api/rag/documents");
  } else if (state.platformSection === "mcp") {
    state.mcpServers = await api("/api/mcp/servers");
  } else {
    [state.runs, state.agents] = await Promise.all([api("/api/runs"), api("/api/agents")]);
  }
}

async function saveAgent(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const mcpToolBindings = form.getAll("mcp_tool_bindings").map((value) => {
    const separator = String(value).indexOf("::");
    return {
      server_id: String(value).slice(0, separator),
      tool_name: String(value).slice(separator + 2),
    };
  }).filter((item) => item.server_id && item.tool_name);
  const agentId = event.currentTarget.dataset.agentId;
  const creating = !agentId;
  await api(creating ? "/api/agents" : `/api/agents/${agentId}`, {
    method: creating ? "POST" : "PUT",
    body: JSON.stringify({
      name: form.get("name"),
      description: form.get("description"),
      system_prompt: form.get("system_prompt"),
      skill_ids: form.getAll("skill_ids"),
      rag_document_ids: form.getAll("rag_document_ids"),
      mcp_tool_bindings: mcpToolBindings,
      tool_ids: form.getAll("tool_ids"),
    }),
  });
  state.agentEditorOpen = false;
  state.editingAgent = null;
  state.notice = creating ? "新 Agent 草稿已创建；请继续创建候选 Release 并人工发布。" : "Agent 草稿已保存；Active Release 未改变。请创建候选 Release、检查变更后人工发布。";
  await loadPlatform();
  render();
}

async function agentAction(agentId, action) {
  if (action === "edit") {
    state.editingAgent = state.agents.find((item) => item.id === agentId) || null;
    state.agentEditorOpen = Boolean(state.editingAgent);
    render();
    return;
  }
  const agent = state.agents.find((item) => item.id === agentId);
  if (!agent || !window.confirm(`确定删除 Agent 草稿“${agent.name}”吗？当前 Active Release 和历史 Run 不会被改写。`)) return;
  await api(`/api/agents/${agentId}`, { method: "DELETE" });
  state.notice = `Agent 草稿“${agent.name}”已删除。Active Release 仍保留原快照，发布新 Release 后才从新消息移除。`;
  await loadPlatform();
  render();
}

function mcpList(value) {
  return String(value || "").split(/[\n,，]/).map((item) => item.trim()).filter(Boolean);
}

async function saveMcpServer(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = {
    name: form.get("name"), git_url: form.get("git_url"), version_ref: form.get("version_ref"),
    endpoint: form.get("endpoint"), transport: form.get("transport"), auth_type: form.get("auth_type"),
    auth_value: form.get("auth_value"), allowed_tools: mcpList(form.get("allowed_tools")),
    declared_read_only_tools: mcpList(form.get("declared_read_only_tools")),
    runtime_config: JSON.parse(form.get("runtime_config")),
  };
  const editingId = state.editingMcp?.id;
  await api(editingId ? `/api/mcp/servers/${editingId}` : "/api/mcp/servers", {
    method: editingId ? "PUT" : "POST", body: JSON.stringify(payload),
  });
  state.editingMcp = null;
  state.mcpEditorOpen = false;
  state.notice = "MCP 配置已保存；连接测试通过并随候选 Release 发布前，不影响在线运行。";
  await loadPlatform(); render();
}

async function mcpAction(serverId, action) {
  if (action === "edit") {
    state.editingMcp = state.mcpServers.find((item) => item.id === serverId) || null;
    state.mcpEditorOpen = Boolean(state.editingMcp);
    render(); return;
  }
  if (action === "tool") {
    state.testingMcp = state.mcpServers.find((item) => item.id === serverId) || null;
    state.mcpToolResult = null;
    render(); return;
  }
  const result = await api(`/api/mcp/servers/${serverId}/${action}`, { method: "POST" });
  state.notice = action === "test"
    ? (result.status === "CONNECTED" ? `连接与 Tool List 成功：允许 ${result.allowed_tools.length} 个只读 Tool，拒绝 ${result.rejected_tools.length} 个 Tool。` : `连接测试失败：${result.last_test?.error || "请查看完整结果"}`)
    : "MCP 已停用并解绑；发布下一 Release 后新消息不再调用，历史 Run 快照保留。";
  await loadPlatform(); render();
}

async function testMcpTool(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  state.mcpToolResult = await api(`/api/mcp/servers/${event.currentTarget.dataset.mcpId}/tool-test`, {
    method: "POST", body: JSON.stringify({
      tool_name: form.get("tool_name"), arguments: JSON.parse(form.get("arguments")),
    }),
  });
  state.notice = "白名单 Tool 已真实调用；结果仅用于连接页测试，不改变 Release。";
  render();
}

function ragFormPayload(formElement) {
  const form = new FormData(formElement);
  return {
    name: form.get("name"),
    tags: String(form.get("tags") || "").split(/[,，]/).map((item) => item.trim()).filter(Boolean),
    version_note: form.get("version_note"),
    content: form.get("content"),
  };
}

async function previewRagDocument() {
  const form = document.querySelector("#rag-form");
  if (!form?.reportValidity()) return;
  const payload = ragFormPayload(form);
  state.ragDraft = payload;
  state.ragPreview = await api("/api/rag/preview", {
    method: "POST",
    body: JSON.stringify({ content: payload.content }),
  });
  state.notice = `预览完成：${state.ragPreview.chunk_count} 个确定性切片；尚未保存或发布。`;
  render();
}

async function saveRagDocument(event) {
  event.preventDefault();
  const editingId = state.editingRag?.id;
  await api(editingId ? `/api/rag/documents/${editingId}` : "/api/rag/documents", {
    method: editingId ? "PUT" : "POST",
    body: JSON.stringify(ragFormPayload(event.currentTarget)),
  });
  state.ragPreview = null;
  state.ragEditorOpen = false;
  state.editingRag = null;
  state.ragDraft = { name: "", tags: ["服务", "规则"], version_note: "", content: "" };
  state.notice = editingId ? "RAG 新版本和本地索引已保存；需重新校验并发布。" : "RAG 草稿与本地索引已创建；校验并发布前不会影响在线运行。";
  await loadPlatform();
  render();
}

async function ragAction(documentId, action) {
  if (action === "edit") {
    const document = state.ragDocuments.find((item) => item.id === documentId);
    if (!document) return;
    state.editingRag = document;
    state.ragDraft = {
      name: document.name,
      tags: document.tags || [],
      version_note: document.current_version.version_note || "",
      content: document.current_version.original_content || "",
    };
    state.ragPreview = null;
    state.ragEditorOpen = true;
    render();
    return;
  }
  if (action === "test") {
    state.testingRag = state.ragDocuments.find((item) => item.id === documentId) || null;
    state.ragQueryResult = null;
    render();
    return;
  }
  const result = await api(`/api/rag/documents/${documentId}/${action}`, { method: "POST" });
  state.notice = action === "validate"
    ? (result.status === "VALIDATED" ? "RAG 校验通过，可进入下一候选 Release。" : "RAG 校验未通过，请查看原因。")
    : "RAG 已停用；发布下一 Release 后在线运行不再使用。";
  await loadPlatform();
  render();
}

async function testRagRetrieval(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  state.ragQueryResult = await api("/api/rag/retrieve", {
    method: "POST",
    body: JSON.stringify({
      rag_version_id: event.currentTarget.dataset.ragVersionId,
      query: form.get("query"),
      limit: 5,
    }),
  });
  state.notice = "已分别执行真实 BM25、真实本地 LSA 向量与加权 RRF 混合检索。";
  render();
}

async function importSkill(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const response = await fetch("/api/skill-imports", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: form.get("url") }),
  });
  const result = await response.json();
  state.notice = response.ok
    ? `导入成功并固定 commit ${result.attempt.commit_sha}；Skill 仍是 Draft，校验后请从 Agent 页面装配。`
    : result.reason || "导入失败，请查看扫描记录。";
  if (response.ok) state.skillImportOpen = false;
  await loadPlatform();
  render();
}

async function saveSkill(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = {
    name: form.get("name"),
    description: form.get("description"),
    applicability: form.get("applicability"),
    non_applicability: form.get("non_applicability"),
    content: form.get("content"),
    output_requirements: form.get("output_requirements"),
  };
  const editingId = state.editingSkill?.id;
  await api(editingId ? `/api/skills/${editingId}` : "/api/skills", {
    method: editingId ? "PUT" : "POST",
    body: JSON.stringify(payload),
  });
  state.editingSkill = null;
  state.skillEditorOpen = false;
  state.notice = editingId ? "已保存为新的不可变 SkillVersion，需重新校验并发布。" : "Skill Draft 已创建，尚未影响运行。";
  await loadPlatform();
  render();
}

async function skillAction(skillId, action) {
  if (action === "edit") {
    state.editingSkill = state.skills.find((item) => item.id === skillId) || null;
    state.skillEditorOpen = Boolean(state.editingSkill);
    render();
    return;
  }
  const result = await api(`/api/skills/${skillId}/${action}`, { method: "POST" });
  state.notice = action === "validate" ? (result.status === "VALIDATED" ? "Skill 校验通过，可进入下一个 Candidate Release。" : "Skill 校验未通过，请查看原因。") : "Skill 已停用；发布下一 Release 后在线运行不再使用。";
  await loadPlatform();
  render();
}

async function createCandidate(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  await api("/api/releases/candidates", {
    method: "POST",
    body: JSON.stringify({
      version: form.get("version"),
      change_summary: form.get("summary"),
    }),
  });
  state.notice = "候选 Release 已创建，尚未影响在线运行。";
  state.releaseEditorOpen = false;
  await loadPlatform();
  render();
}

async function changeActive(releaseId, action) {
  await api(`/api/releases/${releaseId}/${action}`, { method: "POST" });
  state.notice =
    action === "publish"
      ? "已人工发布；下一条新消息使用新 Release。"
      : "已人工回滚；下一条新消息使用恢复的 Release。";
  state.workspace = await api("/api/workspace");
  await loadPlatform();
  render();
}

async function sendChat(event) {
  event.preventDefault();
  const input = document.querySelector("#chat-input");
  const text = input.value.trim();
  if (!text || state.sending) return;
  const now = new Date().toISOString();
  state.sending = true;
  state.streamTerminal = null;
  state.run = null;
  state.messages.push({ role: "user", content: text, created_at: now });
  state.messages.push({ role: "assistant", content: "", created_at: now });
  render();
  try {
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: text, conversation_id: state.conversationId }),
    });
    if (!response.ok || !response.body) throw new Error("连接失败");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";
      for (const block of blocks) handleSseBlock(block);
    }
  } catch {
    state.streamTerminal = "error";
    const message = state.messages[state.messages.length - 1];
    message.content = "连接中断，请稍后重试。";
    message.run_status = "ERROR";
  } finally {
    state.sending = false;
    if (state.conversationId) {
      if (state.streamTerminal === "done") {
        state.messages = await api(`/api/conversations/${state.conversationId}/messages`);
      }
      await loadConversations();
      await loadUserData();
    }
    render();
  }
}

function handleSseBlock(block) {
  const lines = block.split("\n");
  const eventName = lines.find((line) => line.startsWith("event: "))?.slice(7);
  const dataLine = lines.find((line) => line.startsWith("data: "))?.slice(6);
  if (!eventName || !dataLine) return;
  const data = JSON.parse(dataLine);
  const assistant = state.messages[state.messages.length - 1];
  if (eventName === "run_started") {
    state.conversationId = data.conversation_id;
    localStorage.setItem("yiai-conversation-id", data.conversation_id);
    state.run = {
      run_id: data.run_id,
      release_version: data.release_version,
    };
    assistant.run_id = data.run_id;
    assistant.release_version = data.release_version;
    assistant.run_status = "RUNNING";
  } else if (eventName === "agent_selected") {
    state.run = { ...(state.run || {}), ...data };
    assistant.agent_id = data.agent_id;
    assistant.agent_name = data.agent_name;
  } else if (eventName === "delta") {
    assistant.content += data.content;
  } else if (eventName === "action_pending") {
    persistActionToken(data);
  } else if (eventName === "codrive" || eventName === "human_active") {
    state.codriveSession = data;
  } else if (eventName === "done") {
    state.streamTerminal = "done";
    state.run = { ...(state.run || {}), ...data };
    assistant.run_status = "DONE";
  } else if (eventName === "error") {
    state.streamTerminal = "error";
    assistant.content = data.message;
    assistant.run_id = data.run_id || assistant.run_id;
    assistant.run_status = "ERROR";
  }
  render();
}

async function boot() {
  try {
    state.workspace = await api("/api/workspace");
    await loadConversations();
    if (state.conversationId) {
      state.messages = await api(`/api/conversations/${state.conversationId}/messages`);
    }
    await loadUserData();
  } catch {
    state.notice = "后端暂不可用。";
  }
  render();
}

boot();
