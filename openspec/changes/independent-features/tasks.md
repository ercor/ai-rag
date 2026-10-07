# Tasks: Independent Features Implementation

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~3200-3800 (across 5 features) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (Reranking) → PR 2 (Query Rewriting) → PR 3 (Redis Caching) → PR 4 (Conversation History) → PR 5 (Evaluation Framework) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Cross-Encoder Reranking — port, adapter, pipeline integration, config, DI, tests | PR 1 | `pytest tests/unit/test_reranker.py tests/unit/test_pipeline_reranking.py` | Real cross-encoder model on CPU; verify latency <500ms p95 for 20 candidates | `src/ports/reranker.py`, `src/adapters/cross_encoder_reranker.py`, reranker config, pipeline rerank step — all removable via `reranker_enabled=false` |
| 2 | Query Rewriting — port, adapter, multi-query search, cross-variant RRF, config, DI, tests | PR 2 | `pytest tests/unit/test_query_rewriter.py tests/unit/test_multi_query_rrf.py tests/unit/test_pipeline_rewriting.py` | Real Ollama Generator; verify 3 variants produced, parallel search, latency overhead <2s | `src/ports/query_rewriter.py`, `src/adapters/llm_query_rewriter.py`, rewriter config, multi-query pipeline — all removable via `query_rewriter_enabled=false` |
| 3 | Redis Caching — port, adapter, cache key, pipeline integration, Docker, health check, tests | PR 3 | `pytest tests/unit/test_cache_key.py tests/unit/test_redis_cache.py tests/unit/test_noop_cache.py && pytest tests/integration/test_redis_cache.py` | testcontainers Redis; verify get/set round-trip, TTL, graceful degradation | `src/ports/cache.py`, `src/adapters/redis_cache.py`, `src/adapters/noop_cache.py`, `src/core/cache_key.py`, cache config, Redis Docker service — all removable via `cache_enabled=false` |
| 4 | Conversation History — migration, port, adapter, API, pipeline integration, frontend sidebar, tests | PR 4 | `pytest tests/unit/test_conversation_repository.py tests/unit/test_conversation_prompt.py tests/integration/test_conversation_api.py` | testcontainers PostgreSQL; verify CRUD, cascade delete, prompt history; frontend E2E with Playwright | `migrations/004_conversations.sql`, `src/ports/conversation_repository.py`, `src/adapters/pg_conversation_repository.py`, `src/api/conversations.py`, frontend sidebar — all removable by dropping migration and sidebar component |
| 5 | Evaluation Framework — port, RAGAS adapter, custom metrics, CLI runner, gold dataset, report, tests | PR 5 | `pytest tests/unit/test_custom_metrics.py tests/unit/test_eval_dataset.py tests/unit/test_eval_runner.py && python -m src.evaluation --dataset data/eval/gold_set.json --metrics citation_precision` | Real Ollama as LLM judge; verify JSON report output, deterministic metrics | `src/evaluation/`, `src/ports/evaluation.py`, `data/eval/`, `[eval]` extras — all removable by not invoking CLI |

## Phase 1: Cross-Encoder Reranking

### 1.1 Create Reranker port

- [ ] 1.1.1 Create `src/ports/reranker.py` with `Reranker` Protocol
  - Define `rerank(query: str, candidates: list[RetrievedChunk], top_k: int = 5) -> list[RetrievedChunk]`
  - Import `RetrievedChunk` from `src.core.retrieval`
  - Docstring: "Re-scores retrieval candidates using a cross-encoder model"
  - **Verify**: `python -c "from src.ports.reranker import Reranker"` succeeds

### 1.2 Create CrossEncoderReranker adapter

- [ ] 1.2.1 Create `src/adapters/cross_encoder_reranker.py`
  - Class `CrossEncoderReranker` implementing `Reranker` protocol
  - Constructor accepts `model_name: str` (default: `"cross-encoder/ms-marco-MiniLM-L-6-v2"`)
  - Lazy-load model on first `rerank()` call; cache as instance attribute
  - `rerank()`: create (query, chunk_content) pairs, call `model.predict()`, sort by score descending, return top_k
  - Replace each returned chunk's `score` with the cross-encoder score
  - Handle empty candidate list: return empty list immediately
  - **Verify**: Unit test with mocked model passes

### 1.3 Add reranker configuration

- [ ] 1.3.1 Modify `src/config.py`
  - Add fields: `reranker_enabled: bool = True`, `reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"`, `reranker_top_k_before: int = 20`, `reranker_top_k_after: int = 5`, `reranker_timeout_seconds: float = 5.0`
  - **Verify**: `python -c "from src.config import Settings; s = Settings(); print(s.reranker_enabled)"` prints `True`

