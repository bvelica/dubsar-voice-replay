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

### Local Provider Credential Loading

- Decision: Load provider configuration from environment variables and a repo-local `.env` file during development.
- Reason: It keeps API keys out of source control while making local startup practical without re-exporting variables in every shell session.

### Default WebSocket Backend

- Decision: Use Uvicorn with the `websockets-sansio` backend as the default local run configuration.
- Reason: It avoids the legacy `websockets` handler deprecation warning while keeping the standard FastAPI/Uvicorn stack.
