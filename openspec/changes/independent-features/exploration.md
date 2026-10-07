## Exploration: Independent Features Implementation

### Current State

The ai-rag system is a functional MVP with hexagonal architecture. The query pipeline flows: embed query → parallel BM25 + vector search → RRF fusion → abstention check → build prompt → generate (streaming) → validate citations → persist answer. The frontend is a single-page chat UI with messages held in React state (no persistence). There is no reranking, caching, query rewriting, conversation history, or evaluation framework.

**Existing Ports:** SearchIndex, Embedder, Generator, AnswerRepository, CitationValidator, Parser, Chunker, DocumentSource
**Existing Adapters:** pgvector_index, ollama_embedder, ollama_generator, pg_answer_repository, filesystem_source, parsers, recursive_chunker, regex_citation_validator
**Schema:** chunks (with embedding, tsv, page_number, anchor), answers (question, answer, status, citations, vote), documents (registry)
**No existing:** Reranker port, Cache port, QueryRewriter port, Conversation model, EvaluationMetric port

---

### Feature 1: Cross-Encoder Reranking (8-12h)

#### Current State

ADR-003 in ARCHITECTURE.md already mandates cross-encoder reranking as default. The current pipeline goes directly from RRF fusion to prompt building. No `Reranker` port exists. The retrieval returns top_k=5 fused chunks directly to generation.

#### Affected Areas

- `src/ports/` — new `reranker.py` port (Protocol)
- `src/core/retrieval.py` — or new `src/core/reranking.py` module
- `src/core/query_pipeline.py` — insert reranking step after RRF, before abstention
- `src/config.py` — add reranker config (model, top_k_before, top_k_after, enabled flag)
- `src/container.py` — add `get_reranker()` factory
- `src/adapters/` — new reranker adapter (sentence-transformers CrossEncoder or Ollama-based)
- `pyproject.toml` — add `sentence-transformers` or `torch` dependency
- `tests/unit/` — unit tests for reranker port and fusion+rerank integration
- `tests/integration/` — integration test with real model

#### Approach

**Option A: sentence-transformers CrossEncoder (Recommended)**
- New port: `Reranker` with `async def rerank(query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]`
- Adapter: `CrossEncoderReranker` using `sentence-transformers` with `cross-encoder/ms-marco-MiniLM-L-6-v2`
- Load model once (lazy init), run inference on (query, chunk_content) pairs
- Pros: proven quality, fast on small candidate sets (20-50), well-documented
- Cons: adds `torch` + `sentence-transformers` (~500MB), first-load latency
- Effort: Medium

**Option B: Ollama-based reranking**
- Use Ollama's rerank API (if available) or a lightweight scoring model via Ollama
- Pros: no new heavy dependencies, consistent with existing model serving
- Cons: Ollama rerank API is limited, less control over model selection
- Effort: Low-Medium

**Pipeline integration:**
```
embed query → BM25 + vector (top_k=20 each) → RRF fusion (top_k=20)
→ RERANK (top_k=5) → abstain check → build prompt → generate
```

Config changes:
- `reranker_enabled: bool = True`
- `reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"`
- `reranker_top_k_before: int = 20` (fetch more candidates for reranking)
- `reranker_top_k_after: int = 5` (final count after reranking)
- `retrieval_top_k` stays but becomes the "before rerank" fetch count per channel

#### Testing Strategy

- **Unit:** Mock reranker, verify pipeline calls it with correct args, verify ordering
- **Unit:** Test reranker adapter with pre-computed scores
- **Integration:** Real cross-encoder model with test chunks, verify score ordering
- **Verify:** nDCG improvement on a small gold set

#### Dependencies

- `sentence-transformers>=2.7.0` (includes torch)
- Model download on first use (~80MB for MiniLM-L-6-v2)
- Optional: GPU for faster inference (CPU is acceptable for 20 candidates)

#### Effort Estimate: 8-12h (confirmed)

- Port + adapter: 3h
- Pipeline integration: 2h
- Config + DI: 1h
- Tests: 3h
- Model loading optimization: 1-2h

