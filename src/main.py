"""FastAPI application entry point.

Configures lifespan (startup/shutdown), CORS middleware, and router includes.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.answers import router as answers_router
from src.api.health import router as health_router
from src.api.ingestion import router as ingestion_router
from src.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def _run_startup_scan() -> None:
    """Run the ingestion pipeline on application startup as a background job.

    Submits a job to JobRegistry and runs it as a background task.
    The job is queryable via GET /v1/ingest/{job_id}.
    Errors are logged but do not prevent the app from starting.
    """
    try:
        from src.container import get_job_registry
        from src.core.job_registry import JobConflictError

        registry = get_job_registry()

        try:
            job_id = await registry.submit()
        except JobConflictError:
            logger.info("Startup scan skipped: another job is already running")
            return

        logger.info("Startup scan submitted as job: %s", job_id)

        # Run as background task (non-blocking)
        asyncio.create_task(_run_startup_job(job_id))

    except Exception as exc:
        logger.error("Startup scan submission failed: %s", exc, exc_info=True)


async def _run_startup_job(job_id: str) -> None:
    """Background task for startup scan."""
    try:
        from src.container import get_ingestion_service, get_job_registry

        registry = get_job_registry()
        await registry.update(job_id, state="running")

        service = get_ingestion_service()
        job = await registry.get(job_id)

        result = await service.run(progress=job)

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
            "Startup scan complete: %d processed, %d skipped, %d chunks, %d failed",
            result.processed,
            result.skipped,
            result.chunks,
            result.failed,
        )

    except Exception as exc:
        logger.error("Startup scan failed: %s", exc, exc_info=True)
        from src.container import get_job_registry
        registry = get_job_registry()
        await registry.update(job_id, state="failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown hooks."""
    settings = get_settings()
    logger.info("Starting ai-rag backend")
    logger.info("Watch directory: %s", settings.watch_dir)
    logger.info("Database: %s", settings.database_url.split("@")[-1])  # hide credentials
    logger.info("Ollama: %s (model=%s)", settings.ollama_base_url, settings.ollama_model)

    # Phase 2: trigger startup scan of WATCH_DIR
    await _run_startup_scan()

    logger.info("Startup complete")

    yield

    # Shutdown: close any open adapter resources
    logger.info("Shutting down ai-rag backend")


app = FastAPI(
    title="ai-rag",
    description="Enterprise RAG MVP with hexagonal architecture",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health_router)
app.include_router(ingestion_router, prefix="/v1")
app.include_router(answers_router, prefix="/v1")
