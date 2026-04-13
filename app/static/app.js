const linesEl = document.getElementById("lines");
const clearButtonEl = document.getElementById("clear-button");
const appStatusEl = document.getElementById("app-status");
const appDetailEl = document.getElementById("app-detail");
const mcpStatusEl = document.getElementById("mcp-status");
const mcpDetailEl = document.getElementById("mcp-detail");
const transcriberStatusEl = document.getElementById("transcriber-status");
const transcriberDetailEl = document.getElementById("transcriber-detail");
const wsStatusEl = document.getElementById("ws-status");
const wsDetailEl = document.getElementById("ws-detail");
const inputLevelStatusEl = document.getElementById("input-level-status");
const inputLevelDetailEl = document.getElementById("input-level-detail");
const assistantStatusEl = document.getElementById("assistant-status");
const assistantDetailEl = document.getElementById("assistant-detail");
const pipelineStatusEl = document.getElementById("pipeline-status");
const pipelineDetailEl = document.getElementById("pipeline-detail");
const requestsEl = document.getElementById("requests");
const routingHelpEl = document.getElementById("routing-help");
const events = new Map();
const utterances = new Map();
const requests = new Map();
const requestEvents = new Map();
let sendingDraftIds = new Set();
let streamConnected = false;
let assistantProcessing = false;
let currentAssistantProvider = "-";
let currentActiveAgents = [];

function setStatus(el, text, tone) {
  const textEl = el.querySelector(".status-text");
  if (textEl) {
    textEl.textContent = text;
  } else {
    el.textContent = text;
  }
  el.className = `value ${tone}`;
}

function setSpinner(el, active) {
  if (active) {
    el.className = `${el.className} spinning`.trim();
    return;
  }
  el.className = el.className.replace(/\bspinning\b/g, "").replace(/\s+/g, " ").trim();
}

function setDetail(el, text) {
  const lines = Array.isArray(text) ? text : [text];
  el.innerHTML = lines
    .filter((line) => line !== null && line !== undefined && `${line}`.length > 0)
    .map((line) => `<span class="detail-item">${escapeHtml(String(line))}</span>`)
    .join("");
}

function setHtmlDetail(el, html) {
  el.innerHTML = html || "";
}

function renderRoutingHelp(configuredSlots) {
  if (!routingHelpEl) {
    return;
  }
  if (!Array.isArray(configuredSlots) || !configuredSlots.length) {
    setHtmlDetail(
      routingHelpEl,
      "<span class=\"detail-item\">Say the configured slot name first, for example: `Agent 1, ...`</span><span class=\"detail-item\">Targeted requests auto-queue after a short pause. `Queue Now` is only a fallback.</span>",
    );
    return;
  }
  const slotExamples = configuredSlots
    .slice(0, 3)
    .map((slot) => {
      const alias = Array.isArray(slot.aliases) && slot.aliases.length ? slot.aliases[0] : slot.label;
      const label = slot.label || slot.target_agent_name || alias;
      return `${escapeHtml(label)} -> ${escapeHtml(alias)}`;
    })
    .join(" · ");
  setHtmlDetail(
    routingHelpEl,
    `<span class="detail-item">Say the configured slot name first. Slots: ${slotExamples}</span><span class="detail-item">Targeted requests auto-queue after a short pause. \`Queue Now\` is only a fallback.</span>`,
  );
}

function normalizeAgentStatus(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "working") {
    return { label: "working", tone: "warn" };
  }
  if (normalized === "ready") {
    return { label: "ready", tone: "ok" };
  }
  if (normalized === "error") {
    return { label: "error", tone: "bad" };
  }
  return { label: normalized || "unknown", tone: "warn" };
}

