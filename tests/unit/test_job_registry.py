"""Unit tests for JobRegistry.

Tests:
- submit returns job_id and creates pending state
- get returns job state
- concurrent submit raises JobConflictError (409)
- update modifies fields
- unknown job_id returns None
- state transitions: pending → running → completed/failed
"""

import pytest

from src.core.job_registry import JobConflictError, JobRegistry, JobState


class TestJobRegistrySubmit:
    async def test_submit_returns_job_id(self):
        """submit() returns a unique job_id string."""
        registry = JobRegistry()
        job_id = await registry.submit()

        assert isinstance(job_id, str)
        assert len(job_id) > 0

    async def test_submit_creates_pending_state(self):
        """Newly submitted job has state='pending' and zero counters."""
        registry = JobRegistry()
        job_id = await registry.submit()
        job = await registry.get(job_id)

        assert job is not None
        assert job.job_id == job_id
        assert job.state == "pending"
        assert job.total == 0
        assert job.processed == 0
        assert job.skipped == 0
        assert job.chunks == 0
        assert job.failed == 0
        assert job.failures == []

    async def test_concurrent_submit_raises_conflict(self):
        """Second submit while first is pending/running → JobConflictError."""
        registry = JobRegistry()
        first_id = await registry.submit()

        with pytest.raises(JobConflictError) as exc_info:
            await registry.submit()

        assert exc_info.value.active_job_id == first_id

    async def test_submit_after_completed_succeeds(self):
        """After a job reaches terminal state, new submit is allowed."""
        registry = JobRegistry()
        first_id = await registry.submit()
        await registry.update(first_id, state="completed")

        second_id = await registry.submit()
        assert second_id != first_id

    async def test_submit_after_failed_succeeds(self):
        """After a job fails, new submit is allowed."""
        registry = JobRegistry()
        first_id = await registry.submit()
        await registry.update(first_id, state="failed")

        second_id = await registry.submit()
        assert second_id != first_id


class TestJobRegistryGet:
    async def test_get_unknown_returns_none(self):
        """get() with unknown job_id returns None."""
        registry = JobRegistry()
        result = await registry.get("nonexistent-id")
        assert result is None

    async def test_get_returns_correct_job(self):
        """get() returns the correct JobState for a known job_id."""
        registry = JobRegistry()
        job_id = await registry.submit()
        job = await registry.get(job_id)

        assert isinstance(job, JobState)
        assert job.job_id == job_id


class TestJobRegistryUpdate:
    async def test_update_state(self):
        """update() changes job state."""
        registry = JobRegistry()
        job_id = await registry.submit()

        await registry.update(job_id, state="running")
        job = await registry.get(job_id)
        assert job.state == "running"

    async def test_update_counters(self):
        """update() modifies counter fields."""
        registry = JobRegistry()
        job_id = await registry.submit()

        await registry.update(
            job_id,
            state="running",
            total=10,
            processed=4,
            chunks=30,
        )
        job = await registry.get(job_id)
        assert job.total == 10
        assert job.processed == 4
        assert job.chunks == 30

    async def test_update_failures(self):
        """update() can append failure records."""
        registry = JobRegistry()
        job_id = await registry.submit()

        await registry.update(
            job_id,
            state="running",
            total=5,
            failed=1,
            failures=[{"path": "/docs/bad.md", "error": "Parse error"}],
        )
        job = await registry.get(job_id)
        assert job.failed == 1
        assert len(job.failures) == 1
        assert job.failures[0]["path"] == "/docs/bad.md"

    async def test_update_unknown_job_raises(self):
        """update() on unknown job_id raises KeyError."""
        registry = JobRegistry()
        with pytest.raises(KeyError):
            await registry.update("nonexistent", state="running")


class TestJobRegistryLifecycle:
    async def test_full_lifecycle(self):
        """pending → running → completed with progress updates."""
        registry = JobRegistry()
        job_id = await registry.submit()

        # Verify pending
        job = await registry.get(job_id)
        assert job.state == "pending"

        # Transition to running with totals
        await registry.update(job_id, state="running", total=10)
        job = await registry.get(job_id)
        assert job.state == "running"
        assert job.total == 10

        # Progress update
        await registry.update(job_id, processed=5, chunks=20)
        job = await registry.get(job_id)
        assert job.processed == 5
        assert job.chunks == 20

        # Complete
        await registry.update(job_id, state="completed", processed=10, chunks=50, skipped=2)
        job = await registry.get(job_id)
        assert job.state == "completed"
        assert job.processed == 10
        assert job.chunks == 50
        assert job.skipped == 2

    async def test_failed_lifecycle(self):
        """pending → running → failed on system error."""
        registry = JobRegistry()
        job_id = await registry.submit()

        await registry.update(job_id, state="running", total=5)
        await registry.update(job_id, state="failed")

        job = await registry.get(job_id)
        assert job.state == "failed"

    async def test_completed_with_per_file_failures(self):
        """All files fail → state=completed, failed=total."""
        registry = JobRegistry()
        job_id = await registry.submit()

        await registry.update(
            job_id,
            state="completed",
            total=3,
            failed=3,
            failures=[
                {"path": "/docs/a.md", "error": "err1"},
                {"path": "/docs/b.md", "error": "err2"},
                {"path": "/docs/c.md", "error": "err3"},
            ],
        )

        job = await registry.get(job_id)
        assert job.state == "completed"
        assert job.failed == 3
        assert job.total == 3
        assert len(job.failures) == 3
