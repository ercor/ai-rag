# Design: MVP Secure Vertical Slice

## Technical Approach

Hexagonal FastAPI backend with single-table PostgreSQL+pgvector storage. One concrete adapter per port, swappable via env vars. SSE streaming for answer tokens. Next.js App Router frontend consuming SSE via fetch+ReadableStream (POST body required; EventSource is GET-only).

## Architecture Decisions

| Decision | Options | Choice | Rationale |
|----------|---------|--------|-----------|
| DB schema | Single chunks table vs. documents+chunks | Single table with document metadata embedded | MVP scale (10-100 docs); avoids JOIN; document_id groups chunks; valid up to ~10K chunks |
| DI approach | DI library vs. FastAPI Depends factory | FastAPI Depends factory functions | No extra dependency; matches FastAPI idioms; env-var configurable |
| Streaming transport | WebSocket vs. SSE | SSE | Spec mandates SSE; unidirectional fits answer streaming |
| Frontend SSE | EventSource vs. fetch+ReadableStream | fetch+ReadableStream | EventSource is GET-only; we need POST /v1/answers to create the answer, then GET stream |
| Chunking | Fixed-size vs. heading-aware recursive | Heading-aware recursive | Spec requires section_path; preserves heading context for retrieval |
| FTS engine | pg_bm25 extension vs. native tsvector | Native tsvector | Zero extra deps; sufficient for 10-100 docs; pg_bm25 is upgrade path |
| Abstention timing | Always stream vs. two-phase | Two-phase: retrieve first, stream only on success | Prevents streaming an answer we already know will be abstained |

## Data Flow

### Query Flow (sequence)
```
Client          API             Retriever           SearchIndex       Generator        Validator       Repo
  |---POST /answers-->|            |                    |                 |                |              |
  |                   |--bm25------>|--tsquery---------->|                |                |              |
  |                   |--vector---->|--embed+cosine----->|                |                |              |
  |                   |<--RRF fused-|                    |                |                |              |
  |                   |--abstain?--->|                    |                |                |              |
  |<--{status, id}---|              |                    |                |                |              |
  |---GET /stream---->|             |                    |                |                |              |
  |                   |----------------------------------------stream--->|                |              |
  |<--SSE tokens------|             |                    |                |                |              |
  |                   |----------------------------------------validate------------------>|              |
  |<--SSE done+cites--|             |                    |                |                |--save-------->|
```

### Ingestion Flow
```
POST /v1/ingest → DocumentSource.scan() → Parser.parse() → Chunker.split()
  → Embedder.embed_batch() → SearchIndex.upsert_chunks() → status response
```

## Database Schema

```sql
CREATE TABLE chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id TEXT NOT NULL,
  document_title TEXT NOT NULL,
  source_path TEXT NOT NULL,
  section_path TEXT,
  chunk_index INT NOT NULL,
  content TEXT NOT NULL,
  token_count INT,
  content_hash TEXT NOT NULL,
  embedding vector(768),
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_chunks_tsv ON chunks USING gin (tsv);
CREATE INDEX idx_chunks_document ON chunks (document_id);
CREATE UNIQUE INDEX idx_chunks_dedup ON chunks (document_id, chunk_index, content_hash);

CREATE TABLE answers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  question TEXT NOT NULL,
  answer TEXT,
  status TEXT NOT NULL DEFAULT 'pending',  -- pending|streaming|answered|insufficient_evidence|failed
  citations JSONB DEFAULT '[]',
  chunk_ids UUID[],
  vote TEXT,  -- up|down|null
  created_at TIMESTAMPTZ DEFAULT now()
);
```

Single-table design validated: at 100 docs × ~15 chunks = 1500 rows, HNSW and GIN indexes fit in memory. Ceiling ~10K chunks before considering partitioning.

## Port Interfaces

```python
from typing import Protocol, AsyncIterator
from dataclasses import dataclass

@dataclass
class Chunk:
    document_id: str; document_title: str; source_path: str
    section_path: str; chunk_index: int; content: str
    token_count: int; content_hash: str

class DocumentSource(Protocol):
    async def scan(self) -> list[dict]: ...  # {path, title}

class Parser(Protocol):
    async def parse(self, path: str) -> str: ...

class Chunker(Protocol):
    def split(self, text: str, doc_id: str, doc_title: str, source: str) -> list[Chunk]: ...

class Embedder(Protocol):
    async def embed(self, text: str) -> list[float]: ...
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...

class SearchIndex(Protocol):
    async def bm25_search(self, query: str, k: int) -> list[tuple[Chunk, float]]: ...
    async def vector_search(self, embedding: list[float], k: int) -> list[tuple[Chunk, float]]: ...
    async def upsert_chunks(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None: ...

class Generator(Protocol):
    async def generate_stream(self, prompt: str) -> AsyncIterator[str]: ...

class CitationValidator(Protocol):
    def validate(self, answer: str, valid_ids: set[int]) -> str: ...

class AnswerRepository(Protocol):
    async def save(self, answer_id: str, question: str, answer: str,
                   status: str, citations: list, chunk_ids: list) -> None: ...
    async def update_vote(self, answer_id: str, vote: str) -> None: ...
```

