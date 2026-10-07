# Answer Caching Specification

## Purpose

Define the answer caching capability that stores complete query results (answer text + citations) in Redis to avoid re-processing identical queries, reducing latency and model inference costs.

## Requirements

### Requirement: Cache Port

The system SHALL define a `Cache` port (Protocol) with three operations: `get(key) -> str | None`, `set(key, value, ttl_seconds) -> None`, and `invalidate(pattern) -> int`.

The port MUST be adapter-agnostic — no Redis-specific types or operations SHALL appear in the interface.

#### Scenario: Cache get hit

- GIVEN a key "abc123" exists in the cache with a stored value
- WHEN `Cache.get("abc123")` is called
- THEN it returns the stored string value

#### Scenario: Cache get miss

- GIVEN a key "xyz789" does not exist in the cache
- WHEN `Cache.get("xyz789")` is called
- THEN it returns `None`

#### Scenario: Cache set with TTL

- GIVEN a key "abc123" and a value `{"answer": "...", "citations": [...]}`
- WHEN `Cache.set("abc123", value, ttl_seconds=1800)` is called
- THEN the value is stored and will expire after 1800 seconds

#### Scenario: Cache invalidate

- GIVEN multiple keys matching a pattern exist in the cache
- WHEN `Cache.invalidate("prefix:*")` is called
- THEN all matching keys are removed
- AND the return value is the count of invalidated keys

### Requirement: Redis Cache Adapter

The system SHALL provide a `RedisCache` adapter that implements the `Cache` port using `redis.asyncio`.

The adapter MUST serialize values as JSON strings. The adapter MUST handle connection errors gracefully without crashing the application.

#### Scenario: Successful get/set round-trip

- GIVEN a running Redis instance
- WHEN a value is set and then retrieved
- THEN the retrieved value matches the original (after JSON round-trip)

#### Scenario: Redis connection failure on get

- GIVEN Redis is unreachable (connection refused)
- WHEN `Cache.get()` is called
- THEN the adapter returns `None` (cache miss) without raising an exception
- AND a warning is logged

#### Scenario: Redis connection failure on set

- GIVEN Redis is unreachable
- WHEN `Cache.set()` is called
- THEN the adapter silently no-ops without raising an exception
- AND a warning is logged

#### Scenario: JSON serialization

- GIVEN a complex answer object with nested citations
- WHEN the value is stored via `Cache.set()`
- THEN it is serialized to a valid JSON string
- AND `Cache.get()` deserializes it back to the original structure

### Requirement: Cache Key Strategy

The system SHALL compute cache keys using SHA-256 of a normalized composition: `normalize(query) + ":" + filters_hash + ":" + index_version`.

Normalization MUST include: lowercase, strip leading/trailing whitespace, collapse internal whitespace to single spaces. The filters hash MUST capture all retrieval parameters that affect results (source filters, date ranges). The index version MUST change when documents are re-ingested.

#### Scenario: Same query produces same key

- GIVEN the query "  What is the Travel Policy?  " with no filters and index version "v1"
- WHEN the cache key is computed
- THEN it produces the same SHA-256 hash as the query "what is the travel policy?" with no filters and index version "v1"

#### Scenario: Different filters produce different keys

- GIVEN the same query with filter `{source: "hr_docs"}` vs. filter `{source: "finance_docs"}`
- WHEN cache keys are computed
- THEN the two keys are different SHA-256 hashes

#### Scenario: Index version change invalidates cache

- GIVEN a cached answer for query Q with index version "v1"
- WHEN documents are re-ingested and the index version changes to "v2"
- THEN the cache key for Q with "v2" differs from the key with "v1"
- AND the old cached entry is effectively invalidated (different key)

#### Scenario: Key normalization edge cases

- GIVEN queries with extra spaces, mixed case, and leading/trailing whitespace
- WHEN cache keys are computed
- THEN all whitespace-normalized, lowercased variants produce the same key

### Requirement: Pipeline Integration

The system SHALL integrate caching into the query pipeline at two points: (1) check cache before retrieval, and (2) store result in cache after successful generation.

On cache hit, the pipeline MUST return the cached answer immediately without calling the embedder, search index, or generator. On cache miss, the pipeline MUST store the full result (answer text + citations + metadata) after successful generation.

