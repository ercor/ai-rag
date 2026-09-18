# Archive Report: mvp-scope

## Change Summary

| Field | Value |
|-------|-------|
| Change name | mvp-scope |
| Title | MVP Secure Vertical Slice |
| Archived to | `openspec/changes/archive/2026-08-24-mvp-scope/` |
| Date archived | 2026-08-24 |
| Branch | feature/mvp-scope |
| Commits | 4 (Phases 1, 2, 4+3, 5) |
| Total tasks | 34/34 complete |
| Review gate | Not applicable (no review performed) |

## What Was Built

A complete end-to-end RAG (Retrieval-Augmented Generation) MVP running locally on CPU with open-source models. The system ingests documents from a watched directory, chunks them with heading-aware splitting, embeds via Ollama (nomic-embed-text, 768 dims), stores in PostgreSQL+pgvector with HNSW+GIN indexes, retrieves via hybrid search (BM25+vector with RRF fusion k=60), generates grounded answers with citation IDs via Ollama (qwen2.5), validates citations post-generation, and streams answers via SSE to a Next.js chat UI.

### Final Implementation Stats

| Layer | Files | Lines |
|-------|-------|-------|
| Backend (Python) | 30 | ~2,666 |
| Frontend (TypeScript/React) | 9 | ~858 |
| Tests (unit/integration/e2e) | 7 (+5 support) | ~1,367 |
| Infrastructure | Docker Compose, Dockerfiles, migrations | - |
| **Total** | **~46 source files** | **~4,891** |

### Architecture

Hexagonal (ports-and-adapters) FastAPI backend with:
- **9 port interfaces** in `src/ports/`: DocumentSource, Parser, Chunker, Embedder, SearchIndex, Generator, CitationValidator, AnswerRepository, + models
- **8 concrete adapters** in `src/adapters/`: filesystem_source, parsers, recursive_chunker, ollama_embedder, ollama_generator, pgvector_index, regex_citation_validator, pg_answer_repository
- **2 core modules** in `src/core/`: retrieval (RRF fusion), query_pipeline (orchestration)
- **3 API routes** in `src/api/`: answers (POST + SSE stream + feedback), ingestion, health
- **DI container** via FastAPI Depends factory functions, env-var configurable

### Frontend

Next.js App Router + Tailwind CSS with:
- Chat input with Enter-to-submit, disabled during streaming
- Streaming answer display with markdown rendering
- Inline citation badges with popover source details
- Source panel listing cited documents with section paths
- Feedback buttons (thumbs up/down) disabled until stream complete
- Responsive layout (side-by-side >= 1024px, stacked below)
- SSE consumption via fetch+ReadableStream (POST body required)

### Database Schema

Single-table `chunks` design (document metadata embedded) with:
- HNSW vector index (768 dims, cosine distance)
- GIN tsvector index (English full-text search)
- Dedup unique index (document_id, chunk_index, content_hash)
- `answers` table with JSONB citations, UUID array chunk_ids, vote tracking

## What Was Deferred

| Item | Target Phase | Rationale |
|------|-------------|-----------|
| Auth/ACL/permissions | Phase 2 | Before multi-user deployment |
| Reranking with cross-encoder | Phase 2 | When quality metrics show gaps |
| Multi-tenancy | Phase 2 | Not needed for single-user validation |
| Conversation history / multi-turn | Phase 1.5 | MVP is single-turn Q&A |
| Incremental ingestion / change detection | Phase 2 | When corpus exceeds ~1000 docs |
| Blue/green indexes | Phase 2 | Zero-downtime re-indexing |
| Admin UI | Phase 2 | Management interface |
| Full observability / structured telemetry | Phase 2 | Basic logging sufficient for MVP |
| Feedback evaluation loop | Phase 2 | Collecting but not acting on feedback |
| Adversarial tests | Phase 2 | Security hardening |
| OCR for scanned PDFs | Phase 2 | Complex layout handling |

