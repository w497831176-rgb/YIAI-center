const state = {
  tab: "user",
  platformSection: "release",
  workspace: null,
  messages: [],
  conversations: [],
  conversationId: localStorage.getItem("yiai-conversation-id"),
  sending: false,
  streamTerminal: null,
  run: null,
  releases: [],
  selectedRelease: null,
  skills: [],
  skillImports: [],
  editingSkill: null,
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
    <div class="section-heading compact">
      <div>
        <span class="eyebrow">VERSIONED CHANGE</span>
        <h1>Release 管理</h1>
        <p>保存候选不会影响运行，只有人工发布或回滚会改变下一条新消息。</p>
      </div>
    </div>
    ${state.notice ? `<div class="notice">${escapeHtml(state.notice)}</div>` : ""}
    <form class="release-form" id="release-form">
      <label><span>候选版本名</span><input name="version" placeholder="例如 V0.5.6-demo-2" required /></label>
      <label><span>变更说明</span><input name="summary" placeholder="说明为什么创建这个候选版本" required /></label>
      <button>复制 Active 创建候选</button>
    </form>
    <div class="release-list">
      ${state.releases
        .map(
          (release) => `<article>
            <div>
              <span class="status ${release.status.toLowerCase()}">${release.status}</span>
              <h3>${escapeHtml(release.version)}</h3>
              <p>${escapeHtml(release.change_summary)}</p>
              <small>创建：${formatTime(release.created_at)}${
                release.published_at ? ` · 发布：${formatTime(release.published_at)}` : ""
              }</small>
            </div>
            <div class="card-actions">
              <button class="secondary" data-release-detail-id="${release.id}">查看 Diff</button>
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
    ${releaseDiff()}
  </div>`;
}

function releaseDiff() {
  const detail = state.selectedRelease;
  if (!detail) return "";
  const diff = detail.diff || {};
  return `<section class="detail-card">
    <div class="detail-card-head"><h3>${escapeHtml(detail.version)} · Release Diff</h3><button class="secondary" data-action="close-release-detail">关闭</button></div>
    <div class="trace-summary">
      ${fact("对比 Active", diff.base_release_id || "—")}
      ${fact("新增 SkillVersion", (diff.skills_added || []).join("、") || "无")}
      ${fact("移除 SkillVersion", (diff.skills_removed || []).join("、") || "无")}
      ${fact("未变化 SkillVersion", (diff.skills_unchanged || []).join("、") || "无")}
    </div>
  </section>`;
}

function skillPanel() {
  const current = state.editingSkill;
  const version = current?.current_version || {};
  const checked = new Set(current?.agent_ids || []);
  return `<div class="platform-content">
    <div class="section-heading compact">
      <div><span class="eyebrow">NATURAL LANGUAGE CAPABILITY</span><h1>Skill</h1>
      <p>保存产生不可变 SkillVersion；校验、绑定并随 Release 发布后才进入运行 Prompt。</p></div>
      ${current ? `<button class="ghost-button" data-action="new-skill">新建 Skill</button>` : ""}
    </div>
    ${state.notice ? `<div class="notice">${escapeHtml(state.notice)}</div>` : ""}
    <form class="import-form" id="skill-import-form">
      <label><span>公开 GitHub Skill URL</span><input name="url" type="url" placeholder="https://github.com/owner/repo/tree/main/path" required /></label>
      <button>固定 commit 并安全扫描</button>
    </form>
    ${skillImportAttempts()}
    <form class="capability-form" id="skill-form">
      <label><span>名称</span><input name="name" maxlength="80" value="${escapeHtml(current?.name || "")}" required /></label>
      <label><span>说明</span><input name="description" maxlength="500" value="${escapeHtml(current?.description || "")}" required /></label>
      <label><span>适用条件</span><textarea name="applicability" rows="2" required>${escapeHtml(version.applicability || current?.applicability || "")}</textarea></label>
      <label><span>不适用条件</span><textarea name="non_applicability" rows="2" required>${escapeHtml(version.non_applicability || current?.non_applicability || "")}</textarea></label>
      <label class="full"><span>Skill 正文（完整可读、可编辑）</span><textarea name="content" rows="10" required>${escapeHtml(version.content || "")}</textarea></label>
      <label class="full"><span>输出要求</span><textarea name="output_requirements" rows="3" required>${escapeHtml(version.output_requirements || current?.output_requirements || "")}</textarea></label>
      <fieldset class="full"><legend>绑定垂直 Agent</legend>
        ${[
          ["general-service", "一般客服"],
          ["complaint-service", "投诉客服"],
          ["work-order-service", "工单处理"],
        ].map(([id, name]) => `<label><input type="checkbox" name="agent_ids" value="${id}" ${checked.has(id) ? "checked" : ""} /> ${name}</label>`).join("")}
      </fieldset>
      <div class="form-actions full"><button>${current ? "保存为新版本" : "创建 Draft"}</button>${current ? `<button type="button" class="secondary" data-action="cancel-skill-edit">取消编辑</button>` : ""}</div>
    </form>
    <div class="capability-list">
      ${state.skills.length ? state.skills.map(skillCard).join("") : `<div class="run-empty">还没有 Skill。</div>`}
    </div>
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
        <p>${escapeHtml(item.reason || "扫描通过，已导入为未绑定 Draft。")}</p>
      </article>`,
    )
    .join("")}</section>`;
}

function skillCard(skill) {
  const version = skill.current_version;
  return `<article class="capability-card">
    <div class="capability-card-head"><div><span class="status ${skill.status.toLowerCase()}">${escapeHtml(skill.status)}</span><h3>${escapeHtml(skill.name)}</h3></div><small>v${version.version_number} · ${escapeHtml(version.id)}</small></div>
    <p>${escapeHtml(skill.description)}</p>
    <div class="trace-summary">
      ${fact("绑定 Agent", skill.agent_ids.map((id) => agentName(id)).join("、") || "未绑定")}
      ${fact("内容 Hash", version.content_hash)}
      ${fact("版本数", String(skill.versions.length))}
      ${fact("更新时间", formatTime(skill.updated_at))}
    </div>
    ${skill.validation_errors.length ? `<div class="validation-errors">${skill.validation_errors.map((item) => `<p>${escapeHtml(item)}</p>`).join("")}</div>` : ""}
    <details><summary>查看完整 Skill 正文</summary><pre>${escapeHtml(version.content)}</pre></details>
    <div class="card-actions">
      <button class="secondary" data-skill-action="edit" data-skill-id="${skill.id}">编辑</button>
      <button class="secondary" data-skill-action="validate" data-skill-id="${skill.id}">校验</button>
      <button class="secondary" data-skill-action="disable" data-skill-id="${skill.id}">停用</button>
    </div>
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
    <div class="section-heading compact">
      <div>
        <span class="eyebrow">RUNTIME EVIDENCE</span>
        <h1>Run 与 Trace</h1>
        <p>每个 Trace 步骤显示时间；调用云 API 的步骤内嵌对应成本快照，底部汇总本次 Run。</p>
      </div>
    </div>
    <div class="runs-grid">
      <div class="runs-list">
        ${
          state.runs.length
            ? state.runs
                .map(
                  (run) => `<button data-run-id="${run.id}" class="${
                    detail?.run?.id === run.id ? "selected" : ""
                  }">
                    <span class="status ${run.status.toLowerCase()}">${run.status}</span>
                    <strong>${escapeHtml(agentName(run.agent_id))}</strong>
                    <small>${escapeHtml(run.release_version)}</small>
                    <time>${formatTime(run.started_at)}</time>
                  </button>`,
                )
                .join("")
            : `<div class="run-empty">还没有真实 Run。</div>`
        }
      </div>
      <div class="trace-panel">
        ${detail ? runDetailContent(detail) : `<div class="run-empty">选择一条 Run 查看证据。</div>`}
      </div>
    </div>
  </div>`;
}

function platformPage() {
  return `<section class="platform-layout">
    <aside class="side-nav">
      <span class="eyebrow">CONTROL PLANE</span>
      <button data-platform-section="release" class="${
        state.platformSection === "release" ? "active" : ""
      }">Release</button>
      <button data-platform-section="skills" class="${
        state.platformSection === "skills" ? "active" : ""
      }">Skill</button>
      <button data-platform-section="runs" class="${
        state.platformSection === "runs" ? "active" : ""
      }">Run 与 Trace</button>
      <div class="later-list">
        <span>后续版本</span>
        <p>Agent · RAG · MCP</p>
        <p>Badcase · 成本治理</p>
      </div>
    </aside>
    ${state.platformSection === "release" ? releasePanel() : state.platformSection === "skills" ? skillPanel() : runsPanel()}
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
  document.querySelector("#skill-form")?.addEventListener("submit", saveSkill);
  document.querySelector("#skill-import-form")?.addEventListener("submit", importSkill);
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
    render();
  });
  document.querySelector("[data-action='cancel-skill-edit']")?.addEventListener("click", () => {
    state.editingSkill = null;
    render();
  });
  document.querySelectorAll("[data-run-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedRun = await api(`/api/runs/${button.dataset.runId}`);
      render();
    });
  });
}

async function loadConversations() {
  state.conversations = await api("/api/conversations");
}

async function loadPlatform() {
  if (state.platformSection === "release") {
    state.releases = await api("/api/releases");
  } else if (state.platformSection === "skills") {
    [state.skills, state.skillImports] = await Promise.all([
      api("/api/skills"),
      api("/api/skill-imports"),
    ]);
  } else {
    state.runs = await api("/api/runs");
  }
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
    ? `导入成功并固定 commit ${result.attempt.commit_sha}；Skill 仍是未绑定 Draft。`
    : result.reason || "导入失败，请查看扫描记录。";
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
    agent_ids: form.getAll("agent_ids"),
  };
  const editingId = state.editingSkill?.id;
  await api(editingId ? `/api/skills/${editingId}` : "/api/skills", {
    method: editingId ? "PUT" : "POST",
    body: JSON.stringify(payload),
  });
  state.editingSkill = null;
  state.notice = editingId ? "已保存为新的不可变 SkillVersion，需重新校验并发布。" : "Skill Draft 已创建，尚未影响运行。";
  await loadPlatform();
  render();
}

async function skillAction(skillId, action) {
  if (action === "edit") {
    state.editingSkill = state.skills.find((item) => item.id === skillId) || null;
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
