"""Unit tests for NoopCache adapter."""

import pytest

from src.adapters.noop_cache import NoopCache


@pytest.fixture
def cache():
    """Create a NoopCache instance."""
    return NoopCache()


class TestNoopCache:
    """Tests for NoopCache — always miss, never store."""

    async def test_get_always_returns_none(self, cache):
        """get() always returns None regardless of key."""
        assert await cache.get("any_key") is None
        assert await cache.get("") is None
        assert await cache.get("abc123") is None

    async def test_set_is_noop(self, cache):
        """set() does not raise and stores nothing."""
        # Should not raise
        await cache.set("any_key", "any_value")
        await cache.set("key", "value", ttl_seconds=3600)

        # Verify nothing was stored
        assert await cache.get("any_key") is None

    async def test_invalidate_returns_zero(self, cache):
        """invalidate() always returns 0."""
        assert await cache.invalidate("*") == 0
        assert await cache.invalidate("prefix:*") == 0
        assert await cache.invalidate("") == 0

    async def test_implements_cache_protocol(self, cache):
        """NoopCache has all required Cache protocol methods."""
        assert hasattr(cache, "get")
        assert hasattr(cache, "set")
        assert hasattr(cache, "invalidate")
        assert callable(cache.get)
        assert callable(cache.set)
        assert callable(cache.invalidate)