function renderTimeline() {
  const ordered = Array.from(events.values()).sort((a, b) => a.created_seq - b.created_seq);
  const assistantRepliesBySourceLineId = buildAssistantRepliesBySourceLineId(ordered);
  const requestEventsByRequestId = buildRequestEventsByRequestId();
  const grouped = groupTimelineEvents(ordered).filter(shouldRenderTimelineEvent);
  if (!grouped.length) {
    linesEl.innerHTML = "";
    return;
  }
  if (assistantProcessing) {
    const activeAgentName = currentAssistantProvider && currentAssistantProvider !== "-"
      ? currentAssistantProvider
      : "Agent";
    grouped.push({
      role: "assistant",
      is_final: false,
      text: "Agent is working...",
      agent_name: activeAgentName,
    });
  }
  linesEl.innerHTML = grouped.map((event) => {
    const utterance = event.role === "user" && Number.isInteger(event.draft_source_line_id)
      ? utterances.get(event.draft_source_line_id)
      : null;
    const request = event.role === "user" && Number.isInteger(event.request_id)
      ? requests.get(event.request_id) || null
      : null;
    const relatedAssistant = event.role === "user" && Number.isInteger(event.draft_source_line_id)
      ? assistantRepliesBySourceLineId.get(event.draft_source_line_id) || null
      : null;
    const relatedRequestEvents = event.role === "user" && Number.isInteger(event.request_id)
      ? requestEventsByRequestId.get(event.request_id) || []
      : [];
    const assistantAgentClass = event.role === "assistant"
      ? agentToneClass(event.agent_name)
      : "";
    const label = event.role === "assistant"
      ? (event.agent_name ? `Assistant · ${escapeHtml(event.agent_name)}` : "Assistant")
      : describeUserEventLabel(event, utterance, relatedAssistant);
    const canQueue = Boolean(
      utterance &&
      utterance.kind === "message" &&
      ["pending", "failed"].includes(utterance.status || "") &&
      Number.isInteger(event.draft_id)
    );
    const actionHtml = canQueue
      ? `<div class="line-actions"><button class="line-button secondary" type="button" data-queue-request-id="${event.draft_id}" ${sendingDraftIds.has(event.draft_id) ? "disabled" : ""}>Queue Now</button></div>`
      : "";
    const requestMetaHtml = event.role === "user" && Number.isInteger(event.request_id)
      ? `<div class="line-submeta">Request ${event.request_id}${request?.target_agent_label ? ` · target ${escapeHtml(request.target_agent_label)}` : ""}${event.source_line_ids.length ? ` · lines ${event.source_line_ids.join(", ")}` : ""}</div>`
      : "";
    const traceHtml = event.role === "user" && relatedRequestEvents.length
      ? `<div class="request-trace">${relatedRequestEvents.map((traceEvent) => {
          const agent = traceEvent.agent_label || traceEvent.agent_name || "Dubsar Voice Relay";
          return `<div class="request-trace-item"><span class="request-trace-kind">${escapeHtml(traceEvent.kind)}</span><span class="request-trace-detail">${escapeHtml(traceEvent.detail)}</span><span class="request-trace-agent">${escapeHtml(agent)}</span></div>`;
        }).join("")}</div>`
      : "";
    return `
      <article class="line ${event.role} ${event.is_final ? "complete" : "pending"} ${assistantAgentClass}">
        <div class="line-head">
          <div class="line-meta">${label}</div>
          ${actionHtml}
        </div>
        ${requestMetaHtml}
        <div class="line-text">${escapeHtml(event.text || "")}</div>
        ${traceHtml}
      </article>
    `;
  }).join("");
  bindLineActions();
  linesEl.scrollTop = linesEl.scrollHeight;
}

