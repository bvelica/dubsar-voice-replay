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
        max-width: 980px;
        margin: 0 auto;
        padding: 20px 16px;
      }
      .statusbar, .panel {
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 10px;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
      }
      .statusbar {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 10px;
        padding: 10px;
        margin-bottom: 12px;
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
        font-size: 0.95rem;
        font-weight: 700;
      }
      .ok { color: var(--good); }
      .bad { color: var(--bad); }
      .warn { color: var(--warn); }
      .panel {
        padding: 12px;
      }
      .panel-header {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        align-items: baseline;
        margin-bottom: 10px;
      }
      .panel-header h2 {
        margin: 0;
        font-size: 0.95rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }
      .meta {
        color: var(--muted);
        font-size: 0.82rem;
      }
      #error-banner {
        display: none;
        margin-bottom: 10px;
        padding: 10px 12px;
        border-radius: 8px;
        background: rgba(255, 123, 114, 0.08);
        border: 1px solid rgba(255, 123, 114, 0.25);
        color: var(--bad);
      }
      #lines {
        display: grid;
        gap: 8px;
      }
      .line {
        padding: 10px 12px;
        border-radius: 8px;
        background: #ffffff;
        border: 1px solid #d7dee7;
      }
      .line.pending {
        border-style: dashed;
      }
      .line-meta {
        margin-bottom: 6px;
        color: var(--muted);
        font-size: 0.76rem;
      }
      .line-text {
        font-size: 1rem;
        line-height: 1.4;
        white-space: pre-wrap;
      }
      .empty {
        color: var(--muted);
        padding: 8px 0;
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
      </section>

      <section class="panel">
        <div class="panel-header">
          <h2>Transcript</h2>
          <div id="line-count" class="meta">Last 10 lines</div>
        </div>
        <div id="error-banner"></div>
        <div id="lines">
          <div class="empty">Waiting for transcript events...</div>
        </div>
      </section>
    </main>

    <script>
      const linesEl = document.getElementById("lines");
      const lineCountEl = document.getElementById("line-count");
      const errorBannerEl = document.getElementById("error-banner");
      const apiStatusEl = document.getElementById("api-status");
      const transcriberStatusEl = document.getElementById("transcriber-status");
      const wsStatusEl = document.getElementById("ws-status");
      const languageStatusEl = document.getElementById("language-status");
      const inputLevelStatusEl = document.getElementById("input-level-status");
      const lines = new Map();
      let streamConnected = false;

      function setStatus(el, text, tone) {
        el.textContent = text;
        el.className = "value " + tone;
      }

      function setError(message) {
        if (!message) {
          errorBannerEl.style.display = "none";
          errorBannerEl.textContent = "";
          return;
        }
        errorBannerEl.style.display = "block";
        errorBannerEl.textContent = message;
      }

      function renderLines() {
        const ordered = Array.from(lines.values())
          .sort((a, b) => a.line_id - b.line_id)
          .slice(-10);
        lineCountEl.textContent = `${ordered.length} of ${lines.size} line${lines.size === 1 ? "" : "s"}`;
        if (!lines.size) {
          linesEl.innerHTML = '<div class="empty">Waiting for transcript events...</div>';
          return;
        }
        linesEl.innerHTML = ordered.map((line) => {
          const speaker = line.speaker_index == null ? "Speaker unknown" : `Speaker ${line.speaker_index}`;
          const state = line.is_complete ? "complete" : "pending";
          const latency = line.latency_ms ? `, ${line.latency_ms} ms` : "";
          return `
            <article class="line ${state}">
              <div class="line-meta">${speaker} • ${line.start_time.toFixed(2)}s • ${state}${latency}</div>
              <div class="line-text">${escapeHtml(line.text || "")}</div>
            </article>
          `;
        }).join("");
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
          setError(status.last_error || "");
          setStatus(wsStatusEl, streamConnected ? "Connected" : "Starting", streamConnected ? "ok" : "warn");
        } catch (error) {
          setStatus(apiStatusEl, "Unavailable", "bad");
          setStatus(transcriberStatusEl, "Unknown", "warn");
          setStatus(wsStatusEl, streamConnected ? "Connected" : "Disconnected", streamConnected ? "ok" : "bad");
          setError(`Failed to load status: ${error}`);
        }
      }

      function applySnapshot(state) {
        lines.clear();
        for (const line of state.lines || []) {
          lines.set(line.line_id, line);
        }
        renderLines();
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
          if (payload.type === "error") {
            setError(payload.message);
            return;
          }
          if (payload.type === "input_level") {
            inputLevelStatusEl.textContent = Number(payload.level || 0).toFixed(4);
            inputLevelStatusEl.className = "value " + ((payload.level || 0) > 0.005 ? "ok" : "warn");
            return;
          }
          if (payload.line) {
            lines.set(payload.line.line_id, payload.line);
            renderLines();
          }
          if (payload.type === "status") {
            refreshStatus();
          }
        });
      }

      refreshStatus();
      connectTranscriptStream();
      window.setInterval(refreshStatus, 4000);
    </script>
  </body>
</html>
"""


def render_index() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)
