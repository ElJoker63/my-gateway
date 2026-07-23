"""
My Gateway AI — Main Application.

FastAPI application factory with lifespan management, middleware,
authentication, and health checks.
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.api import api_router
from app.database.redis import init_redis, close_redis, redis_health_check
from app.database.qdrant import init_qdrant, close_qdrant, qdrant_health_check
from app.providers import init_providers, close_providers
from app.models.responses import HealthResponse, ServiceHealth

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

    # Initialize Redis
    try:
        await init_redis()
        logger.info("✓ Redis connected")
    except Exception as e:
        logger.error(f"✗ Redis connection failed: {e}")

    # Initialize Qdrant
    try:
        init_qdrant()
        logger.info("✓ Qdrant connected")
    except Exception as e:
        logger.error(f"✗ Qdrant connection failed: {e}")

    # Initialize LLM providers
    try:
        init_providers()
        logger.info("✓ LLM providers initialized")
    except Exception as e:
        logger.error(f"✗ Provider initialization failed: {e}")

    logger.info("=" * 60)
    logger.info("My Gateway AI ready on port 8000")
    logger.info("=" * 60)

    yield  # Application runs

    # --- Shutdown ---
    logger.info("My Gateway AI shutting down...")
    await close_providers()
    await close_redis()
    close_qdrant()
    logger.info("My Gateway AI shutdown complete")


# =============================================================================
# Application Factory
# =============================================================================


app = FastAPI(
    title="My Gateway AI",
    description=(
        "Intelligent multi-provider gateway & orchestration platform for AI coding agents and LLM providers. "
        "Provides caching, rate limiting, vector memory, key rotation, and context enrichment."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# =============================================================================
# Middleware
# =============================================================================


# CORS — allow all origins for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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

    # Skip auth for public routes
    public_paths = {"/health", "/docs", "/redoc", "/openapi.json"}
    if request.url.path in public_paths:
        return await call_next(request)

    # Check API key
    auth_header = request.headers.get("Authorization", "")
    api_key = request.headers.get("X-API-Key", "")

    # Support "Bearer <key>" format used by agents
    if auth_header.startswith("Bearer "):
        provided_key = auth_header[7:]
    elif api_key:
        provided_key = api_key
    else:
        provided_key = ""

    # Validate against gateway key (skip if default key)
    if settings.gateway_api_key != "change-me-to-a-secure-key":
        if provided_key != settings.gateway_api_key:
            # Also allow if the key is an LLM provider key (agent pass-through)
            if provided_key not in {settings.nvidia_api_key, settings.openai_api_key}:
                return JSONResponse(
                    status_code=401,
                    content={"error": "Invalid API key"},
                )

    return await call_next(request)


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
    qdrant_status = qdrant_health_check()

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
        version="1.0.0",
        services=services,
    )


# =============================================================================
# Key Pool Status
# =============================================================================


@app.get("/api/keys/status", tags=["System"])
async def key_pool_status(provider: Optional[str] = None):
    """
    Get API key pool status for a provider or all providers.
    Shows per-key usage, rate limits, and availability.
    """
    from app.services.key_manager import key_manager

    if provider:
        return await key_manager.get_pool_status(provider)
    return await key_manager.get_all_pools_status()


# =============================================================================
# Rate Limit Status (legacy — delegates to key manager)
# =============================================================================


@app.get("/api/rate-limit", tags=["System"])
async def rate_limit_status(provider: Optional[str] = None):
    """Get current rate limit status (per-key breakdown)."""
    from app.services.key_manager import key_manager

    provider_name = provider or settings.default_provider
    return await key_manager.get_pool_status(provider_name)


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