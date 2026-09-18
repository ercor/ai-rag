# Tasks: Ingestion Enhancements (Iteration 1)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | PR 1: ~450, PR 2: ~300, PR 3: ~480 |
| 400-line budget risk | PR 1: Medium, PR 2: Low, PR 3: High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 (per design); PR 3 may need sub-split if chunker grows |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | IngestionService extraction + document registry dedup | PR 1 | `pytest tests/unit/test_ingestion_service.py tests/unit/test_document_registry.py -v` | `POST /v1/ingest` against test DB; verify skip-unchanged on re-run | Revert `src/core/ingestion_service.py`, `src/adapters/document_registry.py`, `migrations/002_documents.sql`; restore inline pipeline in `api/ingestion.py` + `main.py` |
| 2 | Async job API + batched embedding + threaded parsers | PR 2 | `pytest tests/unit/test_job_registry.py tests/unit/test_ollama_embedder.py -v` | `POST /v1/ingest` → 202; `GET /v1/ingest/{id}` → progress; concurrent → 409 | Revert `src/core/job_registry.py`; restore sync pipeline in `api/ingestion.py`; revert batch embed in `ollama_embedder.py` |
| 3 | Structure-aware chunking with per-type config | PR 3 | `pytest tests/unit/test_chunker.py tests/unit/test_parsers.py -v` | Ingest PDF → verify `page_number` in chunks; ingest MD with list → verify no mid-item split | Revert `migrations/003_chunk_metadata.sql`; restore `parse() -> str` contract; revert `Chunk` fields |

---

## PR 1: IngestionService Extraction + Document Registry

### Phase 1.1 — Foundation: Migration + Port Extensions

