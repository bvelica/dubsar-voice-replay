# Project Context

## What This Project Is

`Dubsar Voice Relay` is a local-first voice-to-agent host.

The intended flow is:

1. Capture speech locally.
2. Transcribe it live with Moonshine.
3. Map transcript updates into a conversation timeline.
4. Keep the transcript and conversation state in one shared in-process store.
5. Stream conversation updates to a web UI.
6. Expose the same conversation state through MCP so external AI agents can consume requests and trigger actions.
7. Keep the web UI as the human-facing monitor and explicit control surface over that shared state.

## Current Intent

The current direction should prioritize:

- low-latency local speech-to-text
- real-time transcript visibility
- local transcript persistence
- a conversation-style timeline for recent user and assistant messages
- explicit manual control over when an open request is acted on
- a clean MCP integration surface that outside agents can rely on
- visibility into what agents read, do, and write back
- provider-agnostic agent participation through MCP
- a conservative action model
- explicit user-directed routing without hidden autonomous delegation

The current interaction model is:

1. The user speaks naturally.
2. The user starts the utterance with a configured agent-slot alias when they want to direct a request to a specific agent.
3. Moonshine may finalize that speech in multiple chunks.
4. The app should group those finalized chunks into one targeted request/thought even when the user speaks slowly and pauses.
5. That request should be routed based on the leading agent command rather than a later button press.
6. After a short idle pause, that targeted request should auto-queue.
7. MCP exposes requests and conversation state to external agent clients.
8. The targeted external agent claims the request and appends a reply or failure back through MCP.
9. That reply stays in the shared conversation timeline so the user can ask another configured slot to confirm, challenge, or expand on it.
10. The main visibility unit is `request_id`, which groups one user thought across one or more finalized Moonshine chunks.

## Constraints

- English-first initially
- local deployment first, not cloud-first
- architecture should be simple enough to iterate quickly

## Current Stack Decisions

- Backend: Python
- API framework: FastAPI
- Default ASGI server: Uvicorn with `--ws websockets-sansio`
- MCP server framework: FastMCP mounted into the FastAPI app
- AI integration model direction: treat AI agents as external MCP clients instead of the long-term in-process reply path
- Command model direction: keep submission explicit and avoid voice-triggered routing while the interaction model is being refined
- Local configuration source: environment variables with repo-local `.env` support for development
- Lower-level languages such as Go or Rust are acceptable later for isolated performance-sensitive components
- Moonshine upstream repo: `moonshine-ai/moonshine`
- Initial speech path: use Moonshine's Python microphone transcription flow as the reference integration
- Current implementation path: host-native `sounddevice` microphone capture feeding Moonshine's streaming transcriber
- Frontend delivery path: FastAPI serves a small index shell plus static HTML/CSS/JS assets from `app/static/`
- Current external-agent reference path: `workers/mcp_agent_worker.py` connects to the mounted MCP endpoint and calls model APIs from a separate process
- Agent startup model: Dubsar Voice Relay auto-starts configured external MCP workers from `.env` on app startup
- Spoken routing model: configurable agent slots loaded from typed settings and `.env`, so the user can choose stable aliases such as `Agent 1` and `Agent 2`

## Release Tracking

- The canonical app version lives in `VERSION`.
- Human-readable release history lives in `CHANGELOG.md`.
- Git history records code changes, while tags can mark release points.

## Open Product Questions

- Whether browser-based audio capture should be added after the initial local microphone version
- How rich the utterance lifecycle tracking should be in the UI and MCP surface
- What MCP should expose next beyond the current basics: agent/task lifecycle, claiming, delegation, or some combination
- What the exact close/submit rule should be for a spoken request after a leading agent command when Moonshine produces multiple finalized chunks
- How rich the per-request trace UI should become beyond the current compact lifecycle view
- Whether explicit child requests should remain only for follow-up verification tasks rather than normal first-hop routing
- Whether a separate stdio bridge should be added for MCP clients that cannot connect to the local HTTP endpoint
- How far to push lifecycle detail into the store versus keeping some agent state ephemeral on the MCP clients
- When to add Gemini or other model systems as first-class external MCP clients
- How far to refactor the frontend into smaller modules now that the inline UI blob has been split into static assets
