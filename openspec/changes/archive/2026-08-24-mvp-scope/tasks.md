# Tasks: MVP Secure Vertical Slice

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 3000–4000 (greenfield, ~30 new files) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (Foundation + Ingestion) → PR 2 (Retrieval + Generation) → PR 3 (Frontend + E2E) |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Backend foundation + ingestion pipeline | PR 1 | `pytest tests/unit/test_chunker.py tests/integration/test_ingestion.py` | `docker compose up postgres ollama && pytest` | `src/`, `migrations/`, `docker-compose.yml` — removable without affecting future PRs |
| 2 | Retrieval + generation + SSE streaming | PR 2 | `pytest tests/unit/test_rrf.py tests/integration/test_query.py` | `docker compose up && pytest -m integration` | `src/core/`, `src/adapters/pgvector_index.py`, `src/api/answers.py` — independent revert |
| 3 | Frontend chat UI + E2E wiring | PR 3 | `cd frontend && npm run build && playwright test` | `docker compose up` (full stack) + manual E2E | `frontend/` — fully isolated from backend |

## Phase 1: Foundation & Infrastructure

- [x] 1.1 Create `docker-compose.yml` with postgres+pgvector, ollama, backend, frontend services; health checks and dependency ordering
- [x] 1.2 Create `migrations/001_init.sql` with chunks table (pgvector HNSW + GIN tsvector indexes) and answers table per design schema
- [x] 1.3 Create `src/config.py` with pydantic-settings: DATABASE_URL, OLLAMA_BASE_URL, OLLAMA_MODEL, WATCH_DIR, RETRIEVAL_TOP_K, MIN_SCORE_THRESHOLD, adapter selectors
- [x] 1.4 Create `src/ports/` — one Protocol file per port: DocumentSource, Parser, Chunker, Embedder, SearchIndex, Generator, CitationValidator, AnswerRepository
- [x] 1.5 Create `src/container.py` — DI factory functions (`get_embedder()`, `get_generator()`, etc.) configurable via env vars
- [x] 1.6 Create `src/main.py` — FastAPI app with lifespan (startup scan trigger), CORS, router includes
- [x] 1.7 Create `src/api/health.py` — `GET /health` returns `{"status": "ok"}`; `GET /ready` checks port connectivity, returns 503 on failure
- [x] 1.8 Create `pyproject.toml` / `requirements.txt` with all backend dependencies (fastapi, uvicorn, asyncpg, pgvector, pymupdf, python-docx, beautifulsoup4, httpx, pydantic-settings)

## Phase 2: Ingestion Pipeline

- [x] 2.1 Create `src/adapters/filesystem_source.py` — scan WATCH_DIR, return list of file metadata dicts; read-only, skip unsupported extensions
- [x] 2.2 Create `src/adapters/parsers.py` — dispatch by extension: pymupdf (PDF), python-docx (DOCX), bs4 (HTML), plain read (TXT/MD); log+skip on failure
- [x] 2.3 Create `src/adapters/recursive_chunker.py` — heading-aware recursive split: 300–600 tokens, 10% overlap, section_path prefix, chunk metadata (document_id, chunk_index, token_count, content_hash)
- [x] 2.4 Create `src/adapters/ollama_embedder.py` — implement Embedder port: `embed()` and `embed_batch()` via Ollama API (nomic-embed-text, 768 dims)
- [x] 2.5 Create `src/adapters/pgvector_index.py` — implement SearchIndex port: `upsert_chunks()` with ON CONFLICT dedup, `bm25_search()` via tsquery, `vector_search()` via cosine distance; sanitize tsquery input
- [x] 2.6 Create `src/api/ingestion.py` — `POST /v1/ingest` triggers scan→parse→chunk→embed→upsert pipeline; returns `{processed, chunks, failed, failures}`
- [x] 2.7 Wire startup scan in `src/main.py` lifespan — call ingestion on boot; write unit tests for chunker splitting logic (normal doc, short doc, metadata)

## Phase 3: Retrieval & Generation

- [x] 3.1 Create `src/core/retrieval.py` — RRF fusion (k=60) over BM25 + vector results; dedup by chunk id; abstention when 0 chunks or all below MIN_SCORE_THRESHOLD
- [x] 3.2 Create `src/adapters/ollama_generator.py` — implement Generator port: `generate_stream()` yields tokens via Ollama streaming API (qwen2.5)
- [x] 3.3 Create `src/adapters/regex_citation_validator.py` — implement CitationValidator: regex `[N]` extraction, strip invalid refs, log warnings
- [x] 3.4 Create `src/adapters/pg_answer_repository.py` — implement AnswerRepository: `save()` and `update_vote()` via asyncpg
- [x] 3.5 Create `src/core/query_pipeline.py` — orchestrate: embed query → retrieve → abstain? → build prompt → generate → validate citations → persist answer
- [x] 3.6 Create `src/api/answers.py` — `POST /v1/answers` (sync retrieval, two-phase abstention), `GET /v1/answers/{id}/stream` (SSE token stream + done event), `POST /v1/answers/{id}/feedback`
- [x] 3.7 Write unit tests for RRF fusion math (overlapping, disjoint, empty) and citation validator (valid, invalid, all-invalid)

## Phase 4: Frontend Chat UI

- [x] 4.1 Scaffold Next.js app: `frontend/package.json`, `next.config.mjs`, `tailwind.config.ts`, `app/layout.tsx`, `app/page.tsx`
- [x] 4.2 Create `frontend/lib/sse.ts` — POST to `/v1/answers`, then fetch ReadableStream from `/v1/answers/{id}/stream`; parse SSE events, invoke token callback
- [x] 4.3 Create `frontend/components/ChatInput.tsx` — text input + submit button; Enter-to-submit; disabled while streaming; empty-input guard
- [x] 4.4 Create `frontend/components/AnswerDisplay.tsx` — incremental token rendering, typing indicator, markdown formatting, insufficient-evidence message
- [x] 4.5 Create `frontend/components/CitationBadge.tsx` — clickable `[N]` badges; tooltip/popover with source doc name + section path
- [x] 4.6 Create `frontend/components/SourcePanel.tsx` — list of cited documents with section paths and chunk snippets
- [x] 4.7 Create `frontend/components/FeedbackButtons.tsx` — thumbs-up/down; disabled until stream complete; POST feedback on click
- [x] 4.8 Implement responsive layout: side-by-side at >=1024px, stacked below; add Dockerfile for frontend service

## Phase 5: Integration & Verification

- [x] 5.1 Write integration tests: PG tsvector/pgvector queries with testcontainers, answer persistence, ingestion idempotency
- [x] 5.2 Write E2E test: docker compose up → ingest sample docs → POST question → verify SSE stream → verify citations
- [x] 5.3 Add `.env.example` with all config variables and defaults; update `README.md` with setup instructions and `docker compose up` quickstart
- [x] 5.4 Verify `docker compose up` starts full stack; health checks pass; end-to-end query returns streamed answer with citations

## Key Learnings

1. Greenfield RAG MVP with ~30 files clearly exceeds 400-line review budget, requiring chained PRs with stacked-to-main strategy.
2. Two-phase SSE approach (retrieve synchronously, stream on success) prevents streaming answers that will be abstained.
3. Single-table chunks design with embedded document metadata avoids JOINs and is valid up to ~10K chunks for MVP scale.
4. fetch+ReadableStream is required on frontend because EventSource API only supports GET, but answer creation needs POST.
5. Threat matrix is entirely N/A for MVP — no routing, shell, subprocess, or VCS boundaries in scope.
