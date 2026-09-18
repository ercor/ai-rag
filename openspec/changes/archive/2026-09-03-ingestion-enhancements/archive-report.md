# Archive Report: ingestion-enhancements

**Change**: ingestion-enhancements
**Archived to**: `openspec/changes/archive/2026-09-03-ingestion-enhancements/`
**Date**: 2026-09-03
**Verdict**: PASS
**Branch**: feature/iter1-ingestion-enhancements

## Executive Summary

Three chained PRs delivering ingestion scale and performance foundations: shared IngestionService with document-registry dedup, async job API with batched embedding and threaded parsers, and structure-aware chunking with per-type configuration. 39/39 tasks complete, 151 unit tests passing, verify verdict PASS.

## What Was Implemented

### PR 1: IngestionService Extraction + Document Registry (13 tasks)
- Extracted shared `IngestionService` from duplicated pipeline (api/ingestion.py + main.py)
- Created `documents` table (migration 002) with SHA-256 content hash
- `DocumentRegistry` adapter: skip-unchanged, rename detection, deletion cleanup, stale chunk removal
- `SearchIndex.delete_chunks(doc_id)` port extension

### PR 2: Async Job API + Batched Processing (12 tasks)
- `JobRegistry` in-memory with asyncio.Lock; POST /v1/ingest → 202 + job_id; GET /v1/ingest/{job_id} → progress
- 409 Conflict on concurrent submission; 404 on unknown job_id
- Bounded concurrency: `asyncio.Semaphore(ingest_concurrency=2)`
- Native batch embedding: `OllamaEmbedder.embed_batch()` splits at `embed_batch_size=64`
- Threaded parsers: `asyncio.to_thread()` wrapping all sync parser libraries

### PR 3: Structure-Aware Chunking (14 tasks)
- `ParsedDocument` block model: Heading, Paragraph, ListBlock, TableBlock, PageMarker
- Parser contract break: `parse() -> str` → `parse() -> ParsedDocument` (all 4 parsers)
- Block-aware chunker: respects ListBlock/TableBlock boundaries, heading hierarchy in section_path
- Per-type chunking config: `CHUNK_MIN_{TYPE}`, `CHUNK_MAX_{TYPE}`, `CHUNK_OVERLAP_{TYPE}`
- Migration 003: nullable `page_number INT` + `anchor TEXT` on chunks table

## Key Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| A1 | IngestionService in `src/core/` | Follows hexagonal layout; core owns orchestration |
| A2 | DocumentRegistry in `src/adapters/` | Clean port/adapter split; registry is infrastructure |
| A3 | JobRegistry in-memory | Simple; lost on restart acceptable (ingestion idempotent) |
| A4 | ParsedDocument in `ports/models.py` | Shared domain model; parsers and chunkers both import |
| A5 | document_id = sha256(path)[:16] | Backward-compatible with existing chunks |
| A6 | Nullable page_number + anchor columns | Migration 003 additive; existing rows get NULLs |
| A7 | Parser contract break in one PR | Clean break; all parser tests updated together |

## Test Coverage

| Layer | Tests | Status |
|-------|-------|--------|
| Unit | 151 passed / 0 failed / 4 skipped | ✅ |
| Integration (Docker-independent) | 12 passed / 0 failed | ✅ |
| Integration (Docker required) | 36 errors (Docker unavailable) | ⚠️ Not verified at runtime |

## Verification Results

**Verdict**: PASS (per `verify-report.md`)
- 39/39 tasks complete
- 18/18 requirements covered
- 31/32 scenarios compliant, 2 partial, 1 untested, 0 failing
- TDD compliance: 6/6 checks passed
- All critical issues resolved

## Warnings and Suggestions (from verify report)

**Non-blocking warnings**:
1. 5 ruff F841 unused-variable warnings (pg_answer_repository.py, query_pipeline.py, test_ingestion_service.py)
2. No test for "Unsupported format skipped" scenario (parser raises ValueError but no E2E test)
3. 36 Docker-dependent integration tests could not run in verify environment
4. Config deviation: `chunk_overlap` implemented as `int=50` (design said `float=0.10` ratio); `chunk_max_md=600` (design said 500)

**Suggestions**:
- Consider adding pytest-cov for changed-file coverage measurement
- Clean up F841 warnings in a follow-up

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| ingestion-job-tracking | Created | 4 requirements, 8 scenarios (new domain) |
| document-registry | Created | 8 requirements, 10 scenarios (new domain) |
| document-ingestion | Updated | 3 modified, 3 added, 1 removed requirement |

## Archive Contents

- proposal.md ✅
- exploration.md ✅
- design.md ✅
- tasks.md ✅ (39/39 tasks complete)
- verify-report.md ✅ (verdict: PASS)
- specs/ ✅ (3 delta specs)

## Source of Truth Updated

The following main specs now reflect the new behavior:
- `openspec/specs/ingestion-job-tracking/spec.md` (new)
- `openspec/specs/document-registry/spec.md` (new)
- `openspec/specs/document-ingestion/spec.md` (updated)

## Mechanical Copy Verification

All spec copies and archive move verified via `diff -r` with empty diff output (byte-identical).

## SDD Cycle Complete

The change has been fully planned, implemented, verified, and archived. Ready for the next change.
