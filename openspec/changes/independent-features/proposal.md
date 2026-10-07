# Proposal: Independent Features Implementation

## Intent

Implement five independent features that elevate the RAG platform from MVP to production-quality: cross-encoder reranking, query rewriting, Redis caching, conversation history, and an evaluation framework. Each feature is self-contained, follows hexagonal architecture (new port + adapter), and delivers measurable improvement to retrieval quality, latency, or user experience.

## Scope

### In Scope

1. **Cross-Encoder Reranking** — `Reranker` port + `CrossEncoderReranker` adapter (sentence-transformers). Pipeline: fetch top-20 → RRF → rerank top-5 → generate. Implements ADR-003.
2. **Query Rewriting** — `QueryRewriter` port + `LLMQueryRewriter` adapter (multi-query expansion). Generate 2-3 variants per query, search each, merge via RRF. Uses existing Ollama.
3. **Redis Caching** — `Cache` port + `RedisCache` adapter. Cache full answers (query + filters + index version → answer), TTL 30min. Graceful degradation if Redis unavailable.
4. **Conversation History** — `conversations` table + `conversation_id` FK on `answers`. Pipeline accepts last N messages as context. Frontend sidebar with conversation list.
5. **Evaluation Framework** — `EvaluationMetric` port + RAGAS adapter. CLI-first runner with gold set (JSON). Metrics: faithfulness, answer relevancy, context precision, context recall, citation precision.

### Out of Scope

- Authentication, authorization, multi-tenancy (blocked features — depend on identity provider)
- Observability / OpenTelemetry tracing
- Admin UI / operational dashboards
- RBAC/ABAC enforcement in retrieval
- Blue/green index management
- Prompt injection detection
- Multi-hop or agentic retrieval
- Model fine-tuning

## Capabilities

> Contract between proposal and specs phases. Each new capability gets a full spec at `openspec/changes/independent-features/specs/<name>/spec.md`.

### New Capabilities

- `cross-encoder-reranking`: Reranker port, CrossEncoder adapter, pipeline integration after RRF fusion, configurable candidate counts and model selection
- `query-rewriting`: QueryRewriter port, LLM-based multi-query expansion adapter, per-query variant generation and RRF merge of multi-search results
- `answer-caching`: Cache port, Redis adapter, cache-key composition (normalized query + filters + index version), TTL-based expiry, graceful degradation
- `conversation-history`: Conversation model and repository, conversation CRUD API, multi-turn prompt assembly with bounded context window, frontend conversation sidebar
- `evaluation-framework`: EvaluationMetric port, RAGAS adapter, CLI runner, gold dataset management, metric aggregation and reporting

### Modified Capabilities

- `hybrid-retrieval`: Pipeline gains reranking step after RRF (top-20 candidates → top-5 after rerank) and multi-query search merge when query rewriting is enabled
- `grounded-generation`: Prompt builder accepts optional conversation history; system prompt includes prior Q&A turns before current question
- `chat-ui`: Frontend gains conversation sidebar (list, create, switch, delete conversations); messages persist across page refreshes via conversation API

## Approach

### Sequential Implementation (5 Work Units)

Each feature is implemented as a complete work unit — port, adapter, pipeline integration, config, DI wiring, tests — before moving to the next. This minimizes merge conflicts and allows each feature to be verified independently.

**Work Unit 1: Cross-Encoder Reranking (8-12h)**
- New `src/ports/reranker.py` with `Reranker` Protocol
- New `src/adapters/cross_encoder_reranker.py` using `sentence-transformers` CrossEncoder (`ms-marco-MiniLM-L-6-v2`)
- Modify `src/core/query_pipeline.py`: after RRF fusion, call reranker on top-20 candidates, keep top-5
- Add config: `reranker_enabled`, `reranker_model`, `reranker_top_k_before` (20), `reranker_top_k_after` (5)
- Wire in `src/container.py`: `get_reranker()` factory
- Pipeline: `embed → BM25+vector (top-20) → RRF → RERANK (top-5) → abstain → prompt → generate`

