"""JSON report generator for evaluation results."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class SampleResult:
    """Result for a single evaluation sample."""

    question: str
    metric_scores: dict[str, float | None] = field(default_factory=dict)


@dataclass
class EvalResults:
    """Aggregated evaluation results."""

    dataset_path: str
    samples: list[SampleResult]
    metric_names: list[str] = field(default_factory=list)

    def metric_aggregates(self, metric_name: str) -> dict:
        """Compute aggregate statistics for a single metric.

        Returns dict with mean, std, min, max, count (excluding None values).
        """
        scores = [
            s.metric_scores[metric_name]
            for s in self.samples
            if metric_name in s.metric_scores and s.metric_scores[metric_name] is not None
        ]

        if not scores:
            return {"mean": None, "std": None, "min": None, "max": None, "count": 0}

        n = len(scores)
        mean = sum(scores) / n
        variance = sum((x - mean) ** 2 for x in scores) / n if n > 1 else 0.0
        std = variance**0.5

        return {
            "mean": round(mean, 4),
            "std": round(std, 4),
            "min": round(min(scores), 4),
            "max": round(max(scores), 4),
            "count": n,
        }


def generate_report(
    results: EvalResults,
    output_path: str | None = None,
    report_dir: str = "data/eval/reports",
) -> str:
    """Generate a JSON evaluation report and write it to a file.

    Args:
        results: Aggregated evaluation results.
        output_path: Explicit output file path. If None, generates a timestamped
                     filename in report_dir.
        report_dir: Default directory for reports (used when output_path is None).

    Returns:
        The path to the written report file.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    # Build metrics aggregates
    metrics = {}
    for metric_name in results.metric_names:
        metrics[metric_name] = results.metric_aggregates(metric_name)

    # Build per-sample results
    per_sample = []
    for sample in results.samples:
        per_sample.append({
            "question": sample.question,
            "metric_scores": {
                k: (round(v, 4) if v is not None else None)
                for k, v in sample.metric_scores.items()
            },
        })

    report = {
        "timestamp": timestamp,
        "dataset": results.dataset_path,
        "samples": len(results.samples),
        "metrics": metrics,
        "per_sample": per_sample,
    }

    # Determine output path
    if output_path:
        out = Path(output_path)
    else:
        dir_path = Path(report_dir)
        dir_path.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out = dir_path / f"report_{ts}.json"

    # Ensure parent directory exists
    out.parent.mkdir(parents=True, exist_ok=True)

    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return str(out)
