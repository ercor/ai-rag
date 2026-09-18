"""Ingestion API endpoint.

POST /v1/ingest → 202 + job_id (async job submission)
GET /v1/ingest/{job_id} → job progress
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, status

from src.container import get_ingestion_service, get_job_registry
from src.core.job_registry import JobConflictError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingestion"])


@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest():
    """Submit an ingestion job. Returns 202 with job_id immediately.

    The job runs in the background. Use GET /v1/ingest/{job_id} to poll progress.
    Returns 409 if a job is already running.
    """
    registry = get_job_registry()

    try:
        job_id = await registry.submit()
    except JobConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "job_already_running", "job_id": exc.active_job_id},
        )

    # Start background task
    asyncio.create_task(_run_job(job_id))

    logger.info("Ingestion job submitted: %s", job_id)
    return {"job_id": job_id}


@router.get("/ingest/{job_id}")
async def get_ingest_job(job_id: str):
    """Get the status and progress of an ingestion job.

    Returns 404 if job_id not found.
    """
    registry = get_job_registry()
    job = await registry.get(job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    return {
        "job_id": job.job_id,
        "state": job.state,
        "total": job.total,
        "processed": job.processed,
        "skipped": job.skipped,
        "chunks": job.chunks,
        "failed": job.failed,
        "failures": job.failures,
    }


async def _run_job(job_id: str) -> None:
    """Background task that runs the ingestion pipeline."""
    registry = get_job_registry()

    try:
        # Mark as running
        await registry.update(job_id, state="running")

        service = get_ingestion_service()
        job = await registry.get(job_id)

        # Run the pipeline with progress tracking
        result = await service.run(progress=job)

        # Mark as completed
        await registry.update(
            job_id,
            state="completed",
            total=job.total,
            processed=result.processed,
            skipped=result.skipped,
            chunks=result.chunks,
            failed=result.failed,
            failures=result.failures,
        )

        logger.info(
            "Ingestion job %s complete: %d processed, %d skipped, %d chunks, %d failed",
            job_id,
            result.processed,
            result.skipped,
            result.chunks,
            result.failed,
        )

    except Exception as exc:
        logger.error("Ingestion job %s failed: %s", job_id, exc, exc_info=True)
        await registry.update(job_id, state="failed")