function renderRequests() {
  const ordered = orderedRequestsForDisplay();
  const requestEventsByRequestId = buildRequestEventsByRequestId();
  if (!ordered.length) {
    requestsEl.innerHTML = "";
    return;
  }
  requestsEl.innerHTML = ordered.map((request) => {
    const traceEvents = requestEventsByRequestId.get(request.request_id) || [];
    const canQueue = ["pending", "failed"].includes(request.status || "");
    const statusTone = requestStatusTone(request.status);
    const statusLabel = `${formatRequestStatus(request.status)}${request.agent_label ? ` · ${escapeHtml(request.agent_label)}` : ""}${request.target_agent_label ? ` · target ${escapeHtml(request.target_agent_label)}` : ""}`;
    const lineageLabel = [
      request.origin || "speech",
      Number.isInteger(request.parent_request_id) ? `child of ${request.parent_request_id}` : null,
      Array.isArray(request.source_line_ids) && request.source_line_ids.length ? `lines ${request.source_line_ids.join(", ")}` : null,
    ].filter(Boolean).join(" · ");
    return `
      <article class="request-card ${request.parent_request_id ? "child" : "root"}">
        <div class="line-head">
          <div class="line-meta">Request ${request.request_id}</div>
          <div class="line-actions">
            ${canQueue ? `<button class="line-button secondary" type="button" data-queue-request-id="${request.request_id}" ${sendingDraftIds.has(request.request_id) ? "disabled" : ""}>Queue Now</button>` : ""}
          </div>
        </div>
        <div class="line-submeta"><span class="status-chip ${statusTone}">${statusLabel}</span></div>
        ${lineageLabel ? `<div class="line-submeta">${escapeHtml(lineageLabel)}</div>` : ""}
        <div class="line-text">${escapeHtml(request.text || "")}</div>
        ${traceEvents.length ? `<div class="request-trace">${traceEvents.map((traceEvent) => {
          const agent = traceEvent.agent_label || traceEvent.agent_name || "Dubsar Voice Relay";
          return `<div class="request-trace-item"><span class="request-trace-kind">${escapeHtml(traceEvent.kind)}</span><span class="request-trace-detail">${escapeHtml(traceEvent.detail)}</span><span class="request-trace-agent">${escapeHtml(agent)}</span></div>`;
        }).join("")}</div>` : ""}
      </article>
    `;
  }).join("");
  bindLineActions();
}

function orderedRequestsForDisplay() {
  const items = Array.from(requests.values());
  const byParentId = new Map();
  for (const request of items) {
    const parentId = Number.isInteger(request.parent_request_id) ? request.parent_request_id : null;
    if (!byParentId.has(parentId)) {
      byParentId.set(parentId, []);
    }
    byParentId.get(parentId).push(request);
  }
  const sortByCreated = (a, b) => {
    const seqDelta = Number(a.created_seq || 0) - Number(b.created_seq || 0);
    if (seqDelta !== 0) {
      return seqDelta;
    }
    return Number(a.request_id || 0) - Number(b.request_id || 0);
  };
  for (const group of byParentId.values()) {
    group.sort(sortByCreated);
  }
  const ordered = [];
  const visit = (parentId) => {
    for (const request of byParentId.get(parentId) || []) {
      ordered.push(request);
      visit(request.request_id);
    }
  };
  visit(null);
  return ordered;
}

function buildRequestEventsByRequestId() {
  const grouped = new Map();
  const ordered = Array.from(requestEvents.values()).sort((a, b) => a.created_seq - b.created_seq);
  for (const event of ordered) {
    if (!Number.isInteger(event.request_id)) {
      continue;
    }
    if (!grouped.has(event.request_id)) {
      grouped.set(event.request_id, []);
    }
    grouped.get(event.request_id).push(event);
  }
  return grouped;
}

function shouldRenderTimelineEvent(event) {
  if (event.role !== "user") {
    return true;
  }
  if (!event.is_final) {
    return true;
  }
  return !Number.isInteger(event.request_id);
}

function buildAssistantRepliesBySourceLineId(ordered) {
  const replies = new Map();
  for (const event of ordered) {
    if (event.role !== "assistant" || !event.is_final || !Number.isInteger(event.source_line_id)) {
      continue;
    }
    if (event.kind !== "assistant_reply") {
      continue;
    }
    replies.set(event.source_line_id, {
      agent_name: event.agent_name || null,
    });
  }
  return replies;
}

function agentToneClass(agentName) {
  const normalized = String(agentName || "").trim().toLowerCase();
  if (!normalized) {
    return "";
  }
  if (normalized.includes("claude")) {
    return "agent-claude";
  }
  if (normalized.includes("openai") || normalized.includes("chatgpt")) {
    return "agent-chatgpt";
  }
  if (normalized.includes("gemini")) {
    return "agent-gemini";
  }
  return "agent-other";
}

