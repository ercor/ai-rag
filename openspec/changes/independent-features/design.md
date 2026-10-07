# Design: Independent Features Implementation

## Technical Approach

This design implements five independent features that elevate the ai-rag platform from MVP to production-quality. Each feature follows the existing hexagonal architecture pattern: a new Protocol port in `src/ports/`, a concrete adapter in `src/adapters/`, configuration in `src/config.py`, DI wiring in `src/container.py`, and pipeline integration in `src/core/query_pipeline.py`.

The features are implemented sequentially as five independent work units. Each work unit is a complete vertical slice — port, adapter, config, DI, pipeline integration, tests — that can be reviewed and merged independently. All features are toggleable via config flags, so disabling all features reproduces the current MVP behavior exactly.

The existing pipeline flow is:
```
embed → BM25+vector (top-K) → RRF → abstain → prompt → generate → validate → persist
```

The final pipeline flow (all features enabled) becomes:
```
cache_check → [miss:] rewrite → [q1..qN] → embed_each → parallel_search → RRF_merge → rerank → abstain → prompt_with_history → generate → validate → persist → cache_store
```

## Architecture Decisions

### Decision: Reranker as optional pipeline step after RRF

**Choice**: Insert reranking between RRF fusion and abstention check. RRF produces up to `reranker_top_k_before` (20) candidates; reranker returns top `reranker_top_k_after` (5).

**Alternatives considered**:
- Reranking before RRF: rejected — RRF needs both channels' rankings; reranking individual channels loses cross-channel signal.
- Reranking as a separate endpoint: rejected — adds client complexity; pipeline integration is transparent.
- Using Ollama for reranking: rejected — cross-encoder models are purpose-built for relevance scoring; Ollama's generative models are slower and less accurate for pairwise comparison.

**Rationale**: This matches ADR-003 (cross-encoder reranking) and the ARCHITECTURE.md retrieval defaults: "Rerank the top 20-50 and pass approximately 5-12 passages to generation." The cross-encoder model (`ms-marco-MiniLM-L-6-v2`) is ~80MB, runs in <200ms on CPU for 20 candidates, and is the standard choice for production RAG reranking.

### Decision: Query rewriting uses existing Generator port

**Choice**: `LLMQueryRewriter` adapter reuses the existing `Generator` port (Ollama) with a structured prompt, rather than introducing a separate LLM client.

**Alternatives considered**:
- Dedicated lightweight rewriting model: rejected — adds operational complexity; Ollama already runs the generation model.
- HyDE (Hypothetical Document Embedding): rejected — out of scope per spec; multi-query expansion has better empirical results for ambiguous queries.
- Rule-based query expansion: rejected — cannot handle semantic rephrasing; LLM-based approach produces more diverse variants.

**Rationale**: The Generator port already abstracts Ollama. A structured prompt ("Generate N rephrasings of this query") is sufficient. On failure, the adapter falls back to returning only the original query — the pipeline degrades gracefully to single-query behavior.

### Decision: Redis cache with SHA-256 composite key

**Choice**: Cache key = `sha256(normalize(query) + ":" + filters_hash + ":" + index_version)`. Values are JSON-serialized answer + citations. TTL 1800s (30 min).

**Alternatives considered**:
- Semantic caching (embedding similarity): rejected — authorization-unsafe; different users may have different ACL scopes. Spec explicitly requires authorization-safe keys.
- Query-only key: rejected — different filters or index versions would return stale results.
- Memcached: rejected — no TTL-per-key granularity in the same way; Redis is more widely used and has better Python async support.

**Rationale**: SHA-256 ensures fixed-length keys, handles normalization deterministically, and includes all result-affecting parameters. The index version component ensures re-ingestion automatically invalidates stale cache entries. Graceful degradation (no-op on Redis failure) ensures the cache never blocks the pipeline.

### Decision: Conversations as a new table with nullable FK on answers

**Choice**: New `conversations` table; nullable `conversation_id` FK on `answers`. Additive migration, backward compatible.

**Alternatives considered**:
- Separate `conversation_messages` table: rejected — answers already store questions and responses; adding a FK is simpler and avoids data duplication.
- Storing conversation history in Redis: rejected — conversations are persistent data that must survive restarts; PostgreSQL is the canonical store.
- Non-relational (JSON column on answers): rejected — makes conversation-level queries (list, delete cascade) harder and slower.

