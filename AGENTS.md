# Project Working Agreement

This repository is the source of truth for project context. Do not rely on chat history for persistent decisions.

## How To Work In This Repo

Before making meaningful changes:

1. Read `README.md`.
2. Read `docs/context.md`.
3. Read `docs/decisions.md`.
4. If architecture is relevant, read `docs/architecture.md`.
5. Read `VERSION` and `CHANGELOG.md` if the work affects release state.

After making meaningful product or technical decisions:

1. Update `docs/decisions.md`.
2. Update `docs/context.md` if the scope, goals, or priorities changed.
3. Update `docs/architecture.md` if the system shape changed.

Before creating a release or shipping a meaningful milestone:

1. Update `VERSION`.
2. Add an entry to `CHANGELOG.md`.
3. Create a matching git tag when appropriate.

## Current Defaults

- Backend language: Python
- Web API framework: FastAPI
- Local-first deployment
- Moonshine integration is expected to be the speech-to-text foundation

## Documentation Rule

Keep documents short, current, and decision-oriented. Prefer updating existing files over creating scattered notes.

## Versioning Rule

Use Semantic Versioning:

- `MAJOR` for breaking changes
- `MINOR` for backward-compatible features
- `PATCH` for backward-compatible fixes
