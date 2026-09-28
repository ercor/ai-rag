"""Unit tests for RedisCache adapter (mocked redis)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapters.redis_cache import RedisCache


@pytest.fixture
def mock_redis_client():
    """Create a mocked async Redis client."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock()
    client.scan = AsyncMock(return_value=(0, []))
    client.delete = AsyncMock(return_value=0)
    return client


@pytest.fixture
def cache():
    """Create a RedisCache instance."""
    return RedisCache(redis_url="redis://localhost:6379")


class TestRedisCacheGet:
    """Tests for RedisCache.get()."""

    async def test_get_returns_value_on_hit(self, cache, mock_redis_client):
        """get() returns the stored value when key exists."""
        cache._client = mock_redis_client
        mock_redis_client.get.return_value = "cached_value"

        result = await cache.get("test_key")
        assert result == "cached_value"

    async def test_get_returns_none_on_miss(self, cache, mock_redis_client):
        """get() returns None when key does not exist."""
        cache._client = mock_redis_client
        mock_redis_client.get.return_value = None

        result = await cache.get("missing_key")
        assert result is None

    async def test_get_returns_none_on_connection_error(self, cache, mock_redis_client):
        """get() returns None on connection error (graceful degradation)."""
        cache._client = mock_redis_client
        mock_redis_client.get.side_effect = ConnectionError("Redis unreachable")

        result = await cache.get("test_key")
        assert result is None

    async def test_get_returns_none_on_timeout(self, cache, mock_redis_client):
        """get() returns None on timeout error."""
        cache._client = mock_redis_client
        mock_redis_client.get.side_effect = TimeoutError("Connection timed out")

        result = await cache.get("test_key")
        assert result is None


class TestRedisCacheSet:
    """Tests for RedisCache.set()."""

    async def test_set_serializes_value_with_ttl(self, cache, mock_redis_client):
        """set() stores value as string with TTL."""
        cache._client = mock_redis_client

        await cache.set("test_key", "test_value", ttl_seconds=3600)
        mock_redis_client.set.assert_called_once_with(
            "test_key", "test_value", ex=3600
        )

    async def test_set_default_ttl(self, cache, mock_redis_client):
        """set() uses default TTL of 1800 seconds."""
        cache._client = mock_redis_client

        await cache.set("test_key", "test_value")
        mock_redis_client.set.assert_called_once_with(
            "test_key", "test_value", ex=1800
        )

    async def test_set_silent_noop_on_connection_error(self, cache, mock_redis_client):
        """set() does not raise on connection error."""
        cache._client = mock_redis_client
        mock_redis_client.set.side_effect = ConnectionError("Redis unreachable")

        # Should not raise
        await cache.set("test_key", "test_value")


class TestRedisCacheInvalidate:
    """Tests for RedisCache.invalidate()."""

    async def test_invalidate_deletes_matching_keys(self, cache, mock_redis_client):
        """invalidate() deletes keys matching pattern and returns count."""
        cache._client = mock_redis_client
        mock_redis_client.scan.return_value = (0, ["key:1", "key:2", "key:3"])
        mock_redis_client.delete.return_value = 3

        count = await cache.invalidate("key:*")
        assert count == 3
        mock_redis_client.delete.assert_called_once_with("key:1", "key:2", "key:3")

    async def test_invalidate_returns_zero_on_no_match(self, cache, mock_redis_client):
        """invalidate() returns 0 when no keys match."""
        cache._client = mock_redis_client
        mock_redis_client.scan.return_value = (0, [])

        count = await cache.invalidate("nonexistent:*")
        assert count == 0

    async def test_invalidate_handles_connection_error(self, cache, mock_redis_client):
        """invalidate() returns 0 on connection error."""
        cache._client = mock_redis_client
        mock_redis_client.scan.side_effect = ConnectionError("Redis unreachable")

        count = await cache.invalidate("key:*")
        assert count == 0

    async def test_invalidate_handles_pagination(self, cache, mock_redis_client):
        """invalidate() handles SCAN pagination across multiple cursors."""
        cache._client = mock_redis_client
        # First scan: cursor=5, 2 keys; second scan: cursor=0, 1 key
        mock_redis_client.scan.side_effect = [
            (5, ["key:1", "key:2"]),
            (0, ["key:3"]),
        ]
        mock_redis_client.delete.side_effect = [2, 1]

        count = await cache.invalidate("key:*")
        assert count == 3


class TestRedisCacheJsonRoundTrip:
    """Tests for JSON serialization round-trip."""

    async def test_json_round_trip(self, cache, mock_redis_client):
        """Complex objects survive JSON serialization round-trip."""
        cache._client = mock_redis_client

        original = {
            "answer": "The travel policy allows 20 days PTO.",
            "citations": [
                {"index": 1, "document_title": "HR Policy", "score": 0.95}
            ],
        }
        serialized = json.dumps(original)
        mock_redis_client.get.return_value = serialized

        result = await cache.get("test_key")
        deserialized = json.loads(result)
        assert deserialized == original