**Rationale**: The nullable FK approach means existing answers (without `conversation_id`) remain valid. ON DELETE CASCADE handles conversation deletion cleanly. The `answers(conversation_id, created_at)` index supports efficient history retrieval.

### Decision: Evaluation framework isolated behind [eval] extras

**Choice**: RAGAS and evaluation dependencies are in `pyproject.toml` `[eval]` extras group. Evaluation code lives in `src/evaluation/` and is never imported by the core application at runtime.

**Alternatives considered**:
- Including RAGAS in core dependencies: rejected — RAGAS pulls in heavy ML dependencies (datasets, langchain) that bloat the production image.
- Separate evaluation microservice: rejected — over-engineering for a CLI-first tool; import isolation is sufficient.
- Using an external evaluation service (Ragas Hub): rejected — data leaves the environment; local Ollama as LLM judge is preferred.

**Rationale**: `pip install -e ".[eval]"` installs evaluation deps only when needed. The core Docker image stays lean. The CLI runner processes samples sequentially to avoid overloading the LLM judge.

### Decision: Frontend conversation sidebar with API-driven state

**Choice**: New `ConversationSidebar` React component that fetches conversations from `GET /v1/conversations`. Messages are loaded from the API when a conversation is selected, replacing in-memory-only state.

**Alternatives considered**:
- LocalStorage-based persistence: rejected — doesn't survive device changes; API-driven is the source of truth.
- WebSocket for real-time updates: rejected — over-engineering; polling on mount and after mutations is sufficient.
- Zustand/Redux for state management: rejected — current app uses React useState; adding a state library for one feature is not justified. Conversation state can be managed with useState + useEffect.

**Rationale**: The existing frontend uses React useState with no external state library. Adding a few hooks for conversation management is consistent with the current pattern. The sidebar fetches on mount, and messages are loaded per-conversation from the API.

## Data Flow

### Feature 1: Cross-Encoder Reranking

```
QueryPipeline.retrieve()
    │
    ├── embed(query) → query_embedding
    │
    ├── parallel_search(query, query_embedding, top_k=20)
    │       ├── bm25_search(query, 20) → bm25_results
    │       └── vector_search(embedding, 20) → vector_results
    │
    ├── rrf_fusion(bm25_results, vector_results, top_k=20)
    │       → fused (up to 20 RetrievedChunks)
    │
    ├── [NEW] reranker.rerank(query, fused, top_k_after=5)
    │       → reranked (up to 5 RetrievedChunks)
    │       [on timeout: log warning, use fused as-is]
    │
    └── should_abstain(reranked, threshold)
```

### Feature 2: Query Rewriting

```
QueryPipeline.retrieve()
    │
    ├── [NEW] query_rewriter.rewrite(question)
    │       → [q1, q2, q3]  (original + 2 variants)
    │       [on failure: [question] — fallback to original]
    │
    ├── asyncio.gather(*[search_variant(q) for q in variants])
    │       → [fused_1, fused_2, fused_3]  (per-variant RRF results)
    │
    ├── [NEW] rrf_fusion_multi(variant_results)
    │       → merged (cross-variant RRF, deduplicated)
    │
    ├── reranker.rerank(question, merged)  [if enabled]
    │
    └── should_abstain(...)
```

### Feature 3: Redis Caching

```
POST /v1/answers
    │
    ├── [NEW] cache.get(cache_key)
    │       ├── HIT → return cached answer immediately
    │       └── MISS → continue pipeline
    │
    ├── [full pipeline: rewrite → search → rerank → generate]
    │
    └── [NEW] cache.set(cache_key, result, ttl=1800)
            [on failure: silently no-op]
```

### Feature 4: Conversation History

```
POST /v1/answers (with conversation_id)
    │
    ├── [NEW] conversation_repo.get_answers(conversation_id)
    │       → last N Q&A pairs
    │
    ├── build_prompt(question, chunks, history=pairs)
    │       → prompt with "## Conversation History" section
    │
    ├── generate → validate → persist (with conversation_id)
    │
    └── [NEW] conversation.updated_at = now()
```

### Feature 5: Evaluation Framework

```
python -m src.evaluation --dataset data/eval/gold_set.json
    │
    ├── load gold dataset → validate samples
    │
    ├── for each sample:
    │       ├── run pipeline (retrieve + generate)
    │       ├── compute each metric
    │       └── record per-sample scores
    │
    └── aggregate → write JSON report
```

## File Changes

### Feature 1: Cross-Encoder Reranking

