"""
My Gateway AI — Main Application.

FastAPI application factory with lifespan management, middleware,
authentication, and health checks.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.api import api_router
from app.config import get_settings
from app.database.qdrant import close_qdrant, init_qdrant, qdrant_health_check
from app.database.redis import close_redis, init_redis, redis_health_check
from app.models.responses import HealthResponse, ServiceHealth
from app.providers import close_providers, init_providers
from app.version import APP_NAME
from app.version import VERSION as APP_VERSION

# Configure logging
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("gateway")


# =============================================================================
# Lifespan — Startup / Shutdown
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler. Initializes and cleans up resources."""
    # --- Startup ---
    logger.info("=" * 60)
    logger.info("My Gateway AI starting up...")
    logger.info("=" * 60)

    if not settings.auth_enabled:
        logger.warning("!" * 60)
        logger.warning("AUTHENTICATION IS DISABLED (GATEWAY_API_KEY not set).")
        logger.warning("The gateway will accept ALL requests without a key.")
        logger.warning("Set GATEWAY_API_KEY in your environment before exposing this service.")
        logger.warning("!" * 60)

    # Initialize Redis
    try:
        await init_redis()
        logger.info("✓ Redis connected")
    except Exception as e:
        logger.error(f"✗ Redis connection failed: {e}")

    # Initialize Qdrant
    try:
        await init_qdrant()
        logger.info("✓ Qdrant connected")
    except Exception as e:
        logger.error(f"✗ Qdrant connection failed: {e}")

    # Initialize LLM providers
    try:
        init_providers()
        logger.info("✓ LLM providers initialized")
    except Exception as e:
        logger.error(f"✗ Provider initialization failed: {e}")

    # Restore any keys added via POST /api/providers/{}/keys before shutdown
    try:
        from app.providers import load_persisted_keys_from_redis
        await load_persisted_keys_from_redis()
    except Exception as e:
        logger.warning(f"Could not reload runtime keys: {e}")

    # Configure the circuit breaker from settings
    from app.services.circuit_breaker import configure_circuit_breaker
    configure_circuit_breaker(
        threshold=getattr(settings, "circuit_failure_threshold", None),
        duration=getattr(settings, "circuit_unhealthy_seconds", None),
    )

    # Preload local embedding model in a worker thread (first chat would block otherwise)
    from app.services.embedding import preload_embedding_model
    await preload_embedding_model()

    # Periodic metrics snapshot: keeps the Redis mirror fresh for multi-worker reads
    async def _metrics_snapshot_loop():
        from app.services.metrics import persist_snapshot
        while True:
            await asyncio.sleep(60)
            try:
                await persist_snapshot()
            except Exception as e:
                logger.debug(f"metrics snapshot failed: {e}")

    metrics_task = asyncio.create_task(_metrics_snapshot_loop())

    logger.info("=" * 60)
    logger.info("My Gateway AI ready on port 8000")
    logger.info("=" * 60)

    yield  # Application runs

    metrics_task.cancel()

    # --- Shutdown ---
    logger.info("My Gateway AI shutting down...")
    await close_providers()
    await close_redis()
    await close_qdrant()
    logger.info("My Gateway AI shutdown complete")


# =============================================================================
# Application Factory
# =============================================================================