**Work Unit 2: Query Rewriting (12-16h)**
- New `src/ports/query_rewriter.py` with `QueryRewriter` Protocol
- New `src/adapters/llm_query_rewriter.py` using existing `Generator` port (Ollama)
- Modify `src/core/query_pipeline.py`: before embedding, rewrite query into N variants; search each; merge all results via RRF
- Add config: `query_rewriter_enabled` (false), `query_rewriter_num_variants` (3)
- Pipeline: `query → REWRITE → [q1,q2,q3] → embed each → parallel search → RRF merge → rerank → generate`

**Work Unit 3: Redis Caching (8-12h)**
- New `src/ports/cache.py` with `Cache` Protocol (`get`, `set`, `invalidate`)
- New `src/adapters/redis_cache.py` using `redis.asyncio`
- Modify `src/core/query_pipeline.py`: check cache before retrieval, store result after generation
- Cache key: `sha256(normalize(query) + ":" + filters_hash + ":" + index_version)`
- Add Redis to `docker-compose.yml`
- Add config: `cache_enabled`, `redis_url`, `cache_ttl_seconds` (1800)
- Graceful degradation: if Redis unavailable, pipeline continues without caching

**Work Unit 4: Conversation History (12-16h)**
- New migration: `conversations` table (id, title, created_at, updated_at); add `conversation_id` FK to `answers`
- New `src/ports/conversation_repository.py` port
- New `src/adapters/pg_conversation_repository.py` adapter
- New `src/api/conversations.py` router: CRUD endpoints
- Modify `src/core/query_pipeline.py`: accept `conversation_id`, load last N messages, include in prompt
- Modify `build_prompt()` to prepend conversation history
- Frontend: `ConversationSidebar` component, conversation persistence, "New conversation" button
- Add config: `max_conversation_history` (5)

**Work Unit 5: Evaluation Framework (20-28h)**
- New `src/ports/evaluation.py` with `EvaluationMetric` Protocol
- New `src/adapters/ragas_metrics.py` adapter (faithfulness, relevancy, precision, recall)
- New `src/core/evaluation/` module: runner, dataset loader, report aggregator
- Custom metrics: citation precision, citation completeness, retrieval hit rate
- CLI: `python -m src.evaluation --dataset data/eval/gold_set.json --metrics all`
- Gold dataset: 20-30 samples in JSON format (question, ground_truth, contexts, metadata)
- Output: JSON report with mean/std per metric
- Dependencies isolated in `[eval]` extras group

### Dependency Graph

