# syntax=docker/dockerfile:1

# ---------- Dashboard builder ----------
FROM node:22-alpine AS dashboard-builder

WORKDIR /build
COPY dashboard/package.json dashboard/package-lock.json* ./
RUN npm ci || npm install

COPY dashboard/ ./
RUN npm run build

# ---------- Python builder ----------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

# ---------- Runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:${PATH}"

# Non-root user for the gateway process
RUN groupadd -r gateway && useradd -r -g gateway -d /app -s /usr/sbin/nologin gateway

WORKDIR /app

# Bring in installed packages from builder
COPY --from=builder /install /usr/local

# Pre-download the local embedding model at build time (as root into the shared cache)
ENV SENTENCE_TRANSFORMERS_HOME=/app/models
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# App code only — .dockerignore keeps .env, tests, docs, and vcs out
COPY --chown=gateway:gateway . .

# Prebuilt dashboard from the node stage
COPY --from=dashboard-builder --chown=gateway:gateway /build/dist /app/app/dashboard/dist

# Data volume for anything the app persists (Qdrant/Redis live in their own containers)
RUN mkdir -p /data && chown gateway:gateway /data /app/models

USER gateway

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=5)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-level", "info"]
