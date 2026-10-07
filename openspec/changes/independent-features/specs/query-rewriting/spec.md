# Query Rewriting Specification

## Purpose

Define the query rewriting capability that generates multiple query variants from the user's original question, searches for each variant, and merges results via Reciprocal Rank Fusion to improve retrieval recall for complex or ambiguously-phrased queries.

## Requirements

### Requirement: QueryRewriter Port

The system SHALL define a `QueryRewriter` port (Protocol) that accepts a query string and returns a list of query variants, including the original query.

The port MUST be adapter-agnostic — no LLM-specific constructs SHALL appear in the interface.

#### Scenario: Rewriter produces variants

- GIVEN a query "What is the travel reimbursement policy?"
- WHEN `QueryRewriter.rewrite()` is called
- THEN it returns a list of 3 strings: the original query plus 2 semantically related variants
- AND the original query is included in the returned list

#### Scenario: Single variant (degenerate case)

- GIVEN a very short or ambiguous query
- WHEN `QueryRewriter.rewrite()` is called
- THEN it returns at least the original query (minimum list length: 1)

### Requirement: LLM Query Rewriter Adapter

The system SHALL provide an `LLMQueryRewriter` adapter that uses the existing `Generator` port (Ollama) to produce query variants via multi-query expansion prompting.

The adapter MUST use a structured prompt that instructs the LLM to produce N semantically distinct rephrasings of the input query. The adapter MUST parse the LLM output into a clean list of query strings.

#### Scenario: Multi-query expansion

- GIVEN `query_rewriter_num_variants=3` and the query "How do I file an expense report?"
- WHEN the adapter generates variants
- THEN it produces 3 strings: the original plus 2 rephrasings (e.g., "What is the process for submitting expenses?", "Steps to file an expense claim")
- AND each variant is a standalone query (no references to "the above" or "this question")

#### Scenario: LLM failure fallback

- GIVEN the Generator port is unavailable or returns an error
- WHEN the adapter attempts to generate variants
- THEN it returns a list containing only the original query
- AND a warning is logged indicating the fallback

#### Scenario: Malformed LLM output

- GIVEN the LLM returns output that cannot be parsed into separate queries
- WHEN the adapter processes the response
- THEN it returns a list containing only the original query
- AND a warning is logged with the raw output for debugging

### Requirement: Multi-Query Search and Merge

The system SHALL execute a separate hybrid search (BM25 + vector + RRF) for each query variant and merge all results into a single ranked list using Reciprocal Rank Fusion.

The merge MUST deduplicate chunks appearing across multiple variant results. A chunk's merged RRF score SHALL accumulate contributions from each variant result list where it appears.

#### Scenario: Merge of multi-query results

- GIVEN 3 query variants producing result sets: V1=[A,B,C], V2=[B,C,D], V3=[A,D,E]
- WHEN the merge step runs
- THEN the merged list contains [A,B,C,D,E] with no duplicates
- AND chunks appearing in multiple result sets (B, C, D, A) have higher merged RRF scores
- AND the final list is sorted by descending merged RRF score

#### Scenario: All variants return identical results

- GIVEN 3 query variants that all return the same 5 chunks in the same order
- WHEN the merge step runs
- THEN the merged list contains exactly those 5 chunks with accumulated RRF scores
- AND the ranking order is preserved

#### Scenario: Single variant (rewriting disabled or fallback)

- GIVEN only 1 query variant (the original)
- WHEN the merge step runs
- THEN the behavior is identical to the current single-query pipeline (no merge overhead)

### Requirement: Pipeline Integration

The system SHALL integrate query rewriting into the pipeline before the embedding step.

When enabled, the pipeline flow becomes: `query → REWRITE → [q1,q2,...,qN] → embed each → parallel search per variant → RRF merge → rerank (if enabled) → abstain → generate`.

The per-variant searches SHOULD be executed in parallel using `asyncio.gather` to minimize latency impact.

#### Scenario: Rewriting enabled in pipeline

- GIVEN `query_rewriter_enabled=true` and `query_rewriter_num_variants=3`
- WHEN a query enters the pipeline
- THEN the rewriter produces 3 variants
- AND each variant is embedded and searched in parallel
- AND results are merged via RRF before reranking/abstention

#### Scenario: Rewriting disabled

- GIVEN `query_rewriter_enabled=false`
- WHEN a query enters the pipeline
- THEN the pipeline uses the raw query directly (no rewriting)
- AND behavior is identical to the pre-rewriting pipeline

#### Scenario: Parallel search execution

- GIVEN 3 query variants
- WHEN the pipeline executes searches
- THEN all 3 variant searches run concurrently via `asyncio.gather`
- AND the total search time is approximately the time of the slowest single search (not 3x)

### Requirement: Query Rewriting Configuration

The system SHALL expose query rewriting settings via environment variables with sensible defaults.

Required settings: `query_rewriter_enabled` (bool, default: false), `query_rewriter_num_variants` (int, default: 3).

#### Scenario: Default configuration

- GIVEN no query rewriter environment variables are set
- WHEN settings are loaded
- THEN `query_rewriter_enabled=false` and `query_rewriter_num_variants=3`

#### Scenario: Custom variant count

- GIVEN `QUERY_REWRITER_NUM_VARIANTS=2` is set
- WHEN settings are loaded
- THEN `query_rewriter_num_variants=2`
- AND the rewriter produces at most 2 variants (original + 1)

### Requirement: Dependency Injection Wiring

The system SHALL provide a `get_query_rewriter()` factory in the DI container that returns the configured `QueryRewriter` adapter instance.

The factory MUST respect the `query_rewriter_enabled` flag — when disabled, it SHALL return `None`.

#### Scenario: Query rewriter factory when enabled

- GIVEN `query_rewriter_enabled=true`
- WHEN `get_query_rewriter()` is called
- THEN it returns an `LLMQueryRewriter` instance using the existing Generator port

#### Scenario: Query rewriter factory when disabled

- GIVEN `query_rewriter_enabled=false`
- WHEN `get_query_rewriter()` is called
- THEN it returns `None`
- AND the pipeline receives `None` and skips rewriting

### Requirement: Latency Budget

The query rewriting step (LLM call + parallel searches) MUST add no more than 2 seconds of latency overhead (p95) compared to the non-rewriting pipeline.

The system SHOULD log the rewriting duration and the number of variants produced for each query.

#### Scenario: Latency within budget

- GIVEN a query and `query_rewriter_num_variants=3`
- WHEN the rewriting step completes (including parallel searches)
- THEN the total overhead compared to single-query search is under 2 seconds at p95

#### Scenario: Latency logged

- GIVEN a query processed with rewriting enabled
- WHEN the pipeline completes
- THEN a log entry includes the rewriting duration and variant count

## Out of Scope

- HyDE (Hypothetical Document Embedding) strategy
- Step-back prompting strategy
- Per-variant embedding caching
- Adaptive variant count based on query complexity
- Dedicated lightweight model for rewriting (uses existing Generator port)
