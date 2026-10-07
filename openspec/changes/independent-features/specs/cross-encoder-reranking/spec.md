# Cross-Encoder Reranking Specification

## Purpose

Define the cross-encoder reranking capability that re-scores retrieval candidates using a learned cross-encoder model after initial hybrid retrieval, improving retrieval quality by producing a more accurate final ranking.

## Requirements

### Requirement: Reranker Port

The system SHALL define a `Reranker` port (Protocol) that accepts a query string and a list of candidate chunks, and returns the same chunks re-ordered and re-scored by relevance.

The port MUST be adapter-agnostic — no implementation details (model names, frameworks) SHALL leak into the port interface.

#### Scenario: Reranker port contract

- GIVEN a query "What is the travel reimbursement policy?" and 20 candidate `RetrievedChunk` objects
- WHEN the `Reranker.rerank()` method is called
- THEN it returns a list of `RetrievedChunk` objects sorted by descending cross-encoder relevance score
- AND the returned list contains at most `top_k_after` elements

#### Scenario: Empty candidate list

- GIVEN a query and an empty candidate list
- WHEN `Reranker.rerank()` is called
- THEN it returns an empty list without error

### Requirement: Cross-Encoder Adapter

The system SHALL provide a `CrossEncoderReranker` adapter that uses the `sentence-transformers` library with a configurable cross-encoder model.

The default model MUST be `cross-encoder/ms-marco-MiniLM-L-6-v2`. The adapter MUST lazy-load the model on first invocation and cache it for subsequent calls.

#### Scenario: Model loaded on first use

- GIVEN the adapter is instantiated but the model has not been loaded yet
- WHEN `rerank()` is called for the first time
- THEN the cross-encoder model is loaded from the local cache (or downloaded if absent)
- AND subsequent `rerank()` calls reuse the loaded model without re-downloading

#### Scenario: Model download failure

- GIVEN the model is not cached locally and the network is unavailable
- WHEN `rerank()` is called
- THEN the adapter raises a clear error indicating model download failed
- AND the error message includes the model name and suggested resolution

#### Scenario: Reranking with 20 candidates

- GIVEN 20 candidate chunks with varying relevance to the query
- WHEN `rerank()` is called with `top_k_after=5`
- THEN the adapter scores all 20 (query, chunk_content) pairs
- AND returns the top 5 sorted by descending cross-encoder score

### Requirement: Pipeline Integration

The system SHALL integrate the reranker into the query pipeline after RRF fusion and before the abstention check.

When reranking is enabled, the pipeline MUST fetch `reranker_top_k_before` candidates (default: 20) from RRF fusion, pass them to the reranker, and use the `reranker_top_k_after` (default: 5) results for subsequent steps.

#### Scenario: Reranking enabled in pipeline

- GIVEN `reranker_enabled=true` and `reranker_top_k_before=20`, `reranker_top_k_after=5`
- WHEN a query is processed through the pipeline
- THEN RRF fusion produces up to 20 candidates
- AND the reranker re-scores and returns the top 5
- AND those 5 chunks are passed to the abstention check and generation

#### Scenario: Reranking disabled

- GIVEN `reranker_enabled=false`
- WHEN a query is processed
- THEN the pipeline skips the reranking step entirely
- AND RRF fusion results (top `retrieval_top_k`) go directly to the abstention check
- AND behavior is identical to the pre-reranking pipeline

#### Scenario: Reranker timeout

- GIVEN the reranker is enabled but takes longer than the configured timeout
- WHEN `rerank()` does not complete within the timeout period
- THEN the pipeline logs a warning and falls back to the non-reranked RRF results
- AND the query completes successfully with degraded (non-reranked) results

### Requirement: Reranker Configuration

The system SHALL expose reranker settings via environment variables with sensible defaults.

Required settings: `reranker_enabled` (bool, default: true), `reranker_model` (str, default: "cross-encoder/ms-marco-MiniLM-L-6-v2"), `reranker_top_k_before` (int, default: 20), `reranker_top_k_after` (int, default: 5), `reranker_timeout_seconds` (float, default: 5.0).

#### Scenario: Default configuration

- GIVEN no reranker environment variables are set
- WHEN the settings are loaded
- THEN `reranker_enabled=true`, `reranker_model="cross-encoder/ms-marco-MiniLM-L-6-v2"`, `reranker_top_k_before=20`, `reranker_top_k_after=5`

#### Scenario: Custom model override

- GIVEN `RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-12-v2` is set
- WHEN the settings are loaded
- THEN `reranker_model` reflects the custom value

### Requirement: Dependency Injection Wiring

The system SHALL provide a `get_reranker()` factory in the DI container that returns the configured `Reranker` adapter instance.

The factory MUST respect the `reranker_enabled` flag — when disabled, it MAY return `None` or a no-op adapter.

#### Scenario: Reranker factory when enabled

- GIVEN `reranker_enabled=true`
- WHEN `get_reranker()` is called
- THEN it returns a `CrossEncoderReranker` instance configured with the model from settings

#### Scenario: Reranker factory when disabled

- GIVEN `reranker_enabled=false`
- WHEN `get_reranker()` is called
- THEN it returns `None`
- AND the pipeline receives `None` and skips reranking

### Requirement: Latency Budget

The reranking step MUST complete within 500ms (p95) for 20 candidates on CPU.

The system SHOULD log the reranking duration for each query to enable latency monitoring.

#### Scenario: Latency within budget

- GIVEN 20 candidate chunks and a loaded cross-encoder model
- WHEN `rerank()` is called
- THEN it completes within 500ms at p95

#### Scenario: Latency logged

- GIVEN a query processed with reranking enabled
- WHEN the pipeline completes
- THEN a log entry includes the reranking duration in milliseconds

## Out of Scope

- GPU-accelerated inference (CPU-only for this iteration)
- Custom fine-tuned cross-encoder models
- Reranking of more than 50 candidates per query
- Batch reranking across multiple queries
