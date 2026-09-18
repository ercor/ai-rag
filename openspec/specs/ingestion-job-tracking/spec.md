# Ingestion Job Tracking Specification

## Purpose

Asynchronous job API for ingestion progress. Replaces synchronous `POST /v1/ingest` with a 202 + job-id pattern and a polling endpoint for live status, counts, and per-file failure details.

## Requirements

### Requirement: Job Submission

The system SHALL accept `POST /v1/ingest` and return HTTP 202 with a `job_id` immediately. A background job MUST start processing. The system MUST reject concurrent submissions with 409 Conflict when a job is in `pending` or `running` state.

| Field | Type | Description |
|-------|------|-------------|
| 202 body | object | `{"job_id": "<uuid>"}` |
| 409 body | object | `{"error": "job_already_running", "job_id": "<active>"}` |

#### Scenario: Successful submission

- GIVEN no job is currently running
- WHEN `POST /v1/ingest` is called
- THEN response is 202 with `{"job_id": "<id>"}`
- AND a background job begins processing

#### Scenario: Concurrent submission rejected

- GIVEN a job is in `pending` or `running` state
- WHEN `POST /v1/ingest` is called
- THEN response is 409 with the active `job_id`

### Requirement: Job Progress Query

The system SHALL expose `GET /v1/ingest/{job_id}` returning state and progress.

| Field | Type | Description |
|-------|------|-------------|
| state | enum | `pending`, `running`, `completed`, `failed` |
| total | int | Files discovered in scan |
| processed | int | Files fully indexed |
| skipped | int | Files unchanged (hash match) |
| chunks | int | Total chunks created/updated |
| failed | int | Files that failed |
| failures | array | Per-file: `{path, error}` |

#### Scenario: Query running job

- GIVEN a job processing 10 docs, 4 done, 30 chunks created
- WHEN `GET /v1/ingest/{job_id}` is called
- THEN response includes `state: "running"`, `total: 10`, `processed: 4`, `chunks: 30`

#### Scenario: Query completed job with failure

- GIVEN a job finished, 1 file failed
- WHEN `GET /v1/ingest/{job_id}` is called
- THEN `state` is `completed`, `failures` has 1 entry with `path` and `error`

#### Scenario: Unknown job ID

- GIVEN no job exists with the given ID
- WHEN `GET /v1/ingest/{job_id}` is called
- THEN response is 404

### Requirement: Job Lifecycle States

The system SHALL transition jobs: `pending` → `running` → `completed` | `failed`. A job MUST reach a terminal state even if individual files fail. `failed` terminal state is reserved for system-level errors (DB down, Ollama unreachable); per-file parse failures do NOT fail the job.

#### Scenario: All files fail to parse

- GIVEN a job where every file fails to parse
- WHEN the job finishes
- THEN `state` is `completed`, `failed` equals `total`

#### Scenario: Startup scan as background job

- GIVEN the app starts with documents in the watch directory
- WHEN startup triggers ingestion
- THEN a background job is created, queryable via `GET /v1/ingest/{job_id}`

### Requirement: Job State Storage

The system SHOULD store job state in memory for this iteration. State MUST be consistent during process lifetime. State MAY be lost on restart (ingestion is idempotent; re-submit is safe).

#### Scenario: Job lost on restart

- GIVEN a job was running when the app restarts
- WHEN `GET /v1/ingest/{old_job_id}` is called
- THEN response is 404

## Dependencies

- `document-ingestion` (pipeline provides counts)
- `document-registry` (provides `skipped` count)
