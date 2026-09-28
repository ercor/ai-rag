"""No-op cache adapter — always misses, never stores.

Used when caching is disabled (cache_enabled=false) or as a fallback
when Redis is unavailable at startup.
"""


class NoopCache:
    """No-op cache implementing the Cache protocol.

    All get() calls return None (cache miss).
    All set() calls are no-ops.
    invalidate() returns 0.
    """

    async def get(self, key: str) -> str | None:
        """Always return None (cache miss)."""
        return None

    async def set(self, key: str, value: str, ttl_seconds: int = 1800) -> None:
        """No-op — does not store anything."""
        pass

    async def invalidate(self, pattern: str) -> int:
        """Return 0 — nothing to invalidate."""
        return 0
