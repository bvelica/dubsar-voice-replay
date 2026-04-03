# Architecture Notes

## Proposed High-Level Shape

The system should be organized around a single transcript/event flow rather than separate pipelines for UI and MCP.

Core areas:

- audio ingestion
- speech-to-text integration
- transcript state and event stream
- request lifecycle and explicit submission
- request lifecycle and explicit submission
- web API and UI transport
- MCP integration
- external agent participation

## Current Skeleton

- `app/main.py` exposes the FastAPI app and the first API routes.
- `app/conversation_service.py` handles explicit request queueing plus the claim/complete/fail lifecycle for external agents and user-triggered child-request delegation.
- `app/mcp_server.py` exposes MCP resources and tools from the same in-process store used by the web app.
- `app/agent_worker_manager.py` auto-starts configured external MCP worker processes when the app starts.
- `workers/mcp_agent_worker.py` is the reference external MCP client process that claims queued requests and calls model APIs outside the FastAPI app.
- `app/moonshine_service.py` captures microphone audio with `sounddevice` and feeds it into Moonshine's streaming transcriber.
- `app/transcript_store.py` is the source of truth for transcript state, utterance lifecycle state, request/thought grouping, child-request relationships, and the conversation timeline, persists it to local JSON storage, keeps the latest 10 events, and tracks local sequencing for stable history order.
- `request_id` is the primary workflow/trace identifier exposed to the UI and MCP. Multiple finalized `source_line_id` chunks can belong to one request.
- `ws/transcript` streams transcript updates from the shared store.
- `app/ui.py` serves the UI entrypoint, while `app/static/` contains the host-native frontend assets for the status bar, request queue/delegation controls, and recent conversation timeline.

Current protocol and product identity:

- FastAPI app title: `dubsar`
- MCP server name: `dubsar`
- MCP resource URI prefix: `dubsar://`

## Current Interaction Model

1. The microphone feeds Moonshine through `app/moonshine_service.py`.
2. Finalized transcript chunks are written into `app/transcript_store.py` as utterance records plus timeline events.
3. Consecutive message utterances are grouped into one open request/thought.
4. The current request remains pending until the user explicitly queues it.
5. `app/conversation_service.py` queues the request when the user presses a request-level `Queue` button or when an external API or MCP caller queues it.
6. The user can explicitly delegate a request to another connected agent, which creates a child request targeted at that agent.
7. An external MCP agent can then claim that queued request and write an assistant reply or failure back into the same timeline.
8. The UI and MCP surfaces observe the same shared state.
9. Explicit request lifecycle events are appended alongside state changes so the system exposes both current state and workflow history.

## Intended MCP-First Event Flow

1. Audio enters the system.
2. The local audio adapter forwards microphone frames into Moonshine.
3. Moonshine produces partial and/or final transcript updates.
4. Transcript state is updated in one place.
5. Transcript updates are mapped onto conversation events.
6. Finalized utterances become explicit store records with lifecycle state.
7. Consecutive message utterances can accumulate into one open request/thought.
8. The open request remains pending until a human or external MCP client explicitly acts on it.
9. External AI agents connect over MCP and read pending requests, timeline state, and status.
10. The user can create targeted child requests to bring another agent into the same workflow.
11. An external agent decides whether to answer or ignore the request it can see or claim.
12. The external agent writes a reply, status update, or action result back through MCP.
13. Those responses append to the same shared timeline and update request lifecycle state.
14. Updates are broadcast to the web UI.
15. The same state remains available to every MCP consumer, so monitoring and control happen against one source of truth.

## Directional Target

The intended next architecture step is:

- keep FastAPI as the host runtime for UI, MCP mount, and local APIs
- keep `TranscriptStore` as the single shared source of truth
- keep request submission explicit while the agent interaction model is being refined
- group multiple transcript chunks into one request/thought until the user closes that thought
- treat MCP as the standard interface for outside agents
- keep agent participation, replies, and later delegation out of the in-process reply loop
- add an explicit request lifecycle so one thought can later be observed, claimed, delegated, acted on, and completed by external agents

Near-term implementation direction:

- keep the current request-based interaction model stable
- expand MCP resources and tools until external agents can participate with richer lifecycle visibility
- use a separate worker process as the default integration pattern for OpenAI- and Anthropic-backed external agents
- further separate frontend concerns inside `app/static/` so status rendering, timeline rendering, websocket transport, and agent activity views are easier to evolve independently

## Design Bias

- Prefer one source of truth for transcript state.
- Keep the first MCP server in process with the FastAPI app so MCP reads and tool actions operate on live shared state.
- Keep transcription separate from agent execution.
- Keep the first version narrow and easy to debug.
- Prefer explicit, observable audio/transcript flow over opaque wrappers when debugging real-time behavior.
