"""Unit tests for cache key computation."""

import pytest

from src.core.cache_key import compute_cache_key


class TestComputeCacheKey:
    """Tests for compute_cache_key function."""

    def test_same_query_different_whitespace_produces_same_key(self):
        """Whitespace normalization: leading/trailing/internal spaces."""
        key1 = compute_cache_key("  What is the Travel Policy?  ")
        key2 = compute_cache_key("what is the travel policy?")
        assert key1 == key2

    def test_same_query_different_case_produces_same_key(self):
        """Case normalization: uppercase and lowercase produce same key."""
        key1 = compute_cache_key("WHAT IS THE TRAVEL POLICY?")
        key2 = compute_cache_key("what is the travel policy?")
        assert key1 == key2

    def test_internal_whitespace_collapse(self):
        """Multiple internal spaces collapse to single space."""
        key1 = compute_cache_key("what   is    the   policy")
        key2 = compute_cache_key("what is the policy")
        assert key1 == key2

    def test_different_filters_produce_different_keys(self):
        """Different filter dicts produce different cache keys."""
        key1 = compute_cache_key("test query", filters={"source": "hr_docs"})
        key2 = compute_cache_key("test query", filters={"source": "finance_docs"})
        assert key1 != key2

    def test_none_filters_same_as_empty_dict(self):
        """None filters and empty dict produce the same key."""
        key1 = compute_cache_key("test query", filters=None)
        key2 = compute_cache_key("test query", filters={})
        assert key1 == key2

    def test_different_index_versions_produce_different_keys(self):
        """Changing index version invalidates cache (different key)."""
        key1 = compute_cache_key("test query", index_version="v1")
        key2 = compute_cache_key("test query", index_version="v2")
        assert key1 != key2

    def test_key_is_valid_sha256_hex_digest(self):
        """Cache key is a 64-character hex string (SHA-256)."""
        key = compute_cache_key("any query")
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_different_queries_produce_different_keys(self):
        """Different queries produce different cache keys."""
        key1 = compute_cache_key("what is the travel policy?")
        key2 = compute_cache_key("what is the leave policy?")
        assert key1 != key2

    def test_filter_order_does_not_matter(self):
        """Filters with same keys/values in different order produce same key."""
        key1 = compute_cache_key(
            "query", filters={"a": "1", "b": "2"}
        )
        key2 = compute_cache_key(
            "query", filters={"b": "2", "a": "1"}
        )
        assert key1 == key2

    def test_deterministic(self):
        """Same inputs always produce the same key."""
        args = ("test query", {"source": "docs"}, "v1")
        keys = {compute_cache_key(*args) for _ in range(10)}
        assert len(keys) == 1
