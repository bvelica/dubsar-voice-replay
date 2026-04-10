# Decisions Log

This file records decisions that should persist across sessions.

## 2026-03-28

### Backend Language

- Decision: Use Python for the main application.
- Reason: It is the most practical fit for Moonshine integration, API development, MCP integration, and fast iteration.

### API Framework

- Decision: Use FastAPI instead of Flask.
- Reason: The application is real-time and event-oriented, and FastAPI is a better fit for WebSockets, async patterns, and typed APIs.

### Performance Strategy

- Decision: Introduce Go or Rust only if a specific subsystem proves to need lower-level optimization.
- Reason: Early multi-language complexity would slow iteration without clear evidence of need.

### Versioning Strategy

- Decision: Track the app version in a top-level `VERSION` file and maintain release notes in `CHANGELOG.md`.
- Reason: Git history alone is not a clean product-versioning mechanism; explicit version and changelog files make milestones and releases easier to manage.

### Versioning Scheme

- Decision: Use Semantic Versioning.
- Reason: It is simple, standard, and a good fit for an application that may become public and distributed.

### Initial Audio Capture Strategy

- Decision: Start v1 with local microphone capture in the server environment, based on Moonshine's Python microphone transcription flow.
- Reason: This follows the upstream reference path directly and gets to a working CLI-first prototype faster than designing browser audio transport first.

### Speech-to-Text Upstream

- Decision: Build on the `moonshine-ai/moonshine` repository and its Python package flow.
- Reason: It is the canonical upstream for Moonshine Voice and explicitly supports real-time microphone transcription.

### Runtime Model

- Decision: Keep v0/v1 host-native instead of introducing Docker early.
- Reason: Direct microphone access and fast iteration are more important right now than container packaging.

### Audio Integration Detail

- Decision: Use a direct `sounddevice` microphone capture path that feeds audio into Moonshine's streaming transcriber.
- Reason: This gives better observability and proved more reliable for debugging than treating the upstream microphone wrapper as a black box.

### Transcript Persistence

- Decision: Persist transcript history locally in a JSON file under `data/`.
- Reason: It keeps the first persistence layer simple, inspectable, and aligned with the local-first design.

### Transcript Retention

- Decision: Keep only the latest 10 transcript lines in memory, in the API response, in the UI, and in local persistence.
- Reason: The current UI is intentionally focused on the most recent speech, and a short fixed window keeps behavior predictable.

### Transcript Ordering

- Decision: Track local sequencing metadata and display transcript history in chronological order, oldest to newest.
- Reason: Reviewable conversation history should not depend on upstream Moonshine line IDs or reverse-order rendering.

### Conversation Timeline Model

- Decision: Use a unified conversation/event timeline for the UI-facing history instead of rendering only transcript lines.
- Reason: The product is intended to feel conversational, so user speech and assistant output should share one ordered stream.

### Simulated Assistant Replies

- Decision: Add a temporary echo-style assistant reply when a user transcript line becomes final.
- Reason: This makes the conversation loop visible before real agent or action responses exist.

## 2026-03-29

### Initial MCP Server Integration

- Decision: Implement the first MCP server with FastMCP and mount it into the existing FastAPI process at `/mcp`.
- Reason: The shared in-process `TranscriptStore` is the live source of truth; a separate stdio server process would not see current in-memory transcript state without an extra bridge layer.

### Multi-Provider Response Architecture

- Decision: Route finalized user transcript events through an internal agent router and provider adapter layer instead of binding transcript completion directly to one model API.
- Reason: The product direction requires switching between OpenAI, Claude, Gemini, and command-based routing later without reworking the UI or transcript store.

### Initial Real Reply Provider

- Decision: Use the OpenAI Python SDK with the Responses API as the first real provider implementation.
- Reason: It is a practical way to replace the temporary echo reply quickly while keeping the provider interface clean enough for additional backends.

### Second Real Reply Provider

- Decision: Add Claude through Anthropic's Messages API as the second real provider adapter.
- Reason: The app is intended to route drafts across multiple named agents/providers, and Claude is a practical next backend to validate the provider abstraction and visible provider status flow.

