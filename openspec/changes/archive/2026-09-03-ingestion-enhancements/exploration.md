# Exploration: ingestion-enhancements (Iteration 1)

- **Change**: `ingestion-enhancements` — Iteration 1: independent scale/performance quick wins
- **Branch**: `feature/iter1-ingestion-enhancements` (from `feature/mvp-scope`)
- **Date**: 2026-08-30
- **Backbone**: PROJECT_README.md §6 (ingestion flow), §7 (chunking), §10 (scaling model)
- **Out of scope**: GPU acceleration, caching, auth, reranking, distributed architecture

## Current State

Ingestion is a synchronous sequential loop, duplicated in two places:

1. `POST /v1/ingest` (`src/api/ingestion.py`) and
2. `_run_startup_scan()` (`src/main.py`, ~60 lines of copy-pasted pipeline logic).

Per-file pipeline today:

| Stage | Adapter | Behavior today |
|---|---|---|
| Scan | `FilesystemSource.scan()` | rglob WATCH_DIR; returns `path/title/extension/size` only — no mtime, no content hash |
| Parse | `MultiFormatParser.parse()` → `str` | Plain-text output. PDF pages joined with `\n\n` (page boundaries lost). DOCX reads `doc.paragraphs` only — **tables are silently dropped**. HTML uses `get_text()` — headings/structure lost. `async def` but calls blocking sync libs (pymupdf/docx/bs4) — blocks the event loop |
| Chunk | `RecursiveChunker.split()` | One global config (300–600 tokens at 4 chars/token heuristic, 10% char overlap). Heading detection only for markdown `#` and underline styles. `content_hash` = sha256(chunk text)[:16] |
| Embed | `OllamaEmbedder.embed_batch()` | **One HTTP POST per text**, sequential. Ollama `/api/embed` natively accepts `input: string[]` (verified against docs.ollama.com) — unused. Fail-fast: one error aborts the whole document |
| Index | `PgvectorIndex.upsert_chunks()` | One `INSERT ... ON CONFLICT` per chunk; unique index `(document_id, chunk_index, content_hash)`. Dedup only avoids the *write* — parse/chunk/embed compute already happened |

Schema: single `chunks` table (migrations/001_init.sql). No `documents` table, no change detection, no deletion handling, no progress/job state.

**Core gap**: all deduplication happens after all the expensive work; nothing skips or batches; parsers discard structure before the chunker ever sees it.

## Affected Areas

- `src/adapters/filesystem_source.py` — add content hash (+mtime) to scan metadata
- `src/adapters/parsers.py` — structure-preserving output; unblock event loop
- `src/adapters/recursive_chunker.py` — per-type config; boundary handling (lists/tables)
- `src/adapters/ollama_embedder.py` — true batched `/api/embed` calls with bounded batch size
- `src/adapters/pgvector_index.py` — bulk upsert; existing-hash lookups; stale-chunk cleanup
- `src/api/ingestion.py` — dedup-aware orchestration; job/progress semantics
- `src/main.py` — startup scan must be consolidated with the API path (currently duplicated)
- `src/ports/models.py` — Chunk gains optional page/anchor metadata (item 2)
- `src/ports/chunker.py`, `src/ports/parser.py` — contract changes if block model adopted (item 2)
- `migrations/` — 002+: `documents` table (item 1), chunk anchor columns (item 2)

## Item 1 — Document Deduplication

**Exists**: chunk-level `content_hash`; DB unique index makes re-ingestion idempotent at write level.

**Missing**: file-level content hash; document registry; skip-unchanged logic; stale-chunk cleanup.

Known correctness issues in the current model:
- Changed document: new chunks insert, but **old chunks with displaced indexes remain** (unique index only protects identical triples) — stale rows accumulate.
- Renamed file: `document_id` is derived from path hash → new identity, **old chunks orphaned forever**.

### Approaches

1. **Content-hash document registry (recommended)** — new `documents` table (`document_id PK, source_path, content_hash, size, mtime, chunk_count, ingested_at`); scan computes SHA-256 of file bytes; skip parse/chunk/embed entirely when hash unchanged; on change, upsert new chunk set and delete rows for that `document_id` not in the new set; on file disappearance from scan, delete its chunks (backbone FR-03). Response gains `skipped` count.
   - Pros: eliminates 100% of redundant compute; enables deletion semantics; cheap hash check; aligns with backbone "content hash" fetcher step and "incremental updates preferred over full rebuilds"
   - Cons: new migration; one extra DB roundtrip per file; cleanup policy is a behavior change (needs a decision)
   - Effort: Low–Medium
