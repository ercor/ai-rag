# Proposal: Ingestion Enhancements (Iteration 1)

## Intent

MVP ingestion is synchronous, duplicated, re-processes unchanged docs, orphans chunks on rename/delete, blocks the event loop, and sends one HTTP request per text to Ollama. This delivers scale/performance foundations per ADR-006 and ADR-005.

## Scope

### In Scope
- **Deduplication**: `documents` table, SHA-256 content hash, skip-unchanged, stale-chunk cleanup, deletion handling (FR-03)
- **Async job API**: POST /v1/ingest -> 202 + jobId; GET /v1/ingest/{jobId} -> progress; 409 on concurrent submission
- **Batched processing**: asyncio.Semaphore (2 docs), native batch /api/embed (<=64 texts), asyncio.to_thread for parsers
- **Structure-aware chunking**: ParsedDocument block model, per-type env config, PDF page markers only, boundary-aware splitting, optional page/anchor chunk metadata
- **Prerequisite**: extract shared IngestionService from duplicated pipeline

### Out of Scope
- Cross-doc embedding reuse, PDF table extraction, persistent job state, YAML config

## Capabilities

### New
- `ingestion-job-tracking`: async job lifecycle (202, GET progress, 409 on concurrent)
- `document-registry`: documents table, SHA-256 dedup, stale-chunk cleanup, deletion

### Modified
- `document-ingestion`: Parser port str->ParsedDocument; per-type chunking config; Chunk gains page/anchor fields; startup scan as background job

## Approach

Three chained PRs on `feature/iter1-ingestion-enhancements`:

1. **IngestionService + dedup**: extract shared service; documents table; SHA-256 scan; skip-unchanged; stale cleanup
2. **Async job API + batching**: 202/GET endpoints; in-memory jobs; Semaphore; batch embed; to_thread
3. **Structure-aware chunking**: ParsedDocument model; per-type parsers; per-type config; page/anchor columns

## Affected Areas

- `src/core/ingestion_service.py` — new shared pipeline
- `src/api/ingestion.py` — async job endpoints
- `src/main.py` — delegates to service
- `src/adapters/filesystem_source.py` — SHA-256 in scan
- `src/adapters/parsers.py` — ParsedDocument + to_thread
- `src/adapters/recursive_chunker.py` — per-type config, boundaries
- `src/adapters/ollama_embedder.py` — native batch embed
- `src/adapters/pgvector_index.py` — bulk upsert, stale delete
- `src/ports/parser.py`, `src/ports/models.py` — contract + Chunk fields
- `migrations/002_documents.sql` — documents table

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Parser contract break ripples to tests | High | TDD: new contract tests first |
| Chunk model affects retrieval/citations/frontend | Medium | Trace end-to-end in design |
| Parsers still stall event loop | Medium | asyncio.to_thread mandatory + test |
| PR 3 exceeds 400-line budget | Medium | Split parser-contract / chunking-config |

## Rollback Plan

Each PR independently revertable. Migration 002 is additive. No destructive changes.

## Dependencies

ADR-006, ADR-005, FR-03; existing `document-ingestion` spec.

## Success Criteria

- [ ] Re-ingesting unchanged corpus skips 100% of parse/chunk/embed
- [ ] Renamed/deleted file: chunks cleaned up correctly
- [ ] POST returns 202; GET shows live progress; concurrent -> 409
- [ ] Embed throughput >=2x via batched calls
- [ ] DOCX tables, HTML headings, MD lists preserved; PDF page markers present
- [ ] All tests pass; each PR <=400 lines
