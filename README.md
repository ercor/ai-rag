# AI RAG - Enterprise Knowledge Management System

A production-ready Retrieval-Augmented Generation (RAG) system for enterprise document question answering with verifiable citations. Built with Python FastAPI backend, Next.js frontend, and PostgreSQL+pgvector for hybrid search.

## 🎯 Overview

This system enables users to ask questions in natural language and receive answers sourced exclusively from authorized documents, with inline citations and source references. The system implements a complete vertical slice: document ingestion → hybrid retrieval → grounded generation → streaming responses.

**Latest Improvements (v1.1):**
- 🚀 **Cross-Encoder Reranking**: Improved retrieval precision with optional reranking
- 🔄 **Multi-Query Expansion**: Better recall through query rewriting
- ⚡ **Redis Caching**: Faster response times for repeated queries
- 💬 **Conversation History**: Multi-turn Q&A with persistent context
- 📊 **Evaluation Framework**: Comprehensive quality metrics with RAGAS integration

**Key Capabilities:**
- Hybrid search (BM25 + vector similarity) with RRF fusion
- Cross-encoder reranking for improved retrieval precision
- Multi-query expansion for better recall on ambiguous queries
- Redis caching for accelerated response times
- Multi-turn conversation history with context awareness
- Structure-aware document chunking with heading preservation
- Grounded-answer generation with citation validation
- Real-time streaming responses via Server-Sent Events
- Multi-format document support (PDF, DOCX, HTML, TXT, MD)
- Comprehensive evaluation framework with RAGAS metrics
- Hexagonal architecture for extensibility

## ✨ Features

### Core Features
- **Hybrid Retrieval**: Combines lexical search (BM25 via PostgreSQL tsvector) with semantic search (vector similarity via pgvector) using Reciprocal Rank Fusion (RRF)
- **Cross-Encoder Reranking**: Optional re-scoring of retrieval candidates using a cross-encoder model (`ms-marco-MiniLM-L-6-v2`) for improved precision. Fetches top-20 from RRF, reranks, and keeps top-5. Toggleable via `RERANKER_ENABLED` env var
- **Query Rewriting**: Optional multi-query expansion via LLM. Generates semantically distinct rephrasings of the user's query, searches for each variant in parallel, and merges results via cross-variant RRF for improved recall on ambiguous queries. Toggleable via `QUERY_REWRITER_ENABLED` env var
- **Redis Caching**: Optional caching layer for frequent queries. Caches complete answers with configurable TTL. Falls back gracefully when Redis is unavailable. Toggleable via `CACHE_ENABLED` env var
- **Conversation History**: Multi-turn Q&A with conversation management. Groups related questions/answers into conversations. Sidebar UI for browsing conversation history. Configurable history depth via `MAX_CONVERSATION_HISTORY` env var
- **Evaluation Framework**: Comprehensive evaluation suite with RAGAS metrics (faithfulness, answer relevancy, context precision/recall) and custom metrics (citation precision/completeness, retrieval hit rate). CLI-based evaluation with JSON reports. Gold dataset included with 24 stratified samples
- **Structure-Aware Chunking**: Block-based chunking that preserves document hierarchy (headings, lists, tables) and respects block boundaries
- **Grounded Generation**: LLM generates answers only from retrieved evidence, with strict citation requirements
- **Citation Validation**: Post-generation validation ensures all citations reference actual retrieved chunks
- **Streaming Responses**: Real-time token streaming via SSE for better UX
- **Abstention Support**: System abstains when insufficient evidence is found (no hallucination)
- **Multi-Format Parsing**: Supports PDF, DOCX, HTML, plain text, and Markdown with block-level structure extraction
- **Feedback System**: Users can provide thumbs up/down feedback on answers
- **Document Deduplication**: Content-hash-based change detection skips unchanged files and detects renames/deletions
- **Async Ingestion**: Background job processing with progress tracking and bounded concurrency

### Technical Features
- **Hexagonal Architecture**: Clean separation between ports (interfaces) and adapters (implementations)
- **Dependency Injection**: FastAPI Depends-based DI for testability and flexibility
- **Async/Await**: Fully asynchronous I/O for high concurrency
- **Batched Embedding**: Native batch API calls to Ollama (≤64 texts per request in CPU mode, ≤256 in GPU mode) for efficiency
- **GPU Acceleration**: Automatic GPU detection with dynamic batch size adjustment for 4x throughput improvement
- **Threaded Parsing**: Sync parser libraries run in thread pool to avoid blocking the event loop
- **Docker Compose**: One-command deployment with all dependencies
- **Comprehensive Testing**: 277 unit tests + integration tests (pytest)
- **OpenTelemetry Ready**: Structured for observability (logging in place, metrics/tracing ready)

