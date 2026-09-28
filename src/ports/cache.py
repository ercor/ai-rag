"""Cache port — key-value cache with TTL support."""

from typing import Protocol


class Cache(Protocol):
    """Key-value cache with TTL support.

    Implementations: Redis, in-memory LRU, no-op, etc.
    """

    async def get(self, key: str) -> str | None:
        """Return cached value or None on miss/error."""
        ...

    async def set(self, key: str, value: str, ttl_seconds: int = 1800) -> None:
        """Store value with TTL. Silent no-op on error."""
        ...

    async def invalidate(self, pattern: str) -> int:
        """Remove all keys matching pattern. Return count removed."""
        ...
