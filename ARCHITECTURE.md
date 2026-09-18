# Enterprise Knowledge Management RAG

Status: MVP implemented (Phase 1-5)  
Last updated: 2026-08-24  
Target: Enterprise document question answering with verifiable citations  
Scale assumption: approximately 1 million source documents and 1,000 concurrent users

---

## Quick Start (MVP)

The MVP is a fully functional RAG pipeline with hexagonal architecture. It ingests documents from a local directory, answers questions using hybrid search (BM25 + pgvector), and streams answers with citations via SSE.

### Prerequisites

- **Docker** and **Docker Compose** (v2+)
- **8 GB RAM** minimum (Ollama models need memory)
- **Git**

### Setup

```bash
# 1. Clone and enter the project
git clone <repo-url> ai-rag && cd ai-rag

# 2. Create environment file
cp .env.example .env

# 3. (Optional) Add your documents to data/docs/
#    Supported formats: .pdf, .docx, .html, .txt, .md
cp /path/to/your/docs/* data/docs/

# 4. Start the full stack
docker compose up -d --build
```

### Pull Ollama Models

After starting the stack, pull the required models:

```bash
# Embedding model (768 dimensions)
docker compose exec ollama ollama pull nomic-embed-text

# Generation model (qwen2.5 — choose 3b for limited RAM, 7b for quality)
docker compose exec ollama ollama pull qwen2.5
```

### Verify the Stack

```bash
# Health check
curl http://localhost:8000/health
# Expected: {"status":"ok"}

# Readiness check (verifies DB + Ollama connectivity)
curl http://localhost:8000/ready
# Expected: {"status":"ready","checks":{"database":"ok","ollama":"ok"}}

# Trigger ingestion of documents in data/docs/
curl -X POST http://localhost:8000/v1/ingest
# Expected: {"processed": N, "chunks": M, "failed": 0, ...}
```

### Ask a Question

```bash
# Create an answer (synchronous retrieval, returns answer_id)
curl -X POST http://localhost:8000/v1/answers \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the travel policy?"}'

# Response: {"answer_id": "...", "status": "streaming", ...}

# Stream the answer tokens via SSE
curl -N http://localhost:8000/v1/answers/<answer_id>/stream
```

### Open the Chat UI

Navigate to **http://localhost:3000** in your browser. Type a question and watch the answer stream in with clickable citations.

### Stopping the Stack

```bash
docker compose down          # Stop containers (keep data)
docker compose down -v       # Stop and remove volumes (clean slate)
```

### Local Development (without Docker)

```bash
# Backend
pip install -r requirements.txt
export DATABASE_URL=postgresql+asyncpg://rag:rag@localhost:5432/rag
export OLLAMA_BASE_URL=http://localhost:11434
uvicorn src.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

### Running Tests

```bash
# Unit tests (no external dependencies)
pytest tests/unit/ -v

# Integration tests (requires Docker for testcontainers)
pip install "testcontainers[postgres]"
pytest tests/integration/ -v -m integration

# E2E tests (requires full docker compose stack running)
E2E_TEST=1 pytest tests/e2e/ -v --e2e
```

### Project Structure

```
src/
  adapters/       # Concrete implementations (pgvector, ollama, filesystem)
  api/            # FastAPI endpoints (health, ingestion, answers)
  core/           # Domain logic (retrieval, query pipeline)
  ports/          # Protocol interfaces (hexagonal ports)
  config.py       # pydantic-settings configuration
  container.py    # Dependency injection factories
  main.py         # FastAPI app entry point
