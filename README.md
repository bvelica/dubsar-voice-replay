## Description

A small local-first voice-to-action server that uses Moonshine AI for live English speech-to-text, streams transcripts to a web UI, and exposes them through MCP so AI agents can read voice commands and trigger actions.

## Features

- Live English speech-to-text with Moonshine AI
- Real-time transcript display in a web interface
- MCP integration for AI agents
- Local-first workflow for low-latency voice interactions

## Development

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Download the default English Moonshine model into a repo-local cache:

```bash
XDG_CACHE_HOME=$PWD/.cache python -m moonshine_voice.download --language en
```

Run the FastAPI app:

```bash
XDG_CACHE_HOME=$PWD/.cache uvicorn app.main:app --reload
```

Open the app locally at `http://127.0.0.1:8000`.

On startup, the server will attempt to start the Moonshine microphone transcriber automatically. The home page shows component status and live transcript updates.

The current working path is:

1. capture microphone audio with `sounddevice`
2. feed that audio into Moonshine's streaming transcriber
3. keep transcript state in memory
4. stream transcript updates to the browser over WebSocket

Useful endpoints:

- `GET /health`
- `GET /api/status`
- `GET /api/transcript`
- `WS /ws/transcript`

Optional manual controls remain available:

- `POST /api/transcriber/start`
- `POST /api/transcriber/stop`

## Notes

- This project is intended for English-only Moonshine usage.
- It is designed for local deployment and simple integration with AI-agent workflows through MCP.
- Microphone access is expected to work best in a normal host session, not in a restricted sandbox.
- The current implementation is host-native and intentionally keeps the setup simple instead of using Docker.
