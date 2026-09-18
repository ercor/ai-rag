"""JobRegistry — in-memory job tracking for async ingestion.

Stores job state in a dict protected by asyncio.Lock.
Lost on restart (acceptable: ingestion is idempotent).
"""

import uuid
from dataclasses import dataclass, field


class JobConflictError(Exception):
    """Raised when a job is submitted while another is active (pending/running)."""

    def __init__(self, active_job_id: str):
        self.active_job_id = active_job_id
        super().__init__(f"Job already running: {active_job_id}")


@dataclass
class JobState:
    """Represents the state of an ingestion job."""

    job_id: str
    state: str = "pending"  # pending | running | completed | failed
    total: int = 0
    processed: int = 0
    skipped: int = 0
    chunks: int = 0
    failed: int = 0
    failures: list[dict] = field(default_factory=list)


_TERMINAL_STATES = {"completed", "failed"}


class JobRegistry:
    """In-memory job store with asyncio.Lock for thread safety.

    Only one job can be active (pending/running) at a time.
    """

    def __init__(self):
        import asyncio

        self._jobs: dict[str, JobState] = {}
        self._lock = asyncio.Lock()

    async def submit(self) -> str:
        """Create a new job. Returns job_id.

        Raises JobConflictError if a job is already pending/running.
        """
        async with self._lock:
            # Check for active job
            for job in self._jobs.values():
                if job.state not in _TERMINAL_STATES:
                    raise JobConflictError(job.job_id)

            job_id = uuid.uuid4().hex
            self._jobs[job_id] = JobState(job_id=job_id)
            return job_id

    async def get(self, job_id: str) -> JobState | None:
        """Return job state, or None if not found."""
        return self._jobs.get(job_id)

    async def update(self, job_id: str, **fields) -> None:
        """Update job fields. Raises KeyError if job_id not found."""
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)

            for key, value in fields.items():
                if hasattr(job, key):
                    setattr(job, key, value)