2. **mtime+size heuristic** — skip if `(mtime, size)` unchanged.
   - Pros: no hashing cost, trivial
   - Cons: unreliable (touch/edit-same-size/clock issues); backbone explicitly uses content hash; wrong answers are silent
   - Effort: Low (but rejected on correctness)
3. **Cross-document chunk embedding reuse** — before embedding, look up existing `content_hash → embedding` and reuse.
   - Pros: saves embeddings when corpora share boilerplate
   - Cons: requires tracking `embedding_model` per row to avoid cross-model reuse (backbone canonical schema has `embedding_model/version`); low value on a 10–100 doc corpus
   - Effort: Medium — **defer or keep as optional stretch**

**Direction**: Approach 1 as the item scope; Approach 3 deferred. Decision needed on cleanup policy (see Ambiguities A2).

## Item 2 — Advanced Chunking Strategies

**Backbone requirements** (PROJECT_README §7 Chunking): preserve headings, paragraphs, lists, table structure, page numbers, section anchors; 300–600 tokens with 10–15% overlap where structure doesn't suffice; prepend title/section context for retrieval while preserving the original span for citations; **evaluate chunk sizes by source type rather than one global setting**.

**Exists**: heading-aware recursive splitting with section_path breadcrumbs; token bounds + overlap (global only).

**Missing**: parsers emit flat text — structure is destroyed before chunking (PDF page breaks, DOCX tables, HTML headings/lists); no per-source-type config; no table/list boundary protection; no page numbers or anchors in Chunk metadata or DB.

### Approaches

1. **Full block model, all formats incl. PDF tables** — parser returns `ParsedDocument` (typed blocks: heading/paragraph/list/table + page markers); chunker becomes block-aware; pymupdf `find_tables()` for PDF tables.
   - Pros: full backbone fidelity
   - Cons: PDF table extraction is genuinely hard/noisy; highest risk and effort, likely breaks the "quick win" budget
   - Effort: High
2. **Block model for reliable formats + page markers (recommended)** — same `ParsedDocument` contract, but: markdown/HTML/DOCX tables and lists preserved structurally; PDF gets page-boundary markers (`[page N]` or page metadata per block) without table extraction; per-source-type chunking config (min/max/overlap keyed by extension, sensible defaults); chunker never splits inside a list item or table row (oversized tables split at row boundaries with header repeated); Chunk gains optional `page`/anchor metadata + DB column. PDF table extraction deferred to a later iteration.
   - Pros: delivers backbone structure fidelity where extraction is reliable; per-type config is pure config; bounded risk
   - Cons: Parser port contract change ripples to tests; PDF tables still best-effort
   - Effort: Medium–High (largest of the three)
3. **Config-only tuning** — per-type min/max/overlap without parser changes.
   - Pros: tiny
   - Cons: ignores the backbone's structural requirements; doesn't fix dropped tables/lost pages
   - Effort: Low (rejected as insufficient)

**Direction**: Approach 2. The parser contract change (`str` → `ParsedDocument`) is the load-bearing decision; everything else follows. Chunk model changes ripple to `pgvector_index._row_to_chunk`, retrieval, and possibly frontend citation rendering — must be verified.

## Item 3 — Batch Processing for Large Document Sets

**Exists**: per-document error isolation (`failures` list); idempotent upserts make retries safe.

**Missing**: true embedding batching; concurrency; progress; backpressure; request-timeout safety for large sets.

### Approaches

1. **Async job + bounded concurrency (recommended)** — `POST /v1/ingest` returns `202 {job_id}`; in-memory job registry; `GET /v1/ingest/{job_id}` returns progress (`total/processed/skipped/failed/state`). Internals: `asyncio.Semaphore` bounds in-flight documents (default 2–4, configurable); embedder switches to native batched `/api/embed` with bounded batch size (e.g. ≤64 texts/request); blocking parsers run via `asyncio.to_thread` so CPU-bound parsing overlaps without stalling the event loop; backpressure = semaphore + scan list as the queue (no unbounded fan-out, no unbounded memory — keep per-document lifecycle: embed+upsert then release). Aligns with backbone: "asynchronous ingestion plane", "embedding is batched and rate-controlled", "backpressure pauses ... before it overloads downstream".
   - Pros: no HTTP timeout risk; observable progress; real throughput win from batched embed calls alone (measured ~2.4x elsewhere for identical switch); event loop stays responsive
   - Cons: new endpoint + job state; in-memory jobs lost on restart (acceptable at this scale; idempotency makes restart safe)
   - Effort: Medium
