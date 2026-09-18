# Backend Go — compila gateway server + desktop shell.
# Multi-stage: node builds the SPA, golang builds the binaries, runtime is a slim image.

# ---------- Dashboard builder ----------
FROM node:22-alpine AS dashboard-builder
WORKDIR /build
COPY dashboard/package.json dashboard/package-lock.json* ./
RUN npm ci || npm install
COPY dashboard/ ./
RUN npm run build

# ---------- Go build ----------
FROM golang:1.27-alpine AS go-builder
RUN apk add --no-cache git build-base
WORKDIR /src
COPY gateway/go.mod gateway/go.sum ./
RUN go mod download
COPY gateway/ ./
# Build the server binary (no CGO needed for server mode)
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o /out/gateway ./cmd/gateway
# Build the desktop shell (CGO needed by Wails; keep a best-effort build so the image layer still exists)
RUN CGO_ENABLED=1 GOOS=linux go build -o /out/desktop ./cmd/desktop || true

# ---------- Runtime ----------
FROM alpine:3.20
RUN apk add --no-cache ca-certificates tzdata
RUN addgroup -S gateway && adduser -S -G gateway -h /app gateway
WORKDIR /app

# SPA bundle
COPY --from=dashboard-builder --chown=gateway:gateway /build/dist /app/dashboard/dist

# Server binary
COPY --from=go-builder --chown=gateway:gateway /out/gateway /usr/local/bin/gateway

# Non-root runtime
USER gateway
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://localhost:8000/health || exit 1

CMD ["gateway"]
