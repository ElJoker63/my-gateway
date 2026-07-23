# Architecture

## Overview

**My Gateway AI** is a **local proxy + intelligent middleware platform** that sits between AI coding agents and external LLM providers. It is not a simple HTTP relay — it actively enriches, caches, rate-limits, and contextualizes every request.

## System Architecture

```
┌─────────────────────────────────────────────────────┐
│                    AI Agents                        │
│  (Cursor, OpenHands, zcode, CLI, custom agents)     │
└────────────┬───────────┬───────────┬───────────────┘
             │           │           │
     /v1/chat/completions  /v1/messages  /api/chat
             │           │           │
             ▼           ▼           ▼
┌─────────────────────────────────────────────────────┐
│                  FastAPI Gateway                    │
│                                                     │
│  ┌──────────┐  ┌───────────────┐  ┌────────────────┐│
│  │ Auth     │  │ Key Manager   │  │ Request Router ││
│  │ Middleware│→│ Pool Rotation │→ │ (format detect)││
│  └──────────┘  └───────┬───────┘  └────────┬───────┘│
│                        │                   │        │
│      ┌─────────────────┴───────────────────┘        │
│      │                                              │
│      ▼                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ Cache    │  │ Context  │  │ Memory           │   │
│  │ Service  │  │ Builder  │  │ Service          │   │
│  │ (Redis)  │  │          │  │ (Qdrant)         │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────────────┘   │
│       │              │              │                │
│       │         ┌────┘              │                │
│       │         ▼                   │                │
│       │    ┌──────────┐            │                │
│       │    │ Provider │◄───────────┘                │
│       │    │ Layer    │                             │
│       │    └────┬─────┘                             │
│       │         │                                   │
└───────┼─────────┼───────────────────────────────────┘
        │         │
        ▼         ▼
   ┌────────┐ ┌───────────────────┐
   │ Redis  │ │ LLM Provider      │
   │        │ │ (NVIDIA / OpenAI) │
   └────────┘ └───────────────────┘
```

## Request Flow

1. **Agent sends request** → Gateway receives in any supported format
2. **Authentication** → Validates Bearer token or X-API-Key
3. **Format normalization** → Converts to internal message format
4. **Cache check** → SHA-256 hash of messages+model+project → Redis lookup
5. **Context enrichment** → Queries Qdrant for relevant project memories
6. **Key Acquisition** → KeyManager selects best key from provider pool (least_used/round_robin) & checks per-key sliding window rate limit
7. **LLM call with Fallback** → Forwards request to provider with acquired key; if 429 or auth error occurs, marks key error and retries seamlessly with next available key
8. **Cache store** → Saves response for future identical requests
9. **Memory update** → Stores conversation in Qdrant (background)
10. **Response formatting** → Returns in the format matching the request endpoint

## Component Details

### Key Manager
Provider-agnostic key pool manager. Handles per-key sliding window rate limiting in Redis, multi-key load balancing (`least_used` or `round_robin`), error cooldowns, and automatic key fallback. All API keys are masked in logs (e.g. `nv-****89ab`).

### Provider Abstraction
Abstract `LLMProvider` base class with `chat()` and `chat_stream()` methods. Accepts per-request API key injection from the KeyManager. Adding a new provider (Anthropic, Gemini, local models, etc.) requires only implementing the interface.

### Cache Service
Uses Redis with SHA-256 hash keys generated from `{messages, model, project}`. Cache keys are deterministic — identical requests always hit the same cache entry.

### Rate Limiter / Key Rate Limiter
Atomic sliding window implemented via Redis Lua script per key/provider pool. Tracks request timestamps in a sorted set, removes expired entries, and atomically checks/increments in a single Redis roundtrip.

### Memory Service
Each project gets its own Qdrant collection (`project_{name}`). Memories are stored as embeddings with metadata payloads (text, file, type, timestamp).

### Context Builder
Extracts the user's latest message, queries Qdrant for semantically similar memories, and injects the top results as a system message. Size-limited to prevent token overflow.

### Embedding Service
Lazy-loads a local `sentence-transformers` model (`all-MiniLM-L6-v2`, 384 dimensions) on first use. Zero API cost. Optional NVIDIA embedding API override.

## Data Persistence

| Service | Storage | Survives Restart |
|---------|---------|-----------------|
| Redis   | `./data/redis/` (AOF) | ✅ |
| Qdrant  | `./data/qdrant/` | ✅ |

## Security

- API key authentication (Bearer token or X-API-Key header)
- No secrets in code — all via environment variables
- Request size limits
- Rate limiting protects against abuse
- CORS enabled for local development
