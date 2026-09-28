"""LLM-based QueryRewriter adapter.

Uses the existing Generator port (Ollama) with a structured prompt
to produce semantically distinct rephrasings of the input query.
"""

import logging
from typing import AsyncIterator

from src.ports.generator import Generator

logger = logging.getLogger(__name__)

_REWRITE_PROMPT_TEMPLATE = """You are a helpful assistant that generates alternative search queries.

Given the following user query, generate {num_variants_minus_one} alternative versions that \
convey the same meaning but use different wording. Each alternative should be a standalone \
query that could be used to search for the same information.

Original query: {query}

Generate exactly {num_variants_minus_one} alternative queries, one per line, without numbering \
or bullet points:"""


class LLMQueryRewriter:
    """Generates query variants using an LLM via the Generator port.

    Uses multi-query expansion prompting to produce semantically distinct
    rephrasings. Falls back to [original_query] on any failure.
    """

    def __init__(self, generator: Generator, num_variants: int = 3):
        """Initialize the rewriter.

        Args:
            generator: A Generator port implementation (e.g. OllamaGenerator).
            num_variants: Total number of variants to produce (including the
                original query). Must be >= 1.
        """
        self._generator = generator
        self._num_variants = max(1, num_variants)

    async def rewrite(self, query: str) -> list[str]:
        """Generate query variants via LLM multi-query expansion.

        Returns the original query plus (num_variants - 1) rephrasings.
        On any failure, returns [query] as a graceful fallback.
        """
        if self._num_variants <= 1:
            return [query]

        num_to_generate = self._num_variants - 1
        prompt = _REWRITE_PROMPT_TEMPLATE.format(
            num_variants_minus_one=num_to_generate,
            query=query,
        )

        try:
            raw_output = await self._collect_generator_output(prompt)
        except Exception as exc:
            logger.warning(
                "Query rewriter: Generator failed (%s) — falling back to "
                "original query only",
                exc,
            )
            return [query]

        variants = self._parse_output(raw_output, num_to_generate)

        if not variants:
            logger.warning(
                "Query rewriter: could not parse LLM output — falling back "
                "to original query only. Raw output: %s",
                raw_output[:200],
            )
            return [query]

        # Always include the original query
        all_variants = [query] + variants
        # Deduplicate while preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for v in all_variants:
            normalized = v.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                deduped.append(normalized)

        logger.info(
            "Query rewriter: produced %d variants for query: %s",
            len(deduped),
            query[:80],
        )
        return deduped

    async def _collect_generator_output(self, prompt: str) -> str:
        """Consume the generator stream into a single string."""
        tokens: list[str] = []
        async for token in self._generator.generate_stream(prompt):
            tokens.append(token)
        return "".join(tokens)

    @staticmethod
    def _parse_output(raw: str, expected_count: int) -> list[str]:
        """Parse LLM output into a list of query strings.

        Handles numbered lists ("1. ..."), bullet points ("- ..."),
        and plain one-per-line output.
        """
        lines = raw.strip().splitlines()
        variants: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Remove numbering: "1. query", "1) query", "1: query"
            if stripped and stripped[0].isdigit():
                # Find the first non-digit character
                idx = 0
                while idx < len(stripped) and (stripped[idx].isdigit() or stripped[idx] in ".):"):
                    idx += 1
                if idx < len(stripped):
                    stripped = stripped[idx:].strip()

            # Remove bullet points
            if stripped.startswith(("- ", "* ", "• ")):
                stripped = stripped[2:].strip()

            if stripped:
                variants.append(stripped)

            if len(variants) >= expected_count:
                break

        return variants[:expected_count]
