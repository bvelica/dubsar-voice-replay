# Dubsar Voice Relay

Dubsar Voice Relay is a local-first voice-to-agent host.

It captures microphone audio, transcribes English speech with Moonshine, groups finalized speech into requests, shows that live state in a small web UI, and exposes the same state through MCP so external AI agents can consume it and act on it.

## What It Does

- live local speech-to-text with Moonshine
- request-based voice input instead of auto-sending raw transcript chunks
- one shared transcript and conversation timeline
- MCP resources and tools over the same live in-process state
- a web UI for monitoring, reviewing requests, explicit queue actions, and user-triggered delegation

## Product Direction

The intended architecture is MCP-first:

- Dubsar Voice Relay owns microphone capture, Moonshine transcription, request grouping, persistence, and UI
- MCP is the standard external interface over that live state
- AI agents such as ChatGPT, Claude, Gemini, or Codex-like workers are treated as external MCP clients
- the web app remains the human-facing monitor and manual control surface

The app no longer depends on built-in provider adapters. External MCP clients are the agent execution path.

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

Configure any agents you want to start automatically in `.env`:

```env
OPENAI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
AUTO_START_OPENAI_AGENT=1
AUTO_START_ANTHROPIC_AGENT=1
```

Configure spoken routing slots in `.env` using nested settings keys. Up to 5 slots are supported:

```env
AGENT_SLOT_1__ENABLED=1
AGENT_SLOT_1__TARGET_AGENT_NAME=chatgpt
AGENT_SLOT_1__LABEL=Agent 1
AGENT_SLOT_1__ALIASES=["agent one","one","gpt"]

AGENT_SLOT_2__ENABLED=1
AGENT_SLOT_2__TARGET_AGENT_NAME=claude
AGENT_SLOT_2__LABEL=Agent 2
AGENT_SLOT_2__ALIASES=["agent two","two","claude"]
```

This keeps the spoken command layer configurable. The user can say `Agent 1, ...` or any configured alias instead of depending on hardcoded vendor names in code.

If a provider key exists, Dubsar Voice Relay will start that external MCP worker automatically on app startup by default. You can disable one explicitly by setting its `AUTO_START_...` flag to `0`.

Download the default English Moonshine model into the repo-local cache:

```bash
XDG_CACHE_HOME=$PWD/.cache python -m moonshine_voice.download --language en
```

Run the app:

```bash
XDG_CACHE_HOME=$PWD/.cache uvicorn app.main:app --reload --ws websockets-sansio
```

Open `http://127.0.0.1:8000`.

The app will auto-start external MCP workers for ChatGPT/OpenAI and Claude/Anthropic when their keys are configured.

Manual worker launch is still available for debugging:

```bash
venv/bin/python workers/mcp_agent_worker.py --backend openai
venv/bin/python workers/mcp_agent_worker.py --backend anthropic
```

## Intended Interaction Model

1. Start the utterance with a configured agent-slot alias, such as `Agent 1 ...` or `Agent 2 ...`.
2. Speak naturally after that prefix.
3. Moonshine may finalize the speech in multiple chunks if the user pauses.
4. Dubsar Voice Relay should keep grouping those chunks into one targeted request while the user is still on the same thought.
5. After a short idle pause, the targeted request is queued automatically.
6. The targeted agent claims it and replies.
7. That reply is appended to the shared conversation timeline and remains visible to other agents.
8. The user can then ask another agent to confirm, verify, or challenge the earlier reply by starting the next utterance with that other slot's alias.

Example flow:

- `Agent 1, what is the capital of France?`
- `Agent 2, is Agent 1 correct?`
- `Agent 2, please confirm whether Paris is the capital of France.`

Each spoken thought is tracked as a `request_id`. One request can contain multiple finalized Moonshine chunks, and the conversation timeline is shared across agents so later requests can reference earlier replies naturally.

The current implementation still keeps a manual `Queue Now` fallback in the UI, but targeted spoken requests now route from configured leading aliases in the backend and auto-queue after a short idle pause.

## Intended MCP-First Flow

1. The microphone feeds Moonshine locally.
2. Moonshine writes transcript updates into Dubsar Voice Relay's shared store.
3. Dubsar Voice Relay exposes requests, timeline events, and status through MCP.
4. External AI agents connect as MCP clients.
5. Those agents read pending requests, decide what to do, and write replies or status updates back through MCP.
6. The web UI shows the same shared state so the whole interaction remains visible.

## API Surface

Useful endpoints:

- `GET /health`
- `GET /api/status`
- `GET /api/transcript`
- `POST /api/drafts/{draft_id}/queue`
- `POST /api/requests/{request_id}/delegate/{agent_name}`
- `POST /api/transcript/clear`
- `WS /ws/transcript`
- MCP mounted at `/mcp/`

Current MCP resources:

- `dubsar://status`
- `dubsar://snapshot`
- `dubsar://latest-user-message`
- `dubsar://utterances`
- `dubsar://requests`
- `dubsar://queued-drafts`
- `dubsar://queued-requests`
- `dubsar://agent-statuses`
- `dubsar://request-events`

Current MCP tools:

- `start_transcriber`
- `stop_transcriber`
- `clear_transcript`
- `set_agent_status`
- `queue_draft`
- `delegate_request`
- `claim_draft`
- `complete_draft`
- `fail_draft`

## Main Modules

- `app/main.py`: FastAPI app, routes, WebSocket, MCP mount
- `app/moonshine_service.py`: microphone capture and Moonshine transcription
- `app/transcript_store.py`: shared transcript, request, and timeline state
- `app/conversation_service.py`: request queueing plus claim/complete/fail lifecycle for external agents and user-triggered child-request delegation
- `app/mcp_server.py`: MCP resources and tools over live in-process state
- `workers/mcp_agent_worker.py`: external MCP agent process for OpenAI or Anthropic
- `app/static/`: web UI assets

## Notes

- English-only for now
- local conversation history persists in `data/transcript_history.json`
- the current history window is intentionally short
- microphone access works best in a normal host session, not a restricted sandbox
- MCP is the agent integration surface
