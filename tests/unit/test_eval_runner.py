"""Unit tests for evaluation runner."""

import pytest
from src.evaluation.dataset import EvalSample
from src.evaluation.runner import EvaluationRunner


class FakeMetric:
    """A fake metric for testing."""

    def __init__(self, name: str = "fake_metric", return_value: float = 0.5):
        self._name = name
        self._return_value = return_value

    @property
    def name(self) -> str:
        return self._name

    def compute(self, question, answer, contexts, ground_truth=None):
        return self._return_value


class FailingMetric:
    """A metric that always raises."""

    @property
    def name(self) -> str:
        return "failing_metric"

    def compute(self, question, answer, contexts, ground_truth=None):
        raise RuntimeError("Intentional failure")


async def fake_pipeline_fn(question, gold_contexts):
    """Fake pipeline function for testing."""
    return f"Answer to: {question}", ["Retrieved context 1", "Retrieved context 2"]


class TestEvaluationRunner:
    """Tests for EvaluationRunner."""

    def _make_dataset(self, n: int = 3) -> list[EvalSample]:
        return [
            EvalSample(
                question=f"Question {i}?",
                ground_truth=f"Answer {i}.",
                contexts=[f"Context {i}."],
            )
            for i in range(n)
        ]

    @pytest.mark.asyncio
    async def test_runner_processes_all_samples(self):
        """Runner processes all samples and computes all metrics."""
        dataset = self._make_dataset(3)
        metrics = [FakeMetric("m1", 0.8), FakeMetric("m2", 0.6)]
        runner = EvaluationRunner(
            pipeline_fn=fake_pipeline_fn,
            metrics=metrics,
            dataset=dataset,
            dataset_path="test.json",
        )

        results = await runner.run()

        assert len(results.samples) == 3
        assert results.metric_names == ["m1", "m2"]
        for sample in results.samples:
            assert sample.metric_scores["m1"] == 0.8
            assert sample.metric_scores["m2"] == 0.6

    @pytest.mark.asyncio
    async def test_metric_failure_records_null(self):
        """Metric failure records null for that metric, continues."""
        dataset = self._make_dataset(2)
        metrics = [FakeMetric("good", 0.9), FailingMetric()]
        runner = EvaluationRunner(
            pipeline_fn=fake_pipeline_fn,
            metrics=metrics,
            dataset=dataset,
        )

        results = await runner.run()

        assert len(results.samples) == 2
        for sample in results.samples:
            assert sample.metric_scores["good"] == 0.9
            assert sample.metric_scores["failing_metric"] is None

    @pytest.mark.asyncio
    async def test_pipeline_failure_records_all_null(self):
        """Pipeline failure records null for all metrics."""

        async def failing_pipeline(question, contexts):
            raise RuntimeError("Pipeline failure")

        dataset = self._make_dataset(1)
        metrics = [FakeMetric("m1")]
        runner = EvaluationRunner(
            pipeline_fn=failing_pipeline,
            metrics=metrics,
            dataset=dataset,
        )

        results = await runner.run()

        assert len(results.samples) == 1
        assert results.samples[0].metric_scores["m1"] is None

    @pytest.mark.asyncio
    async def test_aggregates_contain_stats(self):
        """Aggregated report contains mean, std, min, max, count."""
        dataset = self._make_dataset(4)
        metrics = [FakeMetric("score", 0.75)]
        runner = EvaluationRunner(
            pipeline_fn=fake_pipeline_fn,
            metrics=metrics,
            dataset=dataset,
        )

        results = await runner.run()
        agg = results.metric_aggregates("score")

        assert agg["mean"] == 0.75
        assert agg["std"] == 0.0
        assert agg["min"] == 0.75
        assert agg["max"] == 0.75
        assert agg["count"] == 4

    @pytest.mark.asyncio
    async def test_dataset_path_preserved(self):
        """Dataset path is preserved in results."""
        dataset = self._make_dataset(1)
        runner = EvaluationRunner(
            pipeline_fn=fake_pipeline_fn,
            metrics=[FakeMetric()],
            dataset=dataset,
            dataset_path="data/eval/gold_set.json",
        )

        results = await runner.run()
        assert results.dataset_path == "data/eval/gold_set.json"
