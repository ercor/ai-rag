"""RAGAS metrics adapter — wraps RAGAS library metrics as EvaluationMetric implementations.

RAGAS (Retrieval Augmented Generation Assessment) provides LLM-judge metrics
for evaluating RAG pipeline quality. This adapter configures RAGAS to use
the local Ollama instance as the LLM judge.

Requires the [eval] extras: pip install -e ".[eval]"
"""

from __future__ import annotations

import logging
import os

from src.config import get_settings

logger = logging.getLogger(__name__)


def _get_ollama_config():
    """Get Ollama configuration from settings."""
    settings = get_settings()
    return settings.ollama_base_url, settings.ollama_model


class RagasFaithfulness:
    """RAGAS Faithfulness metric — what fraction of claims are supported by contexts.

    Requires: question, answer, contexts.
    """

    @property
    def name(self) -> str:
        return "faithfulness"

    def compute(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str | None = None,
    ) -> float | None:
        if not answer or not contexts:
            return None
        try:
            from ragas import evaluate
            from ragas.metrics import faithfulness
            from datasets import Dataset

            base_url, model = _get_ollama_config()
            os.environ["OLLAMA_BASE_URL"] = base_url

            data = {
                "question": [question],
                "answer": [answer],
                "contexts": [contexts],
            }
            dataset = Dataset.from_dict(data)
            result = evaluate(dataset, metrics=[faithfulness])
            return result["faithfulness"]
        except Exception as exc:
            logger.warning("RagasFaithfulness compute failed: %s", exc)
            return None


class RagasAnswerRelevancy:
    """RAGAS Answer Relevancy metric — how relevant the answer is to the question.

    Requires: question, answer.
    """

    @property
    def name(self) -> str:
        return "answer_relevancy"

    def compute(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str | None = None,
    ) -> float | None:
        if not answer or not question:
            return None
        try:
            from ragas import evaluate
            from ragas.metrics import answer_relevancy
            from datasets import Dataset

            base_url, model = _get_ollama_config()
            os.environ["OLLAMA_BASE_URL"] = base_url

            data = {
                "question": [question],
                "answer": [answer],
                "contexts": [contexts if contexts else [""]],
            }
            dataset = Dataset.from_dict(data)
            result = evaluate(dataset, metrics=[answer_relevancy])
            return result["answer_relevancy"]
        except Exception as exc:
            logger.warning("RagasAnswerRelevancy compute failed: %s", exc)
            return None


class RagasContextPrecision:
    """RAGAS Context Precision — how many top-ranked contexts are actually relevant.

    Requires: question, answer, contexts, ground_truth.
    """

    @property
    def name(self) -> str:
        return "context_precision"

    def compute(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str | None = None,
    ) -> float | None:
        if not contexts or not ground_truth:
            return None
        try:
            from ragas import evaluate
            from ragas.metrics import context_precision
            from datasets import Dataset

            base_url, model = _get_ollama_config()
            os.environ["OLLAMA_BASE_URL"] = base_url

            data = {
                "question": [question],
                "answer": [answer],
                "contexts": [contexts],
                "ground_truth": [ground_truth],
            }
            dataset = Dataset.from_dict(data)
            result = evaluate(dataset, metrics=[context_precision])
            return result["context_precision"]
        except Exception as exc:
            logger.warning("RagasContextPrecision compute failed: %s", exc)
            return None


class RagasContextRecall:
    """RAGAS Context Recall — what fraction of ground_truth claims are covered by contexts.

    Requires: question, contexts, ground_truth.
    """

    @property
    def name(self) -> str:
        return "context_recall"

    def compute(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str | None = None,
    ) -> float | None:
        if not contexts or not ground_truth:
            return None
        try:
            from ragas import evaluate
            from ragas.metrics import context_recall
            from datasets import Dataset

            base_url, model = _get_ollama_config()
            os.environ["OLLAMA_BASE_URL"] = base_url

            data = {
                "question": [question],
                "answer": [answer if answer else ""],
                "contexts": [contexts],
                "ground_truth": [ground_truth],
            }
            dataset = Dataset.from_dict(data)
            result = evaluate(dataset, metrics=[context_recall])
            return result["context_recall"]
        except Exception as exc:
            logger.warning("RagasContextRecall compute failed: %s", exc)
            return None


def get_all_ragas_metrics() -> list:
    """Return instances of all RAGAS metric adapters."""
    return [
        RagasFaithfulness(),
        RagasAnswerRelevancy(),
        RagasContextPrecision(),
        RagasContextRecall(),
    ]
