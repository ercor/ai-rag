"""Unit tests for the QueryRewriter port and LLMQueryRewriter adapter.

Tests cover:
- Variant count (original + N-1 rephrasings)
- Original query always included
- Generator failure fallback -> [query]
- Malformed LLM output fallback -> [query]
- Output parsing (numbered lists, bullet points, plain lines)
- Deduplication of variants
- num_variants=1 returns only original
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.adapters.llm_query_rewriter import LLMQueryRewriter


def _mock_generator(output: str) -> AsyncMock:
    """Create a mock Generator that yields the given output as tokens."""
    gen = AsyncMock()

    async def _stream(prompt):
        # Yield the whole output as a single token for simplicity
        yield output

    gen.generate_stream = _stream
    return gen


def _mock_generator_error() -> AsyncMock:
    """Create a mock Generator that raises an error."""
    gen = AsyncMock()

    async def _stream(prompt):
        raise RuntimeError("Ollama unavailable")
        yield  # Make it an async generator  # noqa: E501

    gen.generate_stream = _stream
    return gen


class TestLLMQueryRewriterVariantCount:
    """Test that the correct number of variants is produced."""

    @pytest.mark.asyncio
    async def test_produces_correct_variant_count(self):
        """rewrite() produces num_variants total (original + N-1)."""
        gen = _mock_generator(
            "What is the process for submitting expenses?\n"
            "Steps to file an expense claim"
        )
        rewriter = LLMQueryRewriter(generator=gen, num_variants=3)

        result = await rewriter.rewrite("How do I file an expense report?")

        assert len(result) == 3
        # Original query must be first
        assert result[0] == "How do I file an expense report?"

    @pytest.mark.asyncio
    async def test_num_variants_1_returns_only_original(self):
        """num_variants=1 skips LLM call and returns only original."""
        gen = AsyncMock()
        rewriter = LLMQueryRewriter(generator=gen, num_variants=1)

        result = await rewriter.rewrite("test query")

        assert result == ["test query"]
        # Generator should NOT have been called
        gen.generate_stream.assert_not_called()

    @pytest.mark.asyncio
    async def test_num_variants_2_produces_two(self):
        """num_variants=2 produces original + 1 rephrasing."""
        gen = _mock_generator("What is the expense submission process?")
        rewriter = LLMQueryRewriter(generator=gen, num_variants=2)

        result = await rewriter.rewrite("How do I file an expense report?")

        assert len(result) == 2
        assert result[0] == "How do I file an expense report?"


class TestLLMQueryRewriterOriginalIncluded:
    """Test that the original query is always in the result."""

    @pytest.mark.asyncio
    async def test_original_query_is_first(self):
        """Original query is always the first element."""
        gen = _mock_generator("Alternative phrasing one\nAlternative phrasing two")
        rewriter = LLMQueryRewriter(generator=gen, num_variants=3)

        result = await rewriter.rewrite("What is the travel policy?")

        assert result[0] == "What is the travel policy?"

    @pytest.mark.asyncio
    async def test_original_not_duplicated_if_llm_repeats_it(self):
        """If LLM accidentally repeats the original, it's deduplicated."""
        gen = _mock_generator("What is the travel policy?")
        rewriter = LLMQueryRewriter(generator=gen, num_variants=2)

        result = await rewriter.rewrite("What is the travel policy?")

        # Should be deduplicated to just 1
        assert len(result) == 1
        assert result[0] == "What is the travel policy?"


class TestLLMQueryRewriterFallback:
    """Test graceful fallback on Generator failure."""

    @pytest.mark.asyncio
    async def test_generator_failure_returns_original_only(self):
        """When Generator raises, returns [query]."""
        gen = _mock_generator_error()
        rewriter = LLMQueryRewriter(generator=gen, num_variants=3)

        result = await rewriter.rewrite("test query")

        assert result == ["test query"]

    @pytest.mark.asyncio
    async def test_empty_llm_output_returns_original_only(self):
        """When LLM returns empty output, returns [query]."""
        gen = _mock_generator("")
        rewriter = LLMQueryRewriter(generator=gen, num_variants=3)

        result = await rewriter.rewrite("test query")

        assert result == ["test query"]

    @pytest.mark.asyncio
    async def test_whitespace_only_output_returns_original_only(self):
        """When LLM returns only whitespace, returns [query]."""
        gen = _mock_generator("   \n\n  \n  ")
        rewriter = LLMQueryRewriter(generator=gen, num_variants=3)

        result = await rewriter.rewrite("test query")

        assert result == ["test query"]


class TestLLMQueryRewriterOutputParsing:
    """Test parsing of various LLM output formats."""

    @pytest.mark.asyncio
    async def test_parse_numbered_list(self):
        """Handles numbered list output: '1. query\\n2. query'."""
        gen = _mock_generator(
            "1. What is the process for submitting expenses?\n"
            "2. Steps to file an expense claim"
        )
        rewriter = LLMQueryRewriter(generator=gen, num_variants=3)

        result = await rewriter.rewrite("How do I file an expense report?")

        assert len(result) == 3
        assert "process for submitting expenses" in result[1]
        assert "Steps to file" in result[2]

    @pytest.mark.asyncio
    async def test_parse_bullet_points(self):
        """Handles bullet point output: '- query\\n- query'."""
        gen = _mock_generator(
            "- What is the expense submission process?\n"
            "- How to submit an expense claim"
        )
        rewriter = LLMQueryRewriter(generator=gen, num_variants=3)

        result = await rewriter.rewrite("How do I file an expense report?")

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_parse_plain_lines(self):
        """Handles plain one-per-line output."""
        gen = _mock_generator(
            "What is the process for submitting expenses?\n"
            "Steps to file an expense claim"
        )
        rewriter = LLMQueryRewriter(generator=gen, num_variants=3)

        result = await rewriter.rewrite("How do I file an expense report?")

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_parse_with_extra_blank_lines(self):
        """Handles output with blank lines between variants."""
        gen = _mock_generator(
            "\nWhat is the expense process?\n\nSteps to file a claim\n"
        )
        rewriter = LLMQueryRewriter(generator=gen, num_variants=3)

        result = await rewriter.rewrite("How do I file?")

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_variants_are_standalone_strings(self):
        """Each variant is a non-empty standalone string."""
        gen = _mock_generator(
            "What is the process for submitting expenses?\n"
            "Steps to file an expense claim"
        )
        rewriter = LLMQueryRewriter(generator=gen, num_variants=3)

        result = await rewriter.rewrite("How do I file an expense report?")

        for variant in result:
            assert isinstance(variant, str)
            assert len(variant.strip()) > 0


class TestLLMQueryRewriterDeduplication:
    """Test deduplication of variants."""

    @pytest.mark.asyncio
    async def test_duplicate_variants_deduplicated(self):
        """If LLM produces duplicate variants, they are deduplicated."""
        gen = _mock_generator(
            "Same query\nSame query"
        )
        rewriter = LLMQueryRewriter(generator=gen, num_variants=3)

        result = await rewriter.rewrite("test query")

        # Original + 1 unique variant (deduplicated)
        assert len(result) == 2
        assert result.count("Same query") == 1
