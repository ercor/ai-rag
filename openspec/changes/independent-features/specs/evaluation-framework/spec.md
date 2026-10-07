# Evaluation Framework Specification

## Purpose

Define the evaluation framework that measures RAG pipeline quality using standardized metrics (RAGAS-based and custom), a CLI runner, and a curated gold dataset, producing deterministic JSON reports for regression tracking and improvement measurement.

## Requirements

### Requirement: EvaluationMetric Port

The system SHALL define an `EvaluationMetric` port (Protocol) with a `compute()` method that accepts question, answer, contexts, and ground_truth, and returns a float score in [0.0, 1.0].

The port MUST be adapter-agnostic — no RAGAS-specific or LLM-specific types SHALL appear in the interface.

#### Scenario: Metric computation

- GIVEN a question, a generated answer, a list of retrieved contexts, and a ground truth answer
- WHEN `EvaluationMetric.compute()` is called
- THEN it returns a float score between 0.0 and 1.0

#### Scenario: Metric with missing inputs

- GIVEN a metric that requires ground_truth but none is provided
- WHEN `compute()` is called
- THEN it returns `None` or raises a clear error indicating the missing input

### Requirement: RAGAS Metrics Adapter

The system SHALL provide a `RagasMetrics` adapter that wraps RAGAS library metrics: `Faithfulness`, `AnswerRelevancy`, `ContextPrecision`, `ContextRecall`.

Each RAGAS metric MUST be wrapped as a separate `EvaluationMetric` implementation. The adapter MUST configure RAGAS to use the existing Ollama instance as the LLM judge.

#### Scenario: Faithfulness computation

- GIVEN a question, answer, and contexts
- WHEN the `Faithfulness` metric is computed
- THEN it returns a score indicating what fraction of claims in the answer are supported by the contexts

#### Scenario: Answer relevancy computation

- GIVEN a question and answer
- WHEN the `AnswerRelevancy` metric is computed
- THEN it returns a score indicating how relevant the answer is to the question

#### Scenario: Context precision computation

- GIVEN a question, answer, contexts, and ground_truth
- WHEN the `ContextPrecision` metric is computed
- THEN it returns a score indicating how many of the top-ranked contexts are actually relevant

#### Scenario: Context recall computation

- GIVEN a question, contexts, and ground_truth
- WHEN the `ContextRecall` metric is computed
- THEN it returns a score indicating what fraction of ground_truth claims are covered by the contexts

#### Scenario: RAGAS with local Ollama

- GIVEN Ollama is running with the configured model
- WHEN a RAGAS metric is computed
- THEN RAGAS uses Ollama as the LLM judge (no external API calls)

### Requirement: Custom Metrics

The system SHALL implement the following custom (non-LLM) metrics as `EvaluationMetric` adapters:

1. **Citation Precision**: fraction of citations in the answer that reference valid (retrieved) chunks
2. **Citation Completeness**: fraction of factual claims in the answer that have supporting citations
3. **Retrieval Hit Rate**: whether at least one gold context appears in the top-k retrieved chunks (binary per sample, averaged across dataset)

#### Scenario: Citation precision — all valid

- GIVEN an answer with citations [1], [2], [3] and 3 retrieved chunks
- WHEN citation precision is computed
- THEN the score is 1.0 (all citations reference valid chunks)

#### Scenario: Citation precision — some invalid

- GIVEN an answer with citations [1], [5] and only 3 retrieved chunks
- WHEN citation precision is computed
- THEN the score is 0.5 (1 of 2 citations is valid)

#### Scenario: Citation completeness

- GIVEN an answer with 4 factual claims and 3 of them have citations
- WHEN citation completeness is computed
- THEN the score is 0.75

#### Scenario: Retrieval hit rate

- GIVEN a gold sample with 2 gold contexts
- WHEN the pipeline retrieves top-5 chunks and 1 gold context appears in them
- WHEN retrieval hit rate is computed for this sample
- THEN the score is 1.0 (at least one gold context was retrieved)

#### Scenario: Retrieval hit rate — miss

- GIVEN a gold sample with 2 gold contexts
- WHEN the pipeline retrieves top-5 chunks and none match the gold contexts
- WHEN retrieval hit rate is computed
- THEN the score is 0.0

### Requirement: Gold Dataset Format

The system SHALL define a gold dataset format as a JSON file containing an array of evaluation samples.

Each sample MUST have: `question` (str), `ground_truth` (str), `contexts` (list[str]). Each sample MAY have: `metadata` (dict with `source`, `difficulty`, `category` fields).

The initial gold dataset MUST contain at least 20 samples, stratified by source document, difficulty (easy/medium/hard), and query type (factual, comparative, procedural).

#### Scenario: Valid gold dataset

- GIVEN a JSON file with 25 samples, each having `question`, `ground_truth`, and `contexts`
- WHEN the dataset is loaded
- THEN all 25 samples are parsed and validated successfully

#### Scenario: Invalid sample rejected

- GIVEN a JSON file where one sample is missing the `ground_truth` field
- WHEN the dataset is loaded
- THEN a validation error is raised indicating which sample is invalid and what field is missing

#### Scenario: Gold dataset stratification

- GIVEN the gold dataset at `data/eval/gold_set.json`
- WHEN the dataset is inspected
- THEN it contains at least 20 samples
- AND samples cover at least 3 source documents
- AND samples include easy, medium, and hard difficulties
- AND samples include factual, comparative, and procedural query types