### Local Provider Credential Loading

- Decision: Load provider configuration from environment variables and a repo-local `.env` file during development.
- Reason: It keeps API keys out of source control while making local startup practical without re-exporting variables in every shell session.

### Default WebSocket Backend

- Decision: Use Uvicorn with the `websockets-sansio` backend as the default local run configuration.
- Reason: It avoids the legacy `websockets` handler deprecation warning while keeping the standard FastAPI/Uvicorn stack.

### MCP Role Boundary

- Decision: Keep the built-in voice-to-AI reply loop inside the FastAPI app and transcript/conversation services instead of routing that loop through MCP.
- Reason: MCP is valuable here as the external integration surface for other agent clients, but the local reply loop should stay simple, direct, and in-process.

### Spoken Command Routing Direction

- Decision: Move toward a spoken command model where a freeform utterance is captured first and a later command phrase routes that pending utterance to a chosen agent.
- Reason: This matches how users naturally speak, avoids forcing command syntax into the content utterance itself, and leaves room for later multi-agent delegation.

### Multi-Agent Architecture Direction

- Decision: Treat provider adapters as one layer and agent orchestration as a separate higher-level layer built on the shared transcript/event store.
- Reason: Adding another model provider is not the same as adding another agent role; keeping orchestration separate will make delegation, routing, and parallel agent execution simpler later.

### Utterance Lifecycle Model

- Decision: Represent finalized user speech as explicit utterance state in the shared store with lifecycle statuses such as pending, routed, processing, completed, and failed.
- Reason: Timeline events alone are too implicit for command routing, retry behavior, UI pipeline tracking, and restart-safe agent orchestration.

### Initial Spoken Command Grammar

- Decision: Support explicit spoken control phrases that act on the latest pending utterance, starting with forms such as "command send to <provider>" and "command execute <provider>".
- Reason: A narrow, explicit grammar is easier to say, easier to parse reliably from voice input, and safer than trying to infer control intent from arbitrary speech.

### Short Agent Routing Commands

- Decision: Support short routing utterances such as `agent claude` and `agent chatgpt` as explicit commands that act on the latest pending draft.
- Reason: This keeps routing explicit and reliable in voice use without depending on prompt-text parsing after Moonshine chunking and draft grouping.

### MCP Utterance Exposure

- Decision: Expose utterance lifecycle state and routing actions through MCP using the same internal conversation service used by the web UI.
- Reason: External agents should observe and trigger the same lifecycle semantics as the local app instead of going through a separate MCP-only code path.

### Provider And Target Registry

- Decision: Centralize known agent/provider targets and spoken aliases in a small registry instead of hardcoding them independently across status, command parsing, and app setup.
- Reason: This keeps names like `chatgpt`, `openai`, `claude`, and `gemini` consistent and makes adding new adapters mostly a registry plus provider-wiring change.

### Draft Thought Grouping

- Decision: Group multiple finalized message utterances into a shared draft/thought until the user closes that draft by pressing send or speaking a routing command.
- Reason: Moonshine may split one spoken thought across multiple finalized transcript lines; the app should keep per-utterance identity internally while routing and displaying a more natural user-intent unit.

### Auto-Submit Removal

- Decision: Remove the old transcript auto-submit mode instead of carrying it forward into the draft-based flow.
- Reason: Auto-submitting finalized chunks conflicts with the new draft/thought model and would prematurely send partial speech before the user closes the draft intentionally.

### Draft Submission Semantics

- Decision: Treat drafts as the user-facing submission unit, keep command utterances separate from draft content, and allow failed drafts to be retried explicitly with `Send`.
- Reason: Moonshine chunks are too low-level to be the stable unit of user intent. Commands should operate on drafts rather than becoming part of prompt text, and failed drafts should remain visible and retryable without absorbing unrelated later speech.

### Frontend Asset Split