---

### Feature 2: Query Rewriting & Expansion (12-16h)

#### Current State

The query pipeline takes the user's raw question and directly embeds it for search. No rewriting, expansion, or intent classification exists. The `build_prompt()` function in `query_pipeline.py` is the only text transformation.

#### Affected Areas

- `src/ports/` — new `query_rewriter.py` port (Protocol)
- `src/core/query_pipeline.py` — insert rewriting step before embedding
- `src/core/` — new `query_rewriting.py` module with strategies
- `src/config.py` — add rewriter config (strategy, enabled, max_queries)
- `src/container.py` — add `get_query_rewriter()` factory
- `src/adapters/` — new rewriter adapter(s)
- `tests/unit/` — tests for each strategy
- `tests/integration/` — tests with real LLM

#### Approaches

**Strategy 1: HyDE (Hypothetical Document Embedding)**
- Generate a hypothetical answer, embed that instead of the raw query
- Uses existing Generator port
- Pros: improves semantic recall for complex questions
- Cons: adds one LLM call latency (~1-3s), may hallucinate wrong direction

**Strategy 2: Multi-Query Expansion**
- Generate 2-3 query variants, search each, merge results via RRF
- Uses existing Generator port
- Pros: covers different phrasings and angles
- Cons: multiplies search cost (3x), adds latency

**Strategy 3: Step-Back Prompting**
- Generate a broader/abstract query, combine with original
- Pros: helps with specific questions that need context
- Cons: complex prompting, variable quality

**Recommended: Multi-Query Expansion (Option A)**

New port:
```python
class QueryRewriter(Protocol):
    async def rewrite(self, query: str) -> list[str]:
        """Return a list of query variants (including the original)."""
        ...
```

Adapter: `LLMQueryRewriter` using the existing Generator port (or a dedicated lightweight model)

Pipeline integration:
```
query → REWRITE → [q1, q2, q3] → embed each → parallel search per query
→ merge all results via RRF → rerank → generate
```

Config:
- `query_rewriter_enabled: bool = False`
- `query_rewriter_strategy: str = "multi_query"`
- `query_rewriter_num_variants: int = 3`

#### Testing Strategy

- **Unit:** Mock LLM, verify correct number of variants, verify original included
- **Unit:** Test RRF merge with multi-query results (deduplication)
- **Integration:** Real LLM rewriting, verify variants are semantically related
- **E2E:** Compare retrieval quality with/without rewriting on gold set

#### Dependencies

- No new packages (uses existing Generator port / Ollama)
- Optional: dedicated lightweight model for rewriting (e.g., qwen2.5:0.5b)

#### Effort Estimate: 12-16h (confirmed)

- Port + adapter: 3h
- Strategy implementations: 3h
- Pipeline integration (multi-search merge): 4h
- Config + DI: 1h
- Tests: 3-4h

---

### Feature 3: Caching Layer (Redis) (8-12h)

#### Current State

No caching exists. Every query goes through the full pipeline: embedding → search → generation. Identical queries are re-processed from scratch. The answers table persists results but is not used as a cache.

#### Affected Areas

- `src/ports/` — new `cache.py` port (Protocol)
- `src/adapters/` — new `redis_cache.py` adapter
- `src/core/query_pipeline.py` — add cache check before retrieval, cache store after generation
- `src/config.py` — add Redis config (URL, TTL, enabled flag)
- `src/container.py` — add `get_cache()` factory
- `docker-compose.yml` — add Redis service
- `pyproject.toml` — add `redis[hiredis]` dependency
- `tests/unit/` — tests for cache key generation, hit/miss logic
- `tests/integration/` — tests with real Redis (testcontainers or Docker)

#### Approach

**What to cache:** Full answer (query → answer text + citations). This is the highest-value cache because it avoids both retrieval AND generation costs.

**Cache key strategy:**
```python
cache_key = sha256(normalize(query) + ":" + filters_hash + ":" + index_version)
```
- Normalize: lowercase, strip whitespace, collapse spaces
- Include filters hash (source systems, date ranges)
- Include index version (invalidate on re-ingestion)

