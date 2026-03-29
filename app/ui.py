from __future__ import annotations

from fastapi.responses import HTMLResponse


INDEX_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>transcriptor</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #ffffff;
        --panel: #fafafa;
        --ink: #111111;
        --muted: #4b5563;
        --border: #cbd5e1;
        --good: #177245;
        --bad: #c0392b;
        --warn: #a16207;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        background: var(--bg);
        color: var(--ink);
      }
      main {
        max-width: 960px;
        margin: 0 auto;
        padding: 24px 16px;
      }
      .statusbar {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 10px;
        padding: 10px;
        margin-bottom: 12px;
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 10px;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
      }
      .status-card {
        padding: 10px 12px;
        border-radius: 8px;
        background: #ffffff;
        border: 1px solid #d7dee7;
      }
      .label {
        display: block;
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--muted);
        margin-bottom: 4px;
      }
      .value {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        font-size: 0.95rem;
        font-weight: 700;
      }
      .ok { color: var(--good); }
      .bad { color: var(--bad); }
      .warn { color: var(--warn); }
      .spinner {
        width: 0.9rem;
        height: 0.9rem;
        border-radius: 999px;
        border: 2px solid currentColor;
        border-right-color: transparent;
        display: none;
        animation: spin 0.8s linear infinite;
      }
      .value.spinning .spinner {
        display: inline-block;
      }
      @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
      }
      .timeline-header {
        display: flex;
        justify-content: flex-end;
        gap: 10px;
        margin-bottom: 12px;
      }
      .button {
        appearance: none;
        border: 1px solid #d7dee7;
        background: #ffffff;
        color: var(--ink);
        border-radius: 8px;
        padding: 10px 14px;
        font: inherit;
        cursor: pointer;
      }
      .button:hover {
        background: #f8fafc;
      }
      .button:disabled {
        opacity: 0.6;
        cursor: wait;
      }
      #lines {
        max-height: 60vh;
        overflow-y: auto;
        display: grid;
        gap: 10px;
        min-height: 96px;
        padding-right: 4px;
      }
      .line {
        padding: 14px 16px;
        border-radius: 10px;
        background: var(--panel);
        border: 1px solid var(--border);
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
      }
      .line.user {
        background: #ffffff;
      }
      .line.assistant {
        background: #f2f7ff;
        border-color: #bfd3f2;
      }
      .line.pending {
        border-style: dashed;
      }
      .line-meta {
        margin-bottom: 6px;
        color: var(--muted);
        font-size: 0.76rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
      }
      .line-text {
        font-size: 1.05rem;
        line-height: 1.5;
        white-space: pre-wrap;
      }
    </style>
  </head>
  <body>
    <main>
      <section class="statusbar">
        <div class="status-card">
          <span class="label">API</span>
          <span id="api-status" class="value">Starting...</span>
        </div>
        <div class="status-card">
          <span class="label">Transcriber</span>
          <span id="transcriber-status" class="value">Starting...</span>
        </div>
        <div class="status-card">
          <span class="label">Stream</span>
          <span id="ws-status" class="value">Starting...</span>
        </div>
        <div class="status-card">
          <span class="label">Language</span>
          <span id="language-status" class="value">-</span>
        </div>
        <div class="status-card">
          <span class="label">Mic Input Level</span>
          <span id="input-level-status" class="value">0.0000</span>
        </div>
        <div class="status-card">
          <span class="label">Assistant</span>
          <span id="assistant-status" class="value"><span class="spinner"></span><span class="status-text">Starting...</span></span>
        </div>
      </section>
      <div class="timeline-header">
        <button id="send-button" class="button" type="button">Send Latest</button>
        <button id="clear-button" class="button" type="button">Clear</button>
      </div>
      <section id="lines"></section>
    </main>

    <script>
      const linesEl = document.getElementById("lines");
      const sendButtonEl = document.getElementById("send-button");
      const clearButtonEl = document.getElementById("clear-button");
      const apiStatusEl = document.getElementById("api-status");
      const transcriberStatusEl = document.getElementById("transcriber-status");
      const wsStatusEl = document.getElementById("ws-status");
      const languageStatusEl = document.getElementById("language-status");
      const inputLevelStatusEl = document.getElementById("input-level-status");
      const assistantStatusEl = document.getElementById("assistant-status");
      const events = new Map();
      let streamConnected = false;
      let assistantProcessing = false;

      function setStatus(el, text, tone) {
        const textEl = el.querySelector(".status-text");
        if (textEl) {
          textEl.textContent = text;
        } else {
          el.textContent = text;
        }
        el.className = "value " + tone;
      }

      function setSpinner(el, active) {
        if (active) {
          el.className = `${el.className} spinning`.trim();
          return;
        }
        el.className = el.className.replace(/\bspinning\b/g, "").replace(/\s+/g, " ").trim();
      }

      function renderTimeline() {
        const ordered = Array.from(events.values())
          .sort((a, b) => a.created_seq - b.created_seq);
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
          const label = event.role === "assistant"
            ? (event.agent_name ? `Assistant · ${escapeHtml(event.agent_name)}` : "Assistant")
            : (event.is_final ? "You" : "You · live");
          return `
            <article class="line ${event.role} ${event.is_final ? "complete" : "pending"}">
              <div class="line-meta">${label}</div>
              <div class="line-text">${escapeHtml(event.text || "")}</div>
            </article>
          `;
        }).join("");
        linesEl.scrollTop = linesEl.scrollHeight;
      }

      function groupTimelineEvents(ordered) {
        const grouped = [];
        for (const event of ordered) {
          const previous = grouped[grouped.length - 1];
          const canMerge =
            previous &&
            previous.role === "user" &&
            event.role === "user" &&
            previous.is_final &&
            event.is_final &&
            !previous.agent_name &&
            !event.agent_name;
          if (canMerge) {
            previous.text = `${previous.text} ${event.text}`.replace(/\s+/g, " ").trim();
            previous.updated_seq = event.updated_seq;
            continue;
          }
          grouped.push({ ...event });
        }
        return grouped;
      }

      function escapeHtml(value) {
        return value
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;");
      }

      async function refreshStatus() {
        try {
          const response = await fetch("/api/status");
          const status = await response.json();
          setStatus(apiStatusEl, "Ready", "ok");
          setStatus(
            transcriberStatusEl,
            status.running ? "Listening" : (status.last_error ? "Error" : "Starting"),
            status.running ? "ok" : (status.last_error ? "bad" : "warn"),
          );
          languageStatusEl.textContent = status.language || "-";
          languageStatusEl.className = "value";
          inputLevelStatusEl.textContent = Number(status.input_level || 0).toFixed(4);
          inputLevelStatusEl.className = "value " + ((status.input_level || 0) > 0.005 ? "ok" : "warn");
          const assistant = status.assistant || {};
          assistantProcessing = Boolean(assistant.processing);
          const assistantLabel = assistantProcessing
            ? `Processing · ${assistant.default_provider || "-"}`
            : assistant.ready
              ? `Ready · ${assistant.default_provider || "-"}${assistant.auto_submit ? " · auto" : " · manual"}`
              : `${assistant.default_provider || "assistant"} · ${assistant.error || "Not configured"}`;
          setStatus(
            assistantStatusEl,
            assistantLabel,
            assistantProcessing ? "warn" : (assistant.ready ? "ok" : "bad"),
          );
          setSpinner(assistantStatusEl, assistantProcessing);
          setStatus(wsStatusEl, streamConnected ? "Connected" : "Starting", streamConnected ? "ok" : "warn");
        } catch (error) {
          setStatus(apiStatusEl, "Unavailable", "bad");
          setStatus(transcriberStatusEl, "Unknown", "warn");
          setStatus(assistantStatusEl, "Unknown", "warn");
          setSpinner(assistantStatusEl, false);
          setStatus(wsStatusEl, streamConnected ? "Connected" : "Disconnected", streamConnected ? "ok" : "bad");
        }
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

      function applySnapshot(state) {
        events.clear();
        for (const event of state.events || []) {
          events.set(event.event_id, event);
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
            inputLevelStatusEl.className = "value " + ((payload.level || 0) > 0.005 ? "ok" : "warn");
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
    </script>
  </body>
</html>
"""


def render_index() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)
