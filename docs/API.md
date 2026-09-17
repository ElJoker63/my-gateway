# API Reference

Base URL: `http://localhost:8000`

## Authentication

All endpoints (except `/health`) require authentication:

```
Authorization: Bearer <GATEWAY_API_KEY>
```

or:

```
X-API-Key: <GATEWAY_API_KEY>
```

---

## Chat Endpoints

### POST /v1/chat/completions

OpenAI-compatible chat completion. Used by most AI agents.

**Request:**
```json
{
  "model": "meta/llama-3.1-70b-instruct",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Explain Python decorators"}
  ],
  "temperature": 0.7,
  "max_tokens": 2048,
  "stream": false,
  "project": "my-project",
  "use_memory": true,
  "use_cache": true
}
```

**Response:**
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1700000000,
  "model": "meta/llama-3.1-70b-instruct",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Python decorators are..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 25,
    "completion_tokens": 150,
    "total_tokens": 175
  },
  "cached": false,
  "provider": "nvidia"
}
```

**Streaming (SSE):**
Set `"stream": true`. Response is `text/event-stream`:
```
data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","choices":[{"delta":{"content":"Hello"},"index":0}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","choices":[{"delta":{"content":" world"},"index":0}]}

data: [DONE]
```

---

### POST /v1/messages

Anthropic Messages API compatible endpoint.

**Request:**
```json
{
  "model": "meta/llama-3.1-70b-instruct",
  "system": "You are a coding assistant.",
  "messages": [
    {"role": "user", "content": "What is FastAPI?"}
  ],
  "max_tokens": 4096,
  "project": "my-project"
}
```

**Response:**
```json
{
  "id": "msg-abc123",
  "type": "message",
  "role": "assistant",
  "content": [
    {"type": "text", "text": "FastAPI is..."}
  ],
  "model": "meta/llama-3.1-70b-instruct",
  "stop_reason": "end_turn",
  "usage": {
    "input_tokens": 15,
    "output_tokens": 100
  }
}
```

---

### POST /api/chat

Simplified gateway format.

**Request:**
```json
{
  "project": "udyat",
  "message": "Analyze the authentication system",
  "provider": "nvidia",
  "model": null,
  "use_memory": true,
  "use_cache": true
}
```

**Response:**
```json
{
  "response": "The authentication system uses...",
  "provider": "nvidia",
  "cached": false,
  "project": "udyat",
  "usage": {
    "prompt_tokens": 150,
    "completion_tokens": 200,
    "total_tokens": 350
  }
}
```

---

### POST /response

Alias for `/v1/chat/completions`. Same request/response format.

---

### GET /v1/models

List available models (required by some agents).

**Response:**
```json
{
  "object": "list",
  "data": [
    {
      "id": "meta/llama-3.1-70b-instruct",
      "object": "model",
      "owned_by": "nvidia"
    }
  ]
}
```

---

## Memory Endpoints

### POST /api/memory/store

Store a memory entry manually.

**Request:**
```json
{
  "text": "The users table has columns: id, email, password_hash, created_at",
  "project": "udyat",
  "file": "models/user.py",
  "type": "architecture",
  "metadata": {"table": "users"}
}
```

### POST /api/memory/search

Search memories semantically.

**Request:**
```json
{
  "query": "user authentication",
  "project": "udyat",
  "type": null,
  "top_k": 10
}
```

### GET /api/memory/project/{project}

List all memories for a project.

### DELETE /api/memory/project/{project}

Delete all memories for a project.

---

## Project Endpoints

### POST /api/projects/index

Index a project directory (background task).

**Request:**
```json
{
  "path": "/path/to/project",
  "project_name": "udyat",
  "file_patterns": ["*.py", "*.js", "*.md"]
}
```

### GET /api/projects

List all indexed projects.

### GET /api/projects/{name}

Get project details.

### DELETE /api/projects/{name}

Delete project and all its memories.

---

## System Endpoints

### GET /health

Health check for all services.

### GET /api/rate-limit?provider=nvidia

Current rate limit status.

### GET /api/cache/stats

Cache hit/miss statistics.

### GET /api/metrics

Gateway telemetry: request/error counters, per-provider stats, latency
percentiles (p50/p95/p99 within a rolling window), race outcomes, and
circuit-breaker states.

```json
{
  "uptime_seconds": 3600.2,
  "total_requests": 1520,
  "total_errors": 12,
  "error_rate": 0.0079,
  "total_races": 140,
  "race_wins": 132,
  "providers": { "nvidia": { "requests": 800, "errors": 4, "tokens": 1523400, "models": ["llama-3.3-70b-versatile"] } },
  "latency": { "nvidia:llama-3.3-70b-versatile": { "count": 512, "p50_ms": 420.1, "p95_ms": 980.5, "p99_ms": 1410.2 } },
  "circuit_states": { "groq": { "state": "open", "failures": 3 } }
}
```

---

## Combos

Combos alias a friendly name to an ordered list of provider/model targets.
Use `model: "combo:<name>"` in any chat endpoint to route through the combo.

Strategies:

- `strict` — try targets in order, fail over on error (default).
- `round_robin` — rotate the starting target across requests.
- `least_used` — start with the target with the lowest recent usage.
- `race` — launch up to `race_size` targets in parallel; first valid response wins, losers are cancelled.

### GET /api/combos

```json
{ "combos": [ { "name": "fast", "targets": [ { "provider": "nvidia", "model": "llama-3.3-70b", "weight": 1 } ], "strategy": "race", "race_size": 2 } ], "total": 1 }
```

### POST /api/combos

Create or replace a combo:

```json
{
  "name": "fast",
  "targets": [
    { "provider": "nvidia", "model": "llama-3.3-70b" },
    { "provider": "groq" }
  ],
  "strategy": "race",
  "race_size": 2
}
```

### GET /api/combos/{name}

Fetch one combo. Accepts the bare name or `combo:<name>`.

### DELETE /api/combos/{name}

Delete a combo.

---

## OAuth

OAuth-backed providers (Kiro, Antigravity) authenticate via browser/device flows instead of static API keys.

### POST /api/oauth/{provider}/start

Begin an OAuth handshake for `kiro` or `antigravity`. The response shape differs by flow:

**Device code (kiro)** — response:
```json
{
  "provider": "kiro",
  "flow": "device_code",
  "verificationUri": "https://device.sso.us-east-1.amazonaws.com/",
  "userCode": "ABCD-EFGH",
  "expiresIn": 600,
  "interval": 5,
  "state": "..."
}
```

**PKCE (antigravity)** — response:
```json
{
  "provider": "antigravity",
  "flow": "pkce",
  "authUrl": "https://accounts.google.com/o/oauth2/v2/auth?...&code_challenge_method=S256",
  "state": "..."
}
```

### GET /api/oauth/{provider}/poll?state=...

For device flows. Returns HTTP 202 (`authorization_pending`/`slow_down`) while the user hasn't consented, and HTTP 200 when the tokens are stored.

### GET /api/oauth/{provider}/callback?code=...&state=...

PKCE callback target (Google redirects here after consent).

### GET /api/oauth/status

Current OAuth session per provider:

```json
{ "kiro": { "connected": true, "expires_in": 3120 } }
```

### DELETE /api/oauth/{provider}

Disconnect a provider (drops its stored tokens).
