# Design: Ingestion Enhancements (Iteration 1)

## Technical Approach

Three chained PRs on `feature/iter1-ingestion-enhancements`, each independently deployable. The core move: extract the duplicated pipeline (api/ingestion.py + main.py::_run_startup_scan) into a single `IngestionService`, then layer document-registry dedup, async job tracking, batched embedding, and structure-aware chunking on top.

**PR 1** — IngestionService extraction + document registry (dedup, stale cleanup, rename detection).
**PR 2** — Async job API (202/GET/409) + bounded concurrency + native batch embed + threaded parsers.
**PR 3** — ParsedDocument block model + per-type chunking config + page/anchor chunk metadata.

## Architecture Decisions

### A1: IngestionService location

| Option | Tradeoff | Decision |
|--------|----------|----------|
| `src/core/ingestion_service.py` | Follows hexagonal layout; core owns orchestration | **Chosen** |
| `src/services/ingestion.py` | New top-level dir; breaks existing convention | Rejected |

### A2: Document registry storage

| Option | Tradeoff | Decision |
|--------|----------|----------|
| New `documents` table + `DocumentRegistry` adapter in `src/adapters/` | Clean port/adapter split; registry is infrastructure concern | **Chosen** |
| Add columns to `chunks` table | Breaks chunk identity; denormalized | Rejected |

### A3: Job registry storage

| Option | Tradeoff | Decision |
|--------|----------|----------|
| In-memory dict with asyncio.Lock | Simple; lost on restart (acceptable — ingestion idempotent) | **Chosen** |
| DB-backed job table | Over-engineering for MVP iteration; adds migration | Rejected |

### A4: ParsedDocument model location

| Option | Tradeoff | Decision |
|--------|----------|----------|
| `src/ports/models.py` alongside Chunk | Shared domain model; parsers and chunkers both import it | **Chosen**
| `src/ports/parser.py` inline | Couples model to port file | Rejected |

### A5: document_id strategy

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Keep `sha256(source_path)[:16]` | Backward-compatible with existing chunks; rename changes doc_id | **Chosen for PR 1** |
| Use `documents.id` (UUID or hash of content) | Breaks existing chunk references | Deferred to future iteration |

### A6: Chunk schema extension (PR 3)

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Add nullable `page_number INT` + `anchor TEXT` columns to `chunks` | Migration 003 is additive; existing rows get NULLs; `_row_to_chunk` uses `.get()` | **Chosen** |
| New `chunk_metadata JSONB` column | Flexible but loses type safety; harder to query | Rejected |

### A7: Parser contract migration (PR 3)

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Break: `parse() -> ParsedDocument` in one PR | Clean break; all parser tests updated together | **Chosen** (strict TDD: new contract tests first) |
| Dual: `parse() -> str` + `parse_blocks() -> ParsedDocument` | Gradual migration; more code; chunker must handle both | Rejected (complexity not worth it for 4 parsers) |

## Data Flow

### PR 1: Submit + Process with Dedup

```
POST /v1/ingest
      │
      ▼
IngestionService.run()
      │
      ├─ FilesystemSource.scan() ──→ [{path, title, content_hash, ...}]
      │
      ├─ DocumentRegistry.load_all() ──→ {path: (hash, doc_id)}
      │
      ├─ Diff: new / changed / unchanged / renamed / deleted
      │
      ├─ For each new/changed doc (under semaphore):
      │     ├─ Parser.parse(path) ──→ str
      │     ├─ Chunker.split(text, ...) ──→ [Chunk]
      │     ├─ Embedder.embed_batch(texts) ──→ [vec]
      │     ├─ SearchIndex.delete_chunks(doc_id)  ← stale cleanup
      │     └─ SearchIndex.upsert_chunks(chunks, embeddings)
      │
      ├─ DocumentRegistry.upsert(doc_record)
      │
      └─ For deleted docs:
            ├─ SearchIndex.delete_chunks(doc_id)
            └─ DocumentRegistry.delete(doc_id)
```

### PR 2: Async Job Flow

```
POST /v1/ingest ──→ JobRegistry.submit() ──→ 202 {job_id}
                          │
                          └─ asyncio.create_task(_run_job(job_id))
                                    │
                                    ├─ state: pending → running
                                    ├─ IngestionService.run(job_progress=job)
                                    │     └─ atomic counters: processed++, skipped++, chunks+=N
                                    ├─ state: running → completed
                                    └─ on system error: → failed

GET /v1/ingest/{job_id} ──→ JobRegistry.get(job_id) ──→ {state, total, processed, ...}
```

### PR 3: Structure-Aware Chunking

