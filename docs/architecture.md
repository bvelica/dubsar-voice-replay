# Architecture Notes

## Proposed High-Level Shape

The system should be organized around a single transcript/event flow rather than separate pipelines for UI and MCP.

Core areas:

- audio ingestion
- speech-to-text integration
- transcript state and event stream
- web API and UI transport
- MCP integration
- action execution

## Proposed v1 Event Flow

1. Audio enters the system.
2. Moonshine produces partial and/or final transcript updates.
3. Transcript state is updated in one place.
4. Updates are broadcast to the web UI.
5. The same state is exposed to MCP consumers.
6. Action logic evaluates transcript events.

## Design Bias

- Prefer one source of truth for transcript state.
- Keep action execution separate from transcription.
- Keep the first version narrow and easy to debug.
