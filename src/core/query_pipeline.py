"""Query pipeline — orchestrates the full retrieval-to-generation flow.

Coordinates: embed query -> retrieve -> [rerank] -> abstain? -> build prompt ->
generate -> validate citations -> persist answer.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass

from src.config import get_settings
from src.core.retrieval import RetrievedChunk, rrf_fusion, rrf_fusion_multi, should_abstain

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Result of the retrieval phase (before generation)."""

    answer_id: str
    question: str
    status: str  # "streaming" or "insufficient_evidence"
    retrieved_chunks: list[RetrievedChunk]
    error: str | None = None


@dataclass
class GenerationResult:
    """Result of the full generation phase."""

    answer_id: str
    answer_text: str
    citations: list[dict]
    status: str  # "answered" or "failed"


def build_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
    """Build the generation prompt with retrieved context.

    Formats the question and retrieved chunks into a prompt that
    instructs the LLM to answer using only the provided context,
    citing sources with [N] markers.
    """
    context_parts = []
    for i, rc in enumerate(chunks, start=1):
        chunk = rc.chunk
        header = f"[{i}] {chunk.document_title}"
        if chunk.section_path:
            header += f" > {chunk.section_path}"
        context_parts.append(f"{header}\n{chunk.content}")

    context = "\n\n---\n\n".join(context_parts)

    prompt = (
        "You are a helpful assistant that answers questions based ONLY on the "
        "provided context. Cite your sources using [N] notation where N is the "
        "source number shown above. If the context does not contain enough "
        "information to answer the question, say so clearly.\n\n"
        f"## Context\n\n{context}\n\n"
        f"## Question\n\n{question}\n\n"
        "## Answer\n"
    )

    return prompt