```
Parser.parse(path) ──→ ParsedDocument
                          │
                          ├─ blocks: [Heading, Paragraph, List, Table, PageMarker]
                          │
                          ▼
                    BlockChunker.split(doc, source_type)
                          │
                          ├─ Per-type config: CHUNK_MAX_PDF=600, CHUNK_MAX_MD=500, ...
                          ├─ Never split inside List or Table block
                          ├─ Preserve heading hierarchy → section_path
                          └─ Attach page_number from PageMarker blocks
                                    │
                                    ▼
                              Chunk(... page_number=N, anchor="§2.1")
```

### End-to-End Chunk Schema Impact Trace

```
Chunk model (ports/models.py)
    │ +page_number: int | None
    │ +anchor: str | None
    │
    ├── RecursiveChunker.split()     ← sets page_number, anchor
    ├── PgvectorIndex.upsert_chunks() ← INSERT new columns
    ├── PgvectorIndex._row_to_chunk() ← row.get("page_number"), row.get("anchor")
    ├── retrieval.py._chunk_key()     ← unchanged (uses doc_id:chunk_index:content_hash)
    ├── api/answers.py citations      ← may surface page_number in citation metadata
    └── frontend SourcePanel           ← MAY display page number (future iteration)
```

## File Changes

### PR 1: IngestionService + Document Registry

| File | Action | Description |
|------|--------|-------------|
| `src/core/ingestion_service.py` | Create | Shared pipeline: scan → diff → parse → chunk → embed → upsert |
| `src/adapters/document_registry.py` | Create | CRUD for `documents` table; diff logic (new/changed/renamed/deleted) |
| `migrations/002_documents.sql` | Create | `documents` table with columns per spec |
| `src/adapters/filesystem_source.py` | Modify | Add `content_hash` (SHA-256 of file bytes) to scan output |
| `src/adapters/pgvector_index.py` | Modify | Add `delete_chunks(doc_id)` method for stale cleanup |
| `src/ports/search_index.py` | Modify | Add `delete_chunks(doc_id)` to protocol |
| `src/api/ingestion.py` | Modify | Delegate to IngestionService (remove inline pipeline) |
| `src/main.py` | Modify | Replace `_run_startup_scan()` with IngestionService call |
| `src/container.py` | Modify | Add `get_document_registry()` factory |
| `src/config.py` | Modify | No new config in PR 1 |

### PR 2: Job Tracking + Batching

| File | Action | Description |
|------|--------|-------------|
| `src/core/job_registry.py` | Create | In-memory job store with asyncio.Lock; submit/get/list |
| `src/api/ingestion.py` | Modify | POST → 202 + job_id; GET /v1/ingest/{job_id} → progress; 409 on concurrent |
| `src/core/ingestion_service.py` | Modify | Accept `job_progress` callback; use Semaphore(INGEST_CONCURRENCY) |
| `src/adapters/ollama_embedder.py` | Modify | Native batch: `input: string[]`; split at EMBED_BATCH_SIZE |
| `src/adapters/parsers.py` | Modify | Wrap sync libs in `asyncio.to_thread` |
| `src/main.py` | Modify | Startup scan → `IngestionService.submit()` as background task |
| `src/config.py` | Modify | Add `ingest_concurrency: int = 2`, `embed_batch_size: int = 64` |

### PR 3: Structure-Aware Chunking

| File | Action | Description |
|------|--------|-------------|
| `src/ports/models.py` | Modify | Add `ParsedDocument`, block types; extend `Chunk` with `page_number`, `anchor` |
| `src/ports/parser.py` | Modify | Return type `ParsedDocument` instead of `str` |
| `src/ports/chunker.py` | Modify | Accept `ParsedDocument` + `source_type` instead of `str` |
| `src/adapters/parsers.py` | Modify | Each parser returns `ParsedDocument` with blocks |
| `src/adapters/recursive_chunker.py` | Modify | Block-aware splitting; per-type config; list/table boundary respect |
| `src/adapters/pgvector_index.py` | Modify | Upsert/read `page_number`, `anchor` columns; `_row_to_chunk` updated |
| `migrations/003_chunk_metadata.sql` | Create | ALTER TABLE chunks ADD COLUMN page_number INT; ADD COLUMN anchor TEXT |
| `src/config.py` | Modify | Per-type chunking defaults: `chunk_max_pdf`, `chunk_max_md`, etc. |

## Interfaces / Contracts

### documents table (migration 002)

