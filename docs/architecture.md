# Architecture Notes

## Proposed High-Level Shape

The system should be organized around a single transcript/event flow rather than separate pipelines for UI and MCP.

Core areas:

- audio ingestion
- speech-to-text integration
- transcript state and event stream
- agent routing and provider adapters
- web API and UI transport
- MCP integration
- action execution

## Current v0.1 Skeleton

- `app/main.py` exposes the FastAPI app and the first API routes.
- `app/conversation_service.py` subscribes to finalized user transcript events and turns them into assistant replies.
- `app/agent_router.py` selects a provider for each finalized user utterance.
- `app/commands.py` parses the first simple command prefixes such as `/openai` and leaves room for later voice-command routing.
- `app/agents/` contains provider adapters such as the OpenAI implementation.
- `app/mcp_server.py` exposes MCP resources and tools from the same in-process store used by the web app.
- `app/moonshine_service.py` captures microphone audio with `sounddevice` and feeds it into Moonshine's streaming transcriber.
- `app/transcript_store.py` is the source of truth for transcript state and the conversation timeline, persists it to local JSON storage, keeps the latest 10 events, and tracks local sequencing for stable history order.
- `ws/transcript` streams transcript updates from the shared store.
- `app/ui.py` serves the host-native UI with a status bar and the recent conversation timeline.

## Proposed v1 Event Flow

1. Audio enters the system.
2. The local audio adapter forwards microphone frames into Moonshine.
3. Moonshine produces partial and/or final transcript updates.
4. Transcript state is updated in one place.
5. Transcript updates are mapped onto conversation events.
6. The agent router selects a provider for finalized user events.
7. The selected provider returns an assistant reply.
8. Assistant or action responses append to the same timeline.
9. Updates are broadcast to the web UI.
10. The same state is exposed to MCP consumers.
11. Action logic evaluates transcript events.

## Design Bias

- Prefer one source of truth for transcript state.
- Keep the first MCP server in process with the FastAPI app so MCP reads and tool actions operate on live shared state.
- Keep action execution separate from transcription.
- Keep the first version narrow and easy to debug.
- Prefer explicit, observable audio/transcript flow over opaque wrappers when debugging real-time behavior.
