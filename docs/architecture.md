# Architecture Notes

## Proposed High-Level Shape

The system should be organized around a single transcript/event flow rather than separate pipelines for UI and MCP.

Core areas:

- audio ingestion
- speech-to-text integration
- transcript state and event stream
- command parsing and utterance routing
- agent routing and provider adapters
- web API and UI transport
- MCP integration
- action execution

## Current v0.1 Skeleton

- `app/main.py` exposes the FastAPI app and the first API routes.
- `app/conversation_service.py` subscribes to finalized user transcript events, recognizes spoken control commands, and turns explicitly submitted drafts into assistant replies.
- `app/agent_router.py` selects a provider for each finalized user utterance.
- `app/agent_registry.py` centralizes known target names, spoken aliases, and the configured provider map.
- `app/commands.py` parses simple command prefixes plus spoken command phrases that operate on the latest open draft.
- `app/agents/` contains provider adapters such as the OpenAI implementation.
- `app/mcp_server.py` exposes MCP resources and tools from the same in-process store used by the web app; it is an external integration surface, not the internal reply transport.
- `app/moonshine_service.py` captures microphone audio with `sounddevice` and feeds it into Moonshine's streaming transcriber.
- `app/transcript_store.py` is the source of truth for transcript state, utterance lifecycle state, draft/thought grouping, and the conversation timeline, persists it to local JSON storage, keeps the latest 10 events, and tracks local sequencing for stable history order.
- `ws/transcript` streams transcript updates from the shared store.
- `app/ui.py` serves the UI entrypoint, while `app/static/` contains the host-native frontend assets for the status bar and recent conversation timeline.

Current protocol and product identity:

- FastAPI app title: `dubsar`
- MCP server name: `dubsar`
- MCP resource URI prefix: `dubsar://`
- Preferred config env prefix: `DUBSAR_`
- Legacy config env prefix still accepted temporarily: `TRANSCRIPTOR_`

## Current Interaction Model

1. The microphone feeds Moonshine through `app/moonshine_service.py`.
2. Finalized transcript chunks are written into `app/transcript_store.py` as utterance records plus timeline events.
3. Consecutive message utterances are grouped by `draft_id` into one open draft/thought.
4. A recognized spoken command is stored as a command utterance, not appended to draft text.
5. `app/conversation_service.py` closes and sends the current draft when the user presses `Send` or when a command such as `command send to chatgpt` is recognized.
6. The provider adapter returns an assistant reply, which is written back into the same timeline.
7. The UI and MCP surfaces observe the same shared state.

## Proposed v1 Event Flow

1. Audio enters the system.
2. The local audio adapter forwards microphone frames into Moonshine.
3. Moonshine produces partial and/or final transcript updates.
4. Transcript state is updated in one place.
5. Transcript updates are mapped onto conversation events.
6. Finalized utterances become explicit store records with lifecycle state.
7. Consecutive message utterances can accumulate into one open draft/thought.
8. The open draft remains pending until explicitly submitted or routed by a command.
9. The routing layer interprets any command phrase and selects one or more target agents.
10. The selected provider or agent receives the combined draft text and returns an assistant reply or action result.
11. Assistant or action responses append to the same timeline and complete or fail the utterance lifecycle for the whole draft.
12. Updates are broadcast to the web UI.
13. The same state is exposed to MCP consumers, including utterance lifecycle records.
14. External MCP clients can read or act on the same live state by calling routing tools backed by the internal conversation service.

## Directional Target

The intended next architecture step is:

- keep FastAPI as the host runtime for UI, MCP mount, and local APIs
- keep `TranscriptStore` as the single shared source of truth
- keep the built-in local reply loop internal to the app
- evolve command parsing from text prefixes toward spoken control phrases such as "command send to chatgpt"
- group multiple transcript chunks into one draft/thought until the user closes that thought
- initial spoken commands should act on the latest pending draft rather than embedding routing into the content utterance itself
- add an explicit utterance/task lifecycle so one thought can later be routed to one or more agents
- treat MCP as the external standard interface for outside agents rather than the internal orchestrator

Near-term implementation direction:

- keep the current draft-based interaction model stable
- continue improving command recognition and routing semantics rather than reintroducing automation
- add at least one more real provider adapter through the registry/provider layer
- further separate frontend concerns inside `app/static/` so status rendering, timeline rendering, and websocket transport are easier to evolve independently

## Design Bias

- Prefer one source of truth for transcript state.
- Keep the first MCP server in process with the FastAPI app so MCP reads and tool actions operate on live shared state.
- Keep action execution separate from transcription.
- Keep the first version narrow and easy to debug.
- Prefer explicit, observable audio/transcript flow over opaque wrappers when debugging real-time behavior.