```sql
CREATE TABLE documents (
  id TEXT PRIMARY KEY,                    -- sha256(source_path)[:16], matches chunks.document_id
  source_path TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  content_hash TEXT NOT NULL,             -- SHA-256 hex of file bytes
  content_type TEXT NOT NULL,             -- file extension: .pdf, .md, etc.
  chunk_count INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  modified_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  indexed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_documents_hash ON documents (content_hash);
```

### IngestionService

```python
@dataclass
class IngestionResult:
    processed: int
    skipped: int
    chunks: int
    failed: int
    failures: list[dict]  # [{path, error}]

class IngestionService:
    def __init__(
        self,
        source: DocumentSource,
        parser: Parser,
        chunker: Chunker,
        embedder: Embedder,
        search_index: SearchIndex,
        registry: DocumentRegistry,
    ): ...

    async def run(self, progress: JobProgress | None = None) -> IngestionResult:
        """Full pipeline: scan → diff → parse → chunk → embed → upsert.
        
        progress: optional callback for live counter updates (PR 2).
        """
```

### DocumentRegistry

```python
@dataclass(frozen=True)
class DocumentRecord:
    id: str               # document_id
    source_path: str
    title: str
    content_hash: str
    content_type: str
    chunk_count: int
    created_at: datetime
    modified_at: datetime
    indexed_at: datetime

class DocumentRegistry:
    async def load_all(self) -> dict[str, DocumentRecord]: ...
    async def upsert(self, record: DocumentRecord) -> None: ...
    async def delete(self, doc_id: str) -> None: ...
    async def update_path(self, doc_id: str, new_path: str) -> None: ...
```

### JobRegistry (PR 2)

```python
@dataclass
class JobState:
    job_id: str
    state: str          # pending | running | completed | failed
    total: int = 0
    processed: int = 0
    skipped: int = 0
    chunks: int = 0
    failed: int = 0
    failures: list[dict] = field(default_factory=list)

class JobRegistry:
    async def submit(self) -> str:           # returns job_id; raises Conflict if active
    async def get(self, job_id: str) -> JobState | None: ...
    async def update(self, job_id: str, **fields) -> None: ...
```

### ParsedDocument block model (PR 3)

```python
@dataclass(frozen=True)
class Heading:
    level: int
    text: str

@dataclass(frozen=True)
class Paragraph:
    text: str

@dataclass(frozen=True)
class ListItem:
    text: str
    ordered: bool = False

@dataclass(frozen=True)
class ListBlock:
    items: list[ListItem]

@dataclass(frozen=True)
class TableBlock:
    headers: list[str]
    rows: list[list[str]]

@dataclass(frozen=True)
class PageMarker:
    page_number: int

# Block = Heading | Paragraph | ListBlock | TableBlock | PageMarker

@dataclass
class ParsedDocument:
    blocks: list  # list[Block]
    metadata: dict  # {title, source_path, content_type, ...}
```

### Extended Chunk (PR 3)

```python
@dataclass(frozen=True)
class Chunk:
    document_id: str
    document_title: str
    source_path: str
    section_path: str
    chunk_index: int
    content: str
    token_count: int
    content_hash: str
    page_number: int | None = None   # NEW
    anchor: str | None = None        # NEW
```

### SearchIndex port addition (PR 1)

```python
class SearchIndex(Protocol):
    # ... existing methods ...
    async def delete_chunks(self, document_id: str) -> int:
        """Delete all chunks for a document. Returns count deleted."""
        ...
```

### OllamaEmbedder batch (PR 2)

```python
async def embed_batch(self, texts: list[str]) -> list[list[float]]:
    """Batch texts into groups of EMBED_BATCH_SIZE, send each as
    {"model": ..., "input": string[]} — one HTTP call per batch."""
```

## Testing Strategy

### PR 1

| Layer | What | Approach |
|-------|------|----------|
| Unit | `DocumentRegistry` diff logic (new/changed/renamed/deleted) | Pure functions with mock records; no DB |
| Unit | `IngestionService.run()` with mock ports | Verify skip-unchanged, stale cleanup, rename detection |
| Unit | `FilesystemSource` content_hash computation | Temp files with known content |
| Integration | `DocumentRegistry` CRUD against testcontainers | Apply migration 002; verify constraints |
| Integration | `PgvectorIndex.delete_chunks()` | Insert chunks, delete by doc_id, verify gone |
| Integration | Full pipeline: scan → dedup → upsert | Real DB; verify idempotency + stale cleanup |

### PR 2

