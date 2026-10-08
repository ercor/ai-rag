"""CLI entry point for RAG evaluation.

Usage:
    python -m src.evaluation --dataset data/eval/gold_set.json
    python -m src.evaluation --dataset data/eval/gold_set.json --metrics faithfulness,citation_precision
    python -m src.evaluation --dataset data/eval/gold_set.json --output /tmp/report.json
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from src.evaluation.custom_metrics import CitationCompleteness, CitationPrecision, RetrievalHitRate
from src.evaluation.dataset import load_gold_dataset
from src.evaluation.report import generate_report
from src.evaluation.runner import EvaluationRunner

logger = logging.getLogger(__name__)


def get_all_custom_metrics() -> list:
    """Return instances of all custom (non-LLM) metrics."""
    return [
        CitationPrecision(),
        CitationCompleteness(),
        RetrievalHitRate(),
    ]


def get_all_metrics() -> list:
    """Return instances of all available metrics (custom + RAGAS if available)."""
    metrics = get_all_custom_metrics()

    try:
        from src.evaluation.ragas_adapter import get_all_ragas_metrics

        metrics.extend(get_all_ragas_metrics())
    except ImportError:
        logger.info("RAGAS not installed — skipping LLM-judge metrics. Install with: pip install -e '.[eval]'")

    return metrics


def get_metrics_by_name(names: list[str]) -> list:
    """Get metric instances by name.

    Args:
        names: List of metric names to retrieve.

    Returns:
        List of metric instances matching the given names.

    Raises:
        ValueError: If a requested metric name is not found.
    """
    all_metrics = get_all_metrics()
    available = {m.name: m for m in all_metrics}

    selected = []
    for name in names:
        if name not in available:
            raise ValueError(
                f"Unknown metric: {name}. Available: {', '.join(sorted(available.keys()))}"
            )
        selected.append(available[name])

    return selected


async def run_pipeline_for_eval(question: str, gold_contexts: list[str]) -> tuple[str, list[str]]:
    """Run the RAG pipeline for a single evaluation sample.

    Args:
        question: The question to ask.
        gold_contexts: Gold contexts (unused here, but available for hit rate).

    Returns:
        Tuple of (generated_answer, retrieved_context_strings).
    """
    from src.container import (
        get_answer_repository,
        get_cache,
        get_citation_validator,
        get_embedder,
        get_generator,
        get_query_rewriter,
        get_reranker,
        get_search_index,
    )
    from src.core.query_pipeline import QueryPipeline

    embedder = get_embedder()
    search_index = get_search_index()
    generator = get_generator()
    citation_validator = get_citation_validator()
    answer_repository = get_answer_repository()
    reranker = get_reranker()
    query_rewriter = get_query_rewriter()
    cache = get_cache()

    pipeline = QueryPipeline(
        embedder=embedder,
        search_index=search_index,
        generator=generator,
        citation_validator=citation_validator,
        answer_repository=answer_repository,
        reranker=reranker,
        query_rewriter=query_rewriter,
        cache=cache,
    )

    # Phase 1: Retrieve
    query_result = await pipeline.retrieve(question)

    if query_result.status == "insufficient_evidence":
        return "", []

    # Get retrieved context strings
    retrieved_contexts = [rc.chunk.content for rc in query_result.retrieved_chunks]

    # Phase 2: Generate
    gen_result = await pipeline.generate_and_persist(query_result)

    return gen_result.answer_text, retrieved_contexts


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate RAG pipeline quality using standardized metrics."
    )
    parser.add_argument(
        "--dataset",
        required=True,
        help="Path to gold dataset JSON file.",
    )
    parser.add_argument(
        "--metrics",
        default="all",
        help="Comma-separated list of metric names, or 'all' (default: all).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path for the JSON report (default: auto-generated).",
    )
    parser.add_argument(
        "--report-dir",
        default="data/eval/reports",
        help="Directory for reports when --output is not specified.",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Load dataset
    try:
        dataset = load_gold_dataset(args.dataset)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print(f"Validation error: {exc}", file=sys.stderr)
        sys.exit(1)

    logger.info("Loaded %d samples from %s", len(dataset), args.dataset)

    # Select metrics
    if args.metrics == "all":
        metrics = get_all_metrics()
    else:
        metric_names = [m.strip() for m in args.metrics.split(",")]
        try:
            metrics = get_metrics_by_name(metric_names)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

    logger.info("Using metrics: %s", [m.name for m in metrics])

    # Run evaluation
    runner = EvaluationRunner(
        pipeline_fn=run_pipeline_for_eval,
        metrics=metrics,
        dataset=dataset,
        dataset_path=args.dataset,
    )

    results = asyncio.run(runner.run())

    # Generate report
    report_path = generate_report(
        results,
        output_path=args.output,
        report_dir=args.report_dir,
    )

    logger.info("Report written to: %s", report_path)

    # Print summary
    print(f"\nEvaluation complete: {len(dataset)} samples, {len(metrics)} metrics")
    print(f"Report: {report_path}\n")

    for metric_name in results.metric_names:
        agg = results.metric_aggregates(metric_name)
        if agg["count"] > 0:
            print(f"  {metric_name}: mean={agg['mean']:.4f}  std={agg['std']:.4f}  "
                  f"min={agg['min']:.4f}  max={agg['max']:.4f}  (n={agg['count']})")
        else:
            print(f"  {metric_name}: no valid scores")


if __name__ == "__main__":
    main()