**TTL strategy:**
- Default: 30 minutes (configurable)
- Configurable per-deployment

**Port:**
```python
class Cache(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl_seconds: int) -> None: ...
    async def invalidate(self, pattern: str) -> int: ...
```

**Adapter:** `RedisCache` using `redis.asyncio`

**Pipeline integration:**
```
query → cache check → HIT? return cached answer
                     → MISS? → full pipeline → cache store → return
```

**Cache invalidation:**
- On document re-ingestion: invalidate all (bump index version)
- TTL-based expiry handles stale entries

**Docker compose:**
```yaml
redis:
  image: redis:7-alpine
  ports: ["6379:6379"]
  healthcheck: ...
```

#### Testing Strategy

- **Unit:** Test cache key normalization (same query → same key, different filters → different key)
- **Unit:** Mock cache, verify pipeline checks cache before retrieval
- **Unit:** Mock cache, verify pipeline stores result after generation
- **Integration:** Real Redis, verify TTL expiry, verify get/set round-trip
- **E2E:** Verify cache hit avoids Ollama calls (measure latency difference)

#### Dependencies

- `redis[hiredis]>=5.0.0`
- Redis server (Docker)
- ~50MB additional memory for Redis container

#### Risks

- Cache staleness after document updates → mitigated by index version in key
- Memory pressure with many unique queries → mitigated by TTL + maxmemory policy
- Cache key collisions → mitigated by SHA-256

#### Effort Estimate: 8-12h (confirmed)

- Port + adapter: 3h
- Pipeline integration: 2h
- Config + DI: 1h
- Docker compose: 0.5h
- Tests: 3-4h

---

### Feature 4: Conversation History & Multi-Turn Q&A (12-16h)

#### Current State

- The `answers` table stores individual Q&A pairs with no conversation grouping
- The frontend (`page.tsx`) stores messages in React state (`useState<Message[]>([])`) — lost on refresh
- The API has no conversation endpoints
- The query pipeline has no awareness of prior context
- The `build_prompt()` function has no conversation history parameter

#### Affected Areas

- `migrations/` — new migration: `conversations` table, add `conversation_id` to `answers`
- `src/ports/` — extend `AnswerRepository` or new `ConversationRepository` port
- `src/ports/models.py` — new `Conversation` model
- `src/core/query_pipeline.py` — accept conversation history, include in prompt
- `src/api/` — new `conversations.py` router (CRUD endpoints)
- `src/api/answers.py` — accept optional `conversation_id` in request
- `src/config.py` — add conversation config (max_history_length)
- `src/container.py` — add conversation factory
- `src/main.py` — register conversations router
- `frontend/app/page.tsx` — conversation sidebar, persistent history
- `frontend/lib/sse.ts` — add conversation API calls
- `frontend/components/` — new `ConversationSidebar.tsx`, `ConversationList.tsx`
- `tests/unit/` — context window management tests
- `tests/integration/` — conversation CRUD tests

#### Approach

**Database schema:**
```sql
-- Migration 004: conversations
CREATE TABLE conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE answers ADD COLUMN conversation_id UUID REFERENCES conversations(id);
CREATE INDEX idx_answers_conversation ON answers (conversation_id, created_at);
```

**API endpoints:**
```
POST   /v1/conversations          — create new conversation
GET    /v1/conversations          — list conversations (paginated)
GET    /v1/conversations/{id}     — get conversation with answers
DELETE /v1/conversations/{id}     — delete conversation + answers
```

**Request changes:**
```json
POST /v1/answers
{
  "question": "...",
  "conversation_id": "optional-uuid"  // NEW
}
```

**Context window management:**
- Include last N messages (configurable, default 5) in the prompt
- Format: conversation history as context before the current question
- Token budget: limit history to ~1000 tokens