- Decision: Move the web UI out of the giant inline HTML string in `app/ui.py` into static assets under `app/static/`, while keeping `app/ui.py` as a thin entrypoint.
- Reason: The UI now has enough behavior and structure that inline HTML/CSS/JS is harder to maintain than a small static asset layout. Static files make the frontend easier to inspect, edit, and split further later without changing the host runtime model.

### Product Rename

- Decision: Rename the public-facing app identity to `dubsar`, while temporarily keeping the previous env prefix as fallback inputs.
- Reason: The previous name described the function but was too generic. `dubsar` is more distinctive, and keeping the old env fallback avoided breaking local setups during the rename.

### Remove Legacy Rename Compatibility

- Decision: Remove the temporary old environment-variable prefix fallback and keep the runtime config surface minimal.
- Reason: The rename is complete, and keeping stale compatibility inputs around leaves outdated product identity in the runtime and docs.

### Default Provider Env Name

- Decision: Use `DEFAULT_AI` as the env var for the fallback reply provider instead of `DUBSAR_DEFAULT_PROVIDER`.
- Reason: The app's voice routing model is centered on named AI agents, and `DEFAULT_AI` is shorter and clearer in local `.env` configuration.

## 2026-04-03

### Remove Voice Routing Commands

- Decision: Remove spoken routing commands such as `agent claude` and `agent chatgpt` from the live speech path for now.
- Reason: Moonshine chunking makes short command utterances too brittle in practice, and explicit draft submission through the UI or APIs is more predictable while the routing model is reconsidered.

### Remove Implicit Latest-Draft Submission

- Decision: Remove the implicit "send latest draft" actions from the web/API/MCP surface and keep submission draft-ID-based.
- Reason: A back-to-basics interaction model is easier to reason about when every send action names the draft it is operating on and the app no longer tries to guess user intent from recency alone.

### MCP-First Agent Direction

- Decision: Move the product direction toward treating AI agents as external MCP clients rather than the long-term in-process reply mechanism.
- Reason: This creates a cleaner separation of concerns. Dubsar can own voice capture, Moonshine transcription, shared state, persistence, and UI, while agent behavior becomes externally observable, replaceable, and easier to monitor through one standard protocol surface.

### Built-In Providers As Transitional Path

- Decision: Keep the current built-in OpenAI and Claude provider adapters temporarily as a transition path while the MCP-first model is being designed and implemented.
- Reason: They keep the app usable for testing and comparison while the MCP-first external-agent workflow is still being introduced.

### Remove Built-In Provider Loop

- Decision: Remove the in-process provider-routing and reply-generation path from the live app and make draft queueing plus MCP agent lifecycle the only runtime path.
- Reason: Keeping both architectures active at once kept the code and UI semantically muddy. The MCP-first direction is now explicit enough that the runtime should reflect it directly.

### Request-Centric Visibility Model

- Decision: Use `request_id` as the primary visible workflow identifier and keep `source_line_id` as the lower-level Moonshine chunk identifier underneath it.
- Reason: One spoken thought can span multiple finalized Moonshine chunks. A request-level trace is easier to understand than exposing only low-level utterance/chunk IDs, while still preserving chunk lineage for debugging.

### Explicit Request Event Log

- Decision: Record explicit request lifecycle events such as creation, update, queue, claim, completion, and failure in the shared store and expose them to both the UI and MCP.
- Reason: Current-state fields alone do not tell the story of what happened. A lightweight append-only request event log gives the app the observability needed to debug Moonshine chunking, MCP handoff, and external agent execution.

### User-Triggered Delegation Via Child Requests

- Decision: Model delegation as explicit user-triggered child requests instead of agent-initiated hidden delegation.
- Reason: The user should stay in control of when another agent is pulled in. Child requests keep delegation visible, traceable, and compatible with the request-centric observability model.

## 2026-04-10

### Public Product Name Update

- Decision: Rename the public-facing app identity from `Dubsar` to `Dubsar Voice Relay`, while keeping the `dubsar://` MCP URI prefix stable for compatibility.
- Reason: The new name is more descriptive in UI and documentation, and keeping the MCP URI prefix unchanged avoids an unnecessary protocol-level break.
