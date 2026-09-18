"""Query pipeline — orchestrates the full retrieval-to-generation flow.

Coordinates: embed query -> retrieve -> abstain? -> build prompt ->
generate -> validate citations -> persist answer.
"""

import logging
import uuid
from dataclasses import dataclass

from src.config import get_settings
from src.core.retrieval import RetrievedChunk, rrf_fusion, should_abstain

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
    ):
        self.embedder = embedder
        self.search_index = search_index
        self.generator = generator
        self.citation_validator = citation_validator
        self.answer_repository = answer_repository

    async def retrieve(self, question: str) -> QueryResult:
        """Phase 1: Embed query, retrieve chunks, check abstention.

        This runs synchronously (before streaming). If abstention triggers,
        no answer record is created and status is 'insufficient_evidence'.
        """
        settings = get_settings()
        answer_id = str(uuid.uuid4())

        try:
            # Step 1: Embed the query
            logger.info("Embedding query: %s", question[:100])
            query_embedding = await self.embedder.embed(question)

            # Step 2: Run hybrid search (BM25 + vector)
            top_k = settings.retrieval_top_k
            bm25_results, vector_results = await _parallel_search(
                self.search_index, question, query_embedding, top_k
            )

            # Step 3: RRF fusion
            fused = rrf_fusion(bm25_results, vector_results, top_k=top_k)

            # Step 4: Abstention check
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