#### Scenario: Cache hit bypasses pipeline

- GIVEN a cached answer exists for query Q
- WHEN query Q enters the pipeline
- THEN the cache returns the stored answer
- AND no embedding, search, or generation occurs
- AND the response is returned to the client

#### Scenario: Cache miss triggers full pipeline

- GIVEN no cached answer exists for query Q
- WHEN query Q enters the pipeline
- THEN the full pipeline executes (embed → search → generate)
- AND the result is stored in the cache with the configured TTL
- AND the response is returned to the client

#### Scenario: Cache store after generation

- GIVEN the pipeline completes generation successfully
- WHEN the answer is finalized
- THEN the answer text, citations, and metadata are stored in the cache
- AND the TTL is set to `cache_ttl_seconds` (default: 1800)

#### Scenario: Failed generation not cached

- GIVEN the pipeline fails during generation (status: "failed")
- WHEN the failure is detected
- THEN no result is stored in the cache

#### Scenario: Abstention not cached

- GIVEN the pipeline triggers abstention (insufficient evidence)
- WHEN abstention is detected
- THEN no result is stored in the cache

### Requirement: Graceful Degradation

The system SHALL continue operating normally when Redis is unavailable.

Cache failures MUST NOT cause pipeline failures. If the cache is unreachable, the pipeline MUST proceed as if caching is disabled (every query is a cache miss).

#### Scenario: Redis down, pipeline continues

- GIVEN Redis is unreachable
- WHEN a query enters the pipeline
- THEN the cache check returns `None` (miss)
- AND the full pipeline executes normally
- AND the cache store silently fails
- AND the client receives a valid response

#### Scenario: Redis recovers

- GIVEN Redis was down and has recovered
- WHEN a new query enters the pipeline
- THEN cache operations resume normally (get/set work as expected)

### Requirement: Cache Configuration

The system SHALL expose caching settings via environment variables with sensible defaults.

Required settings: `cache_enabled` (bool, default: true), `redis_url` (str, default: "redis://localhost:6379"), `cache_ttl_seconds` (int, default: 1800).

#### Scenario: Default configuration

- GIVEN no cache environment variables are set
- WHEN settings are loaded
- THEN `cache_enabled=true`, `redis_url="redis://localhost:6379"`, `cache_ttl_seconds=1800`

#### Scenario: Custom TTL

- GIVEN `CACHE_TTL_SECONDS=3600` is set
- WHEN settings are loaded
- THEN `cache_ttl_seconds=3600`

### Requirement: Docker Compose Redis Service

The system SHALL include a Redis service in `docker-compose.yml` with a health check.

The service MUST use `redis:7-alpine` image, expose port 6379, and include a health check that verifies Redis is accepting connections.

#### Scenario: Redis service starts

- GIVEN `docker compose up` is executed
- WHEN the Redis container starts
- THEN it passes the health check within 10 seconds
- AND the backend can connect to `redis://localhost:6379`

### Requirement: Dependency Injection Wiring

The system SHALL provide a `get_cache()` factory in the DI container that returns the configured `Cache` adapter instance.

When caching is disabled or Redis is unavailable at startup, the factory SHALL return a no-op cache implementation that always returns `None` on `get()`.

#### Scenario: Cache factory when enabled

- GIVEN `cache_enabled=true` and Redis is reachable
- WHEN `get_cache()` is called
- THEN it returns a `RedisCache` instance connected to the configured Redis URL

#### Scenario: Cache factory when disabled

- GIVEN `cache_enabled=false`
- WHEN `get_cache()` is called
- THEN it returns a no-op cache (all gets return `None`, sets are no-ops)

### Requirement: Cache Hit Latency

Cache hits MUST return in under 50ms (p95).

#### Scenario: Cache hit latency

- GIVEN a cached answer exists
- WHEN `Cache.get()` is called
- THEN the response is returned in under 50ms at p95

## Out of Scope

- Cache warming or pre-computation
- Per-user or per-session cache partitioning
- Cache statistics dashboard
- Selective cache invalidation by document ID
- Cache compression or size limits beyond Redis maxmemory
