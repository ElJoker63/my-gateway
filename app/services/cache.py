"""
Async Redis cache service.
Provides caching of LLM responses keyed by the full request shape (messages,
model, project, and generation parameters) so two requests that differ only
in temperature/top_p/etc. never collide.
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
PROJECT_INDEX_PREFIX = "gw:cache:project:"


def _build_cache_key(
    messages: list[dict],
    model: str,
    project: str = "default",
    params: Optional[dict] = None,
) -> str:
    """
    Build a deterministic cache key from messages, model, project, and the
    generation parameters that affect the response content.
    """
    effective_params = {
        k: v for k, v in (params or {}).items()
        if v is not None and k in {
            "temperature", "top_p", "max_tokens", "stop",
            "frequency_penalty", "presence_penalty", "n",
            "tools", "tool_choice", "response_format",
        }
    }
    normalized = json.dumps(
        {
            "messages": messages,
            "model": model,
            "project": project,
            "params": effective_params,
        },
        sort_keys=True,
        ensure_ascii=True,
        default=str,
    )
    hash_digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"{CACHE_PREFIX}{hash_digest}"


async def get_cached_response(
    messages: list[dict],
    model: str,
    project: str = "default",
    params: Optional[dict] = None,
) -> Optional[dict]:
    """
    Look up a cached LLM response.

    Returns:
        Cached response dict if found, None if cache miss.
    """
    try:
        redis = await get_redis()
        key = _build_cache_key(messages, model, project, params)
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
    params: Optional[dict] = None,
):
    """
    Store an LLM response in cache.

    Args:
        messages: The conversation messages
        model: Model identifier
        response: The LLM response dict to cache
        project: Project name
        ttl: Time-to-live in seconds (default from settings)
        params: Generation parameters that affect the response
    """
    try:
        settings = get_settings()
        redis = await get_redis()
        key = _build_cache_key(messages, model, project, params)
        expire = ttl or settings.cache_ttl

        await redis.set(
            key,
            json.dumps(response, ensure_ascii=False),
            ex=expire,
        )
        # Maintain the project index so per-project invalidation works
        index_key = f"{PROJECT_INDEX_PREFIX}{project}"
        await redis.sadd(index_key, key)
        await redis.expire(index_key, expire)

        logger.debug(f"Cache SET: {key[:20]}... (ttl={expire}s)")

    except Exception as e:
        logger.error(f"Cache write error: {e}")


async def invalidate_project_cache(project: str) -> int:
    """
    Invalidate all cached responses for a specific project.
    Uses the project key index maintained by set_cached_response.

    Returns:
        Number of cache entries removed.
    """
    try:
        redis = await get_redis()
        index_key = f"{PROJECT_INDEX_PREFIX}{project}"
        keys = await redis.smembers(index_key)

        removed = 0
        if keys:
            removed = await redis.delete(*keys)
        await redis.delete(index_key)
        logger.info(f"Invalidated {removed} cached entries for project '{project}'")
        return removed

    except Exception as e:
        logger.error(f"Cache invalidation error: {e}")
        return 0


async def get_cache_stats() -> dict:
    """Get cache hit/miss statistics."""
    try:
        redis = await get_redis()
        stats = await redis.hgetall(CACHE_STATS_KEY)
        # redis-py returns bytes keys/values on raw hashes
        decoded = {
            (k.decode() if isinstance(k, bytes) else k):
                (v.decode() if isinstance(v, bytes) else v)
            for k, v in stats.items()
        }
        return {
            "hits": int(decoded.get("hits", 0)),
            "misses": int(decoded.get("misses", 0)),
        }
    except Exception as e:
        logger.error(f"Cache stats error: {e}")
        return {"hits": 0, "misses": 0}