```
Reranking ──────────────────────┐
                                 ├──→ Evaluation Framework
Query Rewriting ────────────────┘    (measures all above)

Redis Caching ──→ Conversation History
```

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/ports/reranker.py` | New | Reranker Protocol definition |
| `src/ports/query_rewriter.py` | New | QueryRewriter Protocol definition |
| `src/ports/cache.py` | New | Cache Protocol definition |
| `src/ports/conversation_repository.py` | New | ConversationRepository Protocol definition |
| `src/ports/evaluation.py` | New | EvaluationMetric Protocol definition |
| `src/adapters/cross_encoder_reranker.py` | New | sentence-transformers CrossEncoder adapter |
| `src/adapters/llm_query_rewriter.py` | New | LLM-based multi-query expansion adapter |
| `src/adapters/redis_cache.py` | New | Redis cache adapter |
| `src/adapters/pg_conversation_repository.py` | New | PostgreSQL conversation storage adapter |
| `src/adapters/ragas_metrics.py` | New | RAGAS evaluation metrics adapter |
| `src/core/query_pipeline.py` | Modified | Insert reranking, query rewriting, caching, and conversation history steps |
| `src/core/evaluation/` | New | Evaluation runner, dataset management, reporting |
| `src/config.py` | Modified | Add settings for all 5 features |
| `src/container.py` | Modified | Add DI factories for new ports |
| `src/api/conversations.py` | New | Conversation CRUD API router |
| `src/api/answers.py` | Modified | Accept optional `conversation_id` in request |
| `src/main.py` | Modified | Register conversations router |
| `migrations/` | Modified | New migration for conversations table |
| `docker-compose.yml` | Modified | Add Redis service |
| `pyproject.toml` | Modified | Add `sentence-transformers`, `redis[hiredis]`, `ragas` dependencies |
| `frontend/app/page.tsx` | Modified | Conversation sidebar integration |
| `frontend/components/` | New | ConversationSidebar, ConversationList components |
| `frontend/lib/` | Modified | Add conversation API calls |
| `data/eval/` | New | Gold evaluation dataset |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Cross-encoder model adds ~500MB and CPU latency | Medium | Use MiniLM-L-6-v2 (smallest viable), limit candidates to 20, lazy-load model on first use, add timeout |
| Query rewriting triples search cost and latency | Medium | Disabled by default, configurable variant count, parallelize per-variant searches, measure latency impact |
| Redis adds operational complexity and failure mode | Low | Graceful degradation (pipeline continues without cache), health check in `/ready`, TTL prevents stale data |
| Conversation history bloats prompts beyond model context | Low | Hard limit of 5 messages / ~1000 tokens, configurable, truncation with oldest-first removal |
| RAGAS heavy dependencies conflict with existing packages | Medium | Isolate in `[eval]` extras group, separate virtualenv option, pin versions |
| Evaluation gold set is biased or too small | Medium | Stratify by source/difficulty/query type, start with 20-30 samples, expand iteratively |
| Frontend conversation sidebar increases UI complexity | Low | Clean component separation, existing patterns from chat-ui spec, no new frontend dependencies |

## Rollback Plan

Each feature is independently toggleable via config flags:

1. **Reranking**: Set `reranker_enabled=false` — pipeline reverts to direct RRF → generation (current MVP behavior)
2. **Query Rewriting**: Set `query_rewriter_enabled=false` — pipeline uses raw query (current MVP behavior)
3. **Caching**: Set `cache_enabled=false` — pipeline skips cache check/store (current MVP behavior)
4. **Conversations**: Omit `conversation_id` from requests — answers are created without conversation grouping (current MVP behavior). Frontend sidebar is additive; existing single-page flow still works.
5. **Evaluation**: CLI-only tool, no runtime impact. Remove by not invoking.

**Full rollback**: All features can be disabled simultaneously without code changes. The pipeline degrades gracefully to the current MVP behavior. Database migration for conversations is additive (new table + nullable FK) and does not break existing answers.

**Dependency rollback**: `sentence-transformers`, `redis[hiredis]`, and `ragas` are additive dependencies. Removing them and setting feature flags to disabled restores the original dependency footprint.

## Dependencies

- `sentence-transformers>=2.7.0` — cross-encoder reranking (includes PyTorch)
- `redis[hiredis]>=5.0.0` — Redis cache adapter
- Redis 7 server — Docker container
- `ragas>=0.2.0` — evaluation metrics (heavy, isolated in `[eval]` extras)
- Cross-encoder model download: `cross-encoder/ms-marco-MiniLM-L-6-v2` (~80MB, first-use)
- Gold evaluation dataset: 20-30 manually curated samples

## Success Criteria

- [ ] **Reranking**: Pipeline calls reranker after RRF; nDCG@5 improves on gold set vs. non-reranked baseline; latency increase < 500ms p95 for 20 candidates
- [ ] **Query Rewriting**: Multi-query expansion produces 2-3 semantically valid variants; retrieval recall improves on complex queries; feature toggleable via config
- [ ] **Caching**: Identical queries return cached answers (latency < 100ms); cache key includes query + filters + index version; pipeline works when Redis is down (graceful degradation)
- [ ] **Conversations**: Conversations CRUD via API; answers linked to conversations; frontend sidebar shows conversation list; last 5 messages included in prompt; existing single-query flow still works
- [ ] **Evaluation**: CLI runs gold set and produces JSON report with faithfulness, relevancy, precision, recall, citation metrics; metrics are deterministic (same input → same output); RAGAS adapter works with local Ollama
- [ ] **All features**: Each feature passes unit tests; integration tests pass with Docker stack; no regression in existing functionality; all features independently toggleable