## Key Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| DB schema | Single chunks table with embedded doc metadata | MVP scale (10-100 docs); avoids JOIN; valid up to ~10K chunks |
| DI approach | FastAPI Depends factory functions | No extra dependency; matches FastAPI idioms |
| Streaming transport | SSE (not WebSocket) | Unidirectional fits answer streaming; spec mandate |
| Frontend SSE | fetch+ReadableStream (not EventSource) | EventSource is GET-only; answer creation needs POST |
| Chunking | Heading-aware recursive splitting | Preserves section context for retrieval |
| FTS engine | Native tsvector (not pg_bm25) | Zero extra deps; sufficient for 10-100 docs |
| Abstention timing | Two-phase: retrieve first, stream on success | Prevents streaming answers that will be retracted |
| RRF fusion | Reciprocal Rank Fusion with k=60 | Standard technique; balances lexical+semantic |
| Embedding model | nomic-embed-text (768 dims) via Ollama | Open-source, CPU-friendly, good quality |
| Generation model | qwen2.5 via Ollama | Open-source, follows grounded-answer contract |

## Files Created/Modified

### Backend (`src/`)

```
src/
├── main.py                          # FastAPI app, lifespan, CORS, router includes
├── config.py                        # pydantic-settings from env vars
├── container.py                     # DI factory functions
├── ports/
│   ├── models.py                    # Chunk dataclass + shared types
│   ├── document_source.py           # DocumentSource Protocol
│   ├── parser.py                    # Parser Protocol
│   ├── chunker.py                   # Chunker Protocol
│   ├── embedder.py                  # Embedder Protocol
│   ├── search_index.py             # SearchIndex Protocol
│   ├── generator.py                # Generator Protocol
│   ├── citation_validator.py       # CitationValidator Protocol
│   └── answer_repository.py        # AnswerRepository Protocol
├── adapters/
│   ├── filesystem_source.py         # WATCH_DIR scanner
│   ├── parsers.py                   # PDF/DOCX/HTML/TXT/MD dispatch
│   ├── recursive_chunker.py         # Heading-aware recursive splitter
│   ├── ollama_embedder.py           # nomic-embed-text via Ollama API
│   ├── ollama_generator.py          # qwen2.5 streaming via Ollama API
│   ├── pgvector_index.py            # BM25 (tsquery) + vector (cosine) search
│   ├── regex_citation_validator.py  # [N] citation extraction + validation
│   └── pg_answer_repository.py      # asyncpg answer persistence
├── core/
│   ├── retrieval.py                 # RRF fusion (k=60), abstention check
│   └── query_pipeline.py            # retrieve → abstain? → generate → validate → persist
└── api/
    ├── answers.py                   # POST /v1/answers, GET /stream, POST /feedback
    ├── ingestion.py                 # POST /v1/ingest
    └── health.py                    # GET /health, GET /ready
```

### Frontend (`frontend/`)

```
frontend/
├── app/
│   ├── layout.tsx                   # Root layout with metadata
│   └── page.tsx                     # Chat page (client component)
├── components/
│   ├── ChatInput.tsx                # Input + submit, Enter-to-submit
│   ├── AnswerDisplay.tsx            # Incremental token rendering, markdown
│   ├── CitationBadge.tsx            # Clickable [N] badge with popover
│   ├── SourcePanel.tsx              # Cited documents list with snippets
│   └── FeedbackButtons.tsx          # Thumbs up/down, POST feedback
├── lib/
│   └── sse.ts                       # fetch POST → ReadableStream → SSE parser
├── Dockerfile                       # Frontend container
├── next.config.mjs
├── tailwind.config.ts
└── package.json
```

### Infrastructure & Tests

```
docker-compose.yml                   # postgres+pgvector, ollama, backend, frontend
Dockerfile.backend                   # Backend container
migrations/001_init.sql              # Schema: chunks + answers tables
.env.example                         # All config variables with defaults
data/docs/                           # 3 sample documents for validation
tests/
├── unit/
│   ├── test_chunker.py              # Heading-aware splitting, metadata, short docs
│   ├── test_rrf.py                  # RRF fusion math: overlapping, disjoint, empty
│   └── test_citation_validator.py   # Valid, invalid, all-invalid citation scenarios
├── integration/
│   ├── conftest.py                  # testcontainers-py PostgreSQL fixtures
│   ├── test_pgvector_index.py       # Real PG tsvector/pgvector queries
│   └── test_answer_repository.py    # Answer persistence, vote updates
└── e2e/
    └── test_full_stack.py           # Full query flow: ingest → query → stream → citations
```

