"""
Qdrant vector database client wrapper.
Uses AsyncQdrantClient so vector operations never block the event loop.
Manages collections and provides connection health checks.
"""

import logging
import time
from typing import Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

from app.config import get_settings

logger = logging.getLogger(__name__)

# Singleton async client
_qdrant_client: Optional[AsyncQdrantClient] = None

# Local cache of known collections — avoids a get_collections() round-trip on every write
_known_collections: set[str] = set()


def get_qdrant() -> AsyncQdrantClient:
    """Get the shared async Qdrant client. Creates it on first call."""
    global _qdrant_client
    if _qdrant_client is None:
        raise RuntimeError("Qdrant client not initialized — call init_qdrant() first")
    return _qdrant_client


async def init_qdrant() -> AsyncQdrantClient:
    """Initialize the async Qdrant client and verify connectivity."""
    global _qdrant_client, _known_collections
    settings = get_settings()

    kwargs = {
        "host": settings.qdrant_host,
        "port": settings.qdrant_port,
        "timeout": 10,
    }

    if settings.qdrant_api_key:
        kwargs["api_key"] = settings.qdrant_api_key

    client = AsyncQdrantClient(**kwargs)
    # Real connectivity check — fail loudly at startup instead of failing later on requests
    collections = await client.get_collections()
    _known_collections = {c.name for c in collections.collections}
    _qdrant_client = client
    logger.info(
        f"Qdrant client initialized: {settings.qdrant_host}:{settings.qdrant_port} "
        f"({len(_known_collections)} collections)"
    )
    return _qdrant_client


async def close_qdrant():
    """Close the Qdrant client."""
    global _qdrant_client, _known_collections
    if _qdrant_client is not None:
        await _qdrant_client.close()
        _qdrant_client = None
        _known_collections.clear()
        logger.info("Qdrant client closed")


async def ensure_collection(collection_name: str, vector_size: Optional[int] = None):
    """Create a Qdrant collection if it doesn't exist (cached locally)."""
    if collection_name in _known_collections:
        return

    client = get_qdrant()
    settings = get_settings()
    size = vector_size or settings.embedding_dimension

    try:
        await client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=size,
                distance=Distance.COSINE,
            ),
        )
        logger.info(f"Created Qdrant collection: {collection_name} (dim={size})")
        _known_collections.add(collection_name)
    except Exception as e:
        # Another worker/request may have created it concurrently — refresh and continue
        if "exists" in str(e).lower():
            _known_collections.add(collection_name)
            return
        raise


def forget_collection(collection_name: str):
    """Remove a collection from the local known-collections cache."""
    _known_collections.discard(collection_name)


async def qdrant_health_check() -> dict:
    """Check Qdrant connectivity and return health info."""
    try:
        client = get_qdrant()
        start = time.monotonic()
        await client.get_collections()
        latency = (time.monotonic() - start) * 1000
        return {"status": "healthy", "latency_ms": round(latency, 2)}
    except Exception as e:
        logger.error(f"Qdrant health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}
