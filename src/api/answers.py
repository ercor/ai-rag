"""Answers API endpoints.

POST /v1/answers — create answer (sync retrieval, two-phase abstention)
GET /v1/answers/{id}/stream — SSE token stream + done event
POST /v1/answers/{id}/feedback — record user vote (up/down)
"""

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.container import (
    get_answer_repository,
    get_citation_validator,
    get_embedder,
    get_generator,
    get_query_rewriter,
    get_reranker,
    get_search_index,
)
from src.core.query_pipeline import QueryPipeline

logger = logging.getLogger(__name__)

router = APIRouter(tags=["answers"])

# In-memory store for active generation tasks (answer_id -> asyncio.Task)
# This allows the SSE endpoint to consume tokens from a running generation.
_active_generations: dict[str, asyncio.Queue] = {}


class CreateAnswerRequest(BaseModel):
    """Request body for POST /v1/answers."""

    question: str


class FeedbackRequest(BaseModel):
    """Request body for POST /v1/answers/{id}/feedback."""

    vote: str  # "up" or "down"


def _get_pipeline() -> QueryPipeline:
    """Build a QueryPipeline from the DI container."""
    embedder = get_embedder()
    search_index = get_search_index()
    generator = get_generator()
    citation_validator = get_citation_validator()
    answer_repository = get_answer_repository()
    reranker = get_reranker()
    query_rewriter = get_query_rewriter()

    if not all([embedder, search_index, generator, citation_validator, answer_repository]):
        missing = []
        if not embedder:
            missing.append("embedder")
        if not search_index:
            missing.append("search_index")
        if not generator:
            missing.append("generator")
        if not citation_validator:
            missing.append("citation_validator")
        if not answer_repository:
            missing.append("answer_repository")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Required adapters not configured: {', '.join(missing)}",
        )

    return QueryPipeline(
        embedder=embedder,
        search_index=search_index,
        generator=generator,
        citation_validator=citation_validator,
        answer_repository=answer_repository,
        reranker=reranker,
        query_rewriter=query_rewriter,
    )


@router.post("/answers")
async def create_answer(req: CreateAnswerRequest):
    """Create an answer — runs retrieval synchronously (two-phase).

    Phase 1: Embed query, retrieve chunks, check abstention.
    - If abstention triggers: return {status: "insufficient_evidence", answer: null}
    - If retrieval succeeds: create answer record, start generation task,
      return {status: "streaming", answer_id: "...", answer: null}

    The client then connects to GET /v1/answers/{id}/stream for SSE tokens.
    """
    if not req.question or not req.question.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty",
        )

    pipeline = _get_pipeline()

    # Phase 1: Retrieval (synchronous)
    query_result = await pipeline.retrieve(req.question.strip())

    if query_result.status == "insufficient_evidence":
        return {
            "answer_id": None,
            "status": "insufficient_evidence",
            "answer": None,
            "citations": [],
        }

    # Phase 2: Start generation in background
    queue: asyncio.Queue = asyncio.Queue()
    _active_generations[query_result.answer_id] = queue

    # Launch generation task
    asyncio.create_task(
        _run_generation(pipeline, query_result, queue),
        name=f"generate-{query_result.answer_id}",
    )

    return {
        "answer_id": query_result.answer_id,
        "status": "streaming",
        "answer": None,
        "citations": [],
    }