frontend/         # Next.js 14 chat UI with SSE streaming
migrations/       # SQL schema (applied on postgres startup)
tests/            # Unit, integration, and E2E tests
data/docs/        # Document directory (WATCH_DIR)
docker-compose.yml
```

---

## 1. Executive summary

Build a cloud-agnostic Retrieval-Augmented Generation (RAG) platform that:

- answers only from content the user is authorized to access;
- combines lexical and semantic retrieval, followed by reranking;
- returns source-level and passage-level citations;
- separates ingestion, retrieval, generation, policy, and evaluation concerns;
- uses asynchronous, idempotent ingestion and stateless online services;
- makes quality, security, latency, reliability, and cost measurable;
- remains portable through stable internal contracts, while using managed cloud services behind adapters.

### Recommendation

Use **standard single-hop RAG** as the production baseline:

1. Authenticate the user and resolve their effective permissions.
2. Normalize and classify the query.
3. Run **BM25 lexical search and dense vector search in parallel**, with ACL and metadata filters applied inside each search request.
4. Fuse candidates using Reciprocal Rank Fusion (RRF).
5. Rerank the top candidates with a cross-encoder.
6. Assemble a token-budgeted, deduplicated context.
7. Generate an answer under a strict grounded-answer contract.
8. Validate citations and policy compliance before returning the response.

This offers the best balance of recall, precision, predictable latency, modularity, and operational simplicity. Add multi-query or agentic retrieval only for measured failure classes; do not make it the default.

## 2. Scope and assumptions

### In scope

- Enterprise document Q&A with inline citations and source links.
- Connectors for common document repositories.
- Incremental ingestion, deletion, permission synchronization, and reindexing.
- Text and layout extraction from office documents, HTML, PDF, and plain text.
- Search-time RBAC/ABAC enforcement.
- Multilingual-ready interfaces; initial language support is deployment-specific.
- Evaluation, observability, auditability, feedback, and administrative operations.
- Cloud-agnostic logical architecture with AWS, Azure, and Google Cloud mappings.

### Out of scope for the first release

- Autonomous actions or write access to enterprise systems.
- General web search.
- Model training or fine-tuning.
- Image, audio, and video understanding beyond extracted text.
- Knowledge graph retrieval.
- Fully agentic, unbounded multi-hop reasoning.
- Answers without retrievable evidence.

### Assumptions to validate during discovery

- Documents average 10-20 chunks after parsing; capacity planning starts at 15 million chunks.
- Source repositories expose stable identifiers, modification timestamps, and ACLs.
- Enterprise SSO supports OIDC or SAML and group claims or a directory lookup.
- A regional deployment is acceptable; data residency is configured per tenant or business unit.
- The selected model provider offers contractual privacy controls and does not train on submitted enterprise data.

## 3. Guiding principles

1. **Security before relevance:** an unauthorized result is always worse than a missed result.
2. **Evidence before fluency:** abstain when evidence is insufficient.
3. **Deterministic core, optional intelligence:** use fixed pipelines by default and gated adaptive behavior only where evaluation proves value.
4. **Asynchronous ingestion, synchronous retrieval:** isolate expensive and failure-prone document processing from user requests.
5. **Stable contracts over lowest-common-denominator infrastructure:** keep application interfaces portable without hiding useful managed-service capabilities.
6. **Idempotency and replayability:** every ingestion stage can be retried and rebuilt from canonical source metadata.
7. **Measure components independently:** retrieval, reranking, generation, citations, safety, latency, and cost each have explicit metrics.
8. **Immutable provenance:** every answer can be traced to user, query, model, prompt, index version, and source revisions.

## 4. Requirements

### Functional requirements

| ID | Requirement | Acceptance criterion |
|---|---|---|
| FR-01 | Ingest supported enterprise documents | New or changed content becomes searchable within 15 minutes at p95 under normal load |
| FR-02 | Synchronize source permissions | ACL changes, especially revocations, become effective within 5 minutes at p95 |
| FR-03 | Delete content completely | Source deletion removes searchable chunks within 15 minutes and derived artifacts within the retention SLA |
| FR-04 | Retrieve relevant passages | Hybrid retrieval and reranking are used for production queries |
| FR-05 | Enforce authorization | ACL/ABAC filters are applied within retrieval; unauthorized passages never enter model context |
| FR-06 | Generate grounded answers | Every factual claim is supported by a citation or the system abstains/qualifies it |
| FR-07 | Provide citations | Citations identify document, passage/section, source revision, and authorized deep link where possible |
| FR-08 | Support feedback | Users can record helpful/unhelpful feedback and optionally select a reason |
| FR-09 | Support administration | Operators can inspect connector, ingestion, index, model, evaluation, and quota health |
| FR-10 | Audit material events | Authentication, retrieval authorization, administrative actions, and model calls are auditable |
| FR-11 | Rebuild indexes safely | A new index version can be built, evaluated, canaried, switched atomically, and rolled back |
| FR-12 | Explain abstention | The response distinguishes no evidence, conflicting evidence, authorization limits, and service failure |

### Non-functional requirements

Initial service objectives; refine after load tests and user research.

| Attribute | Initial objective |
|---|---|
| Availability | 99.9% monthly for the query API, excluding agreed model-provider outages |
| Retrieval latency | p95 <= 700 ms including fusion and reranking |
| Time to first token | p95 <= 2.5 seconds |
| Complete answer latency | p95 <= 10 seconds for standard responses |
| Capacity | 1,000 concurrent users; design load test at 2x expected peak request rate |
| Retrieval quality | Recall@20 >= 0.90 on the approved gold set |
| Ranking quality | nDCG@10 target set during baseline; no release may regress by more than 2% |
| Citation quality | Citation precision >= 0.98 and citation completeness >= 0.95 |
| Groundedness | >= 0.95 on the approved evaluation set, with human-audited calibration |
| Security | Zero known retrieval-time ACL leakage in automated adversarial tests |
| Durability | Canonical metadata and configuration RPO <= 15 minutes |
| Recovery | Query path RTO <= 60 minutes; full index rebuild procedure tested quarterly |
| Accessibility | User experience targets WCAG 2.2 AA |
| Maintainability | Versioned interfaces, automated tests, infrastructure as code, and documented runbooks |

Percentile objectives apply over representative peak windows, not daily averages.

## 5. Architecture

### Context

```mermaid
flowchart LR
    User[Enterprise user] --> UI[Web or chat client]
    UI --> Gateway[API gateway]
    Gateway --> RAG[RAG query service]
    RAG --> Search[Hybrid search]
    RAG --> Models[Embedding, reranking and LLM providers]
    Sources[Enterprise sources] --> Ingestion[Ingestion platform]
    Ingestion --> Search
    IdP[Identity provider and directory] --> Gateway
    IdP --> RAG
    Admin[Platform operator] --> Ops[Admin and observability]
    RAG --> Ops
    Ingestion --> Ops
