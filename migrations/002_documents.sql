-- Migration 002: documents table for content-hash-based registry.
-- Tracks ingested documents for skip-unchanged, rename detection, and deletion cleanup.

CREATE TABLE documents (
  id TEXT PRIMARY KEY,
  source_path TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  content_type TEXT NOT NULL,
  chunk_count INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  modified_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  indexed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_documents_hash ON documents (content_hash);