async def _run_generation(pipeline: QueryPipeline, query_result, queue: asyncio.Queue):
    """Background task: generate answer and push tokens to the SSE queue."""
    answer_id = query_result.answer_id

    try:
        # Build prompt
        from src.core.query_pipeline import build_prompt

        prompt = build_prompt(query_result.question, query_result.retrieved_chunks)

        # Save answer record as streaming
        citations_meta = []
        for i, rc in enumerate(query_result.retrieved_chunks, start=1):
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

        await pipeline.answer_repository.save(
            answer_id=answer_id,
            question=query_result.question,
            answer=None,
            status="streaming",
            citations=citations_meta,
            chunk_ids=[],
        )

        # Stream tokens
        tokens: list[str] = []
        async for token in pipeline.generator.generate_stream(prompt):
            tokens.append(token)
            await queue.put({"type": "token", "data": token})

        answer_text = "".join(tokens)

        # Validate citations
        valid_ids = set(range(1, len(query_result.retrieved_chunks) + 1))
        cleaned_text = pipeline.citation_validator.validate(answer_text, valid_ids)
        cited_indices = pipeline.citation_validator.extract_citations(cleaned_text)
        final_citations = [
            citations_meta[i - 1]
            for i in cited_indices
            if i - 1 < len(citations_meta)
        ]

        # Update answer record
        await pipeline.answer_repository.update_status(
            answer_id=answer_id,
            status="answered",
            answer=cleaned_text,
            citations=final_citations,
        )

        # Send done event
        await queue.put({
            "type": "done",
            "data": {
                "answer": cleaned_text,
                "citations": final_citations,
            },
        })

    except Exception as exc:
        logger.error(
            "Generation failed for answer %s: %s",
            answer_id,
            exc,
            exc_info=True,
        )

        # Try to mark as failed
        try:
            await pipeline.answer_repository.update_status(
                answer_id=answer_id,
                status="failed",
            )
        except Exception:
            pass

        await queue.put({
            "type": "error",
            "data": {"reason": str(exc)},
        })

    finally:
        # Signal queue end
        await queue.put(None)


@router.get("/answers/{answer_id}/stream")
async def stream_answer(answer_id: str, request: Request):
    """SSE stream of answer tokens.

    Events:
    - event: token, data: "<token text>"
    - event: done, data: {"answer": "...", "citations": [...]}
    - event: error, data: {"reason": "..."}
    """
    queue = _active_generations.get(answer_id)

    if queue is None:
        # Check if answer already completed in DB
        repo = get_answer_repository()
        if repo:
            record = await repo.get_answer(answer_id)
            if record and record["status"] == "answered":
                # Return a single-event stream with the completed answer
                async def completed_stream():
                    yield _sse_event("done", json.dumps({
                        "answer": record["answer"],
                        "citations": record["citations"],
                    }))

                return StreamingResponse(
                    completed_stream(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    },
                )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active generation for answer {answer_id}",
        )

    async def event_generator():
        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.info("Client disconnected from stream %s", answer_id)
                    break

                try:
                    item = await asyncio.wait_for(queue.get(), timeout=300.0)
                except asyncio.TimeoutError:
                    # Send keepalive comment
                    yield ": keepalive\n\n"
                    continue

                if item is None:
                    # End of stream
                    break

                event_type = item["type"]
                event_data = item["data"]

                if event_type == "token":
                    yield _sse_event("token", event_data)
                elif event_type == "done":
                    yield _sse_event("done", json.dumps(event_data))
                    break
                elif event_type == "error":
                    yield _sse_event("error", json.dumps(event_data))
                    break
        finally:
            # Clean up the queue
            _active_generations.pop(answer_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/answers/{answer_id}/feedback")
async def submit_feedback(answer_id: str, req: FeedbackRequest):
    """Record user feedback (thumbs up/down) for an answer."""
    if req.vote not in ("up", "down"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vote must be 'up' or 'down'",
        )

    repo = get_answer_repository()
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AnswerRepository adapter not configured",
        )

    try:
        await repo.update_vote(answer_id, req.vote)
    except Exception as exc:
        logger.error("Failed to save feedback for %s: %s", answer_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save feedback",
        )

    return {"answer_id": answer_id, "vote": req.vote, "status": "ok"}


def _sse_event(event: str, data: str) -> str:
    """Format a Server-Sent Event."""
    return f"event: {event}\ndata: {data}\n\n"
