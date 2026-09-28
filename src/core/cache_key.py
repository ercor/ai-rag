"""Cache key computation — deterministic SHA-256 keys for answer caching.

Composes a normalized query, a filters hash, and an index version into a
single SHA-256 hex digest suitable as a Redis key.
"""

import hashlib
import json
import re


def compute_cache_key(
    query: str,
    filters: dict | None = None,
    index_version: str = "v1",
) -> str:
    """Compute a deterministic cache key for a query + filters + index version.

    Normalization:
    - Query: lowercase, strip leading/trailing whitespace, collapse internal
      whitespace to single spaces.
    - Filters: sorted JSON serialization (deterministic key order).
    - Index version: used as-is; changing it invalidates all prior keys.

    Returns:
        SHA-256 hex digest (64 characters) of the composed string.
    """
    normalized_query = _normalize_query(query)
    filters_hash = _hash_filters(filters)
    composed = f"{normalized_query}:{filters_hash}:{index_version}"
    return hashlib.sha256(composed.encode("utf-8")).hexdigest()


def _normalize_query(query: str) -> str:
    """Lowercase, strip, and collapse internal whitespace."""
    query = query.strip().lower()
    query = re.sub(r"\s+", " ", query)
    return query


def _hash_filters(filters: dict | None) -> str:
    """SHA-256 of the sorted JSON representation of filters."""
    if filters is None:
        filters = {}
    serialized = json.dumps(filters, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
