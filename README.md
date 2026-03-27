## Description

A small local-first voice-to-action server that uses Moonshine AI for live English speech-to-text, streams transcripts to a web UI, and exposes them through MCP so AI agents can read voice commands and trigger actions.

## Features

- Live English speech-to-text with Moonshine AI
- Real-time transcript display in a web interface
- MCP integration for AI agents
- Docker-based local deployment
- Local-first workflow for low-latency voice interactions

## Quick start with Docker

### Build the image

```bash
docker build -t voice-to-action .
```

### Run the container

```bash
docker run --rm -it \
  -p 8000:8000 \
  --name voice-to-action \
  voice-to-action
```

### Open the app

```text
http://localhost:8000
```

## Notes

- This project is intended for English-only Moonshine usage.
- It is designed for local deployment and simple integration with AI-agent workflows through MCP.
