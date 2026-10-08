"""Evaluation runner — orchestrates pipeline execution and metric computation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.evaluation.dataset import EvalSample
from src.evaluation.report import EvalResults, SampleResult

if TYPE_CHECKING:
    from src.ports.evaluation import EvaluationMetric

logger = logging.getLogger(__name__)


class EvaluationRunner:
    """Runs the RAG pipeline on a gold dataset and computes metrics.

    Processes samples sequentially to avoid overloading the LLM judge.
    Handles metric computation failures gracefully by recording null scores.
    """

    def __init__(
        self,
        pipeline_fn,
        metrics: list[EvaluationMetric],
        dataset: list[EvalSample],
        dataset_path: str = "",
    ):
        """Initialize the evaluation runner.

        Args:
            pipeline_fn: Async callable(question, contexts) -> (answer, retrieved_contexts).
                         Should run the RAG pipeline and return the generated answer
                         and the list of retrieved context strings.
            metrics: List of EvaluationMetric implementations to compute.
            dataset: List of EvalSample objects to evaluate.
            dataset_path: Path to the gold dataset file (for reporting).
        """
        self.pipeline_fn = pipeline_fn
        self.metrics = metrics
        self.dataset = dataset
        self.dataset_path = dataset_path

    async def run(self) -> EvalResults:
        """Execute the evaluation on all samples.

        For each sample:
        1. Run the pipeline to get answer and retrieved contexts
        2. Compute each metric
        3. Record scores (null for failed metrics)

        Returns:
            EvalResults with per-sample scores and metric names.
        """
        total = len(self.dataset)
        metric_names = [m.name for m in self.metrics]
        sample_results: list[SampleResult] = []

        for i, sample in enumerate(self.dataset, start=1):
            logger.info("Evaluating sample %d/%d: %s", i, total, sample.question[:80])

            metric_scores: dict[str, float | None] = {}

            try:
                # Run the pipeline
                answer, retrieved_contexts = await self.pipeline_fn(
                    sample.question, sample.contexts
                )

                # Compute each metric
                for metric in self.metrics:
                    try:
                        score = metric.compute(
                            question=sample.question,
                            answer=answer,
                            contexts=retrieved_contexts,
                            ground_truth=sample.ground_truth,
                        )
                        metric_scores[metric.name] = score
                    except Exception as exc:
                        logger.warning(
                            "Metric %s failed for sample %d: %s",
                            metric.name,
                            i,
                            exc,
                        )
                        metric_scores[metric.name] = None

            except Exception as exc:
                logger.error(
                    "Pipeline failed for sample %d (%s): %s",
                    i,
                    sample.question[:50],
                    exc,
                )
                # All metrics are null for this sample
                for metric in self.metrics:
                    metric_scores[metric.name] = None

            sample_results.append(
                SampleResult(question=sample.question, metric_scores=metric_scores)
            )

        return EvalResults(
            dataset_path=self.dataset_path,
            samples=sample_results,
            metric_names=metric_names,
        )
