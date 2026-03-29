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

By default, finalized transcript lines are not auto-submitted to the assistant. Use the `Send Latest` button in the UI to send the latest finalized user line. You can opt back into automatic submission with `TRANSCRIPTOR_AUTO_SUBMIT_TRANSCRIPTS=true`.

The current working path is:

1. capture microphone audio with `sounddevice`
2. feed that audio into Moonshine's streaming transcriber
3. map transcript updates into a shared conversation timeline
4. keep that state in memory and persist it locally
5. stream conversation updates to the browser over WebSocket

## Current Structure

Key files and modules:

- `app/main.py`: FastAPI entrypoint, lifecycle wiring, API routes, WebSocket route, MCP mount
- `app/config.py`: settings and `.env` loading
- `app/moonshine_service.py`: microphone capture and Moonshine streaming transcription
- `app/transcript_store.py`: in-memory transcript and conversation timeline persistence
- `app/conversation_service.py`: buffered user utterance submission and assistant reply orchestration
- `app/agent_router.py`: provider selection for each finalized utterance
- `app/commands.py`: command parsing for provider overrides such as `/openai`
- `app/agents/base.py`: provider interface and reply model
- `app/agents/openai_provider.py`: first provider implementation using the OpenAI Responses API
- `app/response_writer.py`: appends assistant and system events back into the shared timeline
- `app/mcp_server.py`: FastMCP resources and tools exposed from the live in-process app state
- `app/ui.py`: single-page HTML UI for transcript, assistant replies, and status indicators
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
- MCP endpoint mounted at `/mcp/`

Optional manual controls remain available:

- `POST /api/transcriber/start`
- `POST /api/transcriber/stop`

Optional provider configuration:

```bash
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5-mini
TRANSCRIPTOR_DEFAULT_PROVIDER=openai
TRANSCRIPTOR_AUTO_SUBMIT_TRANSCRIPTS=false
```

Example `.env`:

```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-5-mini
TRANSCRIPTOR_DEFAULT_PROVIDER=openai
TRANSCRIPTOR_AUTO_SUBMIT_TRANSCRIPTS=false
```

Restart the app after changing `.env`.

## Notes

- This project is intended for English-only Moonshine usage.
- It is designed for local deployment and simple integration with AI-agent workflows through MCP.
- The MCP server is mounted into the same FastAPI process so MCP clients can access live in-memory transcript state instead of a stale copy from another process.
- Voice transcripts now flow through an internal agent router and provider adapter layer so different AI backends can be added without changing the UI or transcript store.
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