**Prompt modification:**
```python
def build_prompt(question, chunks, history=None):
    history_text = ""
    if history:
        history_parts = []
        for h in history[-max_history:]:
            history_parts.append(f"Q: {h['question']}\nA: {h['answer']}")
        history_text = "\n\n".join(history_parts)

    # ... existing context building ...
    prompt = (
        f"## Conversation History\n\n{history_text}\n\n"
        f"## Context\n\n{context}\n\n"
        f"## Question\n\n{question}\n\n"
        "## Answer\n"
    )
```

**Frontend changes:**
- Sidebar with conversation list (fetched from API)
- "New conversation" button
- Click conversation → load history → continue chatting
- Persist conversation_id with each answer

#### Testing Strategy

- **Unit:** Test context window truncation (max_history limit)
- **Unit:** Test prompt building with history
- **Unit:** Test conversation creation/listing logic
- **Integration:** Test conversation CRUD against real DB
- **Integration:** Test answers linked to conversations
- **E2E:** Frontend conversation flow (create, chat, switch, resume)

#### Dependencies

- No new packages (uses existing asyncpg)
- Frontend: no new packages (React state + fetch)

#### Risks

- Prompt grows too large with long history → mitigated by token budget
- Conversation table grows unbounded → mitigated by TTL or admin cleanup
- Frontend complexity increases → mitigated by clean component separation

#### Effort Estimate: 12-16h (confirmed, leaning toward 14-16h)

- DB migration + port: 2h
- Backend API (conversations CRUD): 3h
- Pipeline integration (history in prompt): 2h
- Frontend (sidebar, persistence): 4-5h
- Tests: 3-4h

---

### Feature 5: Evaluation Framework (RAGAS, custom metrics) (20-28h)

#### Current State

No evaluation code exists anywhere in the codebase. Tests verify correctness of individual components (RRF, chunking, citation validation) but there is no end-to-end quality measurement. No gold set, no metrics computation, no evaluation CLI or API.

#### Affected Areas

- `src/ports/` — new `evaluation.py` port (EvaluationMetric Protocol)
- `src/core/` — new `evaluation/` module (runner, dataset management, metrics)
- `src/adapters/` — new RAGAS adapter, custom metrics adapters
- `src/api/` — optional: evaluation API endpoint
- `src/config.py` — evaluation config (metrics, dataset path)
- `src/container.py` — evaluation factories
- `pyproject.toml` — add `ragas`, `datasets` dependencies
- `tests/` — evaluation tests
- `data/` — evaluation dataset (JSON/JSONL)
- CLI: new `scripts/evaluate.py` or `python -m src.evaluation`

#### Approach

**Evaluation dataset format:**
```json
{
  "question": "What is the travel policy?",
  "ground_truth": "The travel policy requires...",
  "contexts": ["chunk content 1", "chunk content 2"],
  "metadata": {"source": "manual", "difficulty": "easy", "category": "policy"}
}
```

**Metrics to implement (RAGAS):**

| Metric | What it measures | RAGAS function |
|--------|-----------------|----------------|
| Faithfulness | Are claims supported by context? | `Faithfulness` |
| Answer Relevancy | Is the answer relevant to the question? | `AnswerRelevancy` |
| Context Precision | Are relevant contexts ranked high? | `ContextPrecision` |
| Context Recall | Are all relevant contexts retrieved? | `ContextRecall` |

**Custom metrics (non-LLM):**
- Citation precision: % of citations that reference valid chunks
- Citation completeness: % of factual claims that have citations
- Retrieval hit rate: % of questions where gold context appears in top-k
- Abstention accuracy: % of unanswerable questions correctly abstained

**Port:**
```python
class EvaluationMetric(Protocol):
    async def compute(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str,
    ) -> float: ...
```

**Runner:**
```python
class EvaluationRunner:
    async def run(self, dataset: list[EvalSample]) -> EvaluationReport:
        # For each sample: run pipeline, compute metrics, aggregate
        ...
```

**CLI interface (recommended over API for first version):**
```bash
python -m src.evaluation --dataset data/eval/gold_set.json --metrics faithfulness,relevancy
```