| File | Action | Description |
|------|--------|-------------|
| `src/ports/reranker.py` | Create | `Reranker` Protocol with `rerank(query, candidates, top_k) -> list[RetrievedChunk]` |
| `src/adapters/cross_encoder_reranker.py` | Create | CrossEncoder adapter using sentence-transformers, lazy model loading |
| `src/core/query_pipeline.py` | Modify | Add optional reranker param; insert rerank step after RRF, before abstention |
| `src/core/retrieval.py` | Modify | `rrf_fusion` accepts configurable `top_k` (currently hardcoded default 5); pipeline passes `reranker_top_k_before` when reranking |
| `src/config.py` | Modify | Add `reranker_enabled`, `reranker_model`, `reranker_top_k_before`, `reranker_top_k_after`, `reranker_timeout_seconds` |
| `src/container.py` | Modify | Add `get_reranker()` factory |
| `src/api/answers.py` | Modify | Wire reranker into `_get_pipeline()` |
| `pyproject.toml` | Modify | Add `sentence-transformers>=2.7.0` to dependencies |
| `tests/unit/test_reranker.py` | Create | Unit tests for CrossEncoderReranker (mocked model) |
| `tests/unit/test_pipeline_reranking.py` | Create | Unit tests for pipeline reranking integration |

### Feature 2: Query Rewriting

| File | Action | Description |
|------|--------|-------------|
| `src/ports/query_rewriter.py` | Create | `QueryRewriter` Protocol with `rewrite(query) -> list[str]` |
| `src/adapters/llm_query_rewriter.py` | Create | LLM-based adapter using Generator port, structured prompt, output parsing |
| `src/core/query_pipeline.py` | Modify | Add optional query_rewriter param; multi-query search + cross-variant RRF merge |
| `src/core/retrieval.py` | Modify | Add `rrf_fusion_multi()` for cross-variant merge |
| `src/config.py` | Modify | Add `query_rewriter_enabled`, `query_rewriter_num_variants` |
| `src/container.py` | Modify | Add `get_query_rewriter()` factory |
| `src/api/answers.py` | Modify | Wire query_rewriter into `_get_pipeline()` |
| `tests/unit/test_query_rewriter.py` | Create | Unit tests for LLMQueryRewriter (mocked Generator) |
| `tests/unit/test_multi_query_rrf.py` | Create | Unit tests for cross-variant RRF merge |
| `tests/unit/test_pipeline_rewriting.py` | Create | Unit tests for pipeline multi-query integration |

### Feature 3: Redis Caching

| File | Action | Description |
|------|--------|-------------|
| `src/ports/cache.py` | Create | `Cache` Protocol with `get()`, `set()`, `invalidate()` |
| `src/adapters/redis_cache.py` | Create | Redis adapter using redis.asyncio, JSON serialization, graceful degradation |
| `src/adapters/noop_cache.py` | Create | No-op cache implementation (always miss) for disabled/unavailable state |
| `src/core/query_pipeline.py` | Modify | Add optional cache param; cache check before retrieval, cache store after generation |
| `src/core/cache_key.py` | Create | Cache key computation: normalize + SHA-256 |
| `src/config.py` | Modify | Add `cache_enabled`, `redis_url`, `cache_ttl_seconds` |
| `src/container.py` | Modify | Add `get_cache()` factory |
| `src/api/answers.py` | Modify | Wire cache into `_get_pipeline()`; handle cache hit fast-path |
| `src/api/health.py` | Modify | Add Redis health check to `/ready` endpoint |
| `docker-compose.yml` | Modify | Add Redis service with health check |
| `pyproject.toml` | Modify | Add `redis[hiredis]>=5.0.0` to dependencies |
| `tests/unit/test_cache_key.py` | Create | Unit tests for cache key normalization and hashing |
| `tests/unit/test_redis_cache.py` | Create | Unit tests for RedisCache (mocked redis) |
| `tests/unit/test_noop_cache.py` | Create | Unit tests for NoopCache |
| `tests/integration/test_redis_cache.py` | Create | Integration tests with testcontainers Redis |

### Feature 4: Conversation History

