# Hexagonal Skeleton Specification

## Purpose

Establish the hexagonal (ports-and-adapters) application skeleton for the RAG backend. Defines port interfaces, dependency injection wiring, and Docker Compose infrastructure so that all business logic depends on abstractions, not concrete adapters.

## Requirements

### Requirement: Port Interfaces

The system SHALL define a Python `Protocol` interface for each internal port identified in the architecture: `DocumentSource`, `Parser`, `Chunker`, `Embedder`, `SearchIndex`, `Retriever`, `Generator`, `CitationValidator`, `AnswerRepository`.

Each port MUST declare its input/output types and raise `NotImplementedError` if a default method is unimplemented.

#### Scenario: All ports defined

- GIVEN the backend source tree
- WHEN a developer inspects `src/ports/`
- THEN each port file exists with a `Protocol` class and typed method signatures

#### Scenario: Port contract enforcement

- GIVEN a port protocol `Embedder` with method `embed(text: str) -> list[float]`
- WHEN an adapter implements `Embedder` with a mismatched signature
- THEN static type checking (mypy/pyright) reports the mismatch

### Requirement: Dependency Injection Container

The system SHALL provide a DI container that wires one concrete adapter to each port at application startup.

The container MUST be configurable via environment variables (e.g., `EMBEDDER_ADAPTER=ollama`).

#### Scenario: Default wiring

- GIVEN environment variables are set with default values
- WHEN the FastAPI application starts
- THEN each port is bound to its default adapter and injectable via `Depends()`

#### Scenario: Adapter swap via env var

- GIVEN `EMBEDDER_ADAPTER=fake` is set
- WHEN the application starts
- THEN the `Embedder` port resolves to the fake adapter without code changes

### Requirement: Docker Compose Infrastructure

The system SHALL provide a `docker-compose.yml` that starts all required services: PostgreSQL+pgvector, Ollama, backend (FastAPI), frontend (Next.js).

A single `docker compose up` MUST bring the full stack to a healthy state.

#### Scenario: One-command startup

- GIVEN Docker and Docker Compose are installed
- WHEN the user runs `docker compose up`
- THEN all four services start and health checks pass within 60 seconds

#### Scenario: Service dependency ordering

- GIVEN the compose file
- WHEN services start
- THEN backend waits for PostgreSQL readiness; frontend waits for backend readiness

### Requirement: Health and Readiness Endpoints

The system SHALL expose `GET /health` returning service status and `GET /ready` returning port connectivity status.

#### Scenario: Healthy state

- GIVEN all services are running
- WHEN `GET /health` is called
- THEN response is `200` with `{"status": "ok"}`

#### Scenario: Dependency failure

- GIVEN PostgreSQL is unreachable
- WHEN `GET /ready` is called
- THEN response is `503` with details identifying the failed port
