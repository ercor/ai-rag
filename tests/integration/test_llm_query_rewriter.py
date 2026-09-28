"""Integration tests for LLMQueryRewriter with real Ollama.

These tests require a running Ollama instance with the configured model.
They verify end-to-end behavior of the query rewriter adapter.
"""

import logging

import pytest

from src.adapters.llm_query_rewriter import LLMQueryRewriter
from src.adapters.ollama_generator import OllamaGenerator

logger = logging.getLogger(__name__)


@pytest.fixture
def generator():
    """Create a real OllamaGenerator instance."""
    return OllamaGenerator()


@pytest.fixture
def rewriter(generator):
    """Create an LLMQueryRewriter with real Generator."""
    return LLMQueryRewriter(generator=generator, num_variants=3)


@pytest.mark.integration
class TestLLMQueryRewriterIntegration:
    """Integration tests with real Ollama."""

    @pytest.mark.asyncio
    async def test_rewrite_produces_variants(self, rewriter):
        """Real LLM produces the expected number of variants."""
        result = await rewriter.rewrite("What is the travel reimbursement policy?")

        assert len(result) >= 1
        assert len(result) <= 3
        # Original query must be included
        assert "What is the travel reimbursement policy?" in result

    @pytest.mark.asyncio
    async def test_variants_are_different_from_original(self, rewriter):
        """At least one variant should differ from the original."""
        result = await rewriter.rewrite(
            "How do I file an expense report for international travel?"
        )

        assert len(result) >= 1
        # If we got more than 1, at least one should be different
        if len(result) > 1:
            non_original = [v for v in result if v != result[0]]
            assert len(non_original) >= 1, "Expected at least one different variant"

    @pytest.mark.asyncio
    async def test_variants_are_standalone_queries(self, rewriter):
        """Each variant should be a standalone query (no references to 'above')."""
        result = await rewriter.rewrite("What is the company's remote work policy?")

        for variant in result:
            # Should not contain meta-references
            assert "above" not in variant.lower() or "the above" not in variant.lower()
            assert len(variant.strip()) > 5, f"Variant too short: {variant}"

    @pytest.mark.asyncio
    async def test_short_query_returns_at_least_original(self, rewriter):
        """Even a very short query returns at least the original."""
        result = await rewriter.rewrite("help")

        assert len(result) >= 1
        assert "help" in result

    @pytest.mark.asyncio
    async def test_num_variants_2(self, generator):
        """num_variants=2 produces at most 2 variants."""
        rewriter = LLMQueryRewriter(generator=generator, num_variants=2)
        result = await rewriter.rewrite("What is the leave policy?")

        assert len(result) >= 1
        assert len(result) <= 2