2. **Keep synchronous endpoint, richer summary only** — add per-file statuses + skipped counts, still blocking.
   - Pros: minimal surface
   - Cons: timeout risk grows with corpus size; no progress; doesn't satisfy "progress reporting" requirement
   - Effort: Low (rejected as insufficient for the stated goal)

**Direction**: Approach 1, in-memory job registry (no persisted jobs in this iteration). Note: Ollama serializes model execution on the server, so concurrency mostly helps parse/IO overlap — batch size of the embed call is the dominant throughput lever.

## Dependencies Between Items

- **Shared prerequisite**: extract the duplicated pipeline into a single `IngestionService` (core/service layer) consumed by both the API and the startup scan. Item 1 and Item 3 both rewrite orchestration — without extraction they collide on two copies of the same logic.
- Item 1 ⟂ Item 2: independent, but Item 2 changes chunk content/hashes — dedup keyed on hashes composes cleanly (a chunker change simply re-ingests once).
- Item 1 → Item 3: dedup skip-check belongs inside the same service that batching orchestrates.
- Item 2 is standalone (parser/chunker/schema) but re-ingestion testing becomes cheap only after Item 1 exists.

## Recommended Implementation Order

1. **Item 1 — Deduplication** (incl. `IngestionService` extraction): smallest surface, biggest immediate win, makes every later re-run cheap; introduces the `documents` registry that Item 3 reports against.
2. **Item 3 — Batch processing**: builds on the service; batched embed + semaphore + job endpoint.
3. **Item 2 — Chunking**: largest and riskiest (port contract + schema change); done last so dedup and jobs already exist for safe re-ingestion experiments.

Delivery: one PR per item (3 chained slices targeting the iteration branch). Item 2 alone is forecast to approach/exceed the 400-line review budget — consider splitting it (parser contract + config first, boundary handling second) if the tasks phase confirms.

## Ambiguities (need resolution)

- **A1 — Progress semantics**: async job API (202 + GET status, recommended) vs. synchronous enriched summary? Backbone says async ingestion plane; confirm for this iteration.
- **A2 — Cleanup policy**: on changed document, delete displaced old chunks (recommended: yes). On file removed from WATCH_DIR, delete its chunks (backbone FR-03; recommended: yes)? This changes behavior from append-only to reconciling.
- **A3 — Chunk-level embedding reuse across documents**: defer (recommended) or include?
- **A4 — Chunking config mechanism**: env vars (current convention, `CHUNKING_*`) vs. dedicated YAML (e.g. `data/chunking.yaml`)? Recommend env-with-defaults per type to keep the config story consistent.
- **A5 — PDF tables in scope?** Recommend no (page markers only); pymupdf `find_tables()` deferred.
- **A6 — Concurrency defaults**: semaphore value and embed batch size defaults (recommend 2 docs in flight, ≤64 texts per embed request; both configurable via env).

A1–A2 should be answered before proposal; A3–A6 can carry recommended defaults into the proposal.

## Risks

- **Chunk model/DB schema change (Item 2) ripples** to retrieval (`_row_to_chunk`), answers/citations, and frontend rendering — must be traced end-to-end in design.
- **Orphaned/stale rows** if cleanup policy (A2) is declined — index quality degrades over re-ingestions.
- **Blocking parsers under concurrency**: if not moved to threads, semaphore concurrency still stalls the event loop.
- **Ollama batch input size**: oversized batch requests can exhaust server memory or hit context limits — bound batch size and keep `truncate` behavior explicit.
- **In-memory job registry**: job state lost on backend restart; acceptable because ingestion is idempotent and restartable, but must be documented.
- **Parser contract break**: existing unit/integration tests assume `parse() -> str`; all must be migrated in the same PR (strict TDD: write new contract tests first).
- **Startup-scan behavior change**: dedup makes startup scans near-instant when nothing changed — desirable, but logs/response shape change.

## Ready for Proposal

**Yes, conditionally** — resolve A1 and A2 with the user first (progress style and cleanup policy). A3–A6 can proceed with the recommended defaults stated above. Recommended order: dedup → batch → chunking, three chained PR slices.
