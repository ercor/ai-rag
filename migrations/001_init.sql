-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Chunks table: single-table design with embedded document metadata
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

-- HNSW index for cosine similarity vector search
CREATE INDEX idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops);

-- GIN index for full-text search via tsvector
CREATE INDEX idx_chunks_tsv ON chunks USING gin (tsv);

-- Index for grouping chunks by document
CREATE INDEX idx_chunks_document ON chunks (document_id);

-- Unique index for idempotent upserts (dedup on re-ingestion)
CREATE UNIQUE INDEX idx_chunks_dedup ON chunks (document_id, chunk_index, content_hash);

-- Answers table: stores questions, generated answers, and citations
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