class QueryPipeline:
    """Orchestrates the full query flow from question to answer.

    Uses injected port implementations for each step.
    """

    def __init__(
        self,
        embedder,
        search_index,
        generator,
        citation_validator,
        answer_repository,
        reranker=None,
        query_rewriter=None,
    ):
        self.embedder = embedder
        self.search_index = search_index
        self.generator = generator
        self.citation_validator = citation_validator
        self.answer_repository = answer_repository
        self.reranker = reranker
        self.query_rewriter = query_rewriter

    async def retrieve(self, question: str) -> QueryResult:
        """Phase 1: Embed query, retrieve chunks, check abstention.

        This runs synchronously (before streaming). If abstention triggers,
        no answer record is created and status is 'insufficient_evidence'.

        When query_rewriter is set, the flow becomes:
        rewrite -> [variants] -> embed each -> parallel search per variant
        -> per-variant RRF -> cross-variant RRF merge -> rerank -> abstain.
        """
        settings = get_settings()
        answer_id = str(uuid.uuid4())

        try:
            # Step 0: Optional query rewriting
            if self.query_rewriter is not None:
                fused = await self._retrieve_with_rewriting(question, settings)
            else:
                fused = await self._retrieve_single_query(question, settings)

            # Reranking (after RRF / multi-RRF, before abstention)
            if self.reranker is not None and fused:
                fused = await _rerank_with_timeout(
                    self.reranker,
                    question,
                    fused,
                    settings.reranker_top_k_after,
                    settings.reranker_timeout_seconds,
                )

            # Abstention check
            if should_abstain(fused, settings.min_score_threshold):
                logger.info(
                    "Abstention triggered for query: %s", question[:100]
                )
                return QueryResult(
                    answer_id=answer_id,
                    question=question,
                    status="insufficient_evidence",
                    retrieved_chunks=[],
                )

            logger.info(
                "Retrieval succeeded: %d chunks, best score=%.6f",
                len(fused),
                fused[0].score if fused else 0.0,
            )

            return QueryResult(
                answer_id=answer_id,
                question=question,
                status="streaming",
                retrieved_chunks=fused,
            )

        except Exception as exc:
            logger.error("Retrieval failed: %s", exc, exc_info=True)
            return QueryResult(
                answer_id=answer_id,
                question=question,
                status="insufficient_evidence",
                retrieved_chunks=[],
                error=str(exc),
            )

    async def _retrieve_single_query(
        self, question: str, settings
    ) -> list[RetrievedChunk]:
        """Single-query retrieval path (no rewriting)."""
        # Embed the query
        logger.info("Embedding query: %s", question[:100])
        query_embedding = await self.embedder.embed(question)

        # Determine retrieval target size
        if self.reranker is not None:
            rrf_top_k = settings.reranker_top_k_before
        else:
            rrf_top_k = settings.retrieval_top_k

        # Run hybrid search (BM25 + vector)
        bm25_results, vector_results = await _parallel_search(
            self.search_index, question, query_embedding, rrf_top_k
        )

        # RRF fusion
        return rrf_fusion(bm25_results, vector_results, top_k=rrf_top_k)

    async def _retrieve_with_rewriting(
        self, question: str, settings
    ) -> list[RetrievedChunk]:
        """Multi-query retrieval path (with rewriting)."""
        import time

        rewrite_start = time.monotonic()

        # Step 1: Rewrite query into variants
        variants = await self.query_rewriter.rewrite(question)
        logger.info(
            "Query rewriting: %d variants produced in %.0fms",
            len(variants),
            (time.monotonic() - rewrite_start) * 1000,
        )

        # Step 2: Determine retrieval target size
        if self.reranker is not None:
            rrf_top_k = settings.reranker_top_k_before
        else:
            rrf_top_k = settings.retrieval_top_k

        # Step 3: For each variant, embed and search in parallel
        async def _search_variant(variant_query: str) -> list[RetrievedChunk]:
            embedding = await self.embedder.embed(variant_query)
            bm25_results, vector_results = await _parallel_search(
                self.search_index, variant_query, embedding, rrf_top_k
            )
            return rrf_fusion(bm25_results, vector_results, top_k=rrf_top_k)

        variant_results = await asyncio.gather(
            *[_search_variant(v) for v in variants]
        )

        # Step 4: Cross-variant RRF merge
        merged = rrf_fusion_multi(variant_results, top_k=rrf_top_k)

        rewrite_duration_ms = (time.monotonic() - rewrite_start) * 1000
        logger.info(
            "Query rewriting complete: %d variants, %d merged chunks, "
            "total rewrite+search time=%.0fms",
            len(variants),
            len(merged),
            rewrite_duration_ms,
        )

        return merged

    async def generate_and_persist(
        self,
        query_result: QueryResult,
    ) -> GenerationResult:
        """Phase 2: Build prompt, generate answer, validate, persist.

        Called only if retrieval succeeded (status='streaming').
        """
        answer_id = query_result.answer_id
        question = query_result.question
        chunks = query_result.retrieved_chunks

        try:
            # Step 1: Save answer record with status='streaming'
            citations_meta = []
            for i, rc in enumerate(chunks, start=1):
                chunk = rc.chunk
                citations_meta.append({
                    "index": i,
                    "document_id": chunk.document_id,
                    "document_title": chunk.document_title,
                    "section_path": chunk.section_path,
                    "source_path": chunk.source_path,
                    "chunk_index": chunk.chunk_index,
                    "score": rc.score,
                })
                # Note: chunk_ids in the answers table are UUIDs from the DB,
                # but we don't have them here — store document_id:chunk_index instead.
                # For MVP, we use the chunk's content_hash as a proxy.

            await self.answer_repository.save(
                answer_id=answer_id,
                question=question,
                answer=None,
                status="streaming",
                citations=citations_meta,
                chunk_ids=[],  # Chunk UUIDs not available at this point
            )

            # Step 2: Build prompt
            prompt = build_prompt(question, chunks)

            # Step 3: Generate answer (stream tokens)
            tokens: list[str] = []
            async for token in self.generator.generate_stream(prompt):
                tokens.append(token)

            answer_text = "".join(tokens)
            logger.info(
                "Generation complete for answer %s: %d tokens",
                answer_id,
                len(tokens),
            )

            # Step 4: Validate citations
            valid_ids = set(range(1, len(chunks) + 1))
            cleaned_text = self.citation_validator.validate(answer_text, valid_ids)

            # Step 5: Build final citations list (only those actually referenced)
            cited_indices = self.citation_validator.extract_citations(cleaned_text)
            final_citations = [
                citations_meta[i - 1]
                for i in cited_indices
                if i - 1 < len(citations_meta)
            ]

            # Step 6: Update answer record
            await self.answer_repository.update_status(
                answer_id=answer_id,
                status="answered",
                answer=cleaned_text,
                citations=final_citations,
            )

            return GenerationResult(
                answer_id=answer_id,
                answer_text=cleaned_text,
                citations=final_citations,
                status="answered",
            )

        except Exception as exc:
            logger.error(
                "Generation failed for answer %s: %s",
                answer_id,
                exc,
                exc_info=True,
            )

            # Mark as failed in DB
            try:
                await self.answer_repository.update_status(
                    answer_id=answer_id,
                    status="failed",
                )
            except Exception as db_exc:
                logger.error(
                    "Failed to update answer status to 'failed': %s",
                    db_exc,
                )

            return GenerationResult(
                answer_id=answer_id,
                answer_text="",
                citations=[],
                status="failed",
            )


async def _parallel_search(
    search_index,
    query: str,
    embedding: list[float],
    top_k: int,
) -> tuple[list, list]:
    """Run BM25 and vector search.

    Currently runs sequentially. Could be parallelized with asyncio.gather
    if the search index supports concurrent queries.
    """
    import asyncio

    bm25_task = search_index.bm25_search(query, top_k)
    vector_task = search_index.vector_search(embedding, top_k)

    bm25_results, vector_results = await asyncio.gather(
        bm25_task, vector_task
    )

    return bm25_results, vector_results


async def _rerank_with_timeout(
    reranker,
    query: str,
    candidates: list[RetrievedChunk],
    top_k: int,
    timeout_seconds: float,
) -> list[RetrievedChunk]:
    """Run reranking with a timeout fallback.

    If the reranker does not complete within *timeout_seconds*, log a warning
    and return the original (non-reranked) candidates truncated to *top_k*.
    """
    try:
        return await asyncio.wait_for(
            reranker.rerank(query, candidates, top_k=top_k),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Reranker timed out after %.1fs — falling back to RRF results "
            "(%d candidates truncated to %d)",
            timeout_seconds,
            len(candidates),
            top_k,
        )
        return candidates[:top_k]
    except Exception as exc:
        logger.warning(
            "Reranker failed (%s) — falling back to RRF results", exc
        )
        return candidates[:top_k]