### 1.4 Add reranker DI factory

- [ ] 1.4.1 Modify `src/container.py`
  - Add `get_reranker() -> Reranker | None` function
  - When `settings.reranker_enabled` is True: return `CrossEncoderReranker(model_name=settings.reranker_model)`
  - When False: return `None`
  - **Verify**: `get_reranker()` returns an instance when enabled, `None` when disabled

### 1.5 Integrate reranker into pipeline

- [ ] 1.5.1 Modify `src/core/query_pipeline.py`
  - Add optional `reranker: Reranker | None` parameter to `QueryPipeline.__init__()` or `retrieve()`
  - After RRF fusion, if reranker is not None:
    - Call `reranker.rerank(query, fused_candidates, top_k=settings.reranker_top_k_after)`
    - Wrap in `asyncio.wait_for()` with `timeout=settings.reranker_timeout_seconds`
    - On timeout: log warning, fall back to non-reranked results
  - Pass reranked results to abstention check and generation
  - Log reranking duration in milliseconds
  - **Verify**: Pipeline with reranker returns top-5 reranked chunks; pipeline without reranker behaves as before

- [ ] 1.5.2 Modify `src/core/retrieval.py`
  - Make `rrf_fusion()` accept configurable `top_k` parameter (currently may be hardcoded)
  - When reranking enabled, pipeline passes `reranker_top_k_before` as the RRF top_k
  - **Verify**: RRF produces up to 20 candidates when reranking enabled

### 1.6 Wire reranker into API

- [ ] 1.6.1 Modify `src/api/answers.py`
  - In `_get_pipeline()` or equivalent: call `container.get_reranker()` and pass to pipeline
  - **Verify**: API endpoint works with reranker enabled and disabled

### 1.7 Add sentence-transformers dependency

- [ ] 1.7.1 Modify `pyproject.toml`
  - Add `"sentence-transformers>=2.7.0"` to `[project.dependencies]`
  - **Verify**: `pip install -e .` succeeds

### 1.8 Write unit tests for reranker

