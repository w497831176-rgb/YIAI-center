const state = {
  tab: "user",
  platformSection: "agents",
  workspace: null,
  messages: [],
  conversations: [],
  conversationId: localStorage.getItem("yiai-conversation-id"),
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

function messageMeta(message) {
  const timestamp = `<time>${formatTime(message.created_at)}</time>`;
  if (message.role !== "assistant") {
    return `<div class="bubble-meta">${timestamp}</div>`;
  }
  const runId = message.run_id;
  const agent = message.agent_id
    ? `<span>垂直 Agent：${escapeHtml(agentName(message.agent_id, message.agent_name))}</span>`
    : "";
  const release = message.release_version
    ? `<span>Release：${escapeHtml(message.release_version)}</span>`
    : "";
  const status = message.run_status
    ? `<span class="status ${message.run_status.toLowerCase()}">${escapeHtml(message.run_status)}</span>`
    : "";
  const detail = runId
    ? `<button class="run-detail-link" data-message-run-id="${escapeHtml(runId)}">查看 Run 详情 →</button>`
    : "";
  return `<div class="bubble-meta">${timestamp}${status}${agent}${release}${detail}</div>`;
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
          ${messageMeta(message)}
        </div>
      </article>`,
    )
    .join("");
}

function userPage() {
  return `<section class="chat-layout">
    ${conversationList()}
    <div class="chat-panel">
      <div class="section-heading">
        <div>
          <span class="eyebrow">USER EXPERIENCE</span>
          <h1>今天想处理什么？</h1>
          <p>每条用户请求创建一个 Run；Router 每次只选择一个垂直 Agent。</p>
        </div>
        <button class="ghost-button" data-action="new-conversation">新对话</button>
      </div>
      <div class="message-list">${messageList()}</div>
      <form class="composer" id="chat-form">
        <textarea id="chat-input" placeholder="输入你的问题…" rows="2" ${
          state.sending ? "disabled" : ""
        }></textarea>
        <button ${state.sending ? "disabled" : ""}>${state.sending ? "运行中" : "发送"}</button>
      </form>
      <p class="privacy-note">隐藏思考内容不展示、不保存；Run 详情只展示可核对的输入、输出和运行事实。</p>
    </div>
  </section>`;
}

function employeePage() {
  return `<section class="placeholder-page">
    <span class="eyebrow">HUMAN COLLABORATION</span>
    <h1>员工工作台</h1>
    <p>人机共驾和工单处理将在后续版本接入真实状态与 Tool。</p>
    <div class="scope-card">
      <strong>当前版本诚实边界</strong>
      <p>V0.5.6 已完成自然语言 Skill；员工队列、工单结果和人工接管仍不使用假数据占位。</p>
    </div>
  </section>`;
}

function releasePanel() {
  return `<div class="platform-content">
    ${panelHeading("VERSIONED CHANGE", "Release 管理", "用卡片查看每个版本的状态和发布动作。只有人工发布或回滚才会改变下一条新消息。", `<button class="primary-button" data-action="new-release">＋ 创建候选版本</button>`)}
    ${state.notice ? `<div class="notice">${escapeHtml(state.notice)}</div>` : ""}
    <div class="management-grid">
      ${state.releases
        .map(
          (release) => `<article class="management-card">
            <div class="management-card-top">${cardIcon("R", release.status === "ACTIVE" ? "green" : "amber")}<span class="status ${release.status.toLowerCase()}">${release.status}</span></div>
            <div class="management-card-title"><h3>${escapeHtml(release.version)}</h3><small>${escapeHtml(release.id)}</small></div>
            <p>${escapeHtml(shortText(release.change_summary, 150))}</p>
            <div class="management-card-meta"><span>创建时间</span><strong>${formatTime(release.created_at)}</strong><span>发布时间</span><strong>${release.published_at ? formatTime(release.published_at) : "尚未发布"}</strong></div>
            <div class="card-actions">
              <button class="secondary" data-release-detail-id="${release.id}">查看变更</button>
              ${
                release.status === "ACTIVE"
                  ? ""
                  : `<button class="secondary" data-release-id="${release.id}" data-release-action="${
                      release.status === "CANDIDATE" ? "publish" : "rollback"
                    }">${release.status === "CANDIDATE" ? "人工发布" : "回滚到此版本"}</button>`
              }
            </div>
          </article>`,
        )
        .join("")}
    </div>
    ${state.releaseEditorOpen ? editorDialog("创建候选 Release", "复制当前 Active 配置并固定本次 Agent 与能力快照。", `<form class="release-form modal-form" id="release-form"><label><span>候选版本名</span><input name="version" placeholder="例如 V0.5.9-next" required /></label><label><span>变更说明</span><textarea name="summary" rows="4" placeholder="说明本次变更内容" required></textarea></label><div class="form-actions"><button>创建候选版本</button><button type="button" class="secondary" data-action="close-release-editor">取消</button></div></form>`, "close-release-editor") : ""}
    ${releaseDiff()}
  </div>`;
}

function releaseDiff() {
  const detail = state.selectedRelease;
  if (!detail) return "";
  const diff = detail.diff || {};
  const body = `<section class="detail-card embedded-detail">
    <div class="trace-summary">
      ${fact("对比 Active", diff.base_release_id || "—")}
      ${fact("新增 Agent", (diff.agents_added || []).map((id) => agentName(id)).join("、") || "无")}
      ${fact("移除 Agent", (diff.agents_removed || []).map((id) => agentName(id)).join("、") || "无")}
      ${fact("基础配置变化 Agent", (diff.agents_changed || []).map((id) => agentName(id)).join("、") || "无")}
      ${fact("能力绑定变化 Agent", (diff.agent_bindings_changed || []).map((id) => agentName(id)).join("、") || "无")}
      ${fact("新增 SkillVersion", (diff.skills_added || []).join("、") || "无")}
      ${fact("移除 SkillVersion", (diff.skills_removed || []).join("、") || "无")}
      ${fact("未变化 SkillVersion", (diff.skills_unchanged || []).join("、") || "无")}
      ${fact("新增 RAGVersion", (diff.rag_added || []).join("、") || "无")}
      ${fact("移除 RAGVersion", (diff.rag_removed || []).join("、") || "无")}
      ${fact("未变化 RAGVersion", (diff.rag_unchanged || []).join("、") || "无")}
      ${fact("新增 MCP Server", (diff.mcp_added || []).join("、") || "无")}
      ${fact("移除 MCP Server", (diff.mcp_removed || []).join("、") || "无")}
      ${fact("配置变更 MCP Server", (diff.mcp_changed || []).join("、") || "无")}
      ${fact("未变化 MCP Server", (diff.mcp_unchanged || []).join("、") || "无")}
    </div>
    <details><summary>查看候选 Release 的 Agent 绑定快照</summary><pre>${escapeHtml(JSON.stringify(diff.agent_binding_snapshot || {}, null, 2))}</pre></details>
  </section>`;
  return editorDialog(`${detail.version} · 变更明细`, "对比当前 Active Release 的 Agent 和能力快照。", body, "close-release-detail", true);
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
        ${presetTools.length ? presetTools.map((tool) => `<label><input type="checkbox" name="tool_ids" value="${escapeHtml(tool.id)}" ${toolIds.has(tool.id) ? "checked" : ""} /> ${escapeHtml(tool.name)}</label>`).join("") : `<div class="run-empty">当前版本没有已登记的预置 Tool，不使用占位 Tool 冒充真实能力。</div>`}
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
    <div class="management-grid">
      ${state.skills.length ? state.skills.map(skillCard).join("") : `<div class="run-empty">还没有 Skill，请点击右上角新增或导入。</div>`}
    </div>
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
    ${panelHeading("RETRIEVAL AUGMENTED GENERATION", "RAG 知识库", "管理可被 Agent 装配的知识文档。每张卡片可编辑、校验、检索测试或停用。", `<button class="primary-button" data-action="new-rag">＋ 新增知识文档</button>`)}
    ${state.notice ? `<div class="notice">${escapeHtml(state.notice)}</div>` : ""}
    <div class="management-grid">
      ${state.ragDocuments.length ? state.ragDocuments.map(ragCard).join("") : `<div class="run-empty">还没有 RAG 知识文档，请点击右上角新增。</div>`}
    </div>
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
    ${panelHeading("REMOTE READ-ONLY TOOLS", "MCP Server", "管理远程连接、只读校验和 Tool 白名单。Tool 与 Agent 的装配只在 Agent 卡片内完成。", `<button class="primary-button" data-action="new-mcp">＋ 新增 MCP Server</button>`)}
    ${state.notice ? `<div class="notice">${escapeHtml(state.notice)}</div>` : ""}
    <div class="management-grid">${state.mcpServers.length ? state.mcpServers.map(mcpCard).join("") : `<div class="run-empty">还没有 MCP Server，请点击右上角新增。</div>`}</div>
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
  return `<section class="run-total">
    <h3>Run 汇总</h3>
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
    ${panelHeading("RUNTIME EVIDENCE", "Run 与 Trace", "每张卡片代表一次真实运行。点击查看详情后，再展开完整 Trace、模型用量和 MCP 快照。")}
    <div class="management-grid run-card-grid">
      ${state.runs.length ? state.runs.map((run) => `<article class="management-card">
        <div class="management-card-top">${cardIcon("→", run.status === "DONE" ? "green" : run.status === "ERROR" ? "red" : "amber")}<span class="status ${run.status.toLowerCase()}">${escapeHtml(run.status)}</span></div>
        <div class="management-card-title"><h3>${escapeHtml(agentName(run.agent_id))}</h3><small>${escapeHtml(run.release_version)}</small></div>
        <p class="endpoint-line">${escapeHtml(run.id)}</p>
        <div class="management-card-meta"><span>开始时间</span><strong>${formatTime(run.started_at)}</strong><span>延迟</span><strong>${run.latency_ms == null ? "运行中" : `${run.latency_ms} ms`}</strong><span>预估成本</span><strong>${formatCny(run.estimated_cost_cny)}</strong></div>
        <div class="card-actions"><button class="secondary" data-run-id="${escapeHtml(run.id)}">查看完整 Trace</button></div>
      </article>`).join("") : `<div class="run-empty">还没有真实 Run。</div>`}
    </div>
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
        <span>后续版本</span>
        <p>Badcase · 成本治理</p>
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
  render();
}

async function selectConversation(conversationId) {
  state.conversationId = conversationId;
  localStorage.setItem("yiai-conversation-id", conversationId);
  state.messages = await api(`/api/conversations/${conversationId}/messages`);
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
      if (state.tab === "user") await loadConversations();
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
  } catch {
    state.notice = "后端暂不可用。";
  }
  render();
}

boot();
