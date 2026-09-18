"""End-to-end test for the full RAG pipeline.

This test requires docker compose to be running with the full stack:
  - postgres+pgvector
  - ollama (with models pulled)
  - backend (FastAPI)
  - frontend (Next.js)

Usage:
  1. docker compose up -d --build
  2. Wait for all services to be healthy
  3. pytest tests/e2e/test_full_stack.py -v --e2e

The --e2e flag is required to actually run these tests (they are skipped
by default since they need a live stack).
"""

import json
import os
import time

import httpx
import pytest

# E2E tests are opt-in via --e2e flag or E2E_TEST=1 env var
E2E_ENABLED = os.environ.get("E2E_TEST", "") == "1"

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")


def pytest_addoption(parser):
    """Add --e2e flag to pytest."""
    try:
        parser.addoption(
            "--e2e", action="store_true", help="Run E2E tests (needs docker compose)"
        )
    except ValueError:
        pass  # Already registered


def pytest_configure(config):
    """Register the e2e marker."""
    config.addinivalue_line("markers", "e2e: mark test as end-to-end (needs live stack)")


@pytest.fixture(scope="module")
def e2e_enabled(request):
    """Check if E2E tests should run."""
    flag = getattr(request.config, "getoption", lambda x, default=None: None)("--e2e")
    if not flag and not E2E_ENABLED:
        pytest.skip("E2E tests require --e2e flag or E2E_TEST=1 env var")
    return True


@pytest.fixture(scope="module")
def client():
    """HTTP client for the backend API."""
    return httpx.Client(base_url=BACKEND_URL, timeout=30.0)


def wait_for_health(client, max_wait=60):
    """Wait for the backend health endpoint to respond."""
    start = time.time()
    while time.time() - start < max_wait:
        try:
            resp = client.get("/health")
            if resp.status_code == 200:
                return True
        except httpx.ConnectError:
            pass
        time.sleep(2)
    return False


@pytest.mark.e2e
class TestHealthEndpoints:
    async def test_health_returns_ok(self, e2e_enabled, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    async def test_ready_checks_dependencies(self, e2e_enabled, client):
        if not wait_for_health(client):
            pytest.skip("Backend not reachable")
        resp = client.get("/ready")
        # May be 200 or 503 depending on Ollama model availability
        assert resp.status_code in (200, 503)


@pytest.mark.e2e
class TestIngestionE2E:
    async def test_ingest_sample_documents(self, e2e_enabled, client):
        """POST /v1/ingest processes sample documents from data/docs."""
        if not wait_for_health(client):
            pytest.skip("Backend not reachable")

        resp = client.post("/v1/ingest")
        assert resp.status_code == 200
        data = resp.json()

        assert "processed" in data
        assert "chunks" in data
        assert "failed" in data
        assert isinstance(data["processed"], int)
        assert isinstance(data["chunks"], int)

    async def test_ingest_is_idempotent(self, e2e_enabled, client):
        """Running ingest twice produces the same chunk count."""
        if not wait_for_health(client):
            pytest.skip("Backend not reachable")

        resp1 = client.post("/v1/ingest")
        data1 = resp1.json()

        resp2 = client.post("/v1/ingest")
        data2 = resp2.json()

        # Second run should not create new chunks (idempotent)
        assert data1["chunks"] == data2["chunks"]


@pytest.mark.e2e
class TestQueryFlowE2E:
    async def test_create_answer_returns_streaming_or_abstention(
        self, e2e_enabled, client
    ):
        """POST /v1/answers returns either streaming or insufficient_evidence."""
        if not wait_for_health(client):
            pytest.skip("Backend not reachable")

        # Ensure documents are ingested first
        client.post("/v1/ingest")

        resp = client.post(
            "/v1/answers",
            json={"question": "What is the travel policy?"},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert "status" in data
        assert data["status"] in ("streaming", "insufficient_evidence")

        if data["status"] == "streaming":
            assert data["answer_id"] is not None

    async def test_sse_stream_returns_tokens(self, e2e_enabled, client):
        """GET /v1/answers/{id}/stream returns SSE events with tokens."""
        if not wait_for_health(client):
            pytest.skip("Backend not reachable")

        # Ensure documents are ingested
        client.post("/v1/ingest")

        # Create answer
        resp = client.post(
            "/v1/answers",
            json={"question": "What is the travel policy?"},
        )
        data = resp.json()

        if data["status"] != "streaming":
            pytest.skip("Retrieval abstained — no stream to test")

        answer_id = data["answer_id"]

        # Connect to SSE stream
        with httpx.stream(
            "GET",
            f"{BACKEND_URL}/v1/answers/{answer_id}/stream",
            timeout=120.0,
        ) as stream:
            assert stream.status_code == 200

            events = []
            for line in stream.iter_lines():
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: "):
                    event_data = line[6:]
                    events.append((event_type, event_data))
                    if event_type == "done":
                        break

            # Verify we got at least one token event and one done event
            event_types = [e[0] for e in events]
            assert "token" in event_types or "done" in event_types

            # If we got a done event, verify it has citations
            done_events = [e for e in events if e[0] == "done"]
            if done_events:
                done_data = json.loads(done_events[0][1])
                assert "answer" in done_data
                assert "citations" in done_data

    async def test_empty_question_returns_400(self, e2e_enabled, client):
        """POST /v1/answers with empty question returns 400."""
        if not wait_for_health(client):
            pytest.skip("Backend not reachable")

        resp = client.post("/v1/answers", json={"question": ""})
        assert resp.status_code == 400

    async def test_feedback_endpoint(self, e2e_enabled, client):
        """POST /v1/answers/{id}/feedback records vote."""
        if not wait_for_health(client):
            pytest.skip("Backend not reachable")

        # Create an answer first
        client.post("/v1/ingest")
        resp = client.post(
            "/v1/answers",
            json={"question": "What is the travel policy?"},
        )
        data = resp.json()

        if data["status"] != "streaming":
            pytest.skip("No answer to give feedback on")

        answer_id = data["answer_id"]

        # Wait a bit for generation to complete
        time.sleep(3)

        # Submit feedback
        feedback_resp = client.post(
            f"/v1/answers/{answer_id}/feedback",
            json={"vote": "up"},
        )
        assert feedback_resp.status_code == 200
        assert feedback_resp.json()["vote"] == "up"


@pytest.mark.e2e
class TestFrontendE2E:
    async def test_frontend_reachable(self, e2e_enabled):
        """Frontend dev server responds on port 3000."""
        try:
            resp = httpx.get(FRONTEND_URL, timeout=10.0)
            assert resp.status_code == 200
        except httpx.ConnectError:
            pytest.skip("Frontend not reachable")