function groupTimelineEvents(ordered) {
  const grouped = [];
  for (const event of ordered) {
    const utterance = Number.isInteger(event.source_line_id)
      ? utterances.get(event.source_line_id)
      : null;
    const previous = grouped[grouped.length - 1];
    const canMerge =
      previous &&
      previous.role === "user" &&
      event.role === "user" &&
      previous.is_final &&
      event.is_final &&
      utterance &&
      utterance.kind === "message" &&
      Number.isInteger(utterance.draft_id) &&
      previous.draft_id === utterance.draft_id;
    if (canMerge) {
      previous.text = `${previous.text} ${event.text}`.replace(/\s+/g, " ").trim();
      previous.updated_seq = event.updated_seq;
      previous.source_line_id = event.source_line_id;
      previous.source_line_ids.push(event.source_line_id);
      continue;
    }
    grouped.push({
      ...event,
      draft_id: utterance ? utterance.draft_id : null,
      request_id: utterance ? (utterance.request_id ?? utterance.draft_id) : null,
      draft_source_line_id: Number.isInteger(event.source_line_id) ? event.source_line_id : null,
      source_line_ids: Number.isInteger(event.source_line_id) ? [event.source_line_id] : [],
    });
  }
  return grouped;
}

function describeUserEventLabel(event, utterance, relatedAssistant) {
  if (!event.is_final) {
    return "You · live";
  }
  if (!utterance) {
    return "You";
  }
  const status = utterance.status || "pending";
  if (status === "processing") {
    return `You · processing · Request ${utterance.request_id ?? utterance.draft_id}${utterance.agent_label ? ` · ${escapeHtml(utterance.agent_label)}` : ""}`;
  }
  if (status === "completed" && relatedAssistant?.agent_name) {
    return `You · completed · Request ${utterance.request_id ?? utterance.draft_id} · ${escapeHtml(relatedAssistant.agent_name)}`;
  }
  if (status === "completed") {
    return `You · completed · Request ${utterance.request_id ?? utterance.draft_id}${utterance.agent_label ? ` · ${escapeHtml(utterance.agent_label)}` : ""}`;
  }
  if (status === "failed") {
    return `You · failed · Request ${utterance.request_id ?? utterance.draft_id}${utterance.agent_label ? ` · ${escapeHtml(utterance.agent_label)}` : ""}`;
  }
  if (status === "claimed") {
    return `You · claimed · Request ${utterance.request_id ?? utterance.draft_id}${utterance.agent_label ? ` · ${escapeHtml(utterance.agent_label)}` : ""}`;
  }
  if (status === "queued") {
    return `You · queued · Request ${utterance.request_id ?? utterance.draft_id}`;
  }
  return `You · request ${utterance.request_id ?? utterance.draft_id}`;
}

function formatRequestStatus(status) {
  const normalized = String(status || "pending").trim().toLowerCase();
  if (normalized === "pending") {
    return "listening";
  }
  if (normalized === "queued") {
    return "queued";
  }
  if (normalized === "claimed") {
    return "working";
  }
  if (normalized === "completed") {
    return "completed";
  }
  if (normalized === "failed") {
    return "failed";
  }
  return normalized || "unknown";
}

