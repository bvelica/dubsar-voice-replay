const linesEl = document.getElementById("lines");
const sendButtonEl = document.getElementById("send-button");
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
const events = new Map();
const utterances = new Map();
let sendingDraftIds = new Set();
let streamConnected = false;
let assistantProcessing = false;

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

function renderTimeline() {
  const ordered = Array.from(events.values()).sort((a, b) => a.created_seq - b.created_seq);
  const grouped = groupTimelineEvents(ordered);
  if (!grouped.length) {
    linesEl.innerHTML = "";
    return;
  }
  if (assistantProcessing) {
    grouped.push({
      role: "assistant",
      is_final: false,
      text: "Assistant is thinking...",
      agent_name: "OpenAI",
    });
  }
  linesEl.innerHTML = grouped.map((event) => {
    const utterance = event.role === "user" && Number.isInteger(event.draft_source_line_id)
      ? utterances.get(event.draft_source_line_id)
      : null;
    const label = event.role === "assistant"
      ? (event.agent_name ? `Assistant · ${escapeHtml(event.agent_name)}` : "Assistant")
      : describeUserEventLabel(event, utterance);
    const canSend = Boolean(
      utterance &&
      utterance.kind === "message" &&
      ["pending", "failed"].includes(utterance.status || "") &&
      Number.isInteger(event.draft_id)
    );
    const actionHtml = canSend
      ? `<div class="line-actions"><button class="line-button" type="button" data-send-draft-id="${event.draft_id}" ${sendingDraftIds.has(event.draft_id) ? "disabled" : ""}>Send</button></div>`
      : "";
    return `
      <article class="line ${event.role} ${event.is_final ? "complete" : "pending"}">
        <div class="line-head">
          <div class="line-meta">${label}</div>
          ${actionHtml}
        </div>
        <div class="line-text">${escapeHtml(event.text || "")}</div>
      </article>
    `;
  }).join("");
  bindLineActions();
  linesEl.scrollTop = linesEl.scrollHeight;
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
      draft_source_line_id: Number.isInteger(event.source_line_id) ? event.source_line_id : null,
      source_line_ids: Number.isInteger(event.source_line_id) ? [event.source_line_id] : [],
    });
  }
  return grouped;
}

