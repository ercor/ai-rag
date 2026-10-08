"""EvaluationMetric port — adapter-agnostic interface for RAG evaluation metrics.

Defines the contract for computing quality metrics on RAG pipeline outputs.
"""

from __future__ import annotations

from typing import Protocol


class EvaluationMetric(Protocol):
    """Port for a single evaluation metric.

    Adapter-agnostic — no RAGAS-specific or LLM-specific types in the interface.
    """

    @property
    def name(self) -> str:
        """Return the metric name (used as key in reports)."""
        ...

    def compute(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str | None = None,
    ) -> float | None:
        """Compute the metric score for a single evaluation sample.

        Args:
            question: The user's question.
            answer: The generated answer.
            contexts: List of retrieved context strings.
            ground_truth: Optional ground truth answer for reference-based metrics.

        Returns:
            Float score in [0.0, 1.0], or None if the metric cannot be computed
            (e.g., missing required input).
        """
        ...