function requestStatusTone(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "completed") {
    return "ok";
  }
  if (normalized === "failed") {
    return "bad";
  }
  if (normalized === "queued" || normalized === "claimed") {
    return "warn";
  }
  return "muted";
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function bindLineActions() {
  for (const button of linesEl.querySelectorAll("[data-queue-request-id]")) {
    button.addEventListener("click", () => {
      const requestId = Number(button.dataset.queueRequestId);
      if (Number.isInteger(requestId)) {
        queueRequestNow(requestId);
      }
    });
  }
  for (const button of requestsEl.querySelectorAll("[data-queue-request-id]")) {
    button.addEventListener("click", () => {
      const requestId = Number(button.dataset.queueRequestId);
      if (Number.isInteger(requestId)) {
        queueRequestNow(requestId);
      }
    });
  }
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status");
    const status = await response.json();
    const app = status.app || {};
    const mcp = status.mcp || {};
    const agents = status.agents || {};
    const activeAgents = Array.isArray(agents.active_agents) ? agents.active_agents : [];
    const configuredSlots = Array.isArray(agents.configured_slots) ? agents.configured_slots : [];
    currentActiveAgents = activeAgents;
    renderRoutingHelp(configuredSlots);
    setStatus(appStatusEl, `${app.name || "app"} ${app.version || ""}`.trim(), "ok");
    setDetail(
      appDetailEl,
      [
        `FastAPI ${app.fastapi_version || "-"}`,
        `Moonshine ${app.moonshine_version || "-"}`,
        `HTTPX ${app.httpx_version || "-"}`,
      ],
    );
    setStatus(
      mcpStatusEl,
      `${mcp.name || "mcp"} · ${mcp.sdk_version || "-"}`,
      "ok",
    );
    setDetail(
      mcpDetailEl,
      [
        `${mcp.mount_path || "/mcp"} via ${mcp.transport || "-"}`,
        `Protocol ${mcp.protocol_version || "-"}`,
        `${(mcp.resources || []).length} resources`,
        `${(mcp.tools || []).length} tools`,
      ],
    );
    setStatus(
      transcriberStatusEl,
      status.running ? "Listening" : (status.last_error ? "Error" : "Starting"),
      status.running ? "ok" : (status.last_error ? "bad" : "warn"),
    );
    setDetail(
      transcriberDetailEl,
      [
        `Language ${status.language || "-"}`,
        `Cache ${status.cache_dir || "-"}`,
        status.last_error ? `Error: ${status.last_error}` : "Moonshine ready",
      ],
    );
    inputLevelStatusEl.textContent = Number(status.input_level || 0).toFixed(4);
    inputLevelStatusEl.className = `value ${((status.input_level || 0) > 0.005 ? "ok" : "warn")}`;
    setDetail(
      inputLevelDetailEl,
      (status.input_level || 0) > 0 ? "Microphone signal detected" : "No microphone signal yet",
    );
    assistantProcessing = Boolean(agents.processing);
    currentAssistantProvider = agents.current_agent_label || agents.current_agent_name || "-";
    const assistantLabel = assistantProcessing
      ? `Working · ${currentAssistantProvider || "-"}`
      : agents.ready
        ? `${Number(agents.agent_count || activeAgents.length)} connected`
        : "No agents connected";
    setStatus(
      assistantStatusEl,
      assistantLabel,
      assistantProcessing ? "warn" : (agents.ready ? "ok" : "bad"),
    );
    setSpinner(assistantStatusEl, assistantProcessing);
    setHtmlDetail(
      assistantDetailEl,
      activeAgents.length
        ? `<span class="detail-item active-agents">${activeAgents.map((agent) => {
            const statusInfo = normalizeAgentStatus(agent.status);
            return `<span class="agent-pill ${statusInfo.tone}">${escapeHtml(agent.label || agent.name)} · ${escapeHtml(statusInfo.label)}</span>`;
          }).join("")}</span><span class="detail-item">Requests: ${Number(agents.pending_count || 0)} listening · ${Number(agents.queued_count || 0)} queued · ${Number(agents.claimed_count || 0)} working</span>`
        : `<span class="detail-item">No MCP workers reported yet</span><span class="detail-item">Requests: ${Number(agents.pending_count || 0)} listening · ${Number(agents.queued_count || 0)} queued</span>`,
    );
    setStatus(wsStatusEl, streamConnected ? "Connected" : "Starting", streamConnected ? "ok" : "warn");
    setDetail(wsDetailEl, `WebSocket ${window.location.host}/ws/transcript`);
    const transcriberReady = Boolean(status.running);
    const assistantReady = Boolean(agents.ready);
    const mcpReady = Boolean(mcp.mount_path && mcp.sdk_version);
    const pipelineTone = transcriberReady && streamConnected && mcpReady
      ? "ok"
      : ((transcriberReady || streamConnected || mcpReady) ? "warn" : "bad");
    const pipelineLabel = transcriberReady && streamConnected && mcpReady
      ? "Voice host ready"
      : "Startup in progress";
    setStatus(pipelineStatusEl, pipelineLabel, pipelineTone);
    setDetail(
      pipelineDetailEl,
      [
        `Mic/STT ${transcriberReady ? "ok" : "waiting"}`,
        `UI stream ${streamConnected ? "ok" : "down"}`,
        `Agents ${assistantReady ? "ok" : "waiting"}`,
        `MCP ${mcpReady ? "ok" : "down"}`,
      ],
    );
  } catch (error) {
    setStatus(appStatusEl, "Unavailable", "bad");
    setDetail(appDetailEl, "Status endpoint did not respond");
    setStatus(mcpStatusEl, "Unknown", "warn");
    setDetail(mcpDetailEl, "-");
    setStatus(transcriberStatusEl, "Unknown", "warn");
    setDetail(transcriberDetailEl, "-");
    setStatus(assistantStatusEl, "Unknown", "warn");
    setDetail(assistantDetailEl, "-");
    setSpinner(assistantStatusEl, false);
    setStatus(wsStatusEl, streamConnected ? "Connected" : "Disconnected", streamConnected ? "ok" : "bad");
    setDetail(wsDetailEl, `WebSocket ${window.location.host}/ws/transcript`);
    setStatus(pipelineStatusEl, "Unknown", "warn");
    setDetail(pipelineDetailEl, ["Mic/STT -", "UI stream -", "AI -", "MCP -"]);
    setDetail(inputLevelDetailEl, "Waiting for microphone signal");
  }
  renderTimeline();
  renderRequests();
}

