# Project Context

## What This Project Is

`dubsar` is a local-first voice-to-agent host.

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
- user-triggered delegation via child requests instead of hidden autonomous delegation

The current interaction model is:

1. The user speaks naturally.
2. Moonshine may finalize that speech in multiple chunks.
3. The app groups those finalized chunks into one open request/thought.
4. That request remains pending until the user explicitly queues it.
5. The web UI shows requests, trace events, and explicit `Queue` and `Delegate` actions.
6. MCP exposes queued requests and conversation state to external agent clients.
7. External agents, such as the repo's MCP worker process, claim queued requests and append replies or failures back through MCP.
8. Delegation is user-triggered and creates a child request linked to the parent request instead of letting agents silently delegate on their own.
9. The main visibility unit is now `request_id`, which groups one user thought across one or more finalized Moonshine chunks.

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
- Agent startup model: Dubsar auto-starts configured external MCP workers from `.env` on app startup

## Release Tracking

- The canonical app version lives in `VERSION`.
- Human-readable release history lives in `CHANGELOG.md`.
- Git history records code changes, while tags can mark release points.

## Open Product Questions

- Whether browser-based audio capture should be added after the initial local microphone version
- How rich the utterance lifecycle tracking should be in the UI and MCP surface
- What MCP should expose next beyond the current basics: agent/task lifecycle, claiming, delegation, or some combination
- What the first concrete external-agent action model should be
- How rich the per-request trace UI should become beyond the current compact lifecycle view
- How much child-request detail should be shown inline versus behind a collapsible trace
- Whether a separate stdio bridge should be added for MCP clients that cannot connect to the local HTTP endpoint
- How far to push lifecycle detail into the store versus keeping some agent state ephemeral on the MCP clients
- When to add Gemini or other model systems as first-class external MCP clients
- How far to refactor the frontend into smaller modules now that the inline UI blob has been split into static assets
