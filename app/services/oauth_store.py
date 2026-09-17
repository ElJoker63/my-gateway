"""
OAuth token store — Redis-backed persistence for OAuth sessions.

Tokens are stored under `gw:oauth:{provider}` with shape:
    {
        "access_token": str,
        "refresh_token": str | None,
        "expires_at": float (unix ts),
        "scopes": [str],
        "meta": dict (provider-specific extras like profile_arn / project_id),
    }

The in-memory cache covers the hot path; Redis is the durable copy so
tokens survive restarts and are shared across workers.
"""

import json
import logging
import time

from app.database.redis import get_redis

logger = logging.getLogger(__name__)

OAUTH_PREFIX = "gw:oauth:"


class OAuthStore:
    """Redis-backed OAuth token persistence with in-memory hot cache."""

    def __init__(self):
        self._local: dict[str, dict] = {}

    async def save(self, provider: str, token_data: dict) -> None:
        self._local[provider] = token_data
        try:
            redis = await get_redis()
            await redis.set(f"{OAUTH_PREFIX}{provider}", json.dumps(token_data))
        except Exception as e:
            logger.warning(f"OAuth token for '{provider}' kept in memory only: {e}")

    async def get(self, provider: str) -> dict | None:
        if provider in self._local:
            return self._local[provider]
        try:
            redis = await get_redis()
            raw = await redis.get(f"{OAUTH_PREFIX}{provider}")
            if raw:
                data = json.loads(raw if isinstance(raw, str) else raw.decode())
                self._local[provider] = data
                return data
        except Exception as e:
            logger.debug(f"OAuth store read failed for '{provider}': {e}")
        return None

    async def delete(self, provider: str) -> bool:
        self._local.pop(provider, None)
        try:
            redis = await get_redis()
            return bool(await redis.delete(f"{OAUTH_PREFIX}{provider}"))
        except Exception:
            return False

    async def is_expired(self, provider: str, skew_seconds: int = 60) -> bool:
        """True when the stored token is expired or close to expiry."""
        data = await self.get(provider)
        if not data or "expires_at" not in data:
            return True
        return time.time() >= (data["expires_at"] - skew_seconds)

    async def list_connected(self) -> dict[str, dict]:
        """Summary: which providers currently hold a valid token."""
        # Anything in the local cache + anything in Redis
        out: dict[str, dict] = {}
        for provider, data in self._local.items():
            out[provider] = {
                "connected": not await self.is_expired(provider),
                "expires_in": max(0, int(data.get("expires_at", 0) - time.time())),
            }
        try:
            redis = await get_redis()
            keys = await redis.keys(f"{OAUTH_PREFIX}*")
            for raw_key in keys:
                key = raw_key.decode() if isinstance(raw_key, bytes) else raw_key
                provider = key[len(OAUTH_PREFIX):]
                if provider not in out:
                    data = await self.get(provider)
                    if data:
                        out[provider] = {
                            "connected": not await self.is_expired(provider),
                            "expires_in": max(0, int(data.get("expires_at", 0) - time.time())),
                        }
        except Exception as e:
            logger.debug(f"list_connected via Redis failed: {e}")
        return out


oauth_store = OAuthStore()
