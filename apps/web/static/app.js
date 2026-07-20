const state = {
  tab: "user",
  platformSection: "release",
  workspace: null,
  messages: [],
  conversationId: localStorage.getItem("yiai-conversation-id"),
  sending: false,
  run: null,
  route: "",
  releases: [],
  runs: [],
  selectedRun: null,
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

function displayToken(value) {
  return Number.isInteger(value) ? String(value) : "待用量返回";
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
    </div>`;
}

function userPage() {
  const messages =
    state.messages.length === 0
      ? `<div class="empty-state">
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
        </div>`
      : state.messages
          .map(
            (message) => `
              <article class="message ${message.role}">
                <span class="message-role">${message.role === "user" ? "你" : "AI"}</span>
                <div>
                  <p>${escapeHtml(message.content || (state.sending ? "正在生成回答…" : ""))}</p>
                  ${
                    message.release_version
                      ? `<small>${escapeHtml(message.release_version)}${
                          message.agent_id ? ` · ${escapeHtml(message.agent_id)}` : ""
                        }</small>`
                      : ""
                  }
                </div>
              </article>`,
          )
          .join("");

  const run = !state.run
    ? `<div class="run-empty">发送消息后，这里展示真实运行证据。</div>`
    : `<div class="run-facts">
        ${fact("Run", state.run.run_id?.slice(0, 16) || "—")}
        ${fact("Release", state.run.release_version || "—")}
        ${fact("唯一 Agent", state.route || state.run.agent_name || "路由中")}
        ${fact("模型", "deepseek-v4-flash · thinking")}
        ${fact("输入未命中", displayToken(state.run.usage?.prompt_cache_miss_tokens))}
        ${fact("输入命中", displayToken(state.run.usage?.prompt_cache_hit_tokens))}
        ${fact("输出 Token", displayToken(state.run.usage?.completion_tokens))}
        ${fact("总延迟", state.run.latency_ms ? `${state.run.latency_ms} ms` : "运行中")}
        ${fact(
          "Estimated Cost",
          typeof state.run.estimated_cost === "number"
            ? `$${state.run.estimated_cost.toFixed(8)}`
            : "待用量返回",
        )}
      </div>`;

  return `<section class="chat-layout">
    <div class="chat-panel">
      <div class="section-heading">
        <div>
          <span class="eyebrow">USER EXPERIENCE</span>
          <h1>今天想处理什么？</h1>
          <p>每条消息都会创建可追踪的 Run，并由唯一 Router 选择一个 Agent。</p>
        </div>
        <button class="ghost-button" data-action="new-conversation">新对话</button>
      </div>
      <div class="message-list">${messages}</div>
      <form class="composer" id="chat-form">
        <textarea id="chat-input" placeholder="输入你的问题…" rows="2" ${
          state.sending ? "disabled" : ""
        }></textarea>
        <button ${state.sending ? "disabled" : ""}>${state.sending ? "运行中" : "发送"}</button>
      </form>
    </div>
    <aside class="run-panel">
      <span class="eyebrow">CURRENT RUN</span>
      <h2>本轮运行卡</h2>
      ${run}
      <p class="privacy-note">隐藏思考内容不展示、不保存；这里只展示运行事实。</p>
    </aside>
  </section>`;
}

function employeePage() {
  return `<section class="placeholder-page">
    <span class="eyebrow">HUMAN COLLABORATION</span>
    <h1>员工工作台</h1>
    <p>人机共驾和工单处理将在后续版本接入真实状态与 Tool。</p>
    <div class="scope-card">
      <strong>当前版本诚实边界</strong>
      <p>V0.5.5 只完成顶层 TAB 与页面骨架，不伪造员工队列、工单结果和人工接管数据。</p>
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
      <label><span>候选版本名</span><input name="version" placeholder="例如 V0.5.5-demo-2" required /></label>
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
            </div>
            ${
              release.status === "ACTIVE"
                ? ""
                : `<button class="secondary" data-release-id="${release.id}" data-release-action="${
                    release.status === "CANDIDATE" ? "publish" : "rollback"
                  }">${release.status === "CANDIDATE" ? "人工发布" : "回滚到此版本"}</button>`
            }
          </article>`,
        )
        .join("")}
    </div>
  </div>`;
}

function runsPanel() {
  const detail = state.selectedRun;
  return `<div class="platform-content">
    <div class="section-heading compact">
      <div>
        <span class="eyebrow">RUNTIME EVIDENCE</span>
        <h1>Run 与 Trace</h1>
        <p>点击一条 Run 查看只追加事件和逐次云调用 Snap。</p>
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
                    <strong>${escapeHtml(run.agent_id || "路由中")}</strong>
                    <small>${escapeHtml(run.release_version)}</small>
                  </button>`,
                )
                .join("")
            : `<div class="run-empty">还没有真实 Run。</div>`
        }
      </div>
      <div class="trace-panel">
        ${
          !detail
            ? `<div class="run-empty">选择一条 Run 查看证据。</div>`
            : `<div class="trace-summary">
                ${fact("Release", detail.run.release_version)}
                ${fact("唯一 Agent", detail.run.agent_id || "—")}
                ${fact("云调用次数", String(detail.cloud_call_snaps.length))}
                ${fact(
                  "Run 成本",
                  typeof detail.run.estimated_cost === "number"
                    ? `$${detail.run.estimated_cost.toFixed(8)}`
                    : "用量异常",
                )}
              </div>
              <h3>Trace Events</h3>
              <ol class="trace-list">
                ${detail.trace_events
                  .map(
                    (event) => `<li>
                      <span>${event.sequence}</span>
                      <div><strong>${escapeHtml(event.event_type)}</strong>
                      <code>${escapeHtml(JSON.stringify(event.payload))}</code></div>
                    </li>`,
                  )
                  .join("")}
              </ol>
              <h3>CloudCallSnap</h3>
              <div class="snap-list">
                ${detail.cloud_call_snaps
                  .map(
                    (snap) => `<article>
                      <strong>${escapeHtml(snap.phase)} · ${escapeHtml(snap.model)}</strong>
                      <p>miss ${snap.prompt_cache_miss_tokens ?? "null"} · hit ${
                        snap.prompt_cache_hit_tokens ?? "null"
                      } · output ${snap.completion_tokens ?? "null"}</p>
                      <small>${snap.usage_status} · ${snap.latency_ms} ms · ${
                        typeof snap.estimated_cost === "number"
                          ? `$${snap.estimated_cost.toFixed(8)}`
                          : "cost null"
                      }</small>
                    </article>`,
                  )
                  .join("")}
              </div>`
        }
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
      <button data-platform-section="runs" class="${
        state.platformSection === "runs" ? "active" : ""
      }">Run 与 Trace</button>
      <div class="later-list">
        <span>后续版本</span>
        <p>Agent · Skill · RAG · MCP</p>
        <p>Badcase · 成本治理</p>
      </div>
    </aside>
    ${state.platformSection === "release" ? releasePanel() : runsPanel()}
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