- [ ] 1.8.1 Create `tests/unit/test_reranker.py`
  - Test: `rerank()` with 20 candidates returns top 5 sorted by score
  - Test: `rerank()` with empty list returns empty list
  - Test: model is loaded lazily (mock `CrossEncoder` constructor)
  - Test: model is cached after first load (second call doesn't re-instantiate)
  - Test: chunk scores are replaced with cross-encoder scores
  - **Verify**: `pytest tests/unit/test_reranker.py -v` passes

### 1.9 Write unit tests for pipeline reranking

- [ ] 1.9.1 Create `tests/unit/test_pipeline_reranking.py`
  - Test: pipeline with reranker calls reranker after RRF
  - Test: pipeline without reranker (reranker=None) skips reranking
  - Test: pipeline falls back to non-reranked results on timeout
  - Test: reranking duration is logged
  - **Verify**: `pytest tests/unit/test_pipeline_reranking.py -v` passes

### 1.10 Update .env.example

- [ ] 1.10.1 Modify `.env.example`
  - Add: `RERANKER_ENABLED=true`, `RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2`, `RERANKER_TOP_K_BEFORE=20`, `RERANKER_TOP_K_AFTER=5`, `RERANKER_TIMEOUT_SECONDS=5.0`
  - **Verify**: File contains all new variables

## Phase 2: Query Rewriting

### 2.1 Create QueryRewriter port

- [x] 2.1.1 Create `src/ports/query_rewriter.py`
  - Define `QueryRewriter` Protocol with `rewrite(query: str) -> list[str]`
  - Docstring: "Generates query variants for multi-query retrieval"
  - **Verify**: `python -c "from src.ports.query_rewriter import QueryRewriter"` succeeds

### 2.2 Create LLMQueryRewriter adapter

- [x] 2.2.1 Create `src/adapters/llm_query_rewriter.py`
  - Class `LLMQueryRewriter` implementing `QueryRewriter` protocol
  - Constructor accepts `generator: Generator` (existing port) and `num_variants: int`
  - `rewrite()`: construct structured prompt asking LLM to produce N-1 rephrasings of the query
  - Parse LLM output into list of query strings (split by newline or numbered list)
  - Always include original query in returned list
  - On Generator failure: log warning, return `[query]` (fallback)
  - On malformed output: log warning with raw output, return `[query]`
  - **Verify**: Unit test with mocked Generator passes

### 2.3 Add query rewriter configuration

- [x] 2.3.1 Modify `src/config.py`
  - Add fields: `query_rewriter_enabled: bool = False`, `query_rewriter_num_variants: int = 3`
  - **Verify**: `python -c "from src.config import Settings; s = Settings(); print(s.query_rewriter_enabled)"` prints `False`

### 2.4 Add query rewriter DI factory

- [x] 2.4.1 Modify `src/container.py`
  - Add `get_query_rewriter() -> QueryRewriter | None` function
  - When `settings.query_rewriter_enabled` is True: return `LLMQueryRewriter(generator=get_generator(), num_variants=settings.query_rewriter_num_variants)`
  - When False: return `None`
  - **Verify**: `get_query_rewriter()` returns instance when enabled, `None` when disabled

### 2.5 Add cross-variant RRF merge

- [x] 2.5.1 Modify `src/core/retrieval.py`
  - Add `rrf_fusion_multi(variant_results: list[list[RetrievedChunk]]) -> list[RetrievedChunk]` function
  - Deduplicate chunks across variant result lists
  - Accumulate RRF scores for chunks appearing in multiple lists
  - Sort by descending accumulated score
  - When only 1 variant: behavior identical to single-query `rrf_fusion()`
  - **Verify**: Unit test with overlapping results produces correct merged list

### 2.6 Integrate query rewriting into pipeline

- [x] 2.6.1 Modify `src/core/query_pipeline.py`
  - Add optional `query_rewriter: QueryRewriter | None` parameter
  - Before embedding step, if query_rewriter is not None:
    - Call `query_rewriter.rewrite(question)` to get variants
    - For each variant: embed and search in parallel using `asyncio.gather()`
    - Merge all variant results via `rrf_fusion_multi()`
  - Log rewriting duration and variant count
  - When query_rewriter is None: use raw query (current behavior)
  - **Verify**: Pipeline with rewriter produces merged results from multiple variants; pipeline without rewriter behaves as before

### 2.7 Wire query rewriter into API

- [x] 2.7.1 Modify `src/api/answers.py`
  - In `_get_pipeline()`: call `container.get_query_rewriter()` and pass to pipeline
  - **Verify**: API endpoint works with rewriter enabled and disabled

### 2.8 Write unit tests for query rewriter

- [x] 2.8.1 Create `tests/unit/test_query_rewriter.py`
  - Test: `rewrite()` produces correct number of variants (original + N-1)
  - Test: original query is included in returned list
  - Test: Generator failure returns `[query]` (fallback)
  - Test: malformed LLM output returns `[query]` (fallback)
  - Test: each variant is a standalone query string
  - **Verify**: `pytest tests/unit/test_query_rewriter.py -v` passes

### 2.9 Write unit tests for cross-variant RRF

- [x] 2.9.1 Create `tests/unit/test_multi_query_rrf.py`
  - Test: merge of 3 variant results with overlapping chunks produces deduplicated list
  - Test: chunks in multiple variants have higher accumulated scores
  - Test: single variant merge is identical to single-query RRF
  - Test: all variants return identical results preserves ranking
  - **Verify**: `pytest tests/unit/test_multi_query_rrf.py -v` passes

### 2.10 Write unit tests for pipeline rewriting

- [x] 2.10.1 Create `tests/unit/test_pipeline_rewriting.py`
  - Test: pipeline with rewriter calls rewriter before embedding
  - Test: pipeline without rewriter (rewriter=None) uses raw query
  - Test: parallel search execution (mock `asyncio.gather`)
  - Test: rewriting duration and variant count are logged
  - **Verify**: `pytest tests/unit/test_pipeline_rewriting.py -v` passes

### 2.11 Update .env.example

- [x] 2.11.1 Modify `.env.example`
  - Add: `QUERY_REWRITER_ENABLED=false`, `QUERY_REWRITER_NUM_VARIANTS=3`
  - **Verify**: File contains all new variables

## Phase 3: Redis Caching

### 3.1 Create Cache port

- [x] 3.1.1 Create `src/ports/cache.py`
  - Define `Cache` Protocol with:
    - `get(key: str) -> str | None`
    - `set(key: str, value: str, ttl_seconds: int = 1800) -> None`
    - `invalidate(pattern: str) -> int`
  - Docstring: "Key-value cache with TTL support"
  - **Verify**: `python -c "from src.ports.cache import Cache"` succeeds

### 3.2 Create cache key computation

- [x] 3.2.1 Create `src/core/cache_key.py`
  - Function `compute_cache_key(query: str, filters: dict | None, index_version: str) -> str`
  - Normalize query: lowercase, strip leading/trailing whitespace, collapse internal whitespace
  - Compute filters_hash: SHA-256 of sorted JSON representation of filters (or empty dict)
  - Compose: `normalized_query + ":" + filters_hash + ":" + index_version`
  - Return SHA-256 hex digest of composed string
  - **Verify**: Same query with different whitespace produces same key; different filters produce different keys

### 3.3 Create RedisCache adapter

- [x] 3.3.1 Create `src/adapters/redis_cache.py`
  - Class `RedisCache` implementing `Cache` protocol
  - Constructor accepts `redis_url: str`
  - Use `redis.asyncio` for async operations
  - `get()`: deserialize JSON, return value; on connection error: log warning, return `None`
  - `set()`: serialize value as JSON, set with TTL; on connection error: log warning, no-op
  - `invalidate()`: use SCAN + DEL for pattern matching; return count deleted
  - **Verify**: Unit test with mocked redis passes

### 3.4 Create NoopCache adapter

- [x] 3.4.1 Create `src/adapters/noop_cache.py`
  - Class `NoopCache` implementing `Cache` protocol
  - `get()`: always return `None`
  - `set()`: no-op
  - `invalidate()`: return 0
  - **Verify**: Unit test confirms no-op behavior

### 3.5 Add cache configuration

- [x] 3.5.1 Modify `src/config.py`
  - Add fields: `cache_enabled: bool = True`, `redis_url: str = "redis://localhost:6379"`, `cache_ttl_seconds: int = 1800`
  - **Verify**: `python -c "from src.config import Settings; s = Settings(); print(s.cache_enabled)"` prints `True`

### 3.6 Add cache DI factory

- [x] 3.6.1 Modify `src/container.py`
  - Add `get_cache() -> Cache` function
  - When `settings.cache_enabled` is True: return `RedisCache(redis_url=settings.redis_url)`
  - When False: return `NoopCache()`
  - **Verify**: `get_cache()` returns RedisCache when enabled, NoopCache when disabled

### 3.7 Integrate caching into pipeline

- [x] 3.7.1 Modify `src/core/query_pipeline.py`
  - Add optional `cache: Cache | None` parameter
  - At start of `answer()` or equivalent: compute cache key, call `cache.get(key)`
  - On cache hit: return cached answer immediately (no embedding, search, generation)
  - On cache miss: run full pipeline; after successful generation, call `cache.set(key, result, ttl=settings.cache_ttl_seconds)`
  - Do NOT cache failed generations or abstentions
  - **Verify**: Pipeline with cache returns cached answer on second identical query; pipeline without cache behaves as before

### 3.8 Wire cache into API

- [x] 3.8.1 Modify `src/api/answers.py`
  - In `_get_pipeline()`: call `container.get_cache()` and pass to pipeline
  - Handle cache hit fast-path: return cached response without running pipeline
  - **Verify**: API endpoint returns cached answer on cache hit

### 3.9 Add Redis health check

- [x] 3.9.1 Modify `src/api/health.py`
  - In `/ready` endpoint: attempt Redis PING; if successful, include `redis: ok`; if failed, include `redis: degraded`
  - Do NOT fail the health check if Redis is down (graceful degradation)
  - **Verify**: `/ready` returns 200 with Redis status

### 3.10 Add Redis to Docker Compose

- [x] 3.10.1 Modify `docker-compose.yml`
  - Add Redis service:
    ```yaml
    redis:
      image: redis:7-alpine
      ports:
        - "6379:6379"
      healthcheck:
        test: ["CMD", "redis-cli", "ping"]
        interval: 5s
        timeout: 3s
        retries: 5
    ```
  - Add `redis_url` environment variable to backend service
  - Do NOT add Redis to backend `depends_on` (graceful degradation)
  - **Verify**: `docker compose up` starts Redis; backend connects to Redis

### 3.11 Add redis dependency

- [x] 3.11.1 Modify `pyproject.toml`
  - Add `"redis[hiredis]>=5.0.0"` to `[project.dependencies]`
  - **Verify**: `pip install -e .` succeeds

### 3.12 Write unit tests for cache key

- [x] 3.12.1 Create `tests/unit/test_cache_key.py`
  - Test: same query with different whitespace produces same key
  - Test: same query with different case produces same key
  - Test: different filters produce different keys
  - Test: different index versions produce different keys
  - Test: key is valid SHA-256 hex digest (64 chars)
  - **Verify**: `pytest tests/unit/test_cache_key.py -v` passes

### 3.13 Write unit tests for RedisCache

- [x] 3.13.1 Create `tests/unit/test_redis_cache.py`
  - Test: `get()` returns deserialized value on hit
  - Test: `get()` returns `None` on miss
  - Test: `set()` serializes value as JSON
  - Test: `get()` on connection error returns `None` (graceful degradation)
  - Test: `set()` on connection error is silent no-op
  - Test: `invalidate()` deletes matching keys and returns count
  - **Verify**: `pytest tests/unit/test_redis_cache.py -v` passes

### 3.14 Write unit tests for NoopCache

- [x] 3.14.1 Create `tests/unit/test_noop_cache.py`
  - Test: `get()` always returns `None`
  - Test: `set()` is no-op
  - Test: `invalidate()` returns 0
  - **Verify**: `pytest tests/unit/test_noop_cache.py -v` passes

### 3.15 Write integration tests for RedisCache

- [x] 3.15.1 Create `tests/integration/test_redis_cache.py`
  - Use testcontainers Redis (or Docker Redis)
  - Test: `get()`/`set()` round-trip with real Redis
  - Test: TTL expiry (set with short TTL, wait, verify miss)
  - Test: `invalidate()` deletes matching keys
  - **Verify**: `pytest tests/integration/test_redis_cache.py -v` passes with Redis running

### 3.16 Update .env.example

- [x] 3.16.1 Modify `.env.example`
  - Add: `CACHE_ENABLED=true`, `REDIS_URL=redis://localhost:6379`, `CACHE_TTL_SECONDS=1800`
  - **Verify**: File contains all new variables

## Phase 4: Conversation History

### 4.1 Create database migration

- [ ] 4.1.1 Create `migrations/004_conversations.sql`
  - Create `conversations` table:
    ```sql
    CREATE TABLE conversations (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        title TEXT NOT NULL DEFAULT 'New Conversation',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX idx_conversations_updated ON conversations (updated_at DESC);
    ```
  - Add `conversation_id` column to `answers`:
    ```sql
    ALTER TABLE answers ADD COLUMN conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE;
    CREATE INDEX idx_answers_conversation ON answers (conversation_id, created_at);
    ```
  - **Verify**: Migration applies cleanly to existing schema; existing answers remain intact with `conversation_id=NULL`

### 4.2 Create ConversationRepository port

- [ ] 4.2.1 Create `src/ports/conversation_repository.py`
  - Define dataclasses: `Conversation` (id, title, created_at, updated_at), `ConversationAnswer` (id, question, answer, status, citations, created_at)
  - Define `ConversationRepository` Protocol with:
    - `create(title: str | None) -> Conversation`
    - `get_by_id(conversation_id: str) -> Conversation | None`
    - `list(limit: int, offset: int) -> list[Conversation]`
    - `delete(conversation_id: str) -> None`
    - `get_answers(conversation_id: str) -> list[ConversationAnswer]`
    - `update_title(conversation_id: str, title: str) -> None`
    - `touch(conversation_id: str) -> None`
  - **Verify**: `python -c "from src.ports.conversation_repository import ConversationRepository"` succeeds

### 4.3 Create PgConversationRepository adapter

- [ ] 4.3.1 Create `src/adapters/pg_conversation_repository.py`
  - Class `PgConversationRepository` implementing `ConversationRepository` protocol
  - Constructor accepts asyncpg pool
  - Use parameterized queries for all operations (prevent SQL injection)
  - `create()`: INSERT with optional title; auto-generate title if None
  - `get_by_id()`: SELECT by id; return None if not found
  - `list()`: SELECT ORDER BY updated_at DESC with LIMIT/OFFSET
  - `delete()`: DELETE by id (cascades to answers via FK)
  - `get_answers()`: SELECT answers WHERE conversation_id = ? ORDER BY created_at ASC
  - `update_title()`: UPDATE title WHERE id = ?
  - `touch()`: UPDATE updated_at = now() WHERE id = ?
  - **Verify**: Unit test with mocked pool passes

### 4.4 Add conversation configuration

- [ ] 4.4.1 Modify `src/config.py`
  - Add field: `max_conversation_history: int = 5`
  - **Verify**: `python -c "from src.config import Settings; s = Settings(); print(s.max_conversation_history)"` prints `5`

### 4.5 Add conversation repository DI factory

- [ ] 4.5.1 Modify `src/container.py`
  - Add `get_conversation_repository() -> ConversationRepository` function
  - Return `PgConversationRepository(pool=get_db_pool())`
  - **Verify**: Factory returns repository instance

### 4.6 Create conversation API router

- [ ] 4.6.1 Create `src/api/conversations.py`
  - FastAPI router with prefix `/v1/conversations`
  - `POST /v1/conversations`: create conversation (body: optional `title`); return 201
  - `GET /v1/conversations`: list conversations (query params: `limit=20`, `offset=0`); return 200 with list + total
  - `GET /v1/conversations/{id}`: get conversation with answers; return 200 or 404
  - `DELETE /v1/conversations/{id}`: delete conversation; return 204
  - **Verify**: API endpoints return correct status codes

### 4.7 Register conversations router

- [ ] 4.7.1 Modify `src/main.py`
  - Import and include conversations router: `app.include_router(conversations_router)`
  - **Verify**: `/v1/conversations` endpoint is accessible

### 4.8 Modify answers API to accept conversation_id

- [ ] 4.8.1 Modify `src/api/answers.py`
  - Add optional `conversation_id: str | None` field to answer request model
  - When provided: validate conversation exists; pass to pipeline; link answer to conversation
  - When omitted: create answer without conversation link (backward compatible)
  - After answer creation: call `conversation_repo.touch(conversation_id)` to update timestamp
  - Auto-generate conversation title from first question if title is default
  - **Verify**: Answer with conversation_id is linked; answer without conversation_id works as before

### 4.9 Integrate conversation history into prompt

- [ ] 4.9.1 Modify `src/core/query_pipeline.py`
  - Add optional `conversation_repository: ConversationRepository | None` parameter
  - In `answer()` or prompt-building step:
    - If conversation_id is provided: load last N answers via `conversation_repo.get_answers()`
    - Format as "## Conversation History" section with Q/A pairs
    - Truncate to `max_conversation_history` (default 5)
    - Prepend to prompt before "## Context" section
  - When no conversation_id or no history: omit history section (current behavior)
  - **Verify**: Prompt includes history when conversation_id provided; prompt is unchanged when not provided

### 4.10 Create frontend API client

- [ ] 4.10.1 Create `frontend/lib/api.ts` (or modify if exists)
  - Add functions:
    - `listConversations(): Promise<Conversation[]>`
    - `getConversation(id: string): Promise<ConversationWithAnswers>`
    - `createConversation(title?: string): Promise<Conversation>`
    - `deleteConversation(id: string): Promise<void>`
  - **Verify**: Functions call correct API endpoints

### 4.11 Create ConversationSidebar component

- [ ] 4.11.1 Create `frontend/components/ConversationSidebar.tsx`
  - Fetch conversations on mount via `listConversations()`
  - Display list ordered by most recent first
  - Highlight active conversation
  - "New Conversation" button: call `createConversation()`, add to top of list
  - Click conversation: call `getConversation(id)`, load messages
  - Delete button: confirm, call `deleteConversation(id)`, remove from list
  - Show relative time (e.g., "2 hours ago")
  - **Verify**: Sidebar renders conversation list; create/switch/delete work

### 4.12 Integrate sidebar into frontend layout

- [ ] 4.12.1 Modify `frontend/app/layout.tsx`
  - Add sidebar to layout (left side on desktop)
  - Responsive: sidebar visible on desktop (>=1024px), hamburger menu on tablet/mobile
  - **Verify**: Layout renders sidebar on desktop; sidebar collapses on mobile

### 4.13 Modify frontend page for conversation-aware state

- [ ] 4.13.1 Modify `frontend/app/page.tsx`
  - Replace in-memory message state with API-driven state
  - On conversation select: load messages from `getConversation(id)`
  - On new message: send to `POST /v1/answers` with `conversation_id`
  - On page refresh: reload conversations and current conversation's messages from API
  - Empty state for new conversation: "Ask a question to get started"
  - **Verify**: Messages persist across page refresh; new messages appear immediately

### 4.14 Write unit tests for conversation repository

- [ ] 4.14.1 Create `tests/unit/test_conversation_repository.py`
  - Test: `create()` persists conversation and returns model
  - Test: `get_by_id()` returns conversation or None
  - Test: `list()` returns conversations ordered by updated_at DESC
  - Test: `delete()` removes conversation (mock cascade)
  - Test: `get_answers()` returns answers ordered by created_at ASC
  - Test: parameterized queries prevent SQL injection
  - **Verify**: `pytest tests/unit/test_conversation_repository.py -v` passes

### 4.15 Write unit tests for conversation prompt

- [ ] 4.15.1 Create `tests/unit/test_conversation_prompt.py`
  - Test: prompt includes history section with Q/A pairs when conversation_id provided
  - Test: history is truncated to max_conversation_history
  - Test: no history section when conversation_id is None
  - Test: no history section when conversation has no prior answers
  - Test: history section appears before context section
  - **Verify**: `pytest tests/unit/test_conversation_prompt.py -v` passes

### 4.16 Write integration tests for conversation repository

- [ ] 4.16.1 Create `tests/integration/test_conversation_repository.py`
  - Use testcontainers PostgreSQL
  - Test: migration applies cleanly
  - Test: CRUD operations work with real database
  - Test: cascade delete removes linked answers
  - Test: existing answers without conversation_id remain valid
  - **Verify**: `pytest tests/integration/test_conversation_repository.py -v` passes with PostgreSQL running

### 4.17 Write integration tests for conversation API

- [ ] 4.17.1 Create `tests/integration/test_conversation_api.py`
  - Use testcontainers PostgreSQL + FastAPI TestClient
  - Test: POST /v1/conversations returns 201
  - Test: GET /v1/conversations returns 200 with list
  - Test: GET /v1/conversations/{id} returns 200 with answers
  - Test: GET /v1/conversations/{fake-id} returns 404
  - Test: DELETE /v1/conversations/{id} returns 204
  - Test: POST /v1/answers with conversation_id links answer
  - Test: POST /v1/answers without conversation_id works (backward compatible)
  - **Verify**: `pytest tests/integration/test_conversation_api.py -v` passes

### 4.18 Update .env.example

- [ ] 4.18.1 Modify `.env.example`
  - Add: `MAX_CONVERSATION_HISTORY=5`
  - **Verify**: File contains new variable

## Phase 5: Evaluation Framework

### 5.1 Create EvaluationMetric port

- [ ] 5.1.1 Create `src/ports/evaluation.py`
  - Define `EvaluationMetric` Protocol with:
    - `name: str` property
    - `compute(question: str, answer: str, contexts: list[str], ground_truth: str | None) -> float | None`
  - Docstring: "Computes a single evaluation metric for a RAG sample"
  - **Verify**: `python -c "from src.ports.evaluation import EvaluationMetric"` succeeds

### 5.2 Create evaluation package structure

- [ ] 5.2.1 Create `src/evaluation/__init__.py`
  - Empty init file
  - **Verify**: `python -c "import src.evaluation"` succeeds

### 5.3 Create RAGAS metrics adapter

- [ ] 5.3.1 Create `src/evaluation/ragas_adapter.py`
  - Wrap each RAGAS metric as a separate `EvaluationMetric` implementation:
    - `RagasFaithfulness`
    - `RagasAnswerRelevancy`
    - `RagasContextPrecision`
    - `RagasContextRecall`
  - Configure RAGAS to use local Ollama as LLM judge
  - Handle missing inputs: return `None` or raise clear error
  - **Verify**: Each metric computes a score for a sample

### 5.4 Create custom metrics

- [ ] 5.4.1 Create `src/evaluation/custom_metrics.py`
  - Implement:
    - `CitationPrecision`: fraction of citations referencing valid chunks
    - `CitationCompleteness`: fraction of claims with supporting citations
    - `RetrievalHitRate`: binary (1.0 if at least one gold context in top-k, else 0.0)
  - **Verify**: Unit tests with known inputs produce expected scores

### 5.5 Create gold dataset loader

- [ ] 5.5.1 Create `src/evaluation/dataset.py`
  - Function `load_gold_dataset(path: str) -> list[EvalSample]`
  - Validate each sample has: `question`, `ground_truth`, `contexts`
  - Raise clear error if sample is invalid (missing field)
  - Define `EvalSample` dataclass: question, ground_truth, contexts, metadata (optional)
  - **Verify**: Valid dataset loads; invalid sample raises error

### 5.6 Create evaluation runner

- [ ] 5.6.1 Create `src/evaluation/runner.py`
  - Class `EvaluationRunner`
  - Constructor accepts: pipeline, metrics list, dataset
  - `run()`: iterate samples sequentially; for each sample: run pipeline, compute metrics, record scores
  - Log progress: "Evaluating sample N/M"
  - Handle metric computation failure: record `null` for that metric, continue
  - Return aggregated results: per-metric mean, std, min, max, count; per-sample scores
  - **Verify**: Runner processes all samples and produces aggregated report

### 5.7 Create report generator

- [ ] 5.7.1 Create `src/evaluation/report.py`
  - Function `generate_report(results: EvalResults, dataset_path: str, output_path: str)`
  - JSON structure:
    ```json
    {
      "timestamp": "ISO 8601",
      "dataset": "path/to/gold_set.json",
      "samples": 20,
      "metrics": {
        "faithfulness": {"mean": 0.85, "std": 0.1, "min": 0.6, "max": 1.0, "count": 20},
        ...
      },
      "per_sample": [
        {"question": "...", "metric_scores": {"faithfulness": 0.9, ...}},
        ...
      ]
    }
    ```
  - Write to file (default: `data/eval/reports/report_YYYYMMDD_HHMMSS.json`)
  - **Verify**: Report is valid JSON with correct structure

### 5.8 Create CLI entry point

- [ ] 5.8.1 Create `src/evaluation/__main__.py`
  - CLI arguments:
    - `--dataset` (required): path to gold JSON
    - `--metrics` (optional, default "all"): comma-separated list or "all"
    - `--output` (optional): output file path
    - `--pipeline-config` (optional): path to config override
  - Load dataset, instantiate metrics, run evaluation, generate report
  - Handle missing dataset file: print error, exit non-zero
  - **Verify**: `python -m src.evaluation --dataset data/eval/gold_set.json` runs successfully

### 5.9 Create gold dataset

- [ ] 5.9.1 Create `data/eval/gold_set.json`
  - JSON array of 20+ samples
  - Each sample: `{"question": "...", "ground_truth": "...", "contexts": ["...", ...], "metadata": {"source": "...", "difficulty": "easy|medium|hard", "category": "factual|comparative|procedural"}}`
  - Stratify by: source document (3+ sources), difficulty (easy/medium/hard), query type (factual/comparative/procedural)
  - **Verify**: Dataset loads successfully; contains 20+ samples with required fields

### 5.10 Create reports directory

- [ ] 5.10.1 Create `data/eval/reports/.gitkeep`
  - Empty file to ensure directory exists
  - **Verify**: Directory exists

### 5.11 Add evaluation dependencies

- [ ] 5.11.1 Modify `pyproject.toml`
  - Add `[project.optional-dependencies]` section:
    ```toml
    [project.optional-dependencies]
    eval = [
        "ragas>=0.2.0",
        "datasets>=2.14.0",
    ]
    ```
  - **Verify**: `pip install -e ".[eval]"` succeeds

### 5.12 Write unit tests for custom metrics

- [ ] 5.12.1 Create `tests/unit/test_custom_metrics.py`
  - Test: CitationPrecision with all valid citations returns 1.0
  - Test: CitationPrecision with some invalid citations returns fraction
  - Test: CitationCompleteness with 3/4 claims cited returns 0.75
  - Test: RetrievalHitRate with gold context in top-k returns 1.0
  - Test: RetrievalHitRate with no gold context returns 0.0
  - Test: edge cases (empty citations, no contexts)
  - **Verify**: `pytest tests/unit/test_custom_metrics.py -v` passes

### 5.13 Write unit tests for dataset loader

- [ ] 5.13.1 Create `tests/unit/test_eval_dataset.py`
  - Test: valid dataset with 25 samples loads successfully
  - Test: invalid sample (missing ground_truth) raises validation error
  - Test: error message indicates which sample is invalid and what field is missing
  - **Verify**: `pytest tests/unit/test_eval_dataset.py -v` passes

### 5.14 Write unit tests for evaluation runner

- [ ] 5.14.1 Create `tests/unit/test_eval_runner.py`
  - Test: runner processes all samples and computes all metrics
  - Test: metric failure records `null` for that metric, continues
  - Test: progress is logged ("Evaluating sample N/M")
  - Test: aggregated report contains mean, std, min, max, count per metric
  - **Verify**: `pytest tests/unit/test_eval_runner.py -v` passes

### 5.15 Write integration tests for evaluation pipeline

- [ ] 5.15.1 Create `tests/integration/test_eval_pipeline.py`
  - Use real pipeline with testcontainers PostgreSQL
  - Test: full evaluation run produces JSON report
  - Test: report is valid JSON with correct structure
  - Test: metrics are computed for all samples
  - **Verify**: `pytest tests/integration/test_eval_pipeline.py -v` passes

### 5.16 Update .env.example

- [ ] 5.16.1 Modify `.env.example`
  - Add: `EVAL_DATASET_PATH=data/eval/gold_set.json`, `EVAL_METRICS=all`, `EVAL_REPORT_DIR=data/eval/reports`
  - **Verify**: File contains new variables

## Phase 6: Final Verification

### 6.1 Run all unit tests

- [ ] 6.1.1 Execute: `pytest tests/unit/ -v`
  - **Verify**: All unit tests pass

### 6.2 Run all integration tests

- [ ] 6.2.1 Execute: `pytest tests/integration/ -v`
  - **Verify**: All integration tests pass with Docker stack running

### 6.3 Verify all features are toggleable

- [ ] 6.3.1 Test each feature flag:
  - Set `RERANKER_ENABLED=false`, verify pipeline works without reranking
  - Set `QUERY_REWRITER_ENABLED=false`, verify pipeline works without rewriting
  - Set `CACHE_ENABLED=false`, verify pipeline works without caching
  - Omit `conversation_id` from requests, verify answers work without conversation
  - **Verify**: All features independently toggleable; all disabled = current MVP behavior

### 6.4 Verify no regression

- [ ] 6.4.1 Run existing test suite: `pytest tests/ -v`
  - **Verify**: No existing tests fail

### 6.5 Update documentation

- [ ] 6.5.1 Update `README.md` or create `docs/evaluation.md`
  - Document how to run evaluation: `python -m src.evaluation --dataset data/eval/gold_set.json`
  - Document how to add custom metrics
  - Document feature flags and their defaults
  - **Verify**: Documentation is clear and accurate