- [x] **1.1.1** RED: Write integration test for migration 002 — verify `documents` table exists with all columns, `source_path` UNIQUE, `content_hash` indexed.
  - Create: `tests/integration/test_migration_002.py`
  - Deps: None
  - Acceptance: Test fails (table doesn't exist yet)
  - Complexity: small (~25 lines)

- [x] **1.1.2** GREEN: Create `migrations/002_documents.sql` — CREATE TABLE documents (id TEXT PK, source_path TEXT UNIQUE NOT NULL, title TEXT NOT NULL, content_hash TEXT NOT NULL, content_type TEXT NOT NULL, chunk_count INT DEFAULT 0, created_at/modified_at/indexed_at TIMESTAMPTZ). CREATE INDEX idx_documents_hash.
  - Create: `migrations/002_documents.sql`
  - Deps: 1.1.1
  - Acceptance: `pytest tests/integration/test_migration_002.py` passes
  - Complexity: small (~15 lines)

- [x] **1.1.3** RED: Write unit test for `SearchIndex.delete_chunks(doc_id)` port contract — verify protocol method exists and returns int.
  - Create: `tests/unit/test_search_index_port.py`
  - Deps: None
  - Acceptance: Test fails (method doesn't exist on protocol)
  - Complexity: small (~15 lines)

- [x] **1.1.4** GREEN: Add `delete_chunks(document_id: str) -> int` to `src/ports/search_index.py` Protocol. Implement in `src/adapters/pgvector_index.py` — DELETE FROM chunks WHERE document_id = $1.
  - Modify: `src/ports/search_index.py` (+4 lines), `src/adapters/pgvector_index.py` (+10 lines)
  - Deps: 1.1.3
  - Acceptance: Unit test passes; integration test with testcontainers verifies actual deletion
  - Complexity: small (~14 lines)

### Phase 1.2 — Content Hash + Filesystem Source

- [x] **1.2.1** RED: Write unit test for `FilesystemSource.scan()` — verify each result includes `content_hash` (SHA-256 hex of file bytes). Use tmp_path with known content.
  - Create: `tests/unit/test_filesystem_source_hash.py`
  - Deps: None
  - Acceptance: Test fails (scan results don't include content_hash)
  - Complexity: small (~30 lines)

- [x] **1.2.2** GREEN: Add `content_hash` computation to `src/adapters/filesystem_source.py` — read file bytes, compute SHA-256 hex digest, include in scan result dict.
  - Modify: `src/adapters/filesystem_source.py` (+15 lines)
  - Deps: 1.2.1
  - Acceptance: `pytest tests/unit/test_filesystem_source_hash.py` passes
  - Complexity: small (~15 lines)

### Phase 1.3 — DocumentRegistry Adapter

- [x] **1.3.1** RED: Write unit tests for `DocumentRegistry` diff logic — pure function tests for new/changed/renamed/deleted detection. Mock records, no DB. Cover: all unchanged (all skipped), one changed, one new, one deleted, one renamed (hash match + path diff), ambiguous rename (2:2 → delete+insert).
  - Create: `tests/unit/test_document_registry.py`
  - Deps: None
  - Acceptance: Tests fail (module doesn't exist)
  - Complexity: medium (~80 lines)

- [x] **1.3.2** GREEN: Create `src/adapters/document_registry.py` — `DocumentRecord` dataclass, `DocumentRegistry` class with `load_all()`, `upsert()`, `delete()`, `update_path()`, and `compute_diff(scan_results, registry)` static method implementing the rename detection algorithm from design.
  - Create: `src/adapters/document_registry.py`
  - Deps: 1.3.1, 1.1.2
  - Acceptance: `pytest tests/unit/test_document_registry.py` passes
  - Complexity: medium (~100 lines)

- [x] **1.3.3** GREEN (integration): Write integration test for `DocumentRegistry` CRUD against testcontainers — verify upsert, load_all, delete, update_path work against real DB with migration 002.
  - Create: `tests/integration/test_document_registry.py`
  - Deps: 1.3.2, 1.1.2
  - Acceptance: Integration tests pass with real DB
  - Complexity: medium (~60 lines)

### Phase 1.4 — IngestionService

- [x] **1.4.1** RED: Write unit tests for `IngestionService.run()` — mock all ports. Verify: skip-unchanged (hash match → no parse/chunk/embed calls), new file (full pipeline), changed file (delete old chunks + re-process), deleted file (delete chunks + registry delete), renamed file (update_path, no re-process), per-file failure handling (catches exception, records in failures list, continues).
  - Create: `tests/unit/test_ingestion_service.py`
  - Deps: 1.3.1
  - Acceptance: Tests fail (module doesn't exist)
  - Complexity: medium (~120 lines)

- [x] **1.4.2** GREEN: Create `src/core/ingestion_service.py` — `IngestionResult` dataclass, `IngestionService` class with `run(progress=None) -> IngestionResult`. Pipeline: scan → load registry → compute diff → for each new/changed (under semaphore if provided): parse → chunk → embed → delete_chunks → upsert → registry upsert. For deleted: delete_chunks → registry delete. For renamed: registry update_path.
  - Create: `src/core/ingestion_service.py`
  - Deps: 1.4.1, 1.3.2, 1.2.2
  - Acceptance: `pytest tests/unit/test_ingestion_service.py` passes
  - Complexity: large (~120 lines)

- [x] **1.4.3** REFRACTOR: Wire `IngestionService` into `src/container.py` — add `get_ingestion_service()` factory. Update `src/api/ingestion.py` to delegate to service (remove inline pipeline). Update `src/main.py::_run_startup_scan()` to use service.
  - Modify: `src/container.py` (+15 lines), `src/api/ingestion.py` (-70 +15 lines), `src/main.py` (-35 +10 lines)
  - Deps: 1.4.2
  - Acceptance: Existing tests still pass; `POST /v1/ingest` still works end-to-end
  - Complexity: medium (~40 lines net)

### Phase 1.5 — Integration Verification

- [x] **1.5.1** Write integration test for full pipeline: scan → dedup → upsert. Use testcontainers. Verify idempotency (second run skips all), stale cleanup (modify file → old chunks gone, new chunks present), deletion (remove file → chunks gone, registry row gone).
  - Create: `tests/integration/test_ingestion_pipeline.py`
  - Deps: 1.4.3
  - Acceptance: All integration scenarios pass
  - Complexity: medium (~80 lines)

---

## PR 2: Async Job API + Batched Processing

### Phase 2.1 — JobRegistry

- [x] **2.1.1** RED: Write unit tests for `JobRegistry` — submit returns job_id, get returns state, concurrent submit raises Conflict (409), update modifies fields, unknown job_id returns None.
  - Create: `tests/unit/test_job_registry.py`
  - Deps: None
  - Acceptance: Tests fail (module doesn't exist)
  - Complexity: small (~60 lines)

- [x] **2.1.2** GREEN: Create `src/core/job_registry.py` — `JobState` dataclass (job_id, state, total, processed, skipped, chunks, failed, failures), `JobRegistry` class with in-memory dict + asyncio.Lock. `submit()` raises `JobConflictError` if active job exists. `get()`, `update()` methods.
  - Create: `src/core/job_registry.py`
  - Deps: 2.1.1
  - Acceptance: `pytest tests/unit/test_job_registry.py` passes
  - Complexity: medium (~70 lines)

### Phase 2.2 — Config Additions

- [x] **2.2.1** Add `ingest_concurrency: int = 2` and `embed_batch_size: int = 64` to `src/config.py` Settings class.
  - Modify: `src/config.py` (+5 lines)
  - Deps: None
  - Acceptance: Settings loads with defaults; env vars `INGEST_CONCURRENCY`, `EMBED_BATCH_SIZE` override
  - Complexity: small (~5 lines)

### Phase 2.3 — Batched Embedding

- [x] **2.3.1** RED: Write unit test for `OllamaEmbedder.embed_batch()` — mock httpx. Verify: 20 texts → single call with `input: string[]`; 100 texts → two calls (64 + 36); ordering preserved.
  - Create: `tests/unit/test_ollama_embedder_batch.py`
  - Deps: None
  - Acceptance: Tests fail (current impl sends one per text)
  - Complexity: small (~40 lines)

- [x] **2.3.2** GREEN: Modify `src/adapters/ollama_embedder.py` — `embed_batch()` splits texts into groups of `embed_batch_size`, sends each group as `{"model": ..., "input": string[]}` (one HTTP call per batch), concatenates results preserving order.
  - Modify: `src/adapters/ollama_embedder.py` (+25 lines)
  - Deps: 2.3.1, 2.2.1
  - Acceptance: `pytest tests/unit/test_ollama_embedder_batch.py` passes
  - Complexity: small (~25 lines)

### Phase 2.4 — Threaded Parsers

- [x] **2.4.1** RED: Write unit test verifying parsers run via `asyncio.to_thread` — mock a blocking parser, verify event loop not blocked (concurrent hash computation succeeds during parse).
  - Create: `tests/unit/test_parsers_threaded.py`
  - Deps: None
  - Acceptance: Test fails (current parsers block event loop)
  - Complexity: small (~30 lines)

- [x] **2.4.2** GREEN: Wrap sync parser calls in `src/adapters/parsers.py` with `asyncio.to_thread()`. Each parser's `parse()` method becomes async, delegates blocking lib call to thread.
  - Modify: `src/adapters/parsers.py` (+15 lines)
  - Deps: 2.4.1
  - Acceptance: `pytest tests/unit/test_parsers_threaded.py` passes; existing parser tests still pass
  - Complexity: small (~15 lines)

### Phase 2.5 — IngestionService Concurrency + Progress

- [x] **2.5.1** RED: Write unit test for `IngestionService` semaphore bounding — verify at most N docs processed concurrently (N from config). Verify progress callback receives atomic counter updates.
  - Modify: `tests/unit/test_ingestion_service.py` (+40 lines)
  - Deps: 2.1.2
  - Acceptance: Tests fail (no semaphore, no progress callback)
  - Complexity: small (~40 lines)

- [x] **2.5.2** GREEN: Modify `src/core/ingestion_service.py` — add `asyncio.Semaphore(ingest_concurrency)` wrapping per-doc processing. Accept optional `progress: JobState` parameter; update counters atomically after each doc (processed++, skipped++, chunks+=N, failed++).
  - Modify: `src/core/ingestion_service.py` (+30 lines)
  - Deps: 2.5.1, 2.2.1
  - Acceptance: All ingestion service tests pass including concurrency bound
  - Complexity: small (~30 lines)

### Phase 2.6 — API Wiring

- [x] **2.6.1** RED: Write integration tests for async job API — POST /v1/ingest → 202 + job_id; GET /v1/ingest/{job_id} → progress with state/counts; concurrent POST → 409; unknown job_id → 404.
  - Create: `tests/integration/test_ingest_api.py`
  - Deps: 2.1.2
  - Acceptance: Tests fail (API still synchronous)
  - Complexity: medium (~60 lines)

- [x] **2.6.2** GREEN: Rewrite `src/api/ingestion.py` — POST /v1/ingest calls `JobRegistry.submit()`, creates `asyncio.create_task(_run_job(job_id))`, returns 202. GET /v1/ingest/{job_id} returns JobState as JSON. 409 on `JobConflictError`. 404 on unknown.
  - Modify: `src/api/ingestion.py` (+40 lines)
  - Deps: 2.6.1, 2.5.2
  - Acceptance: `pytest tests/integration/test_ingest_api.py` passes
  - Complexity: medium (~40 lines)

- [x] **2.6.3** GREEN: Update `src/main.py` lifespan — startup scan calls `JobRegistry.submit()` + `IngestionService.run(progress=job)` as background task. Wire `JobRegistry` into `src/container.py`.
  - Modify: `src/main.py` (+15 lines), `src/container.py` (+10 lines)
  - Deps: 2.6.2
  - Acceptance: App starts, background job runs, queryable via GET
  - Complexity: small (~25 lines)

---

## PR 3: Structure-Aware Chunking

### Phase 3.1 — Domain Models

- [x] **3.1.1** RED: Write unit tests for `ParsedDocument` block model — verify construction of Heading, Paragraph, ListBlock, TableBlock, PageMarker. Verify `Chunk` accepts optional `page_number` and `anchor`.
  - Create: `tests/unit/test_parsed_document.py`
  - Deps: None
  - Acceptance: Tests fail (models don't exist)
  - Complexity: small (~40 lines)

- [x] **3.1.2** GREEN: Add block types to `src/ports/models.py` — `Heading(level, text)`, `Paragraph(text)`, `ListItem(text, ordered)`, `ListBlock(items)`, `TableBlock(headers, rows)`, `PageMarker(page_number)`, `ParsedDocument(blocks, metadata)`. Extend `Chunk` with `page_number: int | None = None` and `anchor: str | None = None`.
  - Modify: `src/ports/models.py` (+50 lines)
  - Deps: 3.1.1
  - Acceptance: `pytest tests/unit/test_parsed_document.py` passes
  - Complexity: small (~50 lines)

### Phase 3.2 — Migration 003

- [x] **3.2.1** RED: Write integration test for migration 003 — verify `chunks` table has nullable `page_number INT` and `anchor TEXT` columns. Verify existing rows have NULL for new columns.
  - Create: `tests/integration/test_migration_003.py`
  - Deps: None
  - Acceptance: Test fails (columns don't exist)
  - Complexity: small (~20 lines)

- [x] **3.2.2** GREEN: Create `migrations/003_chunk_metadata.sql` — ALTER TABLE chunks ADD COLUMN page_number INT, ADD COLUMN anchor TEXT.
  - Create: `migrations/003_chunk_metadata.sql`
  - Deps: 3.2.1
  - Acceptance: `pytest tests/integration/test_migration_003.py` passes
  - Complexity: small (~5 lines)

### Phase 3.3 — Parser Contract Break

- [x] **3.3.1** RED: Write unit tests for new parser contract — each parser (PDF, DOCX, HTML, TXT/MD) returns `ParsedDocument` with correct block types. PDF includes PageMarker blocks. DOCX preserves tables as TableBlock. HTML preserves headings and lists.
  - Create: `tests/unit/test_parsers_blocks.py`
  - Deps: 3.1.2
  - Acceptance: Tests fail (parsers return str, not ParsedDocument)
  - Complexity: medium (~80 lines)

- [x] **3.3.2** GREEN: Update `src/ports/parser.py` — change return type from `str` to `ParsedDocument`. Update all 4 parsers in `src/adapters/parsers.py` to return `ParsedDocument` with appropriate blocks. PDF: use pymupdf page iteration → PageMarker between pages. DOCX: python-docx paragraphs + tables. HTML: bs4 heading/paragraph/list tags. TXT/MD: heading detection by prefix.
  - Modify: `src/ports/parser.py` (+5 -5 lines), `src/adapters/parsers.py` (+80 lines)
  - Deps: 3.3.1
  - Acceptance: `pytest tests/unit/test_parsers_blocks.py` passes; `asyncio.to_thread` wrapping preserved
  - Complexity: large (~85 lines)

### Phase 3.4 — Block-Aware Chunker

- [x] **3.4.1** RED: Write unit tests for block-aware chunking — verify: list items not split mid-item, table rows kept together, heading hierarchy preserved in section_path, per-type config resolution (CHUNK_MAX_PDF=600, CHUNK_MAX_MD=500, etc.), short doc → single chunk, page_number propagated from PageMarker blocks.
  - Modify: `tests/unit/test_chunker.py` (+100 lines)
  - Deps: 3.1.2
  - Acceptance: Tests fail (chunker doesn't accept ParsedDocument)
  - Complexity: medium (~100 lines)

- [x] **3.4.2** RED: Write unit test for per-type config resolution — verify env vars `CHUNK_MIN_{TYPE}`, `CHUNK_MAX_{TYPE}`, `CHUNK_OVERLAP_{TYPE}` resolve correctly for each source type.
  - Create: `tests/unit/test_chunking_config.py`
  - Deps: None
  - Acceptance: Tests fail (config doesn't exist)
  - Complexity: small (~35 lines)

- [x] **3.4.3** GREEN: Add per-type chunking config to `src/config.py` — `chunk_min_pdf`, `chunk_max_pdf`, `chunk_overlap_pdf`, etc. for pdf/md/docx/html/txt. Add `get_chunking_config(source_type)` method.
  - Modify: `src/config.py` (+20 lines)
  - Deps: 3.4.2
  - Acceptance: `pytest tests/unit/test_chunking_config.py` passes
  - Complexity: small (~20 lines)

- [x] **3.4.4** GREEN: Update `src/ports/chunker.py` — change `split(text: str, ...)` to `split(doc: ParsedDocument, source_type: str)`. Rewrite `src/adapters/recursive_chunker.py` — iterate blocks, track heading hierarchy for section_path, accumulate text within boundaries, never split ListBlock or TableBlock, attach page_number from PageMarker, use per-type config.
  - Modify: `src/ports/chunker.py` (+5 -5 lines), `src/adapters/recursive_chunker.py` (+80 -60 lines)
  - Deps: 3.4.1, 3.4.3
  - Acceptance: `pytest tests/unit/test_chunker.py tests/unit/test_chunking_config.py` passes
  - Complexity: large (~80 lines net)

### Phase 3.5 — Index + Retrieval Adaptation

- [x] **3.5.1** RED: Write unit test for `_row_to_chunk` with new nullable columns — verify NULL → None, value → int/str. Write test for `upsert_chunks` including page_number and anchor in INSERT.
  - Create: `tests/unit/test_pgvector_chunk_metadata.py`
  - Deps: 3.1.2
  - Acceptance: Tests fail (columns not handled)
  - Complexity: small (~30 lines)

- [x] **3.5.2** GREEN: Update `src/adapters/pgvector_index.py` — `upsert_chunks` INSERT includes page_number, anchor. `_row_to_chunk` uses `row.get("page_number")` and `row.get("anchor")` with None default.
  - Modify: `src/adapters/pgvector_index.py` (+20 lines)
  - Deps: 3.5.1, 3.2.2
  - Acceptance: `pytest tests/unit/test_pgvector_chunk_metadata.py` passes
  - Complexity: small (~20 lines)

- [x] **3.5.3** GREEN: Update `src/core/retrieval.py` — `_row_to_chunk` (if duplicated here) uses `.get()` for new columns. Verify citation construction tolerates None page_number.
  - Modify: `src/core/retrieval.py` (+5 lines)
  - Deps: 3.5.2
  - Acceptance: Existing retrieval tests pass; new chunks with page_number retrievable
  - Complexity: small (~5 lines)

### Phase 3.6 — End-to-End Verification

- [x] **3.6.1** Write integration test: ingest PDF with known pages → verify chunks have correct page_number values. Ingest MD with 50-item list → verify no mid-item split. Ingest DOCX with table → verify table content preserved in chunks.
  - Create: `tests/integration/test_structure_aware_chunking.py`
  - Deps: 3.4.4, 3.5.2
  - Acceptance: All structure-aware scenarios pass end-to-end
  - Complexity: medium (~70 lines)

---

## Task Summary

| PR | Phase | Tasks | Focus |
|----|-------|-------|-------|
| PR 1 | 1.1 Foundation | 4 | Migration + port extensions |
| PR 1 | 1.2 Hash | 2 | Content hash in filesystem source |
| PR 1 | 1.3 Registry | 3 | DocumentRegistry adapter + diff |
| PR 1 | 1.4 Service | 3 | IngestionService + wiring |
| PR 1 | 1.5 Integration | 1 | Full pipeline verification |
| **PR 1 Total** | | **13** | |
| PR 2 | 2.1 Jobs | 2 | JobRegistry |
| PR 2 | 2.2 Config | 1 | Concurrency + batch config |
| PR 2 | 2.3 Embed | 2 | Native batch embedding |
| PR 2 | 2.4 Threads | 2 | asyncio.to_thread parsers |
| PR 2 | 2.5 Concurrency | 2 | Semaphore + progress |
| PR 2 | 2.6 API | 3 | 202/GET/409 endpoints |
| **PR 2 Total** | | **12** | |
| PR 3 | 3.1 Models | 2 | ParsedDocument + Chunk fields |
| PR 3 | 3.2 Migration | 2 | page_number + anchor columns |
| PR 3 | 3.3 Parsers | 2 | Parser contract break |
| PR 3 | 3.4 Chunker | 4 | Block-aware chunking + config |
| PR 3 | 3.5 Index | 3 | pgvector + retrieval adaptation |
| PR 3 | 3.6 E2E | 1 | Structure-aware verification |
| **PR 3 Total** | | **14** | |
| **Grand Total** | | **39** | |