function bindEvents() {
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.tab = button.dataset.tab;
      if (state.tab === "platform") await loadPlatform();
      render();
    });
  });

  document.querySelector("[data-action='new-conversation']")?.addEventListener("click", () => {
    localStorage.removeItem("yiai-conversation-id");
    state.conversationId = null;
    state.messages = [];
    state.run = null;
    state.route = "";
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

  document.querySelectorAll("[data-platform-section]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.platformSection = button.dataset.platformSection;
      await loadPlatform();
      render();
    });
  });
  document.querySelector("#release-form")?.addEventListener("submit", createCandidate);
  document.querySelectorAll("[data-release-id]").forEach((button) => {
    button.addEventListener("click", () =>
      changeActive(button.dataset.releaseId, button.dataset.releaseAction),
    );
  });
  document.querySelectorAll("[data-run-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedRun = await api(`/api/runs/${button.dataset.runId}`);
      render();
    });
  });
}

async function loadPlatform() {
  if (state.platformSection === "release") {
    state.releases = await api("/api/releases");
  } else {
    state.runs = await api("/api/runs");
  }
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
  state.sending = true;
  state.route = "";
  state.run = null;
  state.messages.push({ role: "user", content: text });
  state.messages.push({ role: "assistant", content: "" });
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
    state.messages[state.messages.length - 1].content = "连接中断，请稍后重试。";
  } finally {
    state.sending = false;
    render();
  }
}

function handleSseBlock(block) {
  const lines = block.split("\n");
  const eventName = lines.find((line) => line.startsWith("event: "))?.slice(7);
  const dataLine = lines.find((line) => line.startsWith("data: "))?.slice(6);
  if (!eventName || !dataLine) return;
  const data = JSON.parse(dataLine);
  if (eventName === "run_started") {
    state.conversationId = data.conversation_id;
    localStorage.setItem("yiai-conversation-id", data.conversation_id);
    state.run = {
      run_id: data.run_id,
      release_version: data.release_version,
    };
  } else if (eventName === "agent_selected") {
    state.route = data.agent_name;
    state.run = { ...(state.run || {}), ...data };
  } else if (eventName === "delta") {
    state.messages[state.messages.length - 1].content += data.content;
  } else if (eventName === "done") {
    state.run = { ...(state.run || {}), ...data };
  } else if (eventName === "error") {
    state.messages[state.messages.length - 1].content = data.message;
  }
  render();
}

async function boot() {
  try {
    state.workspace = await api("/api/workspace");
    if (state.conversationId) {
      state.messages = await api(`/api/conversations/${state.conversationId}/messages`);
    }
  } catch {
    state.notice = "后端暂不可用。";
  }
  render();
}

boot();
