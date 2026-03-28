# Changelog

All notable changes to this project should be recorded in this file.

The format is based on Keep a Changelog and the project uses Semantic Versioning.

## [Unreleased]

### Added

- Initial FastAPI application skeleton
- In-memory transcript store and WebSocket transcript stream
- Host-native web UI with component status and live transcript display

### Changed

- Shifted runtime direction from Docker-first notes to host-native execution
- Adopted direct `sounddevice` microphone capture feeding Moonshine's streaming transcriber

## [0.1.0] - 2026-03-28

### Added

- Initial project documentation scaffold
- Persistent project context, decisions, and architecture notes
- Repository-level version tracking via `VERSION`
