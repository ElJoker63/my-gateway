# Configuration

All configuration is done via environment variables. Copy `.env.example` to `.env` and customize.

## Environment Variables

### Gateway

| Variable | Default | Description |
|----------|---------|-------------|
| `GATEWAY_API_KEY` | `change-me-to-a-secure-key` | API key for authenticating requests. Set to a secure value. If left as default, auth is effectively disabled. |
| `LOG_LEVEL` | `INFO` | Logging level: DEBUG, INFO, WARNING, ERROR |
| `GATEWAY_HOST` | `0.0.0.0` | Host to bind |
| `GATEWAY_PORT` | `8000` | Port to bind |

### NVIDIA Provider

| Variable | Default | Description |
|----------|---------|-------------|
| `NVIDIA_API_KEY` | *(empty)* | Single NVIDIA API key (backward compatible) |
| `NVIDIA_API_KEYS` | `[]` | JSON array of API keys, e.g. `["key1", "key2"]` (overrides single key if present) |
| `NVIDIA_MODEL` | `meta/llama-3.1-70b-instruct` | Default model |
| `NVIDIA_BASE_URL` | `https://integrate.api.nvidia.com/v1` | API base URL |

### OpenAI Provider

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | *(empty)* | Single OpenAI API key |
| `OPENAI_API_KEYS` | `[]` | JSON array of API keys, e.g. `["sk-key1", "sk-key2"]` |
| `OPENAI_MODEL` | `gpt-4o` | Default model |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | API base URL (change for compatible APIs) |

### Groq Provider

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | *(empty)* | Single Groq API key |
| `GROQ_API_KEYS` | `[]` | JSON array of API keys, e.g. `["gsk_key1", "gsk_key2"]` |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Default model |
| `GROQ_BASE_URL` | `https://api.groq.com/openai/v1` | Groq API base URL |
| `GROQ_RPM_LIMIT` | `0` | Per-key RPM limit for Groq (0 = inherits `MAX_REQUESTS_PER_MINUTE`) |

### Ollama Cloud / Remote Provider

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_API_KEY` | *(empty)* | Single Ollama Cloud API key |
| `OLLAMA_API_KEYS` | `[]` | JSON array of API keys for key pool rotation |
| `OLLAMA_BASE_URL` | `https://ollama.com/v1` | Ollama Cloud / Remote API base URL |
| `OLLAMA_MODEL` | `llama3.1` | Default cloud model (e.g. `llama3.1`, `qwen2.5-coder`, `mistral`, `deepseek-r1`) |
| `OLLAMA_RPM_LIMIT` | `0` | Per-key RPM limit for Ollama Cloud (0 = inherits `MAX_REQUESTS_PER_MINUTE`) |

### Key Management & Rate Limits

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_REQUESTS_PER_MINUTE` | `35` | Global default RPM limit per key |
| `NVIDIA_RPM_LIMIT` | `0` | Per-key RPM limit for NVIDIA (0 = inherits `MAX_REQUESTS_PER_MINUTE`) |
| `OPENAI_RPM_LIMIT` | `0` | Per-key RPM limit for OpenAI (0 = inherits `MAX_REQUESTS_PER_MINUTE`) |
| `KEY_SELECTION_STRATEGY` | `least_used` | Key rotation strategy: `least_used` (load balancing) or `round_robin` |
| `KEY_ERROR_COOLDOWN` | `60` | Cooldown period in seconds for a key after a rate limit (429) or auth error |

### Provider Selection

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_PROVIDER` | `nvidia` | Default provider when not specified in request |

### Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_REQUESTS_PER_MINUTE` | `35` | Max RPM to the LLM provider. Set below your provider's limit. |
| `RATE_LIMIT_WAIT_TIMEOUT` | `60` | Max seconds to wait when rate limited before returning 429 |

### Redis

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `redis` | Redis hostname (use `redis` in Docker, `localhost` for local) |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_PASSWORD` | *(empty)* | Redis password (optional) |
| `CACHE_TTL` | `86400` | Cache time-to-live in seconds (default: 24 hours) |

### Qdrant

| Variable | Default | Description |
|----------|---------|-------------|
| `QDRANT_HOST` | `qdrant` | Qdrant hostname (use `qdrant` in Docker, `localhost` for local) |
| `QDRANT_PORT` | `6333` | Qdrant HTTP port |
| `QDRANT_API_KEY` | *(empty)* | Qdrant API key (optional) |

### Embedding

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_MODEL` | `local` | `local` for sentence-transformers (free), `nvidia` for NVIDIA API |
| `LOCAL_EMBEDDING_MODEL_NAME` | `all-MiniLM-L6-v2` | HuggingFace model for local embeddings |
| `EMBEDDING_DIMENSION` | `384` | Vector dimension (must match embedding model) |

### Context

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_CONTEXT_TOKENS` | `4000` | Max tokens for injected memory context |
| `MEMORY_SEARCH_TOP_K` | `10` | Number of memories to retrieve per search |
| `MEMORY_SCORE_THRESHOLD` | `0.5` | Minimum cosine similarity score for memory results |

### Request Limits

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_REQUEST_SIZE_MB` | `10` | Maximum request body size |

## Tuning Guide

### For NVIDIA Free Tier (40 RPM)
```env
MAX_REQUESTS_PER_MINUTE=35
RATE_LIMIT_WAIT_TIMEOUT=60
CACHE_TTL=86400
```

### For OpenAI (varies by plan)
```env
DEFAULT_PROVIDER=openai
MAX_REQUESTS_PER_MINUTE=50
CACHE_TTL=3600
```

### For Maximum Memory Context
```env
MAX_CONTEXT_TOKENS=8000
MEMORY_SEARCH_TOP_K=20
MEMORY_SCORE_THRESHOLD=0.3
```
