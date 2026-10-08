"""Unit tests for conversation history integration in prompt building."""

import pytest
from src.core.query_pipeline import build_prompt
from src.core.retrieval import RetrievedChunk, Chunk


@pytest.fixture
def sample_chunks():
    """Sample retrieved chunks for testing."""
    return [
        RetrievedChunk(
            score=0.95,
            bm25_rank=1,
            vector_rank=1,
            chunk=Chunk(
                document_id="doc-1",
                document_title="Test Document",
                section_path="Introduction",
                source_path="/test/doc.md",
                chunk_index=0,
                content="This is the first chunk content.",
                token_count=10,
                content_hash="hash1",
            ),
        ),
        RetrievedChunk(
            score=0.85,
            bm25_rank=2,
            vector_rank=2,
            chunk=Chunk(
                document_id="doc-1",
                document_title="Test Document",
                section_path="Methods",
                source_path="/test/doc.md",
                chunk_index=1,
                content="This is the second chunk content.",
                token_count=12,
                content_hash="hash2",
            ),
        ),
    ]


class TestBuildPromptWithConversationHistory:
    """Tests for build_prompt with conversation history."""

    def test_build_prompt_without_history(self, sample_chunks):
        """Test building prompt without conversation history."""
        prompt = build_prompt("What is RAG?", sample_chunks)

        assert "What is RAG?" in prompt
        assert "This is the first chunk content." in prompt
        assert "This is the second chunk content." in prompt
        assert "Conversation History" not in prompt

    def test_build_prompt_with_empty_history(self, sample_chunks):
        """Test building prompt with empty conversation history."""
        prompt = build_prompt("What is RAG?", sample_chunks, conversation_history=[])

        assert "Conversation History" not in prompt

    def test_build_prompt_with_single_exchange(self, sample_chunks):
        """Test building prompt with single Q&A exchange."""
        history = [
            {"question": "What is AI?", "answer": "AI is artificial intelligence."}
        ]

        prompt = build_prompt("What is RAG?", sample_chunks, conversation_history=history)

        assert "Conversation History" in prompt
        assert "Q: What is AI?" in prompt
        assert "A: AI is artificial intelligence." in prompt
        # Current question is under ## Question, not Q:
        assert "What is RAG?" in prompt

    def test_build_prompt_with_multiple_exchanges(self, sample_chunks):
        """Test building prompt with multiple Q&A exchanges."""
        history = [
            {"question": "What is AI?", "answer": "AI is artificial intelligence."},
            {"question": "What is ML?", "answer": "ML is machine learning."},
            {"question": "What is DL?", "answer": "DL is deep learning."},
        ]

        prompt = build_prompt("What is RAG?", sample_chunks, conversation_history=history)

        assert "Q: What is AI?" in prompt
        assert "A: AI is artificial intelligence." in prompt
        assert "Q: What is ML?" in prompt
        assert "A: ML is machine learning." in prompt
        assert "Q: What is DL?" in prompt
        assert "A: DL is deep learning." in prompt

    def test_build_prompt_history_before_context(self, sample_chunks):
        """Test that conversation history appears before context section."""
        history = [
            {"question": "What is AI?", "answer": "AI is artificial intelligence."}
        ]

        prompt = build_prompt("What is RAG?", sample_chunks, conversation_history=history)

        history_pos = prompt.find("Conversation History")
        context_pos = prompt.find("## Context")

        assert history_pos != -1
        assert context_pos != -1
        assert history_pos < context_pos

    def test_build_prompt_with_answerless_exchange(self, sample_chunks):
        """Test building prompt with exchange that has no answer."""
        history = [
            {"question": "What is AI?", "answer": None}
        ]

        prompt = build_prompt("What is RAG?", sample_chunks, conversation_history=history)

        assert "Q: What is AI?" in prompt
        # Should not include "A:" line when answer is None
        assert "A:" not in prompt or "A: What is AI?" not in prompt

    def test_build_prompt_preserves_citation_format(self, sample_chunks):
        """Test that citation format is preserved with conversation history."""
        history = [
            {"question": "What is AI?", "answer": "AI is artificial intelligence [1]."}
        ]

        prompt = build_prompt("What is RAG?", sample_chunks, conversation_history=history)

        # Check that context still has numbered references
        assert "[1] Test Document" in prompt
        assert "[2] Test Document" in prompt
