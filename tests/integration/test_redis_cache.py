"""Integration tests for RedisCache with a real Redis instance.

Uses testcontainers to spin up a Redis container for testing.
Falls back to skipping if Docker is not available.
"""

import asyncio
import json

import pytest

from src.adapters.redis_cache import RedisCache

# Try to import testcontainers; skip all tests if unavailable
try:
    from testcontainers.redis import RedisContainer

    HAS_TESTCONTAINERS = True
except ImportError:
    HAS_TESTCONTAINERS = False

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not HAS_TESTCONTAINERS, reason="testcontainers not installed"),
]


@pytest.fixture(scope="module")
def redis_container():
    """Start a Redis container for the test module."""
    try:
        container = RedisContainer("redis:7-alpine", port=6379)
        container.start()
        yield container
        container.stop()
    except Exception:
        pytest.skip("Docker not available for Redis testcontainer")


@pytest.fixture(scope="module")
def redis_url(redis_container):
    """Get the Redis URL from the container."""
    host = redis_container.get_container_host_ip()
    port = int(redis_container.get_exposed_port(6379))
    return f"redis://{host}:{port}"


@pytest.fixture
def cache(redis_url):
    """Create a RedisCache connected to the test container."""
    return RedisCache(redis_url=redis_url)


class TestRedisCacheIntegration:
    """Integration tests with real Redis."""

    async def test_get_set_round_trip(self, cache):
        """set() followed by get() returns the original value."""
        await cache.set("test:round_trip", "hello world", ttl_seconds=60)
        result = await cache.get("test:round_trip")
        assert result == "hello world"

    async def test_get_returns_none_on_miss(self, cache):
        """get() returns None for non-existent key."""
        result = await cache.get("test:nonexistent_key_xyz")
        assert result is None

    async def test_json_round_trip(self, cache):
        """Complex JSON objects survive serialization round-trip."""
        original = {
            "answer": "The travel policy allows 20 days PTO.",
            "citations": [
                {"index": 1, "document_title": "HR Policy", "score": 0.95}
            ],
        }
        serialized = json.dumps(original)
        await cache.set("test:json", serialized, ttl_seconds=60)

        result = await cache.get("test:json")
        assert json.loads(result) == original

    async def test_ttl_expiry(self, cache):
        """Key expires after TTL elapses."""
        await cache.set("test:ttl", "expires_soon", ttl_seconds=1)

        # Immediately available
        result = await cache.get("test:ttl")
        assert result == "expires_soon"

        # Wait for TTL to expire
        await asyncio.sleep(2)

        result = await cache.get("test:ttl")
        assert result is None

    async def test_invalidate_deletes_matching_keys(self, cache):
        """invalidate() removes all keys matching the pattern."""
        # Set up test keys
        await cache.set("inv:key1", "v1", ttl_seconds=60)
        await cache.set("inv:key2", "v2", ttl_seconds=60)
        await cache.set("inv:key3", "v3", ttl_seconds=60)
        await cache.set("other:key", "v4", ttl_seconds=60)

        # Invalidate matching keys
        count = await cache.invalidate("inv:*")
        assert count == 3

        # Verify matching keys are gone
        assert await cache.get("inv:key1") is None
        assert await cache.get("inv:key2") is None
        assert await cache.get("inv:key3") is None

        # Non-matching key still exists
        assert await cache.get("other:key") == "v4"

    async def test_invalidate_returns_zero_for_no_match(self, cache):
        """invalidate() returns 0 when no keys match."""
        count = await cache.invalidate("nonexistent_pattern:*")
        assert count == 0

    async def test_set_overwrites_existing_value(self, cache):
        """set() overwrites a previously stored value."""
        await cache.set("test:overwrite", "first", ttl_seconds=60)
        await cache.set("test:overwrite", "second", ttl_seconds=60)

        result = await cache.get("test:overwrite")
        assert result == "second"
