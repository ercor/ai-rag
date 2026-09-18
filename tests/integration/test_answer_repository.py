"""Integration tests for PgAnswerRepository adapter.

Tests answer persistence, retrieval, vote updates, and status transitions
against a real PostgreSQL instance via testcontainers.
"""

import uuid

import pytest

from src.adapters.pg_answer_repository import PgAnswerRepository


@pytest.mark.integration
class TestAnswerPersistence:
    async def test_save_and_retrieve_answer(self, clean_db, dsn):
        repo = PgAnswerRepository(database_url=dsn)
        answer_id = str(uuid.uuid4())

        await repo.save(
            answer_id=answer_id,
            question="What is the travel policy?",
            answer="The travel policy requires manager approval [1].",
            status="answered",
            citations=[{"index": 1, "document_title": "Travel Policy"}],
            chunk_ids=[],
        )

        record = await repo.get_answer(answer_id)
        assert record is not None
        assert record["question"] == "What is the travel policy?"
        assert "manager approval" in record["answer"]
        assert record["status"] == "answered"
        await repo.close()

    async def test_save_with_null_answer(self, clean_db, dsn):
        repo = PgAnswerRepository(database_url=dsn)
        answer_id = str(uuid.uuid4())

        await repo.save(
            answer_id=answer_id,
            question="Unknown question?",
            answer=None,
            status="insufficient_evidence",
            citations=[],
            chunk_ids=[],
        )

        record = await repo.get_answer(answer_id)
        assert record is not None
        assert record["answer"] is None
        assert record["status"] == "insufficient_evidence"
        await repo.close()

    async def test_get_nonexistent_answer_returns_none(self, clean_db, dsn):
        repo = PgAnswerRepository(database_url=dsn)
        record = await repo.get_answer(str(uuid.uuid4()))
        assert record is None
        await repo.close()

    async def test_update_vote(self, clean_db, dsn):
        repo = PgAnswerRepository(database_url=dsn)
        answer_id = str(uuid.uuid4())

        await repo.save(
            answer_id=answer_id,
            question="Test?",
            answer="Answer",
            status="answered",
            citations=[],
            chunk_ids=[],
        )

        await repo.update_vote(answer_id, "up")
        record = await repo.get_answer(answer_id)
        assert record["vote"] == "up"

        await repo.update_vote(answer_id, "down")
        record = await repo.get_answer(answer_id)
        assert record["vote"] == "down"
        await repo.close()

    async def test_update_vote_invalid_value_raises(self, clean_db, dsn):
        repo = PgAnswerRepository(database_url=dsn)
        answer_id = str(uuid.uuid4())

        await repo.save(
            answer_id=answer_id,
            question="Test?",
            answer="Answer",
            status="answered",
            citations=[],
            chunk_ids=[],
        )

        with pytest.raises(ValueError, match="Invalid vote"):
            await repo.update_vote(answer_id, "sideways")
        await repo.close()

    async def test_update_status_with_answer_and_citations(self, clean_db, dsn):
        repo = PgAnswerRepository(database_url=dsn)
        answer_id = str(uuid.uuid4())

        await repo.save(
            answer_id=answer_id,
            question="Test?",
            answer=None,
            status="streaming",
            citations=[],
            chunk_ids=[],
        )

        await repo.update_status(
            answer_id=answer_id,
            status="answered",
            answer="Final answer text [1].",
            citations=[{"index": 1, "doc": "test"}],
        )

        record = await repo.get_answer(answer_id)
        assert record["status"] == "answered"
        assert record["answer"] == "Final answer text [1]."
        await repo.close()

    async def test_update_status_without_answer(self, clean_db, dsn):
        repo = PgAnswerRepository(database_url=dsn)
        answer_id = str(uuid.uuid4())

        await repo.save(
            answer_id=answer_id,
            question="Test?",
            answer=None,
            status="streaming",
            citations=[],
            chunk_ids=[],
        )

        await repo.update_status(answer_id=answer_id, status="failed")

        record = await repo.get_answer(answer_id)
        assert record["status"] == "failed"
        await repo.close()

    async def test_save_upsert_on_conflict(self, clean_db, dsn):
        repo = PgAnswerRepository(database_url=dsn)
        answer_id = str(uuid.uuid4())

        await repo.save(
            answer_id=answer_id,
            question="Original?",
            answer="Original answer",
            status="streaming",
            citations=[],
            chunk_ids=[],
        )

        # Re-save with same ID updates the record
        await repo.save(
            answer_id=answer_id,
            question="Updated?",
            answer="Updated answer",
            status="answered",
            citations=[{"index": 1}],
            chunk_ids=[],
        )

        record = await repo.get_answer(answer_id)
        assert record["question"] == "Updated?"
        assert record["answer"] == "Updated answer"
        assert record["status"] == "answered"
        await repo.close()
