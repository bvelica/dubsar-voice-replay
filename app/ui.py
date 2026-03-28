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
        --bg: #f6f1e8;
        --panel: #fffdf8;
        --ink: #1d241f;
        --muted: #5a675f;
        --border: #d7cbb8;
        --good: #1d7a43;
        --bad: #b0442f;
        --warn: #9c6a14;
        --accent: #174c3c;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
        background:
          radial-gradient(circle at top left, rgba(23, 76, 60, 0.10), transparent 30%),
          linear-gradient(180deg, #f8f3ea 0%, var(--bg) 100%);
        color: var(--ink);
      }
      main {
        max-width: 920px;
        margin: 0 auto;
        padding: 32px 20px 64px;
      }
      h1 {
        margin: 0 0 8px;
        font-size: clamp(2rem, 4vw, 3.5rem);
        line-height: 0.95;
      }
      p.lead {
        margin: 0 0 24px;
        max-width: 680px;
        color: var(--muted);
        font-size: 1.05rem;
      }
      .statusbar, .panel {
        background: color-mix(in srgb, var(--panel) 92%, white);
        border: 1px solid var(--border);
        border-radius: 18px;
        box-shadow: 0 10px 30px rgba(29, 36, 31, 0.06);
      }
      .statusbar {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 12px;
        padding: 14px;
        margin-bottom: 20px;
      }
      .status-card {
        padding: 12px 14px;
        border-radius: 14px;
        background: rgba(255, 255, 255, 0.65);
        border: 1px solid rgba(215, 203, 184, 0.7);
      }
      .label {
        display: block;
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--muted);
        margin-bottom: 6px;
      }
      .value {
        font-size: 1rem;
        font-weight: 700;
      }
      .ok { color: var(--good); }
      .bad { color: var(--bad); }
      .warn { color: var(--warn); }
      .panel {
        padding: 22px;
      }
      .diagnostics {
        margin-top: 16px;
        padding-top: 14px;
        border-top: 1px solid rgba(215, 203, 184, 0.75);
      }
      .diagnostics code {
        display: block;
        padding: 12px 14px;
        border-radius: 12px;
        background: rgba(29, 36, 31, 0.05);
        border: 1px solid rgba(215, 203, 184, 0.75);
        overflow-x: auto;
        white-space: pre-wrap;
      }
      .panel-header {
        display: flex;
        justify-content: space-between;
        gap: 16px;
        align-items: baseline;
        margin-bottom: 18px;
      }
      .panel-header h2 {
        margin: 0;
        font-size: 1.3rem;
      }
      .meta {
        color: var(--muted);
        font-size: 0.95rem;
      }
      #error-banner {
        display: none;
        margin-bottom: 16px;
        padding: 12px 14px;
        border-radius: 12px;
        background: rgba(176, 68, 47, 0.08);
        border: 1px solid rgba(176, 68, 47, 0.25);
        color: var(--bad);
      }
      #lines {
        display: grid;
        gap: 12px;
      }
      .line {
        padding: 14px 16px;
        border-radius: 14px;
        background: rgba(255, 255, 255, 0.72);
        border: 1px solid rgba(215, 203, 184, 0.75);
      }
      .line.pending {
        border-style: dashed;
      }
      .line-meta {
        margin-bottom: 8px;
        color: var(--muted);
        font-size: 0.86rem;
      }
      .line-text {
        font-size: 1.08rem;
        line-height: 1.45;
        white-space: pre-wrap;
      }
      .empty {
        color: var(--muted);
        padding: 12px 0;
      }
    </style>
  </head>
  <body>
    <main>
      <h1>transcriptor</h1>
      <p class="lead">Speak into your microphone. The server starts the transcription pipeline on launch and this page follows the live transcript stream.</p>

      <section class="statusbar">
        <div class="status-card">
          <span class="label">API</span>
          <span id="api-status" class="value">Checking...</span>
        </div>
        <div class="status-card">
          <span class="label">Transcriber</span>
          <span id="transcriber-status" class="value">Checking...</span>
        </div>
        <div class="status-card">
          <span class="label">Transcript Stream</span>
          <span id="ws-status" class="value">Connecting...</span>
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
          <h2>Live Transcript</h2>
          <div id="line-count" class="meta">0 lines</div>
        </div>
        <div id="error-banner"></div>
        <div id="lines">
          <div class="empty">Waiting for transcript events...</div>
        </div>
        <div class="diagnostics">
          <div class="meta">Current status payload</div>
          <code id="status-json">{}</code>
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
      const statusJsonEl = document.getElementById("status-json");
      const lines = new Map();

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
        const ordered = Array.from(lines.values()).sort((a, b) => a.line_id - b.line_id);
        lineCountEl.textContent = `${ordered.length} line${ordered.length === 1 ? "" : "s"}`;
        if (!ordered.length) {
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
          statusJsonEl.textContent = JSON.stringify(status, null, 2);
          setStatus(apiStatusEl, "Ready", "ok");
          setStatus(
            transcriberStatusEl,
            status.running ? "Listening" : (status.last_error ? "Error" : "Idle"),
            status.running ? "ok" : (status.last_error ? "bad" : "warn"),
          );
          languageStatusEl.textContent = status.language || "-";
          languageStatusEl.className = "value";
          inputLevelStatusEl.textContent = Number(status.input_level || 0).toFixed(4);
          inputLevelStatusEl.className = "value " + ((status.input_level || 0) > 0.005 ? "ok" : "warn");
          setError(status.last_error || "");
        } catch (error) {
          setStatus(apiStatusEl, "Unavailable", "bad");
          setStatus(transcriberStatusEl, "Unknown", "warn");
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
          setStatus(wsStatusEl, "Connected", "ok");
        });

        socket.addEventListener("close", () => {
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