## 🏗️ Architecture

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend                             │
│                    (Next.js + Tailwind)                      │
│  ChatInput → AnswerDisplay → CitationBadge → SourcePanel    │
│  ConversationSidebar ← → Conversation History               │
└──────────────────────┬──────────────────────────────────────┘
                       │ SSE (POST /v1/answers)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                      API Gateway                             │
│                   (FastAPI + CORS)                           │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        │                             │
        ▼                             ▼
┌──────────────────┐         ┌──────────────────┐
│  Query Pipeline  │         │ Ingestion Service│
│                  │         │                  │
│ 1. Cache Check   │         │ 1. Scan Directory│
│ 2. Rewrite Query │         │ 2. Parse Docs    │
│ 3. Embed Query   │         │ 3. Chunk         │
│ 4. Hybrid Search │         │ 4. Embed         │
│ 5. RRF Fusion    │         │ 5. Store         │
│ 6. Rerank        │         └──────────────────┘
│ 7. Generate      │
│ 8. Validate      │
│ 9. Cache Store   │
└────────┬─────────┘
         │
         ├─────────────────┬──────────────────┐
         │                 │                  │
         ▼                 ▼                  ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  PostgreSQL +    │ │    Redis Cache   │ │    Ollama API    │
│    pgvector      │ │                  │ │                  │
│                  │ │ - Answer Cache   │ │ - Embeddings     │
│ - BM25 (tsvector)│ │ - TTL Support    │ │ - LLM Generation │
│ - Vector (HNSW)  │ │ - Graceful Fail  │ │   (qwen2.5)      │
│ - Metadata       │ └──────────────────┘ │ - Reranking      │
│ - Conversations  │                      │ - Query Rewrite  │
└──────────────────┘                      └──────────────────┘
```

### Hexagonal Architecture (Ports & Adapters)

The system follows hexagonal architecture for maximum extensibility:

**Ports (Interfaces):**
- `DocumentSource` - Document discovery and retrieval
- `Parser` - Multi-format document parsing (returns ParsedDocument with blocks)
- `Chunker` - Structure-aware block-based chunking
- `Embedder` - Text embedding generation (batched)
- `SearchIndex` - Hybrid search (BM25 + vector)
- `Generator` - LLM answer generation
- `CitationValidator` - Citation verification
- `AnswerRepository` - Answer persistence
- `DocumentRegistry` - Document deduplication and tracking
- `Reranker` - Cross-encoder re-scoring of retrieval candidates
- `QueryRewriter` - Multi-query expansion for improved recall
- `Cache` - Key-value caching with TTL (Redis or no-op)
- `ConversationRepository` - Conversation history persistence
- `EvaluationMetric` - RAG evaluation metric computation

**Adapters (Implementations):**
- `filesystem_source.py` - Local directory scanning with SHA-256 content hashing
- `parsers.py` - Block-based parsing for PDF/DOCX/HTML/TXT/MD
- `recursive_chunker.py` - Structure-aware block chunking with per-type config
- `ollama_embedder.py` - Ollama embedding API with native batching
- `ollama_generator.py` - Ollama LLM streaming
- `pgvector_index.py` - PostgreSQL hybrid search
- `document_registry.py` - Document deduplication and change detection
- `regex_citation_validator.py` - Citation regex validation
- `pg_answer_repository.py` - asyncpg answer storage
- `cross_encoder_reranker.py` - Cross-encoder reranking with sentence-transformers
- `llm_query_rewriter.py` - LLM-based query expansion
- `redis_cache.py` - Redis caching with graceful degradation
- `noop_cache.py` - No-op cache for disabled caching
- `pg_conversation_repository.py` - Conversation history persistence

**Core Logic:**
- `retrieval.py` - RRF fusion algorithm
- `query_pipeline.py` - End-to-end query orchestration
- `ingestion_service.py` - Ingestion pipeline orchestration with dedup
- `job_registry.py` - Async job tracking and progress reporting

## 📐 Design Decisions

### Why PostgreSQL + pgvector?
- **Single Source of Truth**: Metadata, vectors, and full-text search in one database
- **ACID Compliance**: Transactional guarantees for data consistency
- **Mature Ecosystem**: Well-tested, production-ready
- **Cost Effective**: No separate vector database licensing
- **Hybrid Search**: Native support for both BM25 (tsvector) and vector similarity

### Why Hexagonal Architecture?
- **Testability**: Mock any adapter for unit testing
- **Flexibility**: Swap implementations without changing core logic
- **Extensibility**: Add new adapters (e.g., OpenAI embeddings, Elasticsearch) without refactoring
- **Clear Boundaries**: Separation of concerns between business logic and infrastructure

### Why Streaming (SSE)?
- **Better UX**: Users see answers as they're generated
- **Lower Perceived Latency**: First token arrives quickly
- **Standard Protocol**: Well-supported by browsers and HTTP clients
- **One-Way Communication**: Perfect for answer streaming (no need for bidirectional WebSocket)

### Why RRF Fusion?
- **Balanced Retrieval**: Combines lexical (exact match) and semantic (conceptual) search
- **No Training Required**: Works out-of-the-box without relevance feedback
- **Proven Technique**: Industry standard for hybrid search
- **Configurable**: Weights can be tuned based on query type

### Why Single-Table Schema?
- **MVP Simplicity**: Fewer JOINs, simpler queries
- **Performance**: All data in one place for fast retrieval
- **Validated Scale**: Works well up to ~10K chunks (sufficient for MVP)
- **Future Path**: Can split into documents + chunks tables when needed

## 📊 Specifications

### Performance Targets
- **Ingestion**: 10-100 documents processed in < 5 minutes
- **Retrieval Latency**: < 500ms for hybrid search + RRF fusion
- **Generation Latency**: < 30s for first token (CPU), < 5s (GPU)
- **Concurrent Users**: 10-50 (MVP scope)
- **Document Corpus**: 10-100 documents, 1K-10K chunks

### Quality Targets
- **Retrieval Precision**: > 0.8 for top-5 chunks
- **Citation Accuracy**: 100% (all citations validated)
- **Groundedness**: LLM generates only from retrieved evidence
- **Abstention Rate**: System abstains when evidence insufficient

### Supported Formats
- **PDF**: Text-based PDFs (no OCR for scanned documents in MVP)
- **DOCX**: Microsoft Word documents
- **HTML**: Web pages and HTML files
- **TXT**: Plain text files
- **MD**: Markdown files

### Chunking Strategy
- **Approach**: Block-based chunking that respects document structure
- **Block Types**: Headings, paragraphs, lists, tables preserved as atomic units
- **Size**: 200-600 tokens per chunk (configurable per source type)
- **Overlap**: 50 tokens between consecutive chunks (configurable per source type)
- **Hierarchy**: Preserves heading structure and section paths
- **Lists/Tables**: Never split mid-item or mid-row
- **Metadata**: Each chunk includes document_id, section_path, chunk_index, page_number (PDF), anchor
- **Per-Type Config**: Different chunk sizes for PDF, DOCX, HTML, TXT/MD via environment variables

### Embedding Configuration
- **Model**: nomic-embed-text (768 dimensions)
- **Provider**: Ollama (local)
- **Similarity**: Cosine distance
- **Index**: HNSW (Hierarchical Navigable Small World)

### Generation Configuration
- **Model**: qwen2.5 (7B parameters)
- **Provider**: Ollama (local)
- **Context**: Top 5 retrieved chunks
- **Temperature**: 0.1 (low for factual accuracy)
- **Max Tokens**: 1024

## 🚀 Capabilities

### What the System Can Do

✅ **Ingest Documents**
- Scan a configured directory for documents
- Parse multiple formats (PDF, DOCX, HTML, TXT, MD) with block-level structure extraction
- Extract text and metadata
- Chunk with structure awareness (respects headings, lists, tables)
- Generate embeddings in batches (≤64 texts per API call)
- Store in PostgreSQL with vectors
- Track document changes via content hashing
- Skip unchanged files on re-ingestion
- Detect renamed and deleted files
- Clean up stale chunks automatically
- Process documents asynchronously with bounded concurrency

✅ **Answer Questions**
- Accept natural language questions
- Embed the query
- Perform hybrid search (BM25 + vector)
- Fuse results with RRF
- Generate grounded answer with citations
- Stream response in real-time
- Validate all citations
- Persist answer with feedback

✅ **Provide Citations**
- Inline citation markers [1], [2], etc.
- Clickable badges showing source document
- Section path (e.g., "Section 2.3 → Subsection A")
- Source document reference

✅ **Handle Edge Cases**
- Abstain when no evidence found
- Handle malformed documents gracefully
- Validate citations post-generation
- Strip invalid citations from response
- Track ingestion job progress
- Report per-file failures

## ⚠️ Limitations

### Current Limitations

❌ **No Authentication/Authorization**
- Single-user system
- No access control
- All users see all documents

❌ **No OCR Support**
- Scanned PDFs (image-only) produce empty text
- Only text-based PDFs supported

❌ **No Multi-Tenancy**
- Single workspace
- No document isolation between users/teams

❌ **No Observability**
- Basic logging only
- No metrics, traces, or dashboards
- No performance monitoring

❌ **No Admin Interface**
- No document management UI
- No user management
- No system configuration UI

### Known Technical Constraints

⚠️ **CPU-Only Performance**
- First-token latency: ~30s on CPU (acceptable for development/testing)
- Recommendation: Use GPU-enabled Ollama for production deployments
- With GPU: First-token latency drops to ~3-5s

⚠️ **Reranker Model Download**
- First-time setup requires downloading the cross-encoder model (~500MB)
- Model is cached locally after first download
- Alternative: Disable reranking with `RERANKER_ENABLED=false`

⚠️ **Evaluation Dependencies**
- RAGAS metrics require additional dependencies: `pip install -e ".[eval]"`
- Custom metrics (citation precision/completeness) work without extra dependencies

## 🛠️ Quick Start Guide

### Prerequisites

Before you begin, ensure you have:

- **Docker** and **Docker Compose** (v2+) installed
- **Git** installed
- **8 GB RAM** minimum (Ollama models require memory)
- **10 GB disk space** for Docker images and models

### Step 1: Clone the Repository

```bash
git clone <repository-url>
cd ai-rag
```

### Step 2: Configure Environment

Copy the example environment file and adjust if needed:

```bash
cp .env.example .env
```

**Default configuration** (no changes needed for local testing):
- Database: PostgreSQL on port 5432
- Backend API: FastAPI on port 8000
- Frontend: Next.js on port 3000
- Ollama: Local LLM service on port 11434

### Step 3: Start the Application

Build and start all services:

```bash
docker compose up -d --build
```

This will:
- Build the backend and frontend Docker images
- Start PostgreSQL with pgvector extension
- Start Ollama service
- Start the FastAPI backend
- Start the Next.js frontend
- Run database migrations

**Verify services are running:**

```bash
docker compose ps
```

You should see 4 services running:
- `postgres` (healthy)
- `ollama` (running)
- `backend` (healthy)
- `frontend` (running)

### Step 4: Download LLM Models

Pull the required models (this takes ~5-10 minutes on first run):

```bash
# Download embedding model (274 MB)
docker compose exec ollama ollama pull nomic-embed-text

