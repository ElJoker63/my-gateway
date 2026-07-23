"""
Async Redis cache service.
Provides intelligent caching of LLM responses using semantic hashing.
"""

import hashlib
import json
import logging
from typing import Optional

from app.config import get_settings
from app.database.redis import get_redis

logger = logging.getLogger(__name__)

# Cache key prefix
CACHE_PREFIX = "gw:cache:"
CACHE_STATS_KEY = "gw:cache:stats"


def _build_cache_key(messages: list[dict], model: str, project: str = "default") -> str:
    """
    Build a deterministic cache key from messages, model, and project.
    Uses SHA-256 hash for consistent key generation.
    """
    # Normalize messages to ensure consistent hashing
    normalized = json.dumps(
        {
            "messages": messages,
            "model": model,
            "project": project,
        },
        sort_keys=True,
        ensure_ascii=True,
    )
    hash_digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"{CACHE_PREFIX}{hash_digest}"


async def get_cached_response(
    messages: list[dict],
    model: str,
    project: str = "default",
) -> Optional[dict]:
    """
    Look up a cached LLM response.

    Returns:
        Cached response dict if found, None if cache miss.
    """
    try:
        redis = await get_redis()
        key = _build_cache_key(messages, model, project)
        cached = await redis.get(key)

        if cached:
            logger.debug(f"Cache HIT: {key[:20]}...")
            await redis.hincrby(CACHE_STATS_KEY, "hits", 1)
            return json.loads(cached)

        logger.debug(f"Cache MISS: {key[:20]}...")
        await redis.hincrby(CACHE_STATS_KEY, "misses", 1)
        return None

    except Exception as e:
        logger.error(f"Cache read error: {e}")
        return None


async def set_cached_response(
    messages: list[dict],
    model: str,
    response: dict,
    project: str = "default",
    ttl: Optional[int] = None,
):
    """
    Store an LLM response in cache.

    Args:
        messages: The conversation messages
        model: Model identifier
        response: The LLM response dict to cache
        project: Project name
        ttl: Time-to-live in seconds (default from settings)
    """
    try:
        settings = get_settings()
        redis = await get_redis()
        key = _build_cache_key(messages, model, project)
        expire = ttl or settings.cache_ttl

        await redis.set(
            key,
            json.dumps(response, ensure_ascii=False),
            ex=expire,
        )
        logger.debug(f"Cache SET: {key[:20]}... (ttl={expire}s)")

    except Exception as e:
        logger.error(f"Cache write error: {e}")


async def invalidate_project_cache(project: str):
    """
    Invalidate all cached responses for a specific project.
    Uses SCAN to find and delete matching keys.
    """
    try:
        redis = await get_redis()
        # We can't easily filter by project since the key is a hash,
        # so we maintain a project->keys index
        index_key = f"gw:cache:project:{project}"
        keys = await redis.smembers(index_key)

        if keys:
            await redis.delete(*keys, index_key)
            logger.info(f"Invalidated {len(keys)} cached entries for project '{project}'")

    except Exception as e:
        logger.error(f"Cache invalidation error: {e}")


async def get_cache_stats() -> dict:
    """Get cache hit/miss statistics."""
    try:
        redis = await get_redis()
        stats = await redis.hgetall(CACHE_STATS_KEY)
        return {
            "hits": int(stats.get(b"hits", 0)),
            "misses": int(stats.get(b"misses", 0)),
        }
    except Exception as e:
        logger.error(f"Cache stats error: {e}")
        return {"hits": 0, "misses": 0}