function describeUserEventLabel(event, utterance) {
  if (!event.is_final) {
    return "You · live";
  }
  if (!utterance) {
    return "You";
  }
  if (utterance.kind === "command") {
    if (utterance.status === "failed") {
      return "You · command failed";
    }
    return `You · command${utterance.provider_label ? ` · ${escapeHtml(utterance.provider_label)}` : ""}`;
  }
  const status = utterance.status || "pending";
  if (status === "processing") {
    return `You · processing${utterance.provider_label ? ` · ${escapeHtml(utterance.provider_label)}` : ""}`;
  }
  if (status === "completed") {
    return `You · sent${utterance.provider_label ? ` · ${escapeHtml(utterance.provider_label)}` : ""}`;
  }
  if (status === "failed") {
    return `You · failed${utterance.provider_label ? ` · ${escapeHtml(utterance.provider_label)}` : ""}`;
  }
  if (status === "routed") {
    return `You · routed${utterance.provider_label ? ` · ${escapeHtml(utterance.provider_label)}` : ""}`;
  }
  return "You · pending";
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function bindLineActions() {
  for (const button of linesEl.querySelectorAll("[data-send-draft-id]")) {
    button.addEventListener("click", () => {
      const draftId = Number(button.dataset.sendDraftId);
      if (Number.isInteger(draftId)) {
        sendDraft(draftId);
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
    const assistant = status.assistant || {};
    setStatus(appStatusEl, `${app.name || "app"} ${app.version || ""}`.trim(), "ok");
    setDetail(
      appDetailEl,
      [
        `FastAPI ${app.fastapi_version || "-"}`,
        `Moonshine ${app.moonshine_version || "-"}`,
        `OpenAI SDK ${app.openai_sdk_version || "-"}`,
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
    assistantProcessing = Boolean(assistant.processing);
    const assistantLabel = assistantProcessing
      ? `Processing · ${assistant.default_provider || "-"}`
      : assistant.ready
        ? `Ready · ${assistant.default_provider || "-"} · manual`
        : `${assistant.default_provider || "assistant"} · ${assistant.error || "Not configured"}`;
    setStatus(
      assistantStatusEl,
      assistantLabel,
      assistantProcessing ? "warn" : (assistant.ready ? "ok" : "bad"),
    );
    setSpinner(assistantStatusEl, assistantProcessing);
    setDetail(
      assistantDetailEl,
      [
        `Known: ${(assistant.known_providers || []).join(", ") || "none"}`,
        `Configured: ${(assistant.configured_providers || []).join(", ") || "none"}`,
        `Pending drafts: ${assistant.pending_count || 0}`,
        assistant.error ? `Issue: ${assistant.error}` : "Reply path available",
      ],
    );
    setStatus(wsStatusEl, streamConnected ? "Connected" : "Starting", streamConnected ? "ok" : "warn");
    setDetail(wsDetailEl, `WebSocket ${window.location.host}/ws/transcript`);
    const transcriberReady = Boolean(status.running);
    const assistantReady = Boolean(assistant.ready);
    const mcpReady = Boolean(mcp.mount_path && mcp.sdk_version);
    const pipelineTone = transcriberReady && streamConnected && assistantReady && mcpReady
      ? "ok"
      : ((transcriberReady || streamConnected || assistantReady || mcpReady) ? "warn" : "bad");
    const pipelineLabel = transcriberReady && streamConnected && assistantReady && mcpReady
      ? "Voice to agent ready"
      : "Partial readiness";
    setStatus(pipelineStatusEl, pipelineLabel, pipelineTone);
    setDetail(
      pipelineDetailEl,
      [
        `Mic/STT ${transcriberReady ? "ok" : "waiting"}`,
        `UI stream ${streamConnected ? "ok" : "down"}`,
        `AI ${assistantReady ? "ok" : "blocked"}`,
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
}

async function clearTimeline() {
  clearButtonEl.disabled = true;
  try {
    const response = await fetch("/api/transcript/clear", { method: "POST" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const snapshot = await response.json();
    applySnapshot(snapshot);
  } catch (error) {
    console.error("Failed to clear timeline", error);
  } finally {
    clearButtonEl.disabled = false;
  }
}

async function sendLatestTranscript() {
  sendButtonEl.disabled = true;
  assistantProcessing = true;
  setStatus(assistantStatusEl, "Processing · openai", "warn");
  setSpinner(assistantStatusEl, true);
  renderTimeline();
  try {
    const response = await fetch("/api/assistant/send-latest", { method: "POST" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    await response.json();
  } catch (error) {
    console.error("Failed to send latest transcript", error);
  } finally {
    assistantProcessing = false;
    sendButtonEl.disabled = false;
    refreshStatus();
    renderTimeline();
  }
}

async function sendDraft(draftId) {
  sendingDraftIds = new Set(sendingDraftIds).add(draftId);
  assistantProcessing = true;
  renderTimeline();
  try {
    const response = await fetch(`/api/assistant/send-draft/${draftId}`, { method: "POST" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    if (!payload.sent) {
      const message = payload.reason || payload.error || "Draft send failed";
      console.error("Failed to send draft", payload);
      window.alert(message);
    }
  } catch (error) {
    console.error("Failed to send draft", error);
    window.alert(`Failed to send draft: ${error.message || error}`);
  } finally {
    sendingDraftIds.delete(draftId);
    assistantProcessing = false;
    refreshStatus();
    renderTimeline();
  }
}

function applySnapshot(state) {
  events.clear();
  utterances.clear();
  for (const event of state.events || []) {
    events.set(event.event_id, event);
  }
  for (const utterance of state.utterances || []) {
    utterances.set(utterance.source_line_id, utterance);
  }
  renderTimeline();
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
      refreshStatus();
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
sendButtonEl.addEventListener("click", sendLatestTranscript);
clearButtonEl.addEventListener("click", clearTimeline);
