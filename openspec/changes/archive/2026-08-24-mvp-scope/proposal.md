# Proposal: MVP Secure Vertical Slice

## Intent

Build the thinnest possible end-to-end RAG pipeline that validates the enterprise architecture on a real corpus. The MVP proves that directory-sourced documents can be parsed, chunked, embedded, stored, retrieved via hybrid search, and answered with grounded citations — all running locally on CPU with open-source models. This vertical slice de-risks the full platform before investing in auth, multi-tenancy, or production infrastructure.

## Scope

### In Scope
- **Ingestion**: Single watched directory, sync scan on startup + manual trigger; parse PDF/DOCX/HTML/TXT/MD
- **Chunking**: Heading-aware recursive splitting (300-600 tokens, 10% overlap, section path prepended)
- **Embedding**: Ollama nomic-embed-text (768 dims) via Embedder port
- **Storage**: PostgreSQL + pgvector; chunks table with HNSW vector index + GIN tsvector index
- **Retrieval**: Hybrid search (BM25 via tsvector + vector cosine) fused with RRF (k=60)
- **Generation**: Ollama qwen2.5 via Generator port; strict grounded-answer prompt with citation IDs
- **Citation validation**: Post-generation check that cited IDs exist in context
- **Abstention**: Return `insufficient_evidence` when retrieval yields 0 chunks or all below threshold
- **Streaming**: SSE streaming of answer tokens + citations (per README query flow step 10)
- **API**: `POST /v1/answers` matching README response envelope; `GET /v1/answers/{id}/stream` for SSE
- **Frontend**: Next.js + Tailwind chat UI with streaming answer display, inline citations, source list, feedback buttons
- **Infrastructure**: Docker Compose (postgres+pgvector, ollama, backend FastAPI, frontend Next.js)
- **Hexagonal skeleton**: Port interfaces for all README internal ports, one adapter per port

### Out of Scope
- Auth/ACL/permissions (Phase 2 — before multi-user deployment)
- Reranking with cross-encoder (Phase 2 — when quality metrics show gaps)
- Multi-tenancy (Phase 2)
- Conversation history / multi-turn (Phase 1.5)
- Incremental ingestion / change detection (Phase 2 — when corpus exceeds ~1000 docs)
- Blue/green indexes (Phase 2)
- Admin UI (Phase 2)
- Full observability / structured telemetry (Phase 2 — basic logging sufficient for MVP)
- Feedback evaluation loop (Phase 2)
- Adversarial tests (Phase 2)
- OCR for scanned PDFs (Phase 2)

## Capabilities

### New Capabilities
- `document-ingestion`: Directory scanning, parsing (PDF/DOCX/HTML/TXT/MD), heading-aware chunking
- `hybrid-retrieval`: BM25 + vector search with RRF fusion, abstention on insufficient evidence
- `grounded-generation`: LLM generation with grounded-answer contract, citation validation, SSE streaming
- `chat-ui`: Next.js chat interface with streaming answers, inline citations, source display, feedback
- `hexagonal-skeleton`: Port interfaces, DI container, adapter wiring, Docker Compose infrastructure

### Modified Capabilities
None (greenfield project).

## Approach

Pure vertical slice through hexagonal architecture. Each README port gets a Python protocol interface and a single concrete adapter. FastAPI backend with dependency injection. PostgreSQL + pgvector handles both lexical (tsvector/tsquery) and vector (HNSW) search in one database, avoiding a separate search engine. RRF fusion in Python. All models served locally via Ollama on CPU. Docker Compose for one-command startup.

**Key constraints**: CPU-only execution, 10-100 doc corpus for validation, design interfaces for 1M doc target scale.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/` | New | FastAPI backend with hexagonal ports and adapters |
| `src/ports/` | New | Protocol interfaces: DocumentSource, Parser, Chunker, Embedder, SearchIndex, Retriever, Generator, CitationValidator, AnswerRepository |
| `src/adapters/` | New | Concrete adapters: filesystem source, pymupdf/docx/bs4 parsers, recursive chunker, Ollama embedder/generator, pgvector search, citation validator |
| `src/api/` | New | FastAPI routes: POST /v1/answers, SSE streaming endpoint |
| `frontend/` | New | Next.js + Tailwind chat UI |
| `docker-compose.yml` | New | postgres+pgvector, ollama, backend, frontend services |
| `migrations/` | New | SQL migrations for chunks, documents, answers tables |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Ollama LLM fails grounded-answer contract on CPU | Medium | Strict system prompt with explicit citation format; citation validator as safety net; fallback to abstention |
| CPU latency unacceptable for streaming UX | Medium | Profile early; qwen2.5 7B quantized; limit context to top-5 chunks; set user expectations |
| PostgreSQL FTS quality gap vs true BM25 | Medium | Acceptable for 10-100 doc corpus; pg_bm25 extension available as upgrade path |
| PDF parsing failures on complex layouts | High | pymupdf handles most; log failures; defer OCR to Phase 2 |
| Chunk boundaries destroy retrieval context | Medium | Heading-aware splitting preserves section coherence; tune overlap if needed |

## Rollback Plan

Docker Compose teardown: `docker compose down -v`. All state is in PostgreSQL volume. No external services modified. Source directory is read-only. Complete rollback in seconds.

## Dependencies

- Docker + Docker Compose (host)
- Ollama with model pulls: `nomic-embed-text`, `qwen2.5` (7B recommended for CPU)
- Python 3.11+, Node.js 20+

## Success Criteria

- [ ] User can drop documents into a directory and see them ingested on startup
- [ ] User can ask a question in the chat UI and receive a streamed answer with inline citations
- [ ] Every cited passage links back to the source document and section
- [ ] System abstains with `insufficient_evidence` when no relevant chunks are found
- [ ] `docker compose up` starts the full stack with one command
- [ ] All hexagonal ports have interfaces; adapters are swappable without changing business logic
- [ ] End-to-end latency under 30s for first token on CPU (acceptable for MVP validation)
