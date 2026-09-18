"""Integration tests for PgvectorIndex adapter.

Tests real PostgreSQL tsvector (BM25) and pgvector (cosine) queries
against a testcontainers PostgreSQL+pgvector instance.
"""

import math
import random

import pytest

from src.adapters.pgvector_index import PgvectorIndex, _sanitize_tsquery
from src.ports.models import Chunk


def _make_chunk(
    doc_id="doc1",
    chunk_index=0,
    content="test content",
    content_hash=None,
    section_path="",
):
    return Chunk(
        document_id=doc_id,
        document_title="Test Document",
        source_path="/test/doc.md",
        section_path=section_path,
        chunk_index=chunk_index,
        content=content,
        token_count=len(content.split()),
        content_hash=content_hash or f"hash_{doc_id}_{chunk_index}",
    )


def _fake_embedding(dim=768, seed=42):
    """Generate a deterministic unit-length fake embedding vector."""
    rng = random.Random(seed)
    vec = [rng.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec]


# -- tsquery sanitization (no DB needed) --


class TestSanitizeTsquery:
    def test_strips_special_characters(self):
        result = _sanitize_tsquery("hello & world | foo")
        assert "&" not in result
        assert "|" not in result

    def test_empty_input_returns_empty(self):
        assert _sanitize_tsquery("") == ""
        assert _sanitize_tsquery("   ") == ""

    def test_preserves_normal_words(self):
        result = _sanitize_tsquery("what is the travel policy")
        assert result == "what is the travel policy"

    def test_strips_parentheses_and_colons(self):
        result = _sanitize_tsquery("foo:(bar)")
        assert ":" not in result
        assert "(" not in result


# -- BM25 (tsvector) search --


@pytest.mark.integration
class TestBm25Search:
    async def test_bm25_finds_matching_chunks(self, clean_db, dsn):
        index = PgvectorIndex(database_url=dsn)
        chunks = [
            _make_chunk("doc1", 0, "The travel policy requires manager approval"),
            _make_chunk("doc1", 1, "The company holiday schedule is published"),
            _make_chunk("doc2", 0, "Travel expenses must be submitted within 30 days"),
        ]
        embeddings = [_fake_embedding(seed=i) for i in range(3)]
        await index.upsert_chunks(chunks, embeddings)

        results = await index.bm25_search("travel policy", k=5)

        assert len(results) >= 1
        contents = [r[0].content for r in results]
        assert any("travel" in c.lower() for c in contents)
        await index.close()

    async def test_bm25_returns_empty_for_no_match(self, clean_db, dsn):
        index = PgvectorIndex(database_url=dsn)
        chunks = [_make_chunk("doc1", 0, "The travel policy requires approval")]
        await index.upsert_chunks(chunks, [_fake_embedding()])

        results = await index.bm25_search("quantum computing", k=5)
        assert results == []
        await index.close()

    async def test_bm25_respects_limit(self, clean_db, dsn):
        index = PgvectorIndex(database_url=dsn)
        chunks = [
            _make_chunk("doc1", i, f"Travel policy section {i} covers expenses")
            for i in range(5)
        ]
        embeddings = [_fake_embedding(seed=i) for i in range(5)]
        await index.upsert_chunks(chunks, embeddings)

        results = await index.bm25_search("travel", k=2)
        assert len(results) <= 2
        await index.close()

    async def test_bm25_scores_are_positive(self, clean_db, dsn):
        index = PgvectorIndex(database_url=dsn)
        chunks = [_make_chunk("doc1", 0, "Kubernetes deployment strategies")]
        await index.upsert_chunks(chunks, [_fake_embedding()])

        results = await index.bm25_search("kubernetes", k=5)
        assert len(results) >= 1
        for _chunk, score in results:
            assert score > 0.0
        await index.close()


# -- Vector (cosine) search --