```

### Logical components

```mermaid
flowchart TB
    subgraph Online["Online query plane"]
      Client --> APIGW[API gateway / BFF]
      APIGW --> AuthZ[Identity and policy service]
      APIGW --> Orchestrator[Query orchestrator]
      Orchestrator --> QueryPrep[Query normalization and intent]
      Orchestrator --> Retriever[Retrieval service]
      Retriever --> Lexical[Lexical index]
      Retriever --> Vector[Vector index]
      Retriever --> Reranker[Reranker]
      Orchestrator --> Context[Context and citation builder]
      Context --> Generator[Generation gateway]
      Generator --> Guardrails[Input/output guardrails]
      Generator --> LLM[LLM provider]
      Orchestrator --> Response[Response and citation validator]
      Response --> Client
    end

    subgraph Ingest["Asynchronous ingestion plane"]
      Connectors[Source connectors] --> Queue[Event bus / work queues]
      Queue --> Fetch[Fetcher and change detector]
      Fetch --> Parse[Malware scan, parse and OCR]
      Parse --> Classify[Classification and policy]
      Classify --> Chunk[Structure-aware chunking]
      Chunk --> Embed[Embedding workers]
      Embed --> Indexer[Versioned index writer]
      Indexer --> Lexical
      Indexer --> Vector
      ACLSync[ACL synchronizer] --> Indexer
    end

    subgraph Control["Control and assurance plane"]
      Config[Versioned configuration]
      Eval[Evaluation service]
      Observe[Telemetry and audit]
      Registry[Prompt/model/index registry]
      AdminUI[Administration]
    end

    Orchestrator --> Observe
    Queue --> Observe
    Eval --> Registry
    Config --> Orchestrator
    Config --> Queue