app = FastAPI(
    title=APP_NAME,
    description=(
        "Intelligent multi-provider gateway & orchestration platform for AI coding agents and LLM providers. "
        "Provides caching, rate limiting, vector memory, key rotation, and context enrichment."
    ),
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# =============================================================================
# Middleware
# =============================================================================


# CORS — origins are explicitly configurable; "*" is not allowed with credentials
cors_origins = [
    o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request size limit middleware (defense against oversized payloads)
@app.middleware("http")
async def body_size_limit_middleware(request: Request, call_next):
    """Reject requests whose body exceeds the configured size limit."""
    settings = get_settings()
    max_bytes = settings.max_request_size_mb * 1024 * 1024
    content_length = request.headers.get("content-length")

    if content_length is not None:
        try:
            if int(content_length) > max_bytes:
                return JSONResponse(
                    status_code=413,
                    content={"error": f"Request body exceeds the {settings.max_request_size_mb} MB limit"},
                )
        except ValueError:
            return JSONResponse(status_code=400, content={"error": "Invalid Content-Length header"})

    return await call_next(request)


# Request timing middleware
@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    """Add response timing header."""
    start = time.monotonic()
    response = await call_next(request)
    elapsed = time.monotonic() - start
    response.headers["X-Response-Time"] = f"{elapsed:.3f}s"
    return response


# API Key authentication middleware
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """
    Validate API key for protected routes.
    Skips auth for /health, /docs, /redoc, /openapi.json.
    """
    settings = get_settings()

    # Skip auth for public routes; /dashboard serves static assets that prompt
    # for the API key client-side, so it stays public purely for UX.
    public_paths = {"/health", "/docs", "/redoc", "/openapi.json", "/"}
    path = request.url.path
    if path in public_paths or path.startswith("/dashboard"):
        return await call_next(request)

    # Skip entirely when auth is disabled for local development
    if not settings.auth_enabled:
        return await call_next(request)

    # Check API key header or Bearer token
    auth_header = request.headers.get("Authorization", "")
    api_key = request.headers.get("X-API-Key", "")

    if auth_header.startswith("Bearer "):
        provided_key = auth_header[7:].strip()
    elif api_key:
        provided_key = api_key.strip()
    else:
        provided_key = ""

    # Only the gateway key authenticates — provider keys are NOT valid credentials.
    if not provided_key or provided_key != settings.gateway_api_key:
        return JSONResponse(
            status_code=401,
            content={"error": "Invalid or missing API key"},
        )

    return await call_next(request)


# =============================================================================
# Landing redirect
# =============================================================================


@app.get("/", include_in_schema=False)
async def root_redirect():
    """Redirect the bare root URL to the dashboard (friendlier first boot)."""
    return RedirectResponse(url="/dashboard/", status_code=302)


# =============================================================================
# Health Check
# =============================================================================


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """
    Gateway health check.
    Returns status of all connected services.
    """
    redis_status = await redis_health_check()
    qdrant_status = await qdrant_health_check()

    services = {
        "redis": ServiceHealth(**redis_status),
        "qdrant": ServiceHealth(**qdrant_status),
    }

    overall = "healthy"
    for svc in services.values():
        if svc.status != "healthy":
            overall = "degraded"
            break

    return HealthResponse(
        status=overall,
        version=APP_VERSION,
        services=services,
    )


# =============================================================================
# Key Pool Status
# =============================================================================


@app.get("/api/keys/status", tags=["System"])
async def key_pool_status(provider: str | None = None):
    """
    Get API key pool status for a provider or all providers.
    Shows per-key usage, rate limits, and availability.
    """
    from app.services.key_manager import key_manager

    if provider:
        return await key_manager.get_pool_status(provider)
    return await key_manager.get_all_pools_status()


class _AddKeyBody(BaseModel):
    key: str = Field(..., min_length=4, max_length=4096)


@app.post("/api/providers/{name}/keys", tags=["System"], status_code=201)
async def add_provider_key(name: str, body: _AddKeyBody):
    """Register a new API key in a provider's pool at runtime (persisted to Redis)."""
    from app.services.key_manager import key_manager

    try:
        return key_manager.add_key(name, body.key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# =============================================================================
# Rate Limit Status (legacy alias of /api/keys/status)
# =============================================================================


@app.get("/api/rate-limit", tags=["System"], deprecated=True, include_in_schema=False)
async def rate_limit_status(provider: str | None = None):
    """Deprecated: use /api/keys/status instead."""
    from app.services.key_manager import key_manager

    provider_name = provider or settings.default_provider
    return await key_manager.get_pool_status(provider_name)


# =============================================================================
# Metrics
# =============================================================================


@app.get("/api/metrics", tags=["System"])
async def get_metrics():
    """
    Gateway telemetry summary: request/error counters, per-provider stats,
    latency percentiles over a rolling window, and race outcomes.
    """
    from app.services.circuit_breaker import circuit_breaker
    from app.services.metrics import summarize_persisted

    snapshot = await summarize_persisted()
    snapshot["circuit_states"] = {
        key: {"state": s.state, "failures": s.consecutive_failures}
        for key, s in (await circuit_breaker.get_all_states()).items()
    }
    return snapshot


# =============================================================================
# Cache Stats
# =============================================================================


@app.get("/api/cache/stats", tags=["System"])
async def cache_stats():
    """Get cache hit/miss statistics."""
    from app.services.cache import get_cache_stats

    stats = await get_cache_stats()
    return stats


# =============================================================================
# Mount API Router
# =============================================================================

app.include_router(api_router)


# =============================================================================
# Static Dashboard (Vue 3 SPA bundled as plain ES modules — no build step)
# =============================================================================

_dashboard_dir = Path(__file__).resolve().parent / "dashboard" / "dist"
if _dashboard_dir.is_dir():
    app.mount(
        "/dashboard",
        StaticFiles(directory=_dashboard_dir, html=True),
        name="dashboard",
    )
