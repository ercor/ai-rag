"""Custom (non-LLM) evaluation metrics for RAG pipeline quality.

These metrics compute scores without requiring an LLM judge,
making them fast and deterministic.
"""

from __future__ import annotations

import re


class CitationPrecision:
    """Fraction of citations in the answer that reference valid (retrieved) chunks.

    A citation [N] is valid if N is between 1 and the number of retrieved contexts.
    """

    @property
    def name(self) -> str:
        return "citation_precision"

    def compute(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str | None = None,
    ) -> float | None:
        """Compute citation precision.

        Args:
            question: The user's question (unused but required by protocol).
            answer: The generated answer with [N] citation markers.
            contexts: List of retrieved context strings (determines valid range).
            ground_truth: Unused for this metric.

        Returns:
            Float in [0.0, 1.0], or None if no citations found.
        """
        if not contexts:
            return None

        # Extract all citation numbers from the answer
        citations = re.findall(r"\[(\d+)\]", answer)
        if not citations:
            return None

        valid_count = sum(1 for c in citations if 1 <= int(c) <= len(contexts))
        return valid_count / len(citations)


class CitationCompleteness:
    """Fraction of sentences/claims in the answer that have supporting citations.

    A sentence is considered "cited" if it contains at least one [N] marker.
    This is a heuristic — full claim-level analysis would require an LLM.
    """

    @property
    def name(self) -> str:
        return "citation_completeness"

    def compute(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str | None = None,
    ) -> float | None:
        """Compute citation completeness.

        Args:
            question: The user's question (unused but required by protocol).
            answer: The generated answer.
            contexts: List of retrieved contexts (unused but required by protocol).
            ground_truth: Unused for this metric.

        Returns:
            Float in [0.0, 1.0], or None if no sentences found.
        """
        # Split answer into sentences (rough heuristic: split on . ! ?)
        sentences = re.split(r"[.!?]+", answer)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return None

        cited_count = sum(1 for s in sentences if re.search(r"\[\d+\]", s))
        return cited_count / len(sentences)


class RetrievalHitRate:
    """Whether at least one gold context appears in the retrieved contexts.

    Binary per sample (1.0 if hit, 0.0 if miss). Uses substring matching
    to check if any gold context text appears in any retrieved context.
    """

    @property
    def name(self) -> str:
        return "retrieval_hit_rate"

    def compute(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str | None = None,
    ) -> float | None:
        """Compute retrieval hit rate.

        This metric requires ground_truth contexts to compare against.
        The `contexts` parameter should be the retrieved chunks, and
        `ground_truth` should contain the gold context passages.

        For proper use, the runner should pass gold contexts separately.
        This implementation checks if any retrieved context contains
        a significant substring from the ground_truth.

        Args:
            question: The user's question (unused but required by protocol).
            answer: The generated answer (unused but required by protocol).
            contexts: List of retrieved context strings.
            ground_truth: Gold context passages to check against.

        Returns:
            1.0 if at least one gold context appears in retrieved, 0.0 otherwise.
            Returns None if ground_truth is not provided.
        """
        if not ground_truth or not contexts:
            return None

        # Check if any significant portion of ground_truth appears in any context
        # Use a minimum substring length to avoid false positives on short words
        gold_lower = ground_truth.lower()
        for ctx in contexts:
            ctx_lower = ctx.lower()
            # Check if a substantial portion of ground_truth is in this context
            # Use 50% overlap as threshold
            if len(gold_lower) < 20:
                # Short ground truth — require exact match
                if gold_lower in ctx_lower:
                    return 1.0
            else:
                # Longer ground truth — check for significant overlap
                # Split into words and check what fraction appears in context
                gold_words = set(gold_lower.split())
                ctx_words = set(ctx_lower.split())
                if len(gold_words) > 0:
                    overlap = len(gold_words & ctx_words) / len(gold_words)
                    if overlap >= 0.5:
                        return 1.0

        return 0.0