## Test Coverage

| Layer | Test file | What it covers |
|-------|-----------|---------------|
| Unit | test_chunker.py (208 lines) | Heading-aware splitting, metadata, short docs, overlap |
| Unit | test_rrf.py (243 lines) | RRF fusion math: overlapping, disjoint, empty result sets |
| Unit | test_citation_validator.py (150 lines) | Valid, invalid, all-invalid citation scenarios |
| Integration | test_pgvector_index.py (238 lines) | Real PG tsvector/pgvector queries via testcontainers |
| Integration | test_answer_repository.py (171 lines) | Answer persistence, vote updates, status transitions |
| E2E | test_full_stack.py (244 lines) | Full query flow: ingest → query → SSE stream → citations |
| **Total** | **7 test files** | **~1,298 lines of test code** |

## Known Issues & Limitations

1. **Phase 3 bundled into Phase 4 commit**: Retrieval & generation code (src/core/, ollama_generator, regex_citation_validator, pg_answer_repository, api/answers.py) was committed as part of the Phase 4 frontend commit (5edac6e) rather than as a separate Phase 3 commit. All code is present and functional; this is a commit organization artifact, not a code gap.

2. **CPU latency**: First-token latency on CPU with qwen2.5 is acceptable for MVP validation (~30s target) but not production-ready. Quantization choice (7B vs 3B) remains an open question.

3. **Single-table ceiling**: The chunks table design is validated up to ~10K chunks. Beyond that, partitioning or a documents+chunks split would be needed.

4. **No auth**: The entire API is unauthenticated. This is intentional for MVP but must be addressed before any multi-user or network deployment.

5. **No incremental ingestion**: Every `POST /v1/ingest` re-scans the full directory. Dedup is handled at the DB level (unique index), but parsing is repeated. Acceptable for 10-100 docs, not for large corpora.

6. **FTS quality**: Native tsvector is sufficient for 10-100 docs but may show quality gaps vs. true BM25 (pg_bm25 extension) at scale.

7. **No OCR**: Scanned PDFs (image-only) will produce empty text. pymupdf handles text-based PDFs well.

## Artifact Traceability

| Artifact | Location | Status |
|----------|----------|--------|
| Proposal | `archive/2026-08-24-mvp-scope/proposal.md` | Archived |
| Specs (5 domains) | `archive/2026-08-24-mvp-scope/specs/*/spec.md` | Archived + synced to main |
| Design | `archive/2026-08-24-mvp-scope/design.md` | Archived |
| Tasks | `archive/2026-08-24-mvp-scope/tasks.md` | Archived (34/34 checked) |
| Archive report | `archive/2026-08-24-mvp-scope/archive-report.md` | This file |

## Main Specs Updated

| Domain | Action | Requirements |
|--------|--------|-------------|
| hexagonal-skeleton | Created | 4 requirements (Port Interfaces, DI Container, Docker Compose, Health/Ready) |
| document-ingestion | Created | 4 requirements (Directory Scanning, Multi-Format Parsing, Heading-Aware Chunking, Status Reporting) |
| hybrid-retrieval | Created | 5 requirements (BM25 Search, Vector Search, RRF Fusion, Abstention, Configurable Top-K) |
| grounded-generation | Created | 5 requirements (Grounded Prompt, LLM Generation, Citation Validation, SSE Streaming, Answer Persistence) |
| chat-ui | Created | 6 requirements (Chat Input, Streaming Display, Inline Citations, Source Panel, Feedback, Responsive Layout) |

## SDD Cycle Complete

The mvp-scope change has been fully planned, implemented, verified, and archived. All 34 tasks are complete. Delta specs have been synced to main specs. The change folder has been moved to `openspec/changes/archive/2026-08-24-mvp-scope/`.

Ready for the next change.
