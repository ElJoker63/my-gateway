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