| File | Action | Description |
|------|--------|-------------|
| `migrations/004_conversations.sql` | Create | Create `conversations` table; add nullable `conversation_id` FK to `answers` |
| `src/ports/conversation_repository.py` | Create | `ConversationRepository` Protocol with CRUD + get_answers |
| `src/adapters/pg_conversation_repository.py` | Create | PostgreSQL adapter using asyncpg |
| `src/api/conversations.py` | Create | FastAPI router: POST/GET/GET-by-id/DELETE endpoints |
| `src/api/answers.py` | Modify | Accept optional `conversation_id` in request; load history; pass to prompt builder |
| `src/core/query_pipeline.py` | Modify | `build_prompt()` accepts optional `history` parameter; `retrieve()` accepts optional `conversation_id` |
| `src/config.py` | Modify | Add `max_conversation_history` |
| `src/container.py` | Modify | Add `get_conversation_repository()` factory |
| `src/main.py` | Modify | Include conversations router |
| `frontend/lib/api.ts` | Create | Conversation API client functions |
| `frontend/components/ConversationSidebar.tsx` | Create | Sidebar component with list, create, switch, delete |
| `frontend/app/page.tsx` | Modify | Integrate sidebar; conversation-aware message state; API-driven persistence |
| `frontend/app/layout.tsx` | Modify | Accommodate sidebar layout (three-column on desktop) |
| `tests/unit/test_conversation_prompt.py` | Create | Unit tests for history formatting in prompt builder |
| `tests/unit/test_conversation_repository.py` | Create | Unit tests for PgConversationRepository (mocked pool) |
| `tests/integration/test_conversation_repository.py` | Create | Integration tests with testcontainers PostgreSQL |
| `tests/integration/test_conversation_api.py` | Create | Integration tests for conversation CRUD endpoints |

### Feature 5: Evaluation Framework

| File | Action | Description |
|------|--------|-------------|
| `src/evaluation/__init__.py` | Create | Package init |
| `src/evaluation/__main__.py` | Create | CLI entry point (`python -m src.evaluation`) |
| `src/ports/evaluation.py` | Create | `EvaluationMetric` Protocol with `compute()` |
| `src/evaluation/ragas_adapter.py` | Create | RAGAS metrics wrapper (Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall) |
| `src/evaluation/custom_metrics.py` | Create | CitationPrecision, CitationCompleteness, RetrievalHitRate |
| `src/evaluation/runner.py` | Create | EvaluationRunner: iterate samples, compute metrics, aggregate |
| `src/evaluation/dataset.py` | Create | Gold dataset loader and validator |
| `src/evaluation/report.py` | Create | JSON report generator |
| `data/eval/gold_set.json` | Create | Initial gold dataset (20+ samples) |
| `data/eval/reports/.gitkeep` | Create | Reports directory |
| `pyproject.toml` | Modify | Add `[eval]` extras group with ragas, datasets |
| `tests/unit/test_custom_metrics.py` | Create | Unit tests for citation precision, completeness, hit rate |
| `tests/unit/test_eval_dataset.py` | Create | Unit tests for gold dataset validation |
| `tests/unit/test_eval_runner.py` | Create | Unit tests for evaluation runner (mocked pipeline) |

### Cross-cutting

| File | Action | Description |
|------|--------|-------------|
| `.env.example` | Modify | Add all new config variables with defaults |
| `docker-compose.yml` | Modify | Add Redis service; add new env vars to backend |
| `Dockerfile.backend` | Modify | Ensure sentence-transformers model cache directory is writable |
| `requirements.txt` | Modify | Add new dependencies (if still used alongside pyproject.toml) |

## Interfaces / Contracts

### Port: Reranker

```python
# src/ports/reranker.py
from typing import Protocol
from src.core.retrieval import RetrievedChunk

class Reranker(Protocol):
    """Re-scores retrieval candidates using a cross-encoder model.
    
    Implementations: CrossEncoder (sentence-transformers), API-based, etc.
    """
    
    async def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        """Re-score and re-order candidates by cross-encoder relevance.
        
        Returns at most top_k candidates sorted by descending relevance score.
        The returned RetrievedChunks have their `score` field replaced with
        the cross-encoder score.
        """
        ...
```

### Port: QueryRewriter

```python
# src/ports/query_rewriter.py
from typing import Protocol

class QueryRewriter(Protocol):
    """Generates query variants for multi-query retrieval.
    
    Implementations: LLM-based, rule-based, etc.
    """
    
    async def rewrite(self, query: str) -> list[str]:
        """Return a list of query variants including the original.
        
        Minimum return length: 1 (the original query).
        Each variant is a standalone query string.
        """
        ...
```

### Port: Cache

```python
# src/ports/cache.py
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
```

### Port: ConversationRepository

