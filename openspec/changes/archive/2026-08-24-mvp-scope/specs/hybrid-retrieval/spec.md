# Hybrid Retrieval Specification

## Purpose

Define the hybrid retrieval pipeline combining BM25 (lexical) and vector (semantic) search with Reciprocal Rank Fusion, plus abstention when evidence is insufficient.

## Requirements

### Requirement: BM25 Lexical Search

The system SHALL perform full-text search using PostgreSQL `tsvector`/`tsquery` via the `SearchIndex` port.

Queries MUST be sanitized to prevent SQL injection through tsquery operators.

#### Scenario: Lexical match found

- GIVEN chunks stored with tsvector indexes
- WHEN a query matches terms in 3 chunks
- THEN those 3 chunks are returned ranked by ts_rank

#### Scenario: Special characters sanitized

- GIVEN a query containing tsquery operators like `& | ! < >`
- WHEN the query is executed
- THEN operators are escaped; no SQL injection occurs; results returned safely

### Requirement: Vector Semantic Search

The system SHALL perform vector similarity search using pgvector cosine distance via the `SearchIndex` port.

The query text MUST be embedded using the `Embedder` port before search.

#### Scenario: Semantic match found

- GIVEN chunks stored with 768-dim vectors
- WHEN a semantically similar query is embedded and searched
- THEN the top-k most similar chunks are returned ranked by cosine similarity

#### Scenario: Embedding failure

- GIVEN the Embedder port is unavailable
- WHEN a search is requested
- THEN the system returns an error response; no partial results without vector scores

### Requirement: RRF Fusion

The system SHALL fuse BM25 and vector results using Reciprocal Rank Fusion with k=60.

The fused result MUST deduplicate chunks appearing in both result sets and produce a single ranked list.

#### Scenario: Fusion of overlapping results

- GIVEN BM25 returns chunks [A, B, C] and vector returns [B, C, D]
- WHEN RRF fusion runs
- THEN the result is a single ranked list with B and C scored by combined RRF rank; no duplicates

#### Scenario: Disjoint results

- GIVEN BM25 returns [A, B] and vector returns [C, D]
- WHEN RRF fusion runs
- THEN all 4 chunks appear in the fused result, each with its single-source RRF score

### Requirement: Abstention on Insufficient Evidence

The system SHALL return `insufficient_evidence` when retrieval yields zero chunks OR all chunks score below a configurable threshold.

The response MUST NOT include a generated answer when abstaining.

#### Scenario: Zero results

- GIVEN a query that matches no chunks
- WHEN retrieval runs
- THEN the response is `{"status": "insufficient_evidence", "answer": null, "citations": []}`

#### Scenario: All below threshold

- GIVEN retrieval returns 3 chunks all scoring below the minimum threshold
- WHEN the threshold check runs
- THEN the response is `insufficient_evidence`; no generation is triggered

### Requirement: Configurable Top-K and Threshold

The system SHALL allow configuring `top_k` (default: 5) and `min_score` threshold via environment variables.

#### Scenario: Custom top_k

- GIVEN `RETRIEVAL_TOP_K=3` is set
- WHEN retrieval runs
- THEN at most 3 chunks are passed to generation