async function clearTimeline() {
  clearButtonEl.disabled = true;
  try {
    const response = await fetch("/api/transcript/clear", { method: "POST" });
    if (!response.ok) {
      const message = await response.text();
      throw new Error(`HTTP ${response.status}${message ? `: ${message}` : ""}`);
    }
    const snapshot = await response.json();
    applySnapshot(snapshot);
    assistantProcessing = false;
    sendingDraftIds = new Set();
    refreshStatus();
  } catch (error) {
    console.error("Failed to clear timeline", error);
    window.alert(`Failed to clear timeline: ${error.message || error}`);
  } finally {
    clearButtonEl.disabled = false;
  }
}

async function queueRequestNow(requestId) {
  sendingDraftIds = new Set(sendingDraftIds).add(requestId);
  renderTimeline();
  renderRequests();
  try {
    const response = await fetch(`/api/requests/${requestId}/queue`, { method: "POST" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    if (!payload.queued) {
      const message = payload.reason || payload.error || "Request queue failed";
      console.error("Failed to queue request", payload);
      window.alert(message);
    } else {
      const transcriptResponse = await fetch("/api/transcript");
      if (transcriptResponse.ok) {
        const snapshot = await transcriptResponse.json();
        applySnapshot(snapshot);
      }
    }
  } catch (error) {
    console.error("Failed to queue request", error);
    window.alert(`Failed to queue request: ${error.message || error}`);
  } finally {
    sendingDraftIds.delete(requestId);
    refreshStatus();
    renderTimeline();
    renderRequests();
  }
}

function applySnapshot(state) {
  events.clear();
  utterances.clear();
  requests.clear();
  requestEvents.clear();
  for (const event of state.events || []) {
    events.set(event.event_id, event);
  }
  for (const utterance of state.utterances || []) {
    utterances.set(utterance.source_line_id, utterance);
  }
  for (const request of state.requests || []) {
    requests.set(request.request_id, request);
  }
  for (const requestEvent of state.request_events || []) {
    requestEvents.set(requestEvent.event_id, requestEvent);
  }
  renderTimeline();
  renderRequests();
}

function connectTranscriptStream() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws/transcript`);

  socket.addEventListener("open", () => {
    streamConnected = true;
    setStatus(wsStatusEl, "Connected", "ok");
  });

  socket.addEventListener("close", () => {
    streamConnected = false;
    setStatus(wsStatusEl, "Disconnected", "bad");
    window.setTimeout(connectTranscriptStream, 1000);
  });

  socket.addEventListener("message", (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "snapshot") {
      applySnapshot(payload.state);
      return;
    }
    if (payload.type === "input_level") {
      inputLevelStatusEl.textContent = Number(payload.level || 0).toFixed(4);
      inputLevelStatusEl.className = `value ${((payload.level || 0) > 0.005 ? "ok" : "warn")}`;
      return;
    }
    if (payload.utterance) {
      utterances.set(payload.utterance.source_line_id, payload.utterance);
      renderTimeline();
      renderRequests();
      refreshStatus();
      return;
    }
    if (payload.request) {
      requests.set(payload.request.request_id, payload.request);
      renderRequests();
      refreshStatus();
      return;
    }
    if (payload.request_event) {
      requestEvents.set(payload.request_event.event_id, payload.request_event);
      renderTimeline();
      renderRequests();
      return;
    }
    if (payload.event) {
      events.set(payload.event.event_id, payload.event);
      renderTimeline();
    }
    if (payload.type === "status") {
      refreshStatus();
    }
  });
}

refreshStatus();
connectTranscriptStream();
window.setInterval(refreshStatus, 4000);
clearButtonEl.addEventListener("click", clearTimeline);
