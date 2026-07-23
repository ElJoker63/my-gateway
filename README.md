# 🧠 AI Agent Gateway

An intelligent local gateway between AI coding agents and LLM providers. Reduces API consumption, enforces rate limits, provides persistent vector memory, and enriches requests with project context.

## ✨ Features

- **Multi-Agent Compatible** — Works with Cursor, OpenHands, zcode, and any OpenAI-compatible agent
- **Three API Formats** — `/v1/chat/completions`, `/v1/messages`, `/api/chat`
- **SSE Streaming** — Real-time streaming support for all chat endpoints
- **Intelligent Cache** — SHA-256 semantic hashing with Redis, avoids repeated API calls
- **Rate Limiting** — Sliding window limiter with auto-queue (never hit provider limits)
- **Vector Memory** — Per-project persistent memory using Qdrant
- **Context Enrichment** — Automatically injects relevant project context into LLM requests
- **Project Indexing** — Scan and index entire codebases for memory
- **Multi-Provider** — NVIDIA API + OpenAI-compatible, easily extensible
- **Dockerized** — One command to run everything

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
