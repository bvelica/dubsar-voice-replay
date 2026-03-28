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

## Current v0.1 Skeleton

- `app/main.py` exposes the FastAPI app and the first API routes.
- `app/moonshine_service.py` captures microphone audio with `sounddevice` and feeds it into Moonshine's streaming transcriber.
- `app/transcript_store.py` is the in-memory source of truth for transcript state.
- `ws/transcript` streams transcript updates from the shared store.
- `app/ui.py` serves the minimal host-native UI with status and live transcript output.

## Proposed v1 Event Flow

1. Audio enters the system.
2. The local audio adapter forwards microphone frames into Moonshine.
3. Moonshine produces partial and/or final transcript updates.
4. Transcript state is updated in one place.
5. Updates are broadcast to the web UI.
6. The same state is exposed to MCP consumers.
7. Action logic evaluates transcript events.

## Design Bias

- Prefer one source of truth for transcript state.
- Keep action execution separate from transcription.
- Keep the first version narrow and easy to debug.
- Prefer explicit, observable audio/transcript flow over opaque wrappers when debugging real-time behavior.