```python
# src/ports/conversation_repository.py
from typing import Protocol
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Conversation:
    id: str
    title: str
    created_at: datetime
    updated_at: datetime

@dataclass
class ConversationAnswer:
    id: str
    question: str
    answer: str | None
    status: str
    citations: list
    created_at: datetime

class ConversationRepository(Protocol):
    """Persists conversations and their linked answers.
    
    Implementations: PostgreSQL (asyncpg), SQLite, etc.
    """
    
    async def create(self, title: str | None = None) -> Conversation:
        """Create a new conversation. Auto-generates title if None."""
        ...
    
    async def get_by_id(self, conversation_id: str) -> Conversation | None:
        """Get conversation by ID, or None if not found."""
        ...
    
    async def list(self, limit: int = 20, offset: int = 0) -> list[Conversation]:
        """List conversations ordered by updated_at descending."""
        ...
    
    async def delete(self, conversation_id: str) -> None:
        """Delete conversation and cascade to linked answers."""
        ...
    
    async def get_answers(self, conversation_id: str) -> list[ConversationAnswer]:
        """Get all answers for a conversation, ordered by created_at ascending."""
        ...
    
    async def update_title(self, conversation_id: str, title: str) -> None:
        """Update the conversation title."""
        ...
    
    async def touch(self, conversation_id: str) -> None:
        """Update the conversation's updated_at timestamp."""
        ...
```

### Port: EvaluationMetric

```python
# src/ports/evaluation.py
from typing import Protocol

class EvaluationMetric(Protocol):
    """Computes a single evaluation metric for a RAG sample.
    
    Implementations: RAGAS metrics, custom metrics, etc.
    """
    
    @property
    def name(self) -> str:
        """Metric identifier (e.g. 'faithfulness', 'citation_precision')."""
        ...
    
    async def compute(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str | None = None,
    ) -> float | None:
        """Compute metric score in [0.0, 1.0]. Returns None on failure."""
        ...
```

### API Contracts

#### Conversation CRUD

```http
POST /v1/conversations
Content-Type: application/json

{"title": "optional title or null"}

Response 201:
{
    "id": "uuid",
    "title": "auto or provided",
    "created_at": "2026-09-28T12:00:00Z",
    "updated_at": "2026-09-28T12:00:00Z"
}
```

```http
GET /v1/conversations?limit=20&offset=0

Response 200:
{
    "conversations": [
        {"id": "...", "title": "...", "created_at": "...", "updated_at": "..."}
    ],
    "total": 42
}
```

```http
GET /v1/conversations/{id}

Response 200:
{
    "id": "...",
    "title": "...",
    "created_at": "...",
    "updated_at": "...",
    "answers": [
        {
            "id": "...",
            "question": "...",
            "answer": "...",
            "status": "answered",
            "citations": [...],
            "created_at": "..."
        }
    ]
}

Response 404: {"detail": "Conversation not found"}
```

```http
DELETE /v1/conversations/{id}

Response 204: No Content
```

#### Modified: Create Answer (with conversation_id)

```http
POST /v1/answers
Content-Type: application/json

{
    "question": "What is the travel policy?",
    "conversation_id": "optional-uuid-or-null"
}
```

#### Evaluation CLI

```bash
python -m src.evaluation \
    --dataset data/eval/gold_set.json \
    --metrics all \
    --output data/eval/reports/report_20260928_120000.json
```

### Data Models

#### New Table: conversations

```sql
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL DEFAULT 'New Conversation',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_conversations_updated ON conversations (updated_at DESC);
```

#### Migration: Add conversation_id to answers

```sql
ALTER TABLE answers ADD COLUMN conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE;
CREATE INDEX idx_answers_conversation ON answers (conversation_id, created_at);
```

### Configuration

All new settings in `src/config.py`:

```python
# Cross-Encoder Reranking
reranker_enabled: bool = True
reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
reranker_top_k_before: int = 20
reranker_top_k_after: int = 5
reranker_timeout_seconds: float = 5.0

# Query Rewriting
query_rewriter_enabled: bool = False
query_rewriter_num_variants: int = 3

# Redis Caching
cache_enabled: bool = True
redis_url: str = "redis://localhost:6379"
cache_ttl_seconds: int = 1800

# Conversation History
max_conversation_history: int = 5

# Evaluation (CLI-only, not needed in server config)
eval_dataset_path: str = "data/eval/gold_set.json"
eval_metrics: str = "all"
eval_report_dir: str = "data/eval/reports"
```

### Dependencies

