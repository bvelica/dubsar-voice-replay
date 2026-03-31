# Dubsar

Dubsar is a local-first voice-to-agent relay.

It captures microphone audio, transcribes English speech with Moonshine, groups finalized speech into a draft, shows that live state in a small web UI, and routes the draft to an AI provider only when you explicitly send it. The same state is also exposed through MCP for external agent clients.

## What It Does

- live local speech-to-text with Moonshine
- draft-based voice input instead of auto-sending raw transcript chunks
- explicit routing by button press or spoken commands such as `command send to chatgpt`
- shared conversation state across the web UI and MCP

## Local-Only

This app is meant to run on a trusted local machine or local network under your control.

Do not expose the HTTP API, WebSocket endpoint, or MCP surface directly to the public internet.

## Quick Start

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Add local provider settings in `.env` if you want OpenAI replies:

```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-5-mini
DUBSAR_DEFAULT_PROVIDER=openai
```

Download the default English Moonshine model into the repo-local cache:

```bash
XDG_CACHE_HOME=$PWD/.cache python -m moonshine_voice.download --language en
```

Run the app:

```bash
XDG_CACHE_HOME=$PWD/.cache uvicorn app.main:app --reload --ws websockets-sansio
```

Open `http://127.0.0.1:8000`.

## Interaction Model

1. Speak normally.
2. Moonshine may finalize that speech in multiple chunks.
3. Dubsar groups those chunks into one open draft.
4. Send the draft with the UI or a spoken command such as `command send to chatgpt`.
5. Spoken commands act as control utterances and are not included in the prompt text.

If a draft fails, it stays visible and can be retried.

## API Surface

Useful endpoints:

- `GET /health`
- `GET /api/status`
- `GET /api/transcript`
- `POST /api/assistant/send-latest`
- `POST /api/assistant/send-draft/{draft_id}`
- `WS /ws/transcript`
- MCP mounted at `/mcp/`

## Main Modules

- `app/main.py`: FastAPI app, routes, WebSocket, MCP mount
- `app/moonshine_service.py`: microphone capture and Moonshine transcription
- `app/transcript_store.py`: shared transcript, draft, and timeline state
- `app/conversation_service.py`: command handling and draft submission
- `app/agent_registry.py` and `app/agent_router.py`: target naming and provider routing
- `app/agents/openai_provider.py`: OpenAI Responses API adapter
- `app/mcp_server.py`: MCP resources and tools over live in-process state
- `app/static/`: web UI assets

## Notes

- English-only for now
- local conversation history persists in `data/transcript_history.json`
- the current history window is intentionally short
- microphone access works best in a normal host session, not a restricted sandbox
