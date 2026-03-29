# Project Context

## What This Project Is

`dubsar` is a local-first voice-to-action server.

The intended flow is:

1. Capture speech locally.
2. Transcribe it live with Moonshine.
3. Map transcript updates into a conversation timeline.
4. Keep the transcript and conversation state in one shared in-process store.
5. Stream conversation updates to a web UI.
6. Route the current finalized draft/thought to one or more AI agents when the user explicitly submits or commands that routing.
7. Expose the same conversation state through MCP so external agents can consume voice input and trigger actions.

## Current Intent

The initial version should prioritize:

- low-latency local speech-to-text
- real-time transcript visibility
- local transcript persistence
- a conversation-style timeline for recent user and assistant messages
- explicit manual control over when an open draft is sent to an agent
- spoken command routing for agent selection and delegation
- a clean MCP integration surface
- provider-agnostic AI response routing
- a conservative action model

The current interaction model is:

1. The user speaks naturally.
2. Moonshine may finalize that speech in multiple chunks.
3. The app groups those finalized chunks into one open draft/thought.
4. That draft remains pending until the user either presses `Send` or speaks a recognized routing command such as `command send to chatgpt`.
5. A recognized command acts on the current draft and is not sent to the AI as prompt text.

## Constraints

- English-first initially
- local deployment first, not cloud-first
- architecture should be simple enough to iterate quickly

## Current Stack Decisions

- Backend: Python
- API framework: FastAPI
- Default ASGI server: Uvicorn with `--ws websockets-sansio`
- MCP server framework: FastMCP mounted into the FastAPI app
- AI routing model: internal agent router plus provider adapters
- Command model direction: spoken command phrases that operate on the latest open draft
- Local configuration source: environment variables with repo-local `.env` support for development
- Lower-level languages such as Go or Rust are acceptable later for isolated performance-sensitive components
- Moonshine upstream repo: `moonshine-ai/moonshine`
- Initial speech path: use Moonshine's Python microphone transcription flow as the reference integration
- Current implementation path: host-native `sounddevice` microphone capture feeding Moonshine's streaming transcriber
- First response provider path: OpenAI Responses API through the official Python SDK
- Frontend delivery path: FastAPI serves a small index shell plus static HTML/CSS/JS assets from `app/static/`

## Release Tracking

- The canonical app version lives in `VERSION`.
- Human-readable release history lives in `CHANGELOG.md`.
- Git history records code changes, while tags can mark release points.

## Open Product Questions

- Whether browser-based audio capture should be added after the initial local microphone version
- How rich the utterance lifecycle tracking should be in the UI and MCP surface
- What MCP should expose first beyond the current basics: transcript history, live subscription, tools, or some combination
- What the first concrete supported actions should be
- Whether a separate stdio bridge should be added for MCP clients that cannot connect to the local HTTP endpoint
- Whether one spoken command should target exactly one agent by default or support explicit parallel fan-out
- When to add the second real provider adapter after OpenAI so `claude` or `gemini` can be tested end-to-end
- How far to refactor the frontend into smaller modules now that the inline UI blob has been split into static assets
