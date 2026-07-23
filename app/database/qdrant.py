"""
Qdrant vector database client wrapper.
Manages collections and provides connection health checks.
"""

import logging
import time
from typing import Optional

from qdrant_client import QdrantClient
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

# Singleton client
_qdrant_client: Optional[QdrantClient] = None


def get_qdrant() -> QdrantClient:
    """Get the shared Qdrant client. Creates it on first call."""
    global _qdrant_client
    if _qdrant_client is None:
        init_qdrant()
    return _qdrant_client


def init_qdrant() -> QdrantClient:
    """Initialize the Qdrant client."""
    global _qdrant_client
    settings = get_settings()

    kwargs = {
        "host": settings.qdrant_host,
        "port": settings.qdrant_port,
        "timeout": 10,
    }

    if settings.qdrant_api_key:
        kwargs["api_key"] = settings.qdrant_api_key

    _qdrant_client = QdrantClient(**kwargs)
    logger.info(f"Qdrant client initialized: {settings.qdrant_host}:{settings.qdrant_port}")
    return _qdrant_client


def close_qdrant():
    """Close the Qdrant client."""
    global _qdrant_client
    if _qdrant_client is not None:
        _qdrant_client.close()
        _qdrant_client = None
        logger.info("Qdrant client closed")


def ensure_collection(collection_name: str, vector_size: int = None):
    """Create a Qdrant collection if it doesn't exist."""
    client = get_qdrant()
    settings = get_settings()
    size = vector_size or settings.embedding_dimension

    collections = [c.name for c in client.get_collections().collections]
    if collection_name not in collections:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=size,
                distance=Distance.COSINE,
            ),
        )
        logger.info(f"Created Qdrant collection: {collection_name} (dim={size})")
    else:
        logger.debug(f"Qdrant collection already exists: {collection_name}")


def qdrant_health_check() -> dict:
    """Check Qdrant connectivity and return health info."""
    try:
        client = get_qdrant()
        start = time.monotonic()
        client.get_collections()
        latency = (time.monotonic() - start) * 1000
        return {"status": "healthy", "latency_ms": round(latency, 2)}
    except Exception as e:
        logger.error(f"Qdrant health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}
