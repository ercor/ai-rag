"""Integration tests for the evaluation pipeline.

Tests the full evaluation flow with custom metrics and report generation.
"""

import json
import pytest
import tempfile
from pathlib import Path

from src.evaluation.custom_metrics import CitationPrecision, CitationCompleteness
from src.evaluation.dataset import EvalSample, load_gold_dataset
from src.evaluation.report import EvalResults, SampleResult, generate_report
from src.evaluation.runner import EvaluationRunner


async def mock_pipeline_fn(question, gold_contexts):
    """Mock pipeline that returns a canned answer and contexts."""
    return (
        f"The answer to '{question}' is supported by evidence [1].",
        gold_contexts if gold_contexts else ["Mock retrieved context."],
    )


class TestEvaluationPipelineIntegration:
    """Integration tests for the full evaluation flow."""

    @pytest.mark.asyncio
    async def test_full_evaluation_run_produces_report(self):
        """Full evaluation run produces a valid JSON report."""
        dataset = [
            EvalSample(
                question="What is X?",
                ground_truth="X is Y.",
                contexts=["X is defined as Y in the document."],
            ),
            EvalSample(
                question="How does Z work?",
                ground_truth="Z works by A and B.",
                contexts=["Z operates through mechanisms A and B."],
            ),
        ]

        metrics = [CitationPrecision(), CitationCompleteness()]
        runner = EvaluationRunner(
            pipeline_fn=mock_pipeline_fn,
            metrics=metrics,
            dataset=dataset,
            dataset_path="test_data.json",
        )

        results = await runner.run()

        # Generate report to temp file
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            output_path = f.name

        report_path = generate_report(results, output_path=output_path)

        # Verify report is valid JSON
        with open(report_path) as f:
            report = json.load(f)

        assert "timestamp" in report
        assert report["dataset"] == "test_data.json"
        assert report["samples"] == 2
        assert "citation_precision" in report["metrics"]
        assert "citation_completeness" in report["metrics"]
        assert len(report["per_sample"]) == 2

        Path(report_path).unlink()

    @pytest.mark.asyncio
    async def test_report_structure_is_correct(self):
        """Report has the correct structure with aggregates."""
        dataset = [
            EvalSample(
                question=f"Q{i}?",
                ground_truth=f"A{i}.",
                contexts=[f"C{i}."],
            )
            for i in range(5)
        ]

        metrics = [CitationPrecision()]
        runner = EvaluationRunner(
            pipeline_fn=mock_pipeline_fn,
            metrics=metrics,
            dataset=dataset,
        )

        results = await runner.run()
        agg = results.metric_aggregates("citation_precision")

        assert "mean" in agg
        assert "std" in agg
        assert "min" in agg
        assert "max" in agg
        assert "count" in agg
        assert agg["count"] == 5

    def test_gold_dataset_stratification(self):
        """Gold dataset is properly stratified across sources/difficulty/category."""
        samples = load_gold_dataset("data/eval/gold_set.json")

        # Check counts
        assert len(samples) >= 20

        # Check source coverage
        sources = {s.metadata.get("source") for s in samples}
        assert len(sources) >= 3
        assert "travel_policy" in sources
        assert "q3_results" in sources
        assert "engineering_onboarding" in sources

        # Check difficulty coverage
        difficulties = {s.metadata.get("difficulty") for s in samples}
        assert {"easy", "medium", "hard"}.issubset(difficulties)

        # Check category coverage
        categories = {s.metadata.get("category") for s in samples}
        assert {"factual", "comparative", "procedural"}.issubset(categories)