| Layer | What | Approach |
|-------|------|----------|
| Unit | `JobRegistry` submit/get/update, 409 on concurrent | Asyncio tests with fake clock |
| Unit | `OllamaEmbedder` batch splitting | Mock httpx; verify ≤64 per call, correct ordering |
| Unit | `IngestionService` semaphore bounding | Verify ≤N concurrent doc processing |
| Integration | POST /v1/ingest → 202 + GET progress | TestClient; verify state transitions |
| Integration | Concurrent POST → 409 | Two simultaneous requests |
| Integration | Startup scan as background job | Verify app serves requests during scan |

### PR 3

| Layer | What | Approach |
|-------|------|----------|
| Unit | `ParsedDocument` construction per parser | Each parser returns correct block types |
| Unit | `BlockChunker` list/table boundary respect | 50-item list not split mid-item |
| Unit | Per-type config resolution | Env vars → correct min/max/overlap |
| Unit | `_row_to_chunk` with new nullable columns | NULL → None, value → int/str |
| Integration | End-to-end: PDF with pages → chunks with page_number | Real parser + chunker + DB |
| Integration | Retrieval still works with extended Chunk | BM25 + vector search return page_number |

**TDD order per PR**: Write failing test → implement → refactor. Contract tests for new ports/models FIRST.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. `asyncio.to_thread` runs Python parser libraries in worker threads within the same process; it does not spawn subprocesses or execute shell commands.

## Migration / Rollout

### Migration 002 (PR 1) — Additive, safe

```sql
-- 002_documents.sql
CREATE TABLE documents ( ... );
CREATE INDEX idx_documents_hash ON documents (content_hash);
```

No existing data affected. `documents` table starts empty; populated on first scan.

### Migration 003 (PR 3) — Additive, safe

```sql
-- 003_chunk_metadata.sql
ALTER TABLE chunks ADD COLUMN page_number INT;
ALTER TABLE chunks ADD COLUMN anchor TEXT;
```

Existing rows get NULL for new columns. `_row_to_chunk` uses `.get()` with None default — backward-compatible.

### Rollback

Each PR independently revertable. Migration 002/003 are additive — rollback = DROP TABLE / DROP COLUMN (safe only if no data depends on it; in practice, just revert code and leave columns).

### Feature flags

None needed. Each PR is a clean cut. Concurrency/batch defaults are env-configurable for tuning without redeploy.

## Sequence: Rename Detection Algorithm (PR 1)

```
scan_paths = {path for path in disk_scan}
registry = {record.source_path: record for record in db_load}

disk_hashes = {content_hash: path for path in scan_paths}  # hash → path
reg_hashes  = {r.content_hash: r for r in registry.values()}

# Detect renames: hash in both, but path differs
for hash_val, reg_record in reg_hashes.items():
    if reg_record.source_path not in scan_paths and hash_val in disk_hashes:
        new_path = disk_hashes[hash_val]
        if new_path not in registry:  # unambiguous: one-to-one
            registry.update_path(reg_record.id, new_path)
            # chunks preserved — no re-processing needed

# After rename pass, diff normally
new_paths = scan_paths - registry.keys()
deleted_paths = registry.keys() - scan_paths
changed_paths = {p for p in scan_paths & registry.keys()
                 if compute_hash(p) != registry[p].content_hash}
```

## Configuration Management (PR 2+)

```python
# src/config.py additions
class Settings(BaseSettings):
    # ... existing ...
    
    # Ingestion concurrency (PR 2)
    ingest_concurrency: int = 2
    embed_batch_size: int = 64
    
    # Per-type chunking (PR 3)
    chunk_min_pdf: int = 300
    chunk_max_pdf: int = 600
    chunk_overlap_pdf: float = 0.10
    chunk_min_md: int = 250
    chunk_max_md: int = 500
    chunk_overlap_md: float = 0.10
    chunk_min_docx: int = 300
    chunk_max_docx: int = 600
    chunk_overlap_docx: float = 0.10
    chunk_min_html: int = 250
    chunk_max_html: int = 500
    chunk_overlap_html: float = 0.10
    chunk_min_txt: int = 300
    chunk_max_txt: int = 600
    chunk_overlap_txt: float = 0.10
```

Env vars: `INGEST_CONCURRENCY`, `EMBED_BATCH_SIZE`, `CHUNK_MAX_PDF`, `CHUNK_MAX_MD`, etc.

## Open Questions

- [ ] **Frontend page display**: SourcePanel may want to show page numbers. Defer to a follow-up iteration unless trivially easy to add in PR 3. Design accommodates it (page_number in Chunk → citation metadata → frontend).
- [ ] **Rename ambiguity**: When multiple files share a hash and multiple paths disappear, the algorithm MAY treat as delete+insert. Implementation should prefer one-to-one matching and fall back to delete+insert for ambiguous cases.