```

### Deployment topology

- Deploy stateless online services across at least two availability zones.
- Scale ingestion workers independently by stage and queue depth.
- Separate online and ingestion compute, quotas, credentials, and network paths.
- Use private network endpoints for search, storage, model, key, and database services.
- Store original documents in their source systems; keep only governed processing artifacts when necessary.
- Maintain a canonical metadata store and immutable processing manifest separate from the search index.
- Use blue/green indexes and an alias for atomic promotion and rollback.
- Isolate tenants with explicit tenant keys at every layer; use physical indexes/accounts where risk or residency requires stronger isolation.

## 6. Key flows

### Query flow

1. Gateway authenticates the request and applies rate, size, and abuse limits.
2. Policy service resolves tenant, user, groups, attributes, and data-purpose constraints.
3. Query service detects unsupported or unsafe intent and creates a correlation ID.
4. Retriever executes lexical and dense searches concurrently with identical tenant, ACL, freshness, language, and source filters.
5. RRF fuses candidate lists; deduplication groups adjacent passages from the same source.
6. Cross-encoder reranks the top 20-50 candidates.
7. Context builder selects passages using relevance, diversity, recency, source authority, and token budget.
8. Generation gateway sends system instructions, the user query, and delimited untrusted evidence to the model.
9. Validator confirms citation identifiers exist in the supplied context and checks response policy.
10. The service streams the answer, citations, confidence/abstention reason, and trace ID.
11. Telemetry records timings, versions, token counts, retrieval IDs, and policy outcomes without logging sensitive content by default.

### Ingestion flow

1. Connector discovers a create, update, ACL change, or deletion.
2. An idempotent event is emitted with tenant, source, document ID, revision, and operation.
3. Fetcher verifies source authorization, content hash, size, type, and malware status.
4. Parser extracts text, layout, headings, tables, page/section anchors, and document metadata.
5. Classifier applies sensitivity, retention, residency, and exclusion policies.
6. Chunker produces structure-aware chunks and stable citation anchors.
7. Embedding workers batch requests and record embedding model/version.
8. Index writer upserts lexical text, vectors, provenance, and normalized ACL metadata.
9. Reconciler compares source and index manifests, repairs drift, and prioritizes revocations/deletions.
10. Dead-letter events remain visible and replayable; failures are never treated as successful ingestion.

## 7. Retrieval and generation design

### Approach comparison

| Approach | Advantages | Disadvantages | Decision |
|---|---|---|---|
| Sparse/BM25 only | Fast, interpretable, strong for names, IDs, acronyms | Misses paraphrases and semantic similarity | Retain as one hybrid channel |
| Dense only | Strong semantic recall and multilingual potential | Weak exact match; model changes require re-embedding | Retain as one hybrid channel |
| Hybrid + RRF | Robust across semantic and exact queries; simple rank fusion | More infrastructure and tuning | **Default** |
| Cross-encoder reranking | Improves top-k precision | Adds latency, cost, and throughput pressure | **Default with bounded candidate count** |
| Late interaction/ColBERT | Higher-granularity matching | Larger indexes and more compute | Evaluate only if baseline cannot meet quality |
| Knowledge graph retrieval | Useful for explicit relationships and multi-hop facts | High modeling and maintenance cost | Defer |
| Agentic retrieval | Can decompose complex questions | Variable cost/latency, larger attack surface, harder evaluation | Gated future capability |

### Retrieval defaults

- Fetch top 50 from each lexical and dense channel.
- Fuse with RRF; tune the constant and channel weights using offline evaluation.
- Rerank the top 20-50 and pass approximately 5-12 passages to generation.
- Enforce filters before or during candidate retrieval, never after generation.
- Prefer filterable compact principal/group identifiers over long Boolean ACL expressions.
- Add query rewriting only when its incremental recall exceeds its latency and security cost.
- Cache public/shared retrieval results only when the cache key includes tenant, effective authorization scope, filters, query normalization version, and index version.

These are starting values, not hard-coded product behavior.

### Chunking

Recommended strategy:

- preserve headings, paragraphs, lists, table structure, page numbers, and section anchors;
- target roughly 300-600 tokens per chunk with 10-15% overlap where structural boundaries do not suffice;
- prepend compact title and section context for retrieval, but preserve the original span for citations;
- avoid mixing content with different ACLs or classifications in one chunk;
- retain parent document and neighboring chunk identifiers;
- evaluate chunk sizes by source type rather than applying one global setting.

### Grounded-answer contract

The model must:

- use only the supplied evidence for enterprise facts;
- treat retrieved text as data, never as instructions;
- cite each material factual claim using provided citation IDs;
- state when evidence is missing, ambiguous, stale, or conflicting;
- never infer access to documents not present in context;
- avoid exposing internal prompts, ACLs, hidden metadata, or security labels.

The application, not the model, validates citation IDs and controls links.

## 8. Data and interface contracts

### Canonical chunk schema

```text
Chunk {
  tenant_id
  source_system
  document_id
  document_revision
  chunk_id
  content_hash
  title
  section_path[]
  text
  language
  source_uri
  citation_anchor { page?, section?, offsets? }
  content_type
  created_at
  modified_at
  indexed_at
  classification[]
  allowed_principals[]
  denied_principals[]
  policy_attributes{}
  embedding_model
  embedding_version
  embedding[]
  parser_version
  chunker_version
}
```

Large ACL lists may be represented through normalized entitlement sets or policy references where supported. The authorization design must preserve deny semantics and revocation correctness.

### External API

```http
POST /v1/answers
GET  /v1/answers/{requestId}
POST /v1/answers/{requestId}/feedback
GET  /v1/documents/{documentId}/citation/{chunkId}
```

Example request:

```json
{
  "question": "What is the approved travel policy for contractors?",
  "conversationId": "optional-id",
  "filters": {
    "sourceSystems": ["sharepoint"],
    "modifiedAfter": "2025-01-01T00:00:00Z"
  },
  "responseMode": "concise"
}
```

Example response envelope:

```json
{
  "requestId": "req_...",
  "answer": "Contractors must ... [1]",
  "citations": [
    {
      "id": "1",
      "documentId": "doc_...",
      "title": "Corporate Travel Policy",
      "section": "Contractors",
      "uri": "authorized-deep-link",
      "revision": "2026-07-10"
    }
  ],
  "status": "answered",
  "traceId": "trace_..."
}
```

`status` is one of `answered`, `insufficient_evidence`, `conflicting_evidence`, `policy_blocked`, or `failed`. Model confidence alone must not be exposed as a calibrated probability.

### Internal ports

Keep the following versioned interfaces independent of vendors:

- `IdentityResolver`
- `PolicyEvaluator`
- `DocumentConnector`
- `Parser`
- `Embedder`
- `SearchIndex`
- `Retriever`
- `Reranker`
- `Generator`
- `Guardrail`
- `EvaluationMetric`

Adapters translate these ports to managed services. Contract tests ensure equivalent authorization and failure behavior across implementations.

## 9. Security, privacy, and governance

Baseline: enterprise SSO, RBAC/ABAC, audit logs, encryption, and GDPR readiness.

### Mandatory controls

- OIDC/SAML SSO, short-lived tokens, MFA inherited from the identity provider.
- Least-privilege workload identities; no shared static cloud credentials.
- Tenant and authorization filters embedded in every retrieval request.
- Permission revocations and deletions receive priority processing.
- TLS in transit and customer-controlled encryption keys where required.
- Secrets stored only in a managed secrets service and rotated.
- Private endpoints, egress allowlists, workload isolation, and web application firewall.
- Input size, rate, token, concurrency, and cost limits.
- Malware scanning and file-type validation before parsing.
- Treat source documents, metadata, user queries, and model output as untrusted.
- Prompt-injection detection for direct and indirect/document attacks.
- Delimit evidence from instructions; do not allow retrieved content to select tools or change system policy.
- Output encoding and link validation; model output is never executable.
- PII minimization/redaction in logs and evaluation datasets.
- Configurable retention, legal deletion, data export, and residency.
- Immutable administrative and authorization audit events.
- Vendor data-processing agreements and explicit no-training/data-retention settings.
- Threat modeling and adversarial RAG tests before each material release.

### Authorization invariants

1. Every chunk belongs to exactly one tenant.
2. Retrieval denies by default when identity, tenant, or policy resolution fails.
3. The same effective policy applies to lexical and vector channels.
4. Post-filtering cannot repair an unauthorized candidate entering model context.
5. Citation resolution reauthorizes the user; a stored link is not proof of access.
6. Caches never broaden access and are invalidated on entitlement/index changes.
7. Audit logs record policy decisions without exposing document content.

### GDPR considerations

- Document purpose, lawful basis, owner, retention, and region.
- Data minimization for content copies, prompts, traces, feedback, and evaluation sets.
- Subject-access and erasure workflows covering indexes, caches, logs, and backups.
- Human review and documented impact assessment for high-risk uses.
- Clear user notice that answers are AI-generated and must be verified against citations.

Controls should map to the current NIST AI RMF/Generative AI Profile and OWASP GenAI guidance; mappings require periodic review as standards evolve.

## 10. Reliability, scalability, and performance

### Scaling model

- Online services are stateless and horizontally autoscaled on concurrency, latency, and queueing.
- Search capacity scales by index size, query rate, filter cardinality, and target recall.
- Reranking and generation use separate bulkheads, quotas, and circuit breakers.
- Ingestion stages use durable queues with bounded retries, exponential backoff, and dead-letter queues.
- Embedding is batched and rate-controlled; incremental updates are preferred over full rebuilds.
- Backpressure pauses connector polling before it overloads downstream services.
- Canonical manifests enable reconciliation and complete index rebuilds.

### Failure behavior

| Failure | Required behavior |
|---|---|
| Dense search unavailable | Degrade to lexical only if policy filtering remains equivalent; label telemetry |
| Lexical search unavailable | Degrade to dense only under the same condition |
| Reranker unavailable | Use fused rank order with an explicit degraded-mode metric |
| LLM unavailable | Return a service error; do not fabricate a success-shaped response |
| Policy/identity unavailable | Fail closed |
| Citation validation fails | Retry generation once with bounded policy, then abstain/fail explicitly |
| Connector/parser failure | Retry safely, surface operational error, then dead-letter |
| Index corruption | Switch to last known-good immutable index |

Degraded modes must be tested, observable, time-bounded, and removable through configuration.

### Capacity validation

Load tests must cover:

- expected and 2x peak QPS with realistic streaming durations;
- high-cardinality group/ACL filters;
- hot and long-tail queries;
- large documents and maximum context;
- model-provider throttling;
- ingestion bursts during concurrent query load;
- entitlement revocation during active sessions;
- blue/green index promotion and rollback.

## 11. Observability and evaluation

### Telemetry

Use OpenTelemetry and GenAI semantic conventions where stable. Propagate one trace across gateway, policy, retrieval channels, reranking, context building, generation, and validation.

Record:

- latency and error rate by stage and dependency;
- candidate counts, scores, filters, index/version, and reranker version;
- model, prompt version, tokens, finish reason, safety result, and cost;
- ingestion lag, queue age, failure class, throughput, and index drift;
- cache hit rate partitioned by authorization scope;
- SLO burn rate and degraded-mode duration.

Do not record raw queries, passages, or answers by default. Enable tightly controlled, sampled content capture only with an approved privacy purpose and retention policy.

### Evaluation layers

| Layer | Metrics |
|---|---|
| Ingestion | parse success, text/table fidelity, metadata/ACL fidelity, freshness, deletion lag |
| Retrieval | Recall@k, Precision@k, MRR, nDCG, ACL violation rate |
| Reranking | nDCG delta, top-k precision delta, latency and cost |
| Generation | correctness, groundedness/faithfulness, completeness, refusal quality |
| Citations | precision, completeness, passage entailment, link validity |
| Safety | prompt-injection success rate, sensitive disclosure, policy bypass |
| Product | answer usefulness, successful task completion, reformulation, adoption |

### Evaluation process

- Maintain a versioned gold set stratified by source, language, sensitivity, query type, and difficulty.
- Include answerable, unanswerable, ambiguous, conflicting, stale, exact-match, and adversarial questions.
- Use deterministic component metrics first; use model-based judges only after calibration against human reviewers.
- Run offline regression on every prompt, model, chunker, embedder, retriever, reranker, or policy change.
- Canary online changes and compare quality, latency, cost, and safety.
- Preserve evaluation inputs, expected evidence, versions, and decisions for reproducibility.

## 12. Technology options

### Search storage

| Option | Pros | Cons | Best fit |
|---|---|---|---|
| Managed hybrid search | Built-in BM25/vector fusion, filters, scaling, enterprise operations | Cloud coupling and service-specific semantics | **Recommended default** |
| OpenSearch/Elasticsearch-compatible | Strong lexical/hybrid features and portability options | Operational tuning and memory cost | Teams with search expertise |
| PostgreSQL + pgvector | ACID metadata, joins, familiar operations, fewer stores | Hybrid search and ANN scaling require more engineering | Smaller scale or PostgreSQL-centric estates |
| Dedicated vector database | Strong vector performance and managed operations | Extra governance surface; lexical/ACL features vary | Vector-heavy workloads with simple metadata |

**Decision:** select the managed hybrid search service in the deployment cloud, but retain canonical chunk/ACL data and a versioned `SearchIndex` contract so indexes are rebuildable elsewhere. Strict multi-cloud runtime portability is not worth sacrificing managed reliability at this scale.

### Orchestration

| Option | Pros | Cons | Decision |
|---|---|---|---|
| Custom thin orchestrator | Explicit behavior, minimal dependencies, predictable performance | More internal implementation | **Recommended for the core path** |
| LangGraph/LangChain | Rich ecosystem and adaptive workflows | Dependency churn and abstraction complexity | Optional for bounded advanced flows |
| Semantic Kernel/agent framework | Strong enterprise integration in relevant ecosystems | Framework/provider coupling | Optional adapter |
| Managed knowledge-base service | Fast delivery and integrated capabilities | Highest lock-in and less pipeline control | Prototype or deployment-specific accelerator |

### Model strategy

- Expose embedding, reranking, and generation models through separate gateways.
- Evaluate models on enterprise data; public benchmarks such as MTEB are only a shortlist input.
- Pin versions and support side-by-side evaluation.
- Prefer a strong general model for generation and a smaller, cheaper model only where quality gates pass.
- Route by explicit policy and task class, not opaque cost-only heuristics.
- Never change model or prompt versions globally without offline regression and canary validation.

## 13. Cloud service mappings

The mappings are deployment accelerators, not a requirement to use every listed service.

| Capability | AWS | Azure | Google Cloud |
|---|---|---|---|
| API/compute | API Gateway + ECS/EKS/Lambda | API Management + Container Apps/AKS/Functions | API Gateway/Apigee + Cloud Run/GKE/Functions |
| Queue/events | SQS/SNS/EventBridge/MSK | Service Bus/Event Grid/Event Hubs | Pub/Sub/Eventarc |
| Object artifacts | S3 | Blob Storage | Cloud Storage |
| Metadata | Aurora PostgreSQL/DynamoDB | Azure Database for PostgreSQL/Cosmos DB | Cloud SQL/AlloyDB/Spanner/Firestore |
| Hybrid/vector search | OpenSearch Service/Serverless; Bedrock Knowledge Bases | Azure AI Search | Gemini Enterprise Vector Search/RAG Engine; managed search composition varies |
| Models | Amazon Bedrock/SageMaker | Azure AI Foundry model endpoints | Vertex AI |
| Guardrails | Bedrock Guardrails | Azure AI Content Safety Prompt Shields | Model Armor and Vertex AI safety controls |
| Identity | IAM Identity Center/Cognito + IAM | Entra ID + managed identities | Cloud Identity/IAP + IAM |
| Keys/secrets | KMS + Secrets Manager | Key Vault | Cloud KMS + Secret Manager |
| Observability | CloudWatch/X-Ray + OTel | Azure Monitor/Application Insights + OTel | Cloud Monitoring/Trace + OTel |

Managed service features, especially ACL semantics, filters, regional availability, quotas, and deletion guarantees, must be verified during vendor selection.

## 14. Architecture decisions

| ID | Decision | Rationale | Consequence |
|---|---|---|---|
| ADR-001 | Standard RAG before agentic RAG | Predictable latency, cost, safety, and evaluation | Complex multi-hop questions may initially abstain |
| ADR-002 | Hybrid BM25 + dense retrieval with RRF | Covers exact and semantic matches | Operate and tune two retrieval channels |
| ADR-003 | Cross-encoder reranking | Improves precision of limited model context | Adds bounded latency and compute |
| ADR-004 | Retrieval-time ACL/ABAC enforcement | Prevents unauthorized context leakage | Permission data becomes index-critical |
| ADR-005 | Structure-aware chunks with immutable provenance | Better retrieval and defensible citations | More parsing and metadata work |
| ADR-006 | Async, event-driven, idempotent ingestion | Scalable recovery and source isolation | Requires queue and reconciliation operations |
| ADR-007 | Managed search behind a portable contract | Balances operational robustness and portability | Adapters must expose semantic differences |
| ADR-008 | Blue/green immutable index versions | Safe evaluation, cutover, and rollback | Temporary duplicate capacity |
| ADR-009 | Thin custom core orchestrator | Maintains deterministic behavior and modularity | Team owns core orchestration code |
| ADR-010 | Abstention is a valid outcome | Protects trust when evidence is insufficient | UX must explain limitations clearly |

## 15. Delivery plan

### Phase 0: Discovery and baseline (2-4 weeks)

- Confirm sources, languages, classifications, residency, usage, peak load, and identity model.
- Build a representative, security-labeled evaluation set.
- Benchmark parsers, embedding models, hybrid search, rerankers, and generators.
- Threat-model ingestion and query flows.
- Exit: approved target metrics, selected services, capacity/cost model, and data-protection assessment.

### Phase 1: Secure vertical slice (4-6 weeks)

- One source connector, incremental ingestion, permission synchronization, hybrid retrieval, reranking, grounded generation, citations, feedback, and end-to-end traces.
- Add deletion, revocation, and adversarial authorization tests.
- Exit: quality and security gates pass on a limited internal corpus.

### Phase 2: Production foundation (6-10 weeks)

- Multi-zone deployment, autoscaling, quotas, blue/green indexes, disaster recovery, admin operations, SLOs, runbooks, cost controls, and second connector.
- Conduct load, resilience, privacy, accessibility, and penetration testing.
- Exit: controlled pilot with on-call ownership.

### Phase 3: Scale and optimize

- Expand sources and languages; tune chunking by source type.
- Add semantic caching only after authorization-safe design validation.
- Optimize model routing and batching.
- Introduce multi-query or multi-hop retrieval only for measured gaps and behind a feature flag.

## 16. Testing strategy

- **Unit:** filters, RRF, context budgets, citation parsing, policy decisions, idempotency.
- **Contract:** connectors, search adapters, model gateways, identity and policy providers.
- **Integration:** create/update/delete/ACL flows; hybrid retrieval; citations; retries.
- **Security:** cross-tenant leakage, group explosion, stale ACLs, indirect injection, malicious files, SSRF, exfiltration, cache isolation.
- **Quality regression:** versioned gold set and adversarial set.
- **Performance:** peak query load, ingestion bursts, large ACL filters, provider throttling.
- **Resilience:** dependency failure, queue poison messages, zonal failure, index rollback.
- **Privacy:** erasure, retention expiry, log minimization, data residency.

Production release gates must include quality, ACL safety, latency, cost, and rollback readiness.

## 17. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Stale or incorrect ACLs | Critical disclosure | Fail closed, priority revocation pipeline, reconciliation, adversarial tests |
| Indirect prompt injection | Data leakage or manipulated answers | Treat documents as untrusted, delimit context, detect attacks, no autonomous tools |
| Poor source quality | Incorrect or conflicting answers | Source authority metadata, freshness, conflict detection, abstention |
| Provider throttling/outage | Latency and availability | Quotas, bulkheads, backoff, bounded fallback, capacity reservation where available |
| Model/index version drift | Silent quality regression | Version registry, offline gates, canaries, blue/green indexes |
| High reranking/generation cost | Unsustainable operation | Candidate bounds, batching, token budgets, caching with authorization-safe keys |
| Connector/API changes | Ingestion gaps | Contract tests, source reconciliation, connector health SLOs |
| Evaluation bias | Misleading quality scores | Stratified datasets, human calibration, production feedback review |
| Premature agentic complexity | Unpredictable behavior | Fixed pipeline baseline and feature-gated experiments |
| Vendor lock-in | Migration cost | Canonical data, internal ports, infrastructure as code, rebuild drills |

## 18. Open decisions

Resolve before Phase 1:

1. Priority source systems and their permission semantics.
2. Supported languages, file formats, OCR, and table requirements.
3. Expected peak queries per second and answer length distribution.
4. Data residency, retention, backup, and legal-hold requirements.
5. Tenant isolation model: logical, index-level, account/project/subscription-level, or mixed.
6. Cloud deployment target and approved model providers.
7. Required regions and availability objective.
8. Source authority and conflict-resolution rules.
9. Exact human-review and escalation workflow.
10. Cost budget per answer and per million ingested pages.

## 19. References

Primary and authoritative sources used for the approach:

- Karpukhin et al., [Dense Passage Retrieval for Open-Domain Question Answering](https://arxiv.org/abs/2004.04906), 2020.
- Khattab and Zaharia, [ColBERT: Efficient and Effective Passage Search via Contextualized Late Interaction](https://arxiv.org/abs/2004.12832), 2020.
- Muennighoff et al., [MTEB: Massive Text Embedding Benchmark](https://arxiv.org/abs/2210.07316), 2022.
- Cormack, Clarke, and Buettcher, [Reciprocal Rank Fusion](https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf), 2009.
- Malkov and Yashunin, [Efficient and Robust Approximate Nearest Neighbor Search Using HNSW](https://arxiv.org/abs/1603.09320).
- NIST, [AI Risk Management Framework and Generative AI Profile](https://www.nist.gov/itl/ai-risk-management-framework).
- OWASP, [GenAI LLM Top 10 2026](https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/).
- OpenTelemetry, [Generative AI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/).
- Microsoft, [RAG solution design and evaluation guide](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/rag/rag-solution-design-and-evaluation-guide).
- Microsoft, [Azure AI Search hybrid search](https://learn.microsoft.com/en-us/azure/search/hybrid-search-overview).
- Microsoft, [Document-level access control and security filters](https://learn.microsoft.com/en-us/azure/search/search-security-trimming-for-azure-search).
- Microsoft, [Chunk documents for vector search](https://learn.microsoft.com/en-us/azure/search/vector-search-how-to-chunk-documents).
- Microsoft, [Prompt Shields for direct and indirect attacks](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/concepts/jailbreak-detection).
- AWS, [Knowledge Bases for Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html).
- AWS, [Guardrails for Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html).
- AWS, [OpenSearch vector search](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/vector-search.html).
- AWS, [Well-Architected Generative AI Lens](https://docs.aws.amazon.com/wellarchitected/latest/generative-ai-lens/generative-ai-lens.html).
- Google Cloud, [RAG Engine overview](https://cloud.google.com/vertex-ai/generative-ai/docs/rag-engine/rag-overview).
- Google Cloud, [RAG-capable generative AI reference architecture](https://cloud.google.com/architecture/rag-capable-gen-ai-app-using-vertex-ai).
- Google Cloud, [Vector Search overview](https://cloud.google.com/vertex-ai/docs/vector-search/overview).
- Google Cloud, [Model Armor](https://cloud.google.com/security/products/model-armor).
- pgvector, [Open-source vector similarity search for PostgreSQL](https://github.com/pgvector/pgvector).
- Ragas, [RAG evaluation metrics](https://docs.ragas.io/en/stable/concepts/metrics/overview/).

Service names and capabilities evolve. Revalidate vendor-specific features, limits, regions, and terminology during implementation.
