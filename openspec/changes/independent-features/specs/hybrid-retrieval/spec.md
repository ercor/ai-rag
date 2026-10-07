# Delta for Hybrid Retrieval

## MODIFIED Requirements

### Requirement: RRF Fusion

The system SHALL fuse BM25 and vector results using Reciprocal Rank Fusion with k=60.

The fused result MUST deduplicate chunks appearing in both result sets and produce a single ranked list.

When query rewriting is enabled, the system SHALL execute separate hybrid searches for each query variant and merge all results via an additional RRF pass over the per-variant fused lists. A chunk's merged score accumulates contributions from each variant result list where it appears.

When reranking is enabled, the RRF fusion output (up to `reranker_top_k_before` candidates, default 20) is passed to the reranker instead of being truncated to `retrieval_top_k` directly.

(Previously: RRF fusion produced a single ranked list from one BM25 + one vector search, truncated to `retrieval_top_k`.)

#### Scenario: Fusion of overlapping results

- GIVEN BM25 returns chunks [A, B, C] and vector returns [B, C, D]
- WHEN RRF fusion runs
- THEN the result is a single ranked list with B and C scored by combined RRF rank; no duplicates

#### Scenario: Disjoint results

- GIVEN BM25 returns [A, B] and vector returns [C, D]
- WHEN RRF fusion runs
- THEN all 4 chunks appear in the fused result, each with its single-source RRF score

#### Scenario: Multi-query merge via RRF

- GIVEN query rewriting is enabled with 3 variants producing per-variant fused lists: V1=[A,B,C], V2=[B,C,D], V3=[A,D,E]
- WHEN the cross-variant RRF merge runs
- THEN the merged list contains [A,B,C,D,E] with no duplicates
- AND chunks appearing in multiple variant lists have higher merged RRF scores
- AND the final list is sorted by descending merged RRF score

#### Scenario: RRF output feeds reranker

- GIVEN reranking is enabled with `reranker_top_k_before=20`
- WHEN RRF fusion completes
- THEN up to 20 fused candidates are passed to the reranker
- AND the reranker output (top 5) is used for subsequent steps

### Requirement: Configurable Top-K and Threshold

The system SHALL allow configuring `top_k` (default: 5) and `min_score` threshold via environment variables.

When reranking is enabled, `retrieval_top_k` controls the per-channel fetch count (BM25 and vector each return up to `retrieval_top_k` results). The RRF fusion produces up to `reranker_top_k_before` candidates. After reranking, `reranker_top_k_after` controls the final candidate count passed to generation.

When reranking is disabled, `retrieval_top_k` controls the final candidate count as before.

(Previously: `retrieval_top_k` directly controlled the final candidate count passed to generation.)

#### Scenario: Custom top_k without reranking

- GIVEN `RETRIEVAL_TOP_K=3` and `reranker_enabled=false`
- WHEN retrieval runs
- THEN at most 3 chunks are passed to generation

#### Scenario: Top_k with reranking

- GIVEN `RETRIEVAL_TOP_K=20`, `reranker_enabled=true`, `reranker_top_k_before=20`, `reranker_top_k_after=5`
- WHEN retrieval runs
- THEN BM25 and vector each return up to 20 results
- AND RRF fusion produces up to 20 candidates
- AND reranking produces the final 5 candidates for generation

## ADDED Requirements

### Requirement: Reranking Step After RRF

The system SHALL support an optional reranking step that executes after RRF fusion and before the abstention check.

When enabled, the reranker re-scores the fused candidates using a cross-encoder model and returns the top `reranker_top_k_after` results. When disabled, the pipeline proceeds directly from RRF to abstention.

#### Scenario: Reranking enabled

- GIVEN `reranker_enabled=true` and 20 fused candidates
- WHEN the reranking step executes
- THEN the cross-encoder model scores all 20 (query, chunk) pairs
- AND the top 5 candidates (by cross-encoder score) are passed to abstention

#### Scenario: Reranking disabled

- GIVEN `reranker_enabled=false`
- WHEN the pipeline executes
- THEN the reranking step is skipped
- AND RRF fusion results go directly to abstention

### Requirement: Multi-Query Search

The system SHALL support executing parallel hybrid searches for multiple query variants when query rewriting is enabled.

Each variant is embedded independently, searched via BM25 + vector, and fused via RRF. The per-variant fused results are then merged via a second RRF pass.

#### Scenario: Multi-query parallel search

- GIVEN 3 query variants from the rewriter
- WHEN the search step executes
- THEN 3 parallel hybrid searches run concurrently
- AND each produces its own RRF-fused result list
- AND all lists are merged via cross-variant RRF

#### Scenario: Single query (rewriting disabled)

- GIVEN query rewriting is disabled
- WHEN the search step executes
- THEN a single hybrid search runs (current behavior)
- AND no cross-variant merge occurs
