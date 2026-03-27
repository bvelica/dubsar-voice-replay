# Project Context

## What This Project Is

`transcriptor` is a local-first voice-to-action server.

The intended flow is:

1. Capture speech locally.
2. Transcribe it live with Moonshine.
3. Stream transcript updates to a web UI.
4. Expose transcript state through MCP so AI agents can consume voice input.
5. Allow agents or application logic to trigger actions from those transcripts.

## Current Intent

The initial version should prioritize:

- low-latency local speech-to-text
- real-time transcript visibility
- a clean MCP integration surface
- a conservative action model

## Constraints

- English-first initially
- local deployment first, not cloud-first
- architecture should be simple enough to iterate quickly

## Current Stack Decisions

- Backend: Python
- API framework: FastAPI
- Lower-level languages such as Go or Rust are acceptable later for isolated performance-sensitive components

## Open Product Questions

- Where audio capture should happen in v1: browser, local process, or both
- Whether action triggering should be fully automatic or gated
- What MCP should expose first: transcript history, live subscription, tools, or some combination
- What the first concrete supported actions should be
