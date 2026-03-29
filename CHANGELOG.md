# Changelog

All notable changes to this project should be recorded in this file.

The format is based on Keep a Changelog and the project uses Semantic Versioning.

## [Unreleased]

### Added

- Initial FastAPI application skeleton
- In-memory transcript store and WebSocket transcript stream
- Host-native web UI with component status and live transcript display
- Local transcript persistence in `data/transcript_history.json`
- Unified conversation timeline with user transcript events and simulated assistant echo replies
- Mounted FastMCP server for live in-process transcript access
- Agent router, command resolver, and provider adapter architecture
- OpenAI-backed assistant replies appended into the shared conversation timeline
- Repo-local `.env` support for provider configuration

### Changed

- Shifted runtime direction from Docker-first notes to host-native execution
- Adopted direct `sounddevice` microphone capture feeding Moonshine's streaming transcriber
- Updated the UI to render recent conversation events instead of only raw transcript lines
- Replaced the temporary echo-reply path with provider-driven assistant responses
- Switched the documented local Uvicorn run command to `--ws websockets-sansio`
- Renamed the public app identity to `dubsar`, including the FastAPI title, MCP server identity, and preferred config env prefix

## [0.1.0] - 2026-03-28

### Added

- Initial project documentation scaffold
- Persistent project context, decisions, and architecture notes
- Repository-level version tracking via `VERSION`