@pytest.mark.integration
class TestVectorSearch:
    async def test_vector_search_returns_similar_chunks(self, clean_db, dsn):
        index = PgvectorIndex(database_url=dsn)
        ref_embedding = _fake_embedding(seed=100)
        similar_vec = _fake_embedding(seed=100)
        different_vec = _fake_embedding(seed=999)

        chunks = [
            _make_chunk("doc1", 0, "Similar content"),
            _make_chunk("doc1", 1, "Different content"),
        ]
        await index.upsert_chunks(chunks, [similar_vec, different_vec])

        results = await index.vector_search(ref_embedding, k=5)
        assert len(results) == 2
        assert results[0][0].content == "Similar content"
        assert results[0][1] > results[1][1]
        await index.close()

    async def test_vector_search_scores_are_bounded(self, clean_db, dsn):
        index = PgvectorIndex(database_url=dsn)
        chunks = [_make_chunk("doc1", 0, "Some content")]
        await index.upsert_chunks(chunks, [_fake_embedding(seed=42)])

        results = await index.vector_search(_fake_embedding(seed=43), k=5)
        assert len(results) == 1
        _, score = results[0]
        assert -1.0 <= score <= 1.0
        await index.close()

    async def test_vector_search_respects_limit(self, clean_db, dsn):
        index = PgvectorIndex(database_url=dsn)
        chunks = [
            _make_chunk("doc1", i, f"Content chunk {i}") for i in range(5)
        ]
        embeddings = [_fake_embedding(seed=i) for i in range(5)]
        await index.upsert_chunks(chunks, embeddings)

        results = await index.vector_search(_fake_embedding(seed=50), k=2)
        assert len(results) == 2
        await index.close()


# -- Upsert / idempotency --


@pytest.mark.integration
class TestUpsertIdempotency:
    async def test_upsert_is_idempotent(self, clean_db, dsn):
        index = PgvectorIndex(database_url=dsn)
        chunks = [
            _make_chunk("doc1", 0, "Idempotent content", content_hash="hash_idem_0"),
            _make_chunk("doc1", 1, "Another chunk", content_hash="hash_idem_1"),
        ]
        embeddings = [_fake_embedding(seed=i) for i in range(2)]

        await index.upsert_chunks(chunks, embeddings)
        await index.upsert_chunks(chunks, embeddings)

        async with index._pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM chunks WHERE document_id = 'doc1'"
            )
        assert count == 2
        await index.close()

    async def test_upsert_updates_existing_row(self, clean_db, dsn):
        index = PgvectorIndex(database_url=dsn)
        chunks = [
            _make_chunk(
                "doc1", 0, "Original title", content_hash="hash_upd_0"
            ),
        ]
        embeddings = [_fake_embedding(seed=0)]
        await index.upsert_chunks(chunks, embeddings)

        # Upsert again with updated title (same dedup key)
        updated_chunk = Chunk(
            document_id="doc1",
            document_title="Updated Title",
            source_path="/test/doc.md",
            section_path="",
            chunk_index=0,
            content="Original title",
            token_count=2,
            content_hash="hash_upd_0",
        )
        await index.upsert_chunks([updated_chunk], [_fake_embedding(seed=1)])

        async with index._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT document_title FROM chunks WHERE document_id = 'doc1'"
            )
        assert row["document_title"] == "Updated Title"
        await index.close()

    async def test_upsert_empty_list_is_noop(self, clean_db, dsn):
        index = PgvectorIndex(database_url=dsn)
        await index.upsert_chunks([], [])

        async with index._pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM chunks")
        assert count == 0
        await index.close()

    async def test_upsert_mismatched_lengths_raises(self, clean_db, dsn):
        index = PgvectorIndex(database_url=dsn)
        chunks = [_make_chunk("doc1", 0, "content")]
        embeddings = [_fake_embedding(seed=0), _fake_embedding(seed=1)]

        with pytest.raises(ValueError, match="mismatch"):
            await index.upsert_chunks(chunks, embeddings)
        await index.close()
