# Go Backend

The gateway is implemented in Go with the same observable behavior as the Python version.

## Layout

```
gateway/
  cmd/
    gateway/      — the server binary (`gateway`)
    desktop/      — Wails shell (`gateway-desktop`)
  internal/
    api/          — chi router, middlewares, handlers
    breaker/      — circuit breaker per provider/model
    cache/        — response cache with per-project index
    combos/       — combo registry (Redis-backed)
    config/       — env loading
    keymanager/   — key pools, atomic acquire, cooldowns
    memory/       — Qdrant client + NVIDIA embeddings
    metrics/      — latency percentiles + counters
    oauth/        — PKCE + device flow
    providers/    — OpenAI-compatible adapters + Kiro + Antigravity
    racing/       — combo execution strategies
    types/        — request/response shapes
```

## Build

```bash
cd gateway
go build ./...
# server
go build -o bin/gateway ./cmd/gateway
# desktop (requires node for the SPA bundle)
npm --prefix ../dashboard run build
go build -o bin/gateway-desktop ./cmd/desktop
```

## Run

```bash
REDIS_ADDR=localhost:6379 QDRANT_HOST=localhost QDRANT_PORT=6333 \
GATEWAY_API_KEY=... ./bin/gateway
```

Point your browser to `http://localhost:8000/` — it redirects to
`/dashboard/` where the Vue dashboard lives.