### Requirement: Evaluation Runner

The system SHALL provide an `EvaluationRunner` that takes a gold dataset and a list of metrics, runs the pipeline for each sample, computes all metrics, and produces an aggregated report.

The runner MUST process samples sequentially to avoid overloading the LLM judge. The runner SHOULD log progress (sample N of M) during execution.

#### Scenario: Full evaluation run

- GIVEN a gold dataset with 20 samples and metrics [faithfulness, answer_relevancy, citation_precision]
- WHEN the runner executes
- THEN for each sample: the pipeline runs (retrieve + generate), then each metric is computed
- AND an aggregated report is produced with mean and std for each metric

#### Scenario: Partial metric failure

- GIVEN a sample where one metric computation fails (e.g., RAGAS LLM judge error)
- WHEN the runner processes that sample
- THEN the failed metric is recorded as `null` for that sample
- AND other metrics for that sample are still computed
- AND the final report notes the number of failures per metric

#### Scenario: Progress logging

- GIVEN a dataset with 25 samples
- WHEN the runner executes
- THEN log messages indicate progress: "Evaluating sample 1/25", "Evaluating sample 2/25", etc.

### Requirement: JSON Report Output

The system SHALL produce a JSON report containing: timestamp, dataset path, sample count, per-metric aggregates (mean, std, min, max, count), and per-sample scores.

The report MUST be written to a file (default: `data/eval/reports/report_<timestamp>.json`). The report format MUST be deterministic — same inputs produce same outputs (excluding timestamp).

#### Scenario: Report structure

- GIVEN a completed evaluation run
- WHEN the report is generated
- THEN it contains:
  - `timestamp`: ISO 8601 datetime
  - `dataset`: path to the gold dataset file
  - `samples`: number of samples evaluated
  - `metrics`: dict of metric_name → {mean, std, min, max, count}
  - `per_sample`: list of {question, metric_scores: {metric_name: score}}

#### Scenario: Report written to file

- GIVEN a completed evaluation run
- WHEN the report is generated
- THEN a JSON file is written to `data/eval/reports/report_YYYYMMDD_HHMMSS.json`
- AND the file is valid JSON parseable by `json.load()`

#### Scenario: Deterministic metrics

- GIVEN the same gold dataset and same pipeline state
- WHEN the evaluation is run twice
- THEN the per-sample metric scores are identical across both runs (excluding timestamp)

### Requirement: CLI Interface

The system SHALL provide a CLI entry point at `python -m src.evaluation` that accepts dataset path and metric selection.

CLI arguments: `--dataset` (required, path to gold JSON), `--metrics` (optional, comma-separated list or "all", default: "all"), `--output` (optional, output file path), `--pipeline-config` (optional, path to override config).

#### Scenario: Run all metrics

- GIVEN the command `python -m src.evaluation --dataset data/eval/gold_set.json --metrics all`
- WHEN the CLI executes
- THEN all available metrics are computed for all samples
- AND a JSON report is generated

#### Scenario: Run specific metrics

- GIVEN the command `python -m src.evaluation --dataset data/eval/gold_set.json --metrics faithfulness,citation_precision`
- WHEN the CLI executes
- THEN only faithfulness and citation_precision are computed
- AND the report contains only those two metrics

#### Scenario: Custom output path

- GIVEN the command `python -m src.evaluation --dataset data/eval/gold_set.json --output /tmp/my_report.json`
- WHEN the CLI executes
- THEN the report is written to `/tmp/my_report.json`

#### Scenario: Missing dataset file

- GIVEN the command `python -m src.evaluation --dataset nonexistent.json`
- WHEN the CLI executes
- THEN a clear error message is printed: "Dataset file not found: nonexistent.json"
- AND the process exits with a non-zero exit code

### Requirement: Dependency Isolation

The system SHALL isolate evaluation dependencies (RAGAS, datasets) in a `[eval]` extras group in `pyproject.toml`.

The core application MUST NOT import evaluation dependencies at runtime. Evaluation code MUST be importable only when the `[eval]` extras are installed.

#### Scenario: Core app without eval dependencies

- GIVEN the `[eval]` extras are NOT installed
- WHEN the core application starts
- THEN it runs normally without import errors
- AND no evaluation code is loaded

#### Scenario: Eval dependencies installed

- GIVEN `pip install -e ".[eval]"` is run
- WHEN `python -m src.evaluation` is invoked
- THEN RAGAS and custom metrics are available
- AND the CLI runs successfully

### Requirement: Evaluation Configuration

The system SHALL expose evaluation settings via environment variables or CLI arguments.

Settings: `eval_dataset_path` (str), `eval_metrics` (list[str]), `eval_report_dir` (str, default: "data/eval/reports").

#### Scenario: Default configuration

- GIVEN no evaluation environment variables are set
- WHEN the CLI runs without overrides
- THEN the default report directory is `data/eval/reports`
- AND all metrics are computed

## Out of Scope

- Evaluation API endpoint (HTTP) — CLI-first for this iteration
- Continuous evaluation or CI integration hooks
- A/B testing between pipeline configurations
- Human-in-the-loop evaluation or annotation UI
- Streaming evaluation or real-time metric computation
- Evaluation dataset versioning beyond file path
- Multi-model comparison reports
