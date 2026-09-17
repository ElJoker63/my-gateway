<p align="center">
  <img src="docs/assets/banner.png" alt="My Gateway AI Banner" width="100%">
</p>

# 🧠 MY GATEWAY AI

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
- **Multi-Provider** — 28 providers: NVIDIA, OpenAI, Groq, Ollama, OpenRouter, Google, Cloudflare, DeepSeek, Nous Research, Kilocode, OpenCode Zen & Go, and more (any OpenAI-compatible endpoint)
- **Web Dashboard** — Vue 3 SPA served from the gateway itself at `/dashboard` (no build step, no extra deploy): health, provider pools, key status, combos, and live metrics
- **Combos & Racing** *(ported from openproxy)* — Alias stable names to provider chains with `strict` / `round_robin` / `least_used` / `race` strategies; first valid response wins, losers cancelled
- **Circuit Breaker** — Per-provider (+model) breaker with configurable threshold and cooldown, skipping unhealthy targets automatically
- **Built-in Metrics** — `/api/metrics` with request/error counters, tokens, latency percentiles, and race stats
- **Hardened Security** — Dedicated gateway API key, CORS allowlist, request size limits, path-restricted project indexing
- **Dockerized** — One command to run everything

## 🔒 Security

- Set `GATEWAY_API_KEY` before exposing the service — with no key configured, auth is **disabled** and the gateway logs a loud warning at startup (local-only development mode).
- Provider API keys (`NVIDIA_API_KEY`, `OPENAI_API_KEY`, ...) are **never** accepted as gateway credentials.
- Project indexing is disabled until you configure `ALLOWED_INDEX_ROOTS` with the directories the gateway may scan.
- CORS allowlist via `CORS_ALLOWED_ORIGINS`; request bodies limited by `MAX_REQUEST_SIZE_MB`.

## 🏗️ Architecture

```
     AI Agent Client
(Cursor / OpenHands / zcode)
          │
          │  Bearer Token
          ▼
   ┌──────────────┐
   │  AI Gateway   │  FastAPI :8000
   │    API        │
   └──────┬───────┘
          │
    ┌─────┼─────────┐
    │     │         │
    ▼     ▼         ▼
  Redis  Qdrant   Worker
  Cache  Memory   Tasks
    │     │         │
    └─────┼─────────┘
          │
          ▼
   External LLM Provider
   (NVIDIA / OpenAI)
```

## 🚀 Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/your-user/my-gateway.git
cd my-gateway
cp .env.example .env
```

### 2. Set your API key

Edit `.env` and add your NVIDIA API key:

```env
NVIDIA_API_KEY=nvapi-your-key-here
```

### 3. Launch

```bash
docker compose up --build
```

### 4. Test

```bash
# Health check
curl http://localhost:8000/health

# Simple chat
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer change-me-to-a-secure-key" \
  -d '{"project": "test", "message": "Hello!"}'

# OpenAI-compatible (for agents)
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer change-me-to-a-secure-key" \
  -d '{
    "model": "meta/llama-3.1-70b-instruct",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## 🔌 Connecting Your Agent

Point your AI agent to `http://localhost:8000` as the API base URL.

### Cursor / OpenHands
Set API base URL: `http://localhost:8000/v1`

### zcode
Supports all three formats:
- `/v1/chat/completions`
- `/v1/messages`
- `/response`

### Custom Agent
Use the simplified gateway format:
```bash
POST http://localhost:8000/api/chat
{
  "project": "my-project",
  "message": "your prompt here"
}
```

## 📁 Project Structure

```
my-gateway/
├── app/
│   ├── main.py           # FastAPI app, lifespan, middleware
│   ├── config.py          # Pydantic settings
│   ├── api/               # API route handlers
│   │   ├── chat.py        # Chat endpoints (3 formats)
│   │   ├── memory.py      # Memory CRUD
│   │   └── projects.py    # Project indexing
│   ├── providers/         # LLM provider abstraction
│   │   ├── base.py        # Abstract interface
│   │   ├── nvidia.py      # NVIDIA API
│   │   └── openai.py      # OpenAI-compatible
│   ├── services/          # Business logic
│   │   ├── cache.py       # Redis cache
│   │   ├── rate_limit.py  # Sliding window limiter
│   │   ├── memory.py      # Qdrant vector memory
│   │   ├── embedding.py   # Embedding generation
│   │   └── context.py     # Context builder
│   ├── workers/           # Background tasks
│   │   └── tasks.py       # Project indexer
│   ├── database/          # Connection management
│   │   ├── redis.py       # Async Redis pool
│   │   └── qdrant.py      # Qdrant client
│   └── models/            # Pydantic schemas
│       ├── requests.py    # Request models
│       └── responses.py   # Response models
├── tests/                 # Test suite
├── docs/                  # Documentation
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

## 📖 Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [API Reference](docs/API.md)
- [Configuration](docs/CONFIGURATION.md)
- [Memory System](docs/MEMORY_SYSTEM.md)

## 🧪 Testing

```bash
# Run tests inside container
docker compose exec gateway pytest tests/ -v

# Run locally (requires Redis + Qdrant running)
pip install -r requirements.txt pytest pytest-asyncio
pytest tests/ -v
```

## 📄 License

MIT
