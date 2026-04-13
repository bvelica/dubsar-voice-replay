# Changelog

All notable changes to this project should be recorded in this file.

The format is based on Keep a Changelog and the project uses Semantic Versioning.

## [Unreleased]

### Changed

## [0.3.0] - 2026-04-13

### Changed

- Renamed the public-facing app identity from `Dubsar` to `Dubsar Voice Relay` across the UI, docs, prompts, and status metadata while keeping the `dubsar://` MCP URI prefix stable
- Removed spoken agent-routing commands from the live speech path; drafts are now submitted explicitly through the UI or external API/MCP callers
- Removed implicit "latest draft" send endpoints and MCP tools in favor of explicit draft-ID-based submission
- Cleared command-era UI labeling and restored an empty persisted transcript baseline
- Added backend tests for draft grouping and explicit provider submission
- Updated the docs to make the MCP-first external-agent direction the current architectural target while keeping built-in providers as a transitional path
- Replaced the built-in provider reply loop with an MCP-first queued draft lifecycle driven by external agent status, claim, complete, and fail actions
- Removed the old provider-routing modules and updated the UI to queue drafts for external agents instead of sending them directly to in-process adapters
- Added `workers/mcp_agent_worker.py` as a real external MCP client for OpenAI or Anthropic, plus tests for its local draft/prompt handling
- Auto-started configured OpenAI and Anthropic MCP workers from `.env` on app startup so the app is usable without launching extra terminals
- Added a request-centric trace model with visible `request_id` values and explicit request lifecycle events across the store, MCP resources, tests, and UI timeline
- Added user-triggered delegation through child requests, targeted-agent claiming rules, and a dedicated requests panel in the UI so parent and child request activity stays visible
- Updated the product docs to make the next interaction-model refactor explicit: agent-routing commands belong at the beginning of the spoken utterance, replies stay in shared conversation context, and child requests should no longer be the default path for ordinary first-hop routing
- Implemented leading-agent voice routing in the backend so speech like `ChatGPT ...` or `Claude ...` creates targeted requests with the command stripped from request text
- Added automatic queueing for targeted spoken requests after a short idle pause so slow Moonshine chunking can still collapse into one routed request
- Tightened request completion and failure rules so only the agent that claimed a request can finish it
- Added request-first MCP tool names alongside legacy draft aliases and moved the reference MCP worker onto the request-first naming path
- Replaced hardcoded spoken agent names with configurable `.env`-driven agent slots so aliases like `Agent 1` and `Agent 2` can be mapped to any MCP agent target without code changes
- Updated README and architecture/context docs to define the next voice-first routing model around leading agent commands such as `ChatGPT ...` and `Claude ...`
- Recorded the decision that shared agent replies must remain visible to other agents for later verification and cross-checking
- Clarified that child requests should be reserved for explicit follow-up verification work rather than normal first-hop request routing

## [0.2.0] - 2026-04-01

### Added

- Initial FastAPI application skeleton
- In-memory transcript store and WebSocket transcript stream
- Host-native web UI with component status and live transcript display
- Local transcript persistence in `data/transcript_history.json`
- Unified conversation timeline with user transcript events and simulated assistant echo replies
- Mounted FastMCP server for live in-process transcript access
- Agent router, command resolver, and provider adapter architecture
- OpenAI-backed assistant replies appended into the shared conversation timeline
- Claude-backed assistant replies through Anthropic's Messages API
- Repo-local `.env` support for provider configuration

### Changed

- Shifted runtime direction from Docker-first notes to host-native execution
- Adopted direct `sounddevice` microphone capture feeding Moonshine's streaming transcriber
- Updated the UI to render recent conversation events instead of only raw transcript lines
- Replaced the temporary echo-reply path with provider-driven assistant responses
- Switched the documented local Uvicorn run command to `--ws websockets-sansio`
- Renamed the public app identity to `dubsar`, including the FastAPI title, MCP server identity, and preferred config env prefix
- Extended the assistant status header to show per-provider readiness for configured AI agents
- Added short routing utterances such as `agent claude` and `agent chatgpt` to send the latest pending draft to a named agent
- Switched the default-provider env var from `DUBSAR_DEFAULT_PROVIDER` to `DEFAULT_AI`
- Removed the global `Send Latest` button in favor of draft-level send controls
- Colored assistant replies by agent and tightened status and timeline labeling to use the actual routed provider
- Improved the Clear action to surface request failures in the UI instead of failing silently

## [0.1.0] - 2026-03-28

### Added

- Initial project documentation scaffold
- Persistent project context, decisions, and architecture notes
- Repository-level version tracking via `VERSION`