**Output:**
```json
{
  "timestamp": "2026-09-27T...",
  "dataset": "gold_set.json",
  "samples": 25,
  "metrics": {
    "faithfulness": {"mean": 0.85, "std": 0.12},
    "answer_relevancy": {"mean": 0.91, "std": 0.08},
    "context_precision": {"mean": 0.78, "std": 0.15},
    "citation_precision": {"mean": 0.95, "std": 0.05}
  }
}
```

#### Testing Strategy

- **Unit:** Test each metric with known inputs/outputs
- **Unit:** Test dataset loading and validation
- **Unit:** Test report aggregation
- **Integration:** Run evaluation against real pipeline with small gold set
- **Verify:** Metrics are deterministic (same input → same output)

#### Dependencies

- `ragas>=0.2.0` (requires `langchain`, `openai` or local LLM for judge metrics)
- `datasets>=2.14.0` (HuggingFace datasets, optional)
- RAGAS needs an LLM judge — can use existing Ollama instance
- Gold evaluation dataset (must be created manually or semi-automatically)

#### Risks

- RAGAS metrics require an LLM judge → adds latency and cost per evaluation
- Gold set creation is manual and time-consuming → start small (20-30 samples)
- Metric scores may not be comparable across model changes → version everything
- RAGAS has heavy dependencies (langchain) → consider lightweight alternatives

#### Effort Estimate: 20-28h (confirmed, leaning toward 24-28h)

- Port + custom metrics: 4h
- RAGAS adapter integration: 4h
- Evaluation runner + dataset management: 4h
- CLI interface: 2h
- Gold set creation (20-30 samples): 4-6h
- Tests: 3-4h
- Documentation: 2h

---

### Recommended Implementation Order

| # | Feature | Effort | Rationale |
|---|---------|--------|-----------|
| 1 | **Cross-Encoder Reranking** | 8-12h | Highest quality-per-effort ratio. ADR-003 already decided. Natural extension of retrieval pipeline. No new infrastructure. Sets foundation for evaluation (measurable improvement). |
| 2 | **Query Rewriting & Expansion** | 12-16h | Builds on reranking. Uses existing Generator port. No new infrastructure. Improves recall for complex queries. Best evaluated after reranking is in place. |
| 3 | **Caching Layer (Redis)** | 8-12h | Independent infrastructure addition. Reduces latency and model costs. Should be added before conversation history (conversations benefit from caching). |
| 4 | **Conversation History & Multi-Turn** | 12-16h | Largest surface area (DB + API + frontend). Self-contained. Benefits from caching (repeated conversation patterns). |
| 5 | **Evaluation Framework** | 20-28h | Highest effort. Best done LAST so you can measure the impact of all previous features. Needs a stable pipeline to evaluate. Provides the measurement framework for all future improvements. |

**Total estimated effort: 60-84h**

### Dependency Graph

```
Reranking ──────────────────────┐
                                 ├──→ Evaluation Framework
Query Rewriting ────────────────┘    (measures all above)
                                     
Redis Caching ──→ Conversation History
```

### Global Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Cross-encoder model too slow on CPU | High latency | Use MiniLM-L-6-v2 (fast), limit candidates to 20, add timeout |
| Query rewriting adds too much latency | Poor UX | Make it optional (config flag), use lightweight model, parallelize searches |
| Redis adds operational complexity | More things to fail | Make cache optional (graceful degradation), health check in /ready |
| Conversation history bloats prompts | Token overflow, cost | Hard limit on history length (5 messages / 1000 tokens) |
| RAGAS heavy dependencies | Dependency conflicts | Isolate in optional extras `[eval]`, use virtualenv |
| Evaluation gold set is biased | Misleading metrics | Stratify by source, difficulty, query type |

### Ready for Proposal

**Yes.** All five features are well-understood with clear implementation paths in the existing hexagonal architecture. The orchestrator should present the recommended order to the user for confirmation before proceeding to proposal phase.

Key decision points for the user:
1. Reranker model choice (sentence-transformers vs Ollama-based)
2. Query rewriting strategy (multi-query vs HyDE vs both)
3. Evaluation: CLI-first vs API-first
4. Conversation history: how many messages in context (default 5)
5. Whether to implement all 5 or prioritize a subset
