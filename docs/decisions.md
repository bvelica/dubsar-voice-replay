# Decisions Log

This file records decisions that should persist across sessions.

## 2026-03-28

### Backend Language

- Decision: Use Python for the main application.
- Reason: It is the most practical fit for Moonshine integration, API development, MCP integration, and fast iteration.

### API Framework

- Decision: Use FastAPI instead of Flask.
- Reason: The application is real-time and event-oriented, and FastAPI is a better fit for WebSockets, async patterns, and typed APIs.

### Performance Strategy

- Decision: Introduce Go or Rust only if a specific subsystem proves to need lower-level optimization.
- Reason: Early multi-language complexity would slow iteration without clear evidence of need.

### Versioning Strategy

- Decision: Track the app version in a top-level `VERSION` file and maintain release notes in `CHANGELOG.md`.
- Reason: Git history alone is not a clean product-versioning mechanism; explicit version and changelog files make milestones and releases easier to manage.

### Versioning Scheme

- Decision: Use Semantic Versioning.
- Reason: It is simple, standard, and a good fit for an application that may become public and distributed.