## File Structure

```
src/
├── main.py                  # FastAPI app, lifespan (startup scan)
├── config.py                # pydantic-settings from env
├── container.py             # DI: get_embedder(), get_generator(), etc.
├── ports/                   # Protocol classes (one file per port)
├── adapters/
│   ├── filesystem_source.py
│   ├── parsers.py           # pymupdf, python-docx, bs4, plain text
│   ├── recursive_chunker.py
│   ├── ollama_embedder.py
│   ├── ollama_generator.py
│   ├── pgvector_index.py
│   ├── regex_citation_validator.py
│   └── pg_answer_repository.py
├── core/
│   ├── retrieval.py         # RRF fusion (k=60), abstention check
│   └── query_pipeline.py    # retrieve → abstain? → generate → validate → persist
├── api/
│   ├── answers.py           # POST /v1/answers, GET /v1/answers/{id}/stream, POST feedback
│   ├── ingestion.py         # POST /v1/ingest
│   └── health.py            # GET /health, GET /ready
frontend/
├── app/page.tsx             # Chat page (client component)
├── app/layout.tsx
├── components/
│   ├── ChatInput.tsx        # Input + submit, disabled during streaming
│   ├── AnswerDisplay.tsx    # Markdown rendering, typing indicator
│   ├── CitationBadge.tsx    # Clickable [N] badge with popover
│   ├── SourcePanel.tsx      # Cited documents list with snippets
│   └── FeedbackButtons.tsx  # Thumbs up/down, disabled until complete
└── lib/sse.ts               # fetch POST → ReadableStream → token callback
docker-compose.yml           # postgres+pgvector, ollama, backend, frontend
migrations/001_init.sql      # Schema above
```

## Configuration

`pydantic-settings` `Settings` class:

| Variable | Default | Purpose |
|----------|---------|---------|
| `WATCH_DIR` | `./data/docs` | Directory to scan for documents |
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL connection |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | `qwen2.5` | Generation model |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Embedding model (768 dims) |
| `RETRIEVAL_TOP_K` | `5` | Max chunks to generation |
| `MIN_SCORE_THRESHOLD` | `0.0` | RRF score floor for abstention |
| `EMBEDDER_ADAPTER` | `ollama` | Adapter selector |
| `GENERATOR_ADAPTER` | `ollama` | Adapter selector |

## Error Handling

| Error | Behavior |
|-------|----------|
| Parser failure on one file | Log warning, mark doc failed, continue batch |
| Embedder unavailable | 503 on query; ingestion raises and reports failure |
| LLM unavailable | 503; never fabricate answer-shaped response |
| Abstention before streaming | POST returns `{"status": "insufficient_evidence", "answer": null}` |
| Abstention detected mid-stream | Send `{"aborted": true, "reason": "insufficient_evidence"}` SSE event |
| Invalid citations | Strip `[N]` markers silently; log warning; no retry for MVP |
| Client disconnect mid-stream | Cancel asyncio generation task; cleanup |
| Corrupt/zero-byte file | Log + skip; batch continues |

## Streaming + Abstention Strategy

**Two-phase approach**: (1) `POST /v1/answers` runs retrieval synchronously. If abstention triggers (0 chunks or all below threshold), return JSON immediately with `status=insufficient_evidence`. No answer record created. (2) If retrieval succeeds, create answer record (`status=streaming`), return `answer_id`. Client connects to `GET /v1/answers/{id}/stream` for SSE. Generator streams tokens; citation validator runs on complete text; final SSE event sends `{"done": true, "citations": [...]}`.

This prevents the UX problem of streaming an answer that will be retracted.

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | Chunker splitting, RRF fusion math, citation regex | pytest with fixtures; no external deps |
| Integration | PG tsvector/pgvector queries, answer persistence | testcontainers-py for real PG; mock Ollama |
| E2E | Full query flow: ingest → query → stream | docker compose up + pytest hitting API endpoints |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary in MVP.

## Migration / Rollout

No migration required — greenfield project. `migrations/001_init.sql` creates all tables. Docker Compose runs init on startup.

## Open Questions

- [ ] Confirm qwen2.5 quantization (7B vs 3B) for acceptable CPU first-token latency
- [ ] Validate single-table HNSW performance at 10K chunks before MVP demo
