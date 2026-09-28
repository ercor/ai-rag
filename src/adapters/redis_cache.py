"""Redis cache adapter — implements Cache port using redis.asyncio.

Handles connection errors gracefully: get() returns None on failure,
set() is a silent no-op. This ensures the pipeline continues even when
Redis is unavailable.
"""

import json
import logging

logger = logging.getLogger(__name__)


class RedisCache:
    """Redis-backed cache implementing the Cache protocol.

    Uses redis.asyncio for non-blocking operations. All errors are caught
    and logged — the cache never crashes the application.
    """

    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._client = None  # Lazy-initialized on first use

    async def _get_client(self):
        """Lazily create and return the Redis client."""
        if self._client is None:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(
                self._redis_url,
                decode_responses=True,
            )
        return self._client

    async def get(self, key: str) -> str | None:
        """Return cached value or None on miss/error."""
        try:
            client = await self._get_client()
            value = await client.get(key)
            return value
        except Exception as exc:
            logger.warning("Redis GET failed for key %s: %s", key, exc)
            return None

    async def set(self, key: str, value: str, ttl_seconds: int = 1800) -> None:
        """Store value with TTL. Silent no-op on error."""
        try:
            client = await self._get_client()
            await client.set(key, value, ex=ttl_seconds)
        except Exception as exc:
            logger.warning("Redis SET failed for key %s: %s", key, exc)

    async def invalidate(self, pattern: str) -> int:
        """Remove all keys matching pattern. Return count removed.

        Uses SCAN + DEL to avoid blocking Redis on large keyspaces.
        """
        try:
            client = await self._get_client()
            count = 0
            cursor = 0
            while True:
                cursor, keys = await client.scan(
                    cursor=cursor, match=pattern, count=100
                )
                if keys:
                    deleted = await client.delete(*keys)
                    count += deleted
                if cursor == 0:
                    break
            return count
        except Exception as exc:
            logger.warning(
                "Redis INVALIDATE failed for pattern %s: %s", pattern, exc
            )
            return 0