#### Python packages added to `pyproject.toml`:

```toml
[project.dependencies]  # add to existing
"sentence-transformers>=2.7.0",   # cross-encoder reranking
"redis[hiredis]>=5.0.0",          # Redis caching

[project.optional-dependencies]
eval = [                          # new extras group
    "ragas>=0.2.0",
    "datasets>=2.14.0",
]
```

#### Infrastructure:

- Redis 7 Alpine container in `docker-compose.yml`
- sentence-transformers model cache in Docker build (~80MB for MiniLM-L-6-v2)

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| **Unit** | Reranker port contract, CrossEncoder adapter (mocked model), pipeline reranking integration | pytest with mocked sentence-transformers; verify score ordering, top_k truncation, timeout fallback |
| **Unit** | QueryRewriter port contract, LLM adapter (mocked Generator), output parsing | pytest with mocked Generator; verify variant count, fallback on error, malformed output handling |
| **Unit** | Cross-variant RRF merge, multi-query pipeline | pytest; verify deduplication, score accumulation, single-variant equivalence |
| **Unit** | Cache key normalization, SHA-256 determinism | pytest; verify whitespace/case normalization, filter hash differentiation, index version sensitivity |
| **Unit** | RedisCache (mocked redis), NoopCache | pytest; verify get/set round-trip, graceful degradation on connection error, JSON serialization |
| **Unit** | Prompt builder with conversation history | pytest; verify history formatting, truncation to max, no-history equivalence |
| **Unit** | Custom evaluation metrics (citation precision, completeness, hit rate) | pytest; verify known-input scores, edge cases (empty citations, all-valid, none-valid) |
| **Unit** | Gold dataset validation | pytest; verify valid dataset loads, invalid sample rejected with clear error |
| **Integration** | PgConversationRepository CRUD + cascade delete | testcontainers PostgreSQL; verify migration applies, CRUD works, cascade deletes |
| **Integration** | Conversation API endpoints | testcontainers PostgreSQL + FastAPI TestClient; verify 201/200/204/404 responses |
| **Integration** | RedisCache with real Redis | testcontainers Redis; verify get/set/invalidate, TTL expiry |
| **Integration** | Full pipeline with reranking | testcontainers PostgreSQL + mocked cross-encoder; verify end-to-end flow |
| **E2E** | Full stack with all features | docker compose stack; verify conversation sidebar, cached responses, reranked results |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary.

## Migration / Rollout

### Database Migration

Migration `004_conversations.sql` is **additive and backward compatible**:
- Creates new `conversations` table (no existing data affected)
- Adds nullable `conversation_id` column to `answers` (existing rows get NULL)
- Creates indexes for efficient querying

No data transformation needed. Existing answers without `conversation_id` continue to work.

### Feature Flag Rollout

Each feature is independently toggleable. Recommended rollout order:

1. **Cross-Encoder Reranking** (enabled by default) — immediate quality improvement, no behavioral change for users
2. **Redis Caching** (enabled by default) — latency improvement, transparent to users
3. **Conversation History** (always available, used when `conversation_id` provided) — additive API, no breaking changes
4. **Query Rewriting** (disabled by default) — opt-in; enable after measuring latency impact
5. **Evaluation Framework** (CLI-only, no server impact) — zero risk to production

### Rollback

Each feature can be disabled via environment variable:
- `RERANKER_ENABLED=false` → pipeline skips reranking, behaves as before
- `QUERY_REWRITER_ENABLED=false` → pipeline uses single query (default)
- `CACHE_ENABLED=false` → pipeline skips cache, every query is a cache miss
- Conversation history: remove `conversation_id` from requests → no history in prompts
- Evaluation: CLI-only, no server rollback needed

### Docker Compose Changes

Redis service added as optional dependency. Backend `depends_on` is NOT modified to require Redis — graceful degradation means the backend starts even if Redis is down. Redis is added as a service but the backend health check does not depend on it.

## Open Questions

- [ ] Should the cross-encoder model be pre-downloaded during Docker build, or lazy-loaded on first request? (Design recommends lazy-load with Docker build pre-warm as optimization.)
- [ ] Should conversation deletion be soft-delete (mark as deleted) or hard-delete (ON DELETE CASCADE)? (Design recommends hard-delete per spec; soft-delete could be added later.)
- [ ] Should the evaluation gold dataset be versioned in git or stored externally? (Design recommends git-versioned at `data/eval/gold_set.json` for reproducibility.)
