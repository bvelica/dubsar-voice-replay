# Project Context

## What This Project Is

`transcriptor` is a local-first voice-to-action server.

The intended flow is:

1. Capture speech locally.
2. Transcribe it live with Moonshine.
3. Map transcript updates into a conversation timeline.
4. Stream conversation updates to a web UI.
5. Expose conversation state through MCP so AI agents can consume voice input.
6. Allow agents or application logic to trigger actions from those transcripts.

## Current Intent

The initial version should prioritize:

- low-latency local speech-to-text
- real-time transcript visibility
- local transcript persistence
- a conversation-style timeline for recent user and assistant messages
- a clean MCP integration surface
- provider-agnostic AI response routing
- a conservative action model

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
- Local configuration source: environment variables with repo-local `.env` support for development
- Lower-level languages such as Go or Rust are acceptable later for isolated performance-sensitive components
- Moonshine upstream repo: `moonshine-ai/moonshine`
- Initial speech path: use Moonshine's Python microphone transcription flow as the reference integration
- Current implementation path: host-native `sounddevice` microphone capture feeding Moonshine's streaming transcriber
- First response provider path: OpenAI Responses API through the official Python SDK

## Release Tracking

- The canonical app version lives in `VERSION`.
- Human-readable release history lives in `CHANGELOG.md`.
- Git history records code changes, while tags can mark release points.

## Open Product Questions

- Whether browser-based audio capture should be added after the initial local microphone version
- Whether action triggering should be fully automatic or gated
- What MCP should expose first: transcript history, live subscription, tools, or some combination
- What the first concrete supported actions should be
- Whether a separate stdio bridge should be added for MCP clients that cannot connect to the local HTTP endpoint
