"""Health and readiness endpoints."""

import logging

import asyncpg
from fastapi import APIRouter, HTTPException, status

from src.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """Liveness probe — always returns 200 if the process is running."""
    return {"status": "ok"}


@router.get("/ready")
async def ready():
    """Readiness probe — checks connectivity to critical dependencies.

    Returns 503 if any dependency is unreachable.
    """
    settings = get_settings()
    checks: dict[str, str] = {}

    # Check PostgreSQL connectivity
    try:
        # Strip the driver prefix for asyncpg (postgresql+asyncpg:// -> postgresql://)
        dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(dsn, timeout=5.0)
        await conn.execute("SELECT 1")
        await conn.close()
        checks["database"] = "ok"
    except Exception as exc:
        logger.warning("Database readiness check failed: %s", exc)
        checks["database"] = f"error: {exc}"

    # Check Ollama connectivity
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.ollama_base_url}/api/tags",
                timeout=5.0,
            )
            resp.raise_for_status()
        checks["ollama"] = "ok"
    except Exception as exc:
        logger.warning("Ollama readiness check failed: %s", exc)
        checks["ollama"] = f"error: {exc}"

    all_ok = all(v == "ok" for v in checks.values())

    if not all_ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "checks": checks},
        )

    return {"status": "ready", "checks": checks}
