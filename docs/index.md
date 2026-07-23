# 🧠 AI Agent Gateway Documentation

Welcome to the official documentation for **AI Agent Gateway**.

An intelligent local gateway between AI coding agents and LLM providers. Reduces API consumption, enforces rate limits, provides persistent vector memory, and enriches requests with project context.

## ✨ Features

- **Multi-Agent Compatible** — Works with Cursor, OpenHands, zcode, and any OpenAI-compatible agent
- **Multi-API Key Pool & Rotation** — Support multiple API keys per provider with automatic load balancing, per-key rate limiting, and failure fallback
- **Three API Formats** — `/v1/chat/completions`, `/v1/messages`, `/api/chat`
- **SSE Streaming** — Real-time streaming support for all chat endpoints
- **Intelligent Cache** — SHA-256 semantic hashing with Redis, avoids repeated API calls
- **Rate Limiting** — Sliding window per-key limiter with auto-queue (never hit provider limits)
- **Vector Memory** — Per-project persistent memory using Qdrant
- **Context Enrichment** — Automatically injects relevant project context into LLM requests
- **Project Indexing** — Scan and index entire codebases for memory
- **Multi-Provider** — NVIDIA API, OpenAI-compatible, Groq, Ollama Cloud (and remote instances), easily extensible
- **Dockerized** — One command to run everything

---

## 🚀 Quick Navigation

- [System Architecture](ARCHITECTURE.md) — Detailed diagram and component flow
- [API Reference](API.md) — Complete endpoint documentation and request examples
- [Configuration](CONFIGURATION.md) — Environment variables, provider keys, and rate limits
- [Memory System](MEMORY_SYSTEM.md) — Qdrant vector search and project indexer details
