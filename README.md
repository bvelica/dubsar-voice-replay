## Description

A small local-first voice-to-action server that uses Moonshine AI for live English speech-to-text, streams transcripts to a web UI, and exposes them through MCP so AI agents can read voice commands and trigger actions.

## Features

- Live English speech-to-text with Moonshine AI
- Real-time conversation timeline in a web interface
- MCP integration for AI agents
- Local-first workflow for low-latency voice interactions

## Development

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a local environment file for provider credentials:

```bash
cp .env.example .env
```

Only put local secrets in `.env`. Do not commit `.env`, API keys, provider tokens, or exported credential files.

Download the default English Moonshine model into a repo-local cache:

```bash
XDG_CACHE_HOME=$PWD/.cache python -m moonshine_voice.download --language en
```

Run the FastAPI app:

```bash
XDG_CACHE_HOME=$PWD/.cache uvicorn app.main:app --reload --ws websockets-sansio
```

Open the app locally at `http://127.0.0.1:8000`.

On startup, the server will attempt to start the Moonshine microphone transcriber automatically. The home page shows a status bar and a scrollable conversation timeline with recent user transcript events and assistant replies. If `OPENAI_API_KEY` is set, finalized user transcript lines are routed to the OpenAI provider by default and the response is appended back into the shared timeline.

Finalized transcript chunks are grouped into one open draft/thought until you close that draft. Use the `Send Latest` button in the UI or speak a routing command such as `command send to chatgpt` to close and send the current draft.

Finalized user speech is now tracked as explicit utterances with lifecycle state such as pending, processing, completed, or failed. The UI timeline reflects that state for each finalized user message.

The first spoken command path is also available. A finalized command utterance such as `command send to chatgpt` or `command execute openai` will act on the latest open draft and route it to the chosen provider. The alias `chatgpt` currently maps to the OpenAI provider.

Multiple finalized message utterances can now belong to one draft/thought. That means Moonshine can still emit several finalized chunks internally, while the app can display and route them as one user thought until the user closes that draft by pressing `Send Latest` or speaking a routing command.

Important interaction rule:

- recognized spoken commands do not become part of the prompt text sent to the AI
- they act on the current open draft as control utterances
- failed drafts stay visible and can be retried with `Send`
- new normal speech starts a new draft instead of appending to a failed one

Current role split:

- the built-in local voice-to-AI reply loop stays inside the FastAPI app, transcript store, conversation service, and provider adapters
- MCP is mounted into that same app as an external integration surface for outside agent clients
- the product direction is to use explicit manual send or spoken command phrases to close and route the latest open draft

The current working path is:

1. capture microphone audio with `sounddevice`
2. feed that audio into Moonshine's streaming transcriber
3. map transcript updates into a shared conversation timeline
4. keep that state in memory and persist it locally
5. stream conversation updates to the browser over WebSocket
6. expose the same live state to MCP consumers

## Current Structure

Key files and modules:

- `app/main.py`: FastAPI entrypoint, lifecycle wiring, API routes, WebSocket route, MCP mount
- `app/config.py`: settings and `.env` loading
- `app/moonshine_service.py`: microphone capture and Moonshine streaming transcription
- `app/transcript_store.py`: in-memory transcript and conversation timeline persistence
- `app/conversation_service.py`: buffered draft submission, spoken command handling, and assistant reply orchestration
- `app/agent_registry.py`: registry of known target names, aliases, and configured provider adapters
- `app/agent_router.py`: provider selection for each finalized utterance
- `app/commands.py`: current command parsing plus the future landing point for spoken routing phrases
- `app/agents/base.py`: provider interface and reply model
- `app/agents/openai_provider.py`: first provider implementation using the OpenAI Responses API
- `app/response_writer.py`: appends assistant and system events back into the shared timeline
- `app/mcp_server.py`: FastMCP resources and tools exposed from the live in-process app state
- `app/ui.py`: UI entrypoint that serves the index shell
- `app/static/`: static HTML, CSS, and JavaScript assets for the transcript UI
- `docs/context.md`: current product scope and constraints
- `docs/decisions.md`: persistent technical decisions
- `docs/architecture.md`: current system shape and event flow
- `.env.example`: safe template for local provider configuration
- `data/transcript_history.json`: local persisted conversation history

Useful endpoints:

- `GET /health`
- `GET /api/status`
- `GET /api/transcript`
- `WS /ws/transcript`
- `POST /api/assistant/send-draft/{draft_id}`
- MCP endpoint mounted at `/mcp/`

Current MCP resources and tools now include draft-aware lifecycle access in addition to transcript snapshot access. MCP clients can read utterance records, inspect the latest pending draft, send the latest draft through the default provider path, or route a specific/latest draft to a chosen provider.

## Current Course Of Action

The current product direction is:

1. Keep the local voice-to-AI loop simple and explicit.
2. Use drafts/thoughts as the user-facing unit, not raw Moonshine chunks.
3. Use spoken commands as control phrases that act on drafts.
4. Keep MCP as the external integration surface for outside agents.
5. Grow toward multi-agent delegation by extending the provider/agent registry and MCP surface rather than rewriting the core transcript flow.

The current near-term engineering direction is:

- keep refining the draft and command model
- add another real provider adapter after OpenAI
- continue cleaning up the frontend structure now that it has been split into static assets
- preserve one shared source of truth in `TranscriptStore` for UI, MCP, and agent runtime behavior

Optional manual controls remain available:

- `POST /api/transcriber/start`
- `POST /api/transcriber/stop`

Optional provider configuration:

```bash
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5-mini
TRANSCRIPTOR_DEFAULT_PROVIDER=openai
```

Example `.env`:

```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-5-mini
TRANSCRIPTOR_DEFAULT_PROVIDER=openai
```

Restart the app after changing `.env`.

## Notes

- This project is intended for English-only Moonshine usage.
- It is designed for local deployment and simple integration with AI-agent workflows through MCP.
- The MCP server is mounted into the same FastAPI process so MCP clients can access live in-memory transcript state instead of a stale copy from another process.
- The current built-in reply path does not route through MCP; MCP is the external integration layer, not the internal reply transport.
- Voice transcripts now flow through an internal agent router and provider adapter layer so different AI backends can be added without changing the UI or transcript store.
- The planned command model is: speak content first so it builds the current draft, then use a later spoken command phrase to route that draft to a chosen agent.
- Repo-local `.env` loading is supported for provider credentials and router defaults.
- Microphone access is expected to work best in a normal host session, not in a restricted sandbox.
- The current implementation is host-native and intentionally keeps the setup simple instead of using Docker.
- Conversation history is persisted locally in `data/transcript_history.json` and currently keeps the latest 10 events.

## Secret Handling

- `.env` is for local development only and is git-ignored.
- `data/transcript_history.json` is git-ignored because it contains local conversation data.
- Keep real API keys only in environment variables, `.env`, or a proper secret manager.
- Never hardcode provider credentials in Python, JavaScript, or docs.
- Keep `.env.example` as placeholders only.
