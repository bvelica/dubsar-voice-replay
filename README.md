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

## Notes

- This project is intended for English-only Moonshine usage.
- It is designed for local deployment and simple integration with AI-agent workflows through MCP.
- The MCP server is mounted into the same FastAPI process so MCP clients can access live in-memory transcript state instead of a stale copy from another process.
- Voice transcripts now flow through an internal agent router and provider adapter layer so different AI backends can be added without changing the UI or transcript store.
- Repo-local `.env` loading is supported for provider credentials and router defaults.
- Microphone access is expected to work best in a normal host session, not in a restricted sandbox.
- The current implementation is host-native and intentionally keeps the setup simple instead of using Docker.
- Conversation history is persisted locally in `data/transcript_history.json` and currently keeps the latest 10 events.