# Download generation model (4.7 GB)
docker compose exec ollama ollama pull qwen2.5
```

**Verify models are downloaded:**

```bash
docker compose exec ollama ollama list
```

You should see both models listed.

### Step 5: Add Documents

Place your documents in the `data/docs/` directory:

```bash
# Example: Copy your documents
cp /path/to/your/documents/*.pdf data/docs/
cp /path/to/your/documents/*.docx data/docs/
```

**Sample documents included:**
- `data/docs/travel_policy.md` - Example travel policy
- `data/docs/q3_results.md` - Example quarterly results

### Step 6: Ingest Documents

Trigger document ingestion via the API (returns a job ID for tracking):

```bash
curl -X POST http://localhost:8000/api/v1/ingest
```

**Expected response:**

```json
{
  "job_id": "job-abc123",
  "status": "accepted"
}
```

**Check ingestion progress:**

```bash
curl http://localhost:8000/api/v1/ingest/job-abc123
```

**Response:**

```json
{
  "job_id": "job-abc123",
  "status": "completed",
  "total_files": 10,
  "processed_files": 10,
  "chunks_created": 145,
  "failed_files": 0,
  "failures": []
}
```

**Check ingestion logs:**

```bash
docker compose logs backend | grep "Ingestion completed"
```

### Step 7: Use the Application

Open your browser and navigate to:

**http://localhost:3000**

You should see the chat interface.

**Try asking questions like:**
- "What is the termination clause in the contract?"
- "What are the technical requirements?"
- "Summarize the key points from the documents"

**What happens:**
1. You type a question and press Enter
2. The question is embedded and sent to the backend
3. Hybrid search retrieves relevant chunks
4. LLM generates an answer with citations
5. Answer streams back in real-time
6. Citations appear as clickable badges
7. Click a citation to see the source document and section

### Step 8: Provide Feedback

After receiving an answer, you can provide feedback:
- 👍 **Thumbs up**: Answer was helpful
- 👎 **Thumbs down**: Answer was not helpful

Feedback is stored in the database for future analysis.

### Step 9: View Logs (Optional)

Monitor application logs:

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f postgres
```

### Step 10: Stop the Application

When you're done:

```bash
docker compose down
```

**To remove all data (fresh start):**

```bash
docker compose down -v
```

## 📖 Usage Examples

### Example 1: Ask a Question

**Question:** "What are the payment terms?"

**Response:**
> According to the contract, payment terms are net 30 days from invoice date [1]. Late payments incur a 1.5% monthly interest charge [1].

**Citations:**
- [1] travel_policy.md → Section 4: Payment Terms

### Example 2: Ask for a Summary

**Question:** "Summarize the technical requirements"

**Response:**
> The technical requirements include:
> 1. System must support 1000 concurrent users [1]
> 2. Response time under 2 seconds for 95% of queries [1]
> 3. 99.9% uptime SLA [2]
> 4. Data encryption at rest and in transit [2]

**Citations:**
- [1] q3_results.md → Section 2: Performance Requirements
- [2] q3_results.md → Section 3: Reliability Requirements

### Example 3: No Evidence Found

**Question:** "What is the company's vacation policy?"

**Response:**
> I don't have enough information in the provided documents to answer this question. The available documents focus on contract terms and technical specifications, but do not contain information about vacation policies.

**Citations:** None

## 🧪 Testing

### Run Unit Tests

```bash
# Without Docker (fast)
pytest tests/unit/ -v
```

**Expected output:**
```
tests/unit/test_chunker.py::test_chunk_document PASSED
tests/unit/test_rrf.py::test_rrf_fusion PASSED
tests/unit/test_citation_validator.py::test_validate_citations PASSED
...
151 passed in 2.34s
```

### Run Integration Tests

```bash
# Requires Docker (PostgreSQL)
pytest tests/integration/ -v
```

**Tests:**
- Database connection and queries
- Vector similarity search
- BM25 full-text search
- Answer persistence

### Run E2E Tests

```bash
# Requires full stack running
pytest tests/e2e/ -v
```

**Tests:**
- Full ingestion flow
- End-to-end question answering
- Streaming response validation
- Citation accuracy

### Test Coverage

```bash
# Generate coverage report
pytest --cov=src --cov-report=html

# Open in browser
open htmlcov/index.html
```

**Current coverage:** ~85%

## 📊 Evaluation Framework

The system includes a comprehensive evaluation framework for measuring RAG pipeline quality.

### Running Evaluations

```bash
# Install evaluation dependencies
pip install -e ".[eval]"

# Run evaluation with all metrics
python -m src.evaluation --dataset data/eval/gold_set.json

# Run specific metrics only
python -m src.evaluation --dataset data/eval/gold_set.json --metrics citation_precision,faithfulness

# Custom output path
python -m src.evaluation --dataset data/eval/gold_set.json --output reports/my_eval.json
```

### Available Metrics

**RAGAS Metrics** (require LLM judge):
- `faithfulness` - Measures if the answer is faithful to the retrieved contexts
- `answer_relevancy` - Measures if the answer is relevant to the question
- `context_precision` - Measures if retrieved contexts are precise
- `context_recall` - Measures if all relevant contexts were retrieved

**Custom Metrics** (no LLM required):
- `citation_precision` - Fraction of citations that reference valid chunks
- `citation_completeness` - Fraction of claims with supporting citations
- `retrieval_hit_rate` - Whether at least one gold context was retrieved

### Gold Dataset

The gold dataset (`data/eval/gold_set.json`) contains 24 stratified samples covering:
- **Sources**: travel_policy, q3_results, engineering_onboarding
- **Difficulty**: easy, medium, hard
- **Query types**: factual, comparative, procedural

### Report Format

Evaluation reports are JSON files with:
- Per-metric aggregates (mean, std, min, max, count)
- Per-sample scores
- Metadata (timestamp, dataset path)

Reports are saved to `data/eval/reports/` by default.

### Adding Custom Metrics

Create a class implementing the `EvaluationMetric` protocol:

```python
from src.ports.evaluation import EvaluationMetric

class MyMetric:
    @property
    def name(self) -> str:
        return "my_metric"

    def compute(self, question: str, answer: str, contexts: list[str], 
                ground_truth: str | None = None) -> float | None:
        # Your metric logic here
        return score  # 0.0 to 1.0, or None if cannot compute
```

## 📁 Project Structure

```
ai-rag/
├── src/                          # Backend source code
│   ├── main.py                   # FastAPI application entry point
│   ├── config.py                 # Configuration management
│   ├── container.py              # Dependency injection container
│   ├── ports/                    # Hexagonal architecture ports
│   │   ├── models.py            # Data models (Chunk, ParsedDocument, Answer, etc.)
│   │   ├── document_source.py   # DocumentSource interface
│   │   ├── parser.py            # Parser interface
│   │   ├── chunker.py           # Chunker interface
│   │   ├── embedder.py          # Embedder interface
│   │   ├── search_index.py      # SearchIndex interface
│   │   ├── generator.py         # Generator interface
│   │   ├── citation_validator.py # CitationValidator interface
│   │   ├── answer_repository.py # AnswerRepository interface
│   │   ├── reranker.py          # Reranker interface
│   │   ├── query_rewriter.py    # QueryRewriter interface
│   │   ├── cache.py             # Cache interface
│   │   ├── conversation_repository.py # ConversationRepository interface
│   │   └── evaluation.py        # EvaluationMetric interface
│   ├── adapters/                 # Hexagonal architecture adapters
│   │   ├── filesystem_source.py # Local directory scanner with content hashing
│   │   ├── parsers.py           # Multi-format document parsers (block-based)
│   │   ├── recursive_chunker.py # Structure-aware block chunking
│   │   ├── ollama_embedder.py   # Ollama embedding client (batched)
│   │   ├── ollama_generator.py  # Ollama LLM client
│   │   ├── pgvector_index.py    # PostgreSQL hybrid search
│   │   ├── document_registry.py # Document deduplication and tracking
│   │   ├── regex_citation_validator.py # Citation validation
│   │   ├── pg_answer_repository.py     # Answer persistence
│   │   ├── cross_encoder_reranker.py   # Cross-encoder reranking
│   │   ├── llm_query_rewriter.py       # LLM-based query expansion
│   │   ├── redis_cache.py       # Redis caching
│   │   ├── noop_cache.py        # No-op cache
│   │   └── pg_conversation_repository.py # Conversation persistence
│   ├── core/                     # Core business logic
│   │   ├── retrieval.py         # RRF fusion algorithm
│   │   ├── query_pipeline.py    # Query orchestration
│   │   ├── ingestion_service.py # Ingestion pipeline orchestration
│   │   ├── job_registry.py      # Async job tracking
│   │   └── cache_key.py         # Cache key computation
│   ├── evaluation/               # Evaluation framework
│   │   ├── __main__.py          # CLI entry point
│   │   ├── custom_metrics.py    # Custom evaluation metrics
│   │   ├── dataset.py           # Gold dataset loader
│   │   ├── ragas_adapter.py     # RAGAS metrics integration
│   │   ├── report.py            # JSON report generator
│   │   └── runner.py            # Evaluation runner
│   └── api/                      # API routes
│       ├── answers.py           # POST /v1/answers, GET /stream
│       ├── conversations.py     # Conversation CRUD endpoints
│       ├── ingestion.py         # POST /v1/ingest, GET /v1/ingest/{job_id}
│       └── health.py            # GET /health
├── frontend/                     # Next.js frontend
│   ├── app/
│   │   ├── page.tsx             # Main chat interface with conversation support
│   │   ├── layout.tsx           # Root layout with sidebar
│   │   └── icon.svg             # Favicon
│   ├── components/
│   │   ├── ChatInput.tsx        # Question input
│   │   ├── AnswerDisplay.tsx    # Streaming answer display
│   │   ├── CitationBadge.tsx    # Clickable citation badges
│   │   ├── SourcePanel.tsx      # Source document panel
│   │   ├── FeedbackButtons.tsx  # Thumbs up/down feedback
│   │   └── ConversationSidebar.tsx # Conversation list sidebar
│   ├── lib/
│   │   ├── sse.ts               # SSE client for streaming
│   │   └── conversations.ts     # Conversation API client
│   ├── Dockerfile               # Frontend container
│   ├── package.json
│   └── next.config.js
├── tests/                        # Test suites
│   ├── unit/                    # Unit tests (277 tests, no Docker)
│   ├── integration/             # Integration tests (PostgreSQL)
│   └── e2e/                     # End-to-end tests (full stack)
├── migrations/                   # Database migrations
│   ├── 001_initial_schema.sql   # Initial schema with pgvector
│   ├── 002_documents.sql        # Documents table for deduplication
│   ├── 003_chunk_metadata.sql   # Page number and anchor columns
│   └── 004_conversations.sql    # Conversations table and FK on answers
├── data/                         # Sample data
│   ├── docs/                    # Sample documents
│   └── eval/                    # Evaluation framework
│       ├── gold_set.json        # Gold dataset (24 stratified samples)
│       └── reports/             # Evaluation report output directory
├── docker-compose.yml            # Multi-container orchestration
├── Dockerfile.backend            # Backend container
├── .env.example                  # Environment configuration template
├── pyproject.toml                # Python project configuration
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

## 🔧 Configuration

### Environment Variables

All configuration is via environment variables (see `.env.example`):

**Database:**
- `DATABASE_URL` - PostgreSQL connection string

**Ollama:**
- `OLLAMA_BASE_URL` - Ollama API endpoint
- `OLLAMA_EMBEDDING_MODEL` - Embedding model name
- `OLLAMA_GENERATION_MODEL` - Generation model name

**Ingestion:**
- `INGESTION_SOURCE_PATH` - Directory to scan for documents
- `INGEST_CONCURRENCY` - Max documents processed in parallel (default: 2)
- `EMBED_BATCH_SIZE` - Texts per embedding API call in CPU mode (default: 64)
- `EMBED_BATCH_SIZE_GPU` - Texts per embedding API call in GPU mode (default: 256)
- `GPU_ENABLED` - Force GPU acceleration on/off (default: auto-detect)

**GPU Acceleration:**
The system automatically detects NVIDIA GPU availability and adjusts embedding batch sizes accordingly. When GPU is detected:
- Embedding batch size increases from 64 to 256 texts per API call
- Throughput improves significantly (4x larger batches)
- Auto-detection uses `nvidia-smi` to check for GPU availability
- Set `GPU_ENABLED=true` to force GPU mode or `GPU_ENABLED=false` to disable

To use GPU acceleration:
1. Ensure NVIDIA drivers are installed
2. Configure Ollama with GPU support (see Ollama documentation)
3. Set `GPU_ENABLED=true` in `.env` or let auto-detection handle it
4. Monitor logs for "GPU detected" messages

**Chunking (per source type):**
- `CHUNK_MIN_PDF`, `CHUNK_MAX_PDF`, `CHUNK_OVERLAP_PDF` - PDF chunking config
- `CHUNK_MIN_DOCX`, `CHUNK_MAX_DOCX`, `CHUNK_OVERLAP_DOCX` - DOCX chunking config
- `CHUNK_MIN_HTML`, `CHUNK_MAX_HTML`, `CHUNK_OVERLAP_HTML` - HTML chunking config
- `CHUNK_MIN_TXT`, `CHUNK_MAX_TXT`, `CHUNK_OVERLAP_TXT` - TXT/MD chunking config
- Defaults: MIN=200, MAX=600, OVERLAP=50 tokens

**Retrieval:**
- `RETRIEVAL_TOP_K` - Number of chunks to retrieve
- `RRF_K` - RRF fusion constant

**Generation:**
- `GENERATION_MAX_TOKENS` - Maximum tokens in response
- `GENERATION_TEMPERATURE` - LLM temperature (0.0-1.0)

**Reranking:**
- `RERANKER_ENABLED` - Enable cross-encoder reranking (default: true)
- `RERANKER_MODEL` - Cross-encoder model name (default: cross-encoder/ms-marco-MiniLM-L-6-v2)
- `RERANKER_TOP_K_BEFORE` - Number of candidates to fetch before reranking (default: 20)
- `RERANKER_TOP_K_AFTER` - Number of candidates to keep after reranking (default: 5)
- `RERANKER_TIMEOUT_SECONDS` - Timeout for reranking operation (default: 5.0)

**Query Rewriting:**
- `QUERY_REWRITER_ENABLED` - Enable LLM-based query expansion (default: false)
- `QUERY_REWRITER_NUM_VARIANTS` - Number of query variants to generate (default: 3)

**Caching:**
- `CACHE_ENABLED` - Enable Redis caching (default: true)
- `REDIS_URL` - Redis connection URL (default: redis://localhost:6379)
- `CACHE_TTL_SECONDS` - Cache time-to-live in seconds (default: 1800)

**Conversation History:**
- `MAX_CONVERSATION_HISTORY` - Number of previous Q&A pairs to include in prompt (default: 5)

**Evaluation:**
- `EVAL_DATASET_PATH` - Path to gold dataset JSON file (default: data/eval/gold_set.json)
- `EVAL_METRICS` - Comma-separated list of metrics to compute (default: all)
- `EVAL_REPORT_DIR` - Directory for evaluation reports (default: data/eval/reports)

**Application:**
- `LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR)
- `CORS_ORIGINS` - Allowed CORS origins

## 🚦 API Reference

### POST /api/v1/ingest

Trigger document ingestion (async job).

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/ingest
```

**Response (202 Accepted):**
```json
{
  "job_id": "job-abc123",
  "status": "accepted"
}
```

**Note:** If a job is already running, returns 409 Conflict.

### GET /api/v1/ingest/{job_id}

Check ingestion job progress.

**Request:**
```bash
curl http://localhost:8000/api/v1/ingest/job-abc123
```

**Response:**
```json
{
  "job_id": "job-abc123",
  "status": "completed",
  "total_files": 10,
  "processed_files": 10,
  "chunks_created": 145,
  "failed_files": 0,
  "failures": []
}
```

**Status values:** `pending`, `running`, `completed`, `failed`

### POST /api/v1/answers

Submit a question (returns answer_id).

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/answers \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the termination clause?", "conversation_id": "conv-123"}'
```

**Response:**
```json
{
  "answer_id": "abc123-def456",
  "status": "processing"
}
```

**Note:** `conversation_id` is optional. When provided, the answer is linked to the conversation and conversation history is included in the prompt context.

### GET /api/v1/answers/{answer_id}/stream

Stream the answer (SSE).

**Request:**
```bash
curl -N http://localhost:8000/api/v1/answers/abc123-def456/stream
```

**Response (SSE events):**
```
event: token
data: {"text": "According"}

event: token
data: {"text": " to"}

event: token
data: {"text": " the"}

event: citation
data: {"id": 1, "document_id": "doc1", "section": "Section 4"}

event: done
data: {"answer_id": "abc123-def456"}
```

### POST /api/v1/answers/{answer_id}/feedback

Submit feedback for an answer.

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/answers/abc123-def456/feedback \
  -H "Content-Type: application/json" \
  -d '{"rating": "up"}'
```

**Response:**
```json
{
  "status": "success"
}
```

### POST /api/v1/conversations

Create a new conversation.

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/conversations \
  -H "Content-Type: application/json" \
  -d '{"title": "Contract Review"}'
```

**Response (201 Created):**
```json
{
  "id": "conv-abc123",
  "title": "Contract Review",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

### GET /api/v1/conversations

List all conversations (most recent first).

**Request:**
```bash
curl http://localhost:8000/api/v1/conversations
```

**Response:**
```json
[
  {
    "id": "conv-abc123",
    "title": "Contract Review",
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-01-15T10:30:00Z"
  }
]
```

### GET /api/v1/conversations/{conversation_id}

Get a conversation with all its answers.

**Request:**
```bash
curl http://localhost:8000/api/v1/conversations/conv-abc123
```

**Response:**
```json
{
  "id": "conv-abc123",
  "title": "Contract Review",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:35:00Z",
  "answers": [
    {
      "id": "answer-1",
      "question": "What is the termination clause?",
      "answer": "The termination clause states...",
      "status": "answered",
      "citations": [...],
      "created_at": "2024-01-15T10:31:00Z"
    }
  ]
}
```

### DELETE /api/v1/conversations/{conversation_id}

Delete a conversation and all its answers.

**Request:**
```bash
curl -X DELETE http://localhost:8000/api/v1/conversations/conv-abc123
```

**Response (204 No Content):** Empty response

### GET /health

Health check endpoint.

**Request:**
```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

## 🗺️ Roadmap

### Phase 2: Production Hardening
- [ ] Authentication and authorization (OAuth2/OIDC)
- [x] Cross-encoder reranking for improved precision ✅
- [ ] Multi-tenancy support
- [x] Conversation history and multi-turn Q&A ✅
- [ ] Observability (metrics, traces, dashboards)
- [ ] Admin interface for document management

### Phase 3: Scale and Performance
- [ ] Distributed architecture for high availability
- [x] Caching layer (Redis) for frequent queries ✅

### Phase 4: Advanced Features
- [x] Query rewriting and expansion ✅
- [ ] Multi-modal support (images, tables)
- [ ] Federated search across multiple sources
- [ ] Custom embedding models (fine-tuned)
- [x] Evaluation framework (RAGAS, custom metrics) ✅
- [ ] A/B testing framework

### ✅ Completed
- [x] Document deduplication and change detection
- [x] Async ingestion with job tracking
- [x] Batched embedding with bounded concurrency
- [x] Structure-aware chunking (block-based)
- [x] Per-source-type chunking configuration
- [x] GPU acceleration with auto-detection and dynamic batch sizing
- [x] Cross-encoder reranking with timeout handling
- [x] Query rewriting with multi-query expansion
- [x] Redis caching with graceful degradation
- [x] Conversation history with multi-turn Q&A
- [x] Evaluation framework with RAGAS metrics

## 🤝 Contributing

This is an MVP implementation. For production use, consider:
- Adding authentication and authorization
- Implementing incremental ingestion
- Adding comprehensive monitoring
- Scaling for your specific use case
- Customizing chunking strategies for your document types

## 📄 License

This project is provided as-is for educational and evaluation purposes.

## 🙏 Acknowledgments

- **Ollama** - Local LLM runtime
- **pgvector** - PostgreSQL vector extension
- **FastAPI** - Modern Python web framework
- **Next.js** - React framework

## 📞 Support

For issues, questions, or contributions, please open an issue in the repository.

---

**Built with ❤️ using Python, FastAPI, Next.js, and PostgreSQL**
