"""Integration tests for async ingestion job API.

Tests:
- POST /v1/ingest → 202 + job_id
- GET /v1/ingest/{job_id} → progress with state/counts
- Concurrent POST → 409
- Unknown job_id → 404
"""

from unittest.mock import AsyncMock, MagicMock, patch


class TestIngestApiAsync:
    async def test_post_ingest_returns_202_with_job_id(self):
        """POST /v1/ingest → 202 + job_id immediately."""
        from fastapi.testclient import TestClient

        from src.core.job_registry import JobRegistry
        from src.main import app

        # Create a fresh registry for this test
        test_registry = JobRegistry()

        with patch("src.api.ingestion.get_job_registry", return_value=test_registry):
            with patch("src.api.ingestion.get_ingestion_service") as mock_service:
                # Mock the service to return immediately
                from src.core.ingestion_service import IngestionResult
                mock_svc = MagicMock()
                mock_svc.run = AsyncMock(return_value=IngestionResult())
                mock_service.return_value = mock_svc

                client = TestClient(app)
                response = client.post("/v1/ingest")

                assert response.status_code == 202
                data = response.json()
                assert "job_id" in data
                assert isinstance(data["job_id"], str)

    async def test_get_ingest_job_returns_progress(self):
        """GET /v1/ingest/{job_id} → progress with state/counts."""
        from fastapi.testclient import TestClient

        from src.core.job_registry import JobRegistry
        from src.main import app

        test_registry = JobRegistry()

        with patch("src.api.ingestion.get_job_registry", return_value=test_registry):
            with patch("src.api.ingestion.get_ingestion_service") as mock_service:
                # Use a simple mock that returns a result
                from src.core.ingestion_service import IngestionResult
                mock_svc = MagicMock()
                mock_svc.run = AsyncMock(return_value=IngestionResult())
                mock_service.return_value = mock_svc

                client = TestClient(app)

                # Submit a job
                post_response = client.post("/v1/ingest")
                job_id = post_response.json()["job_id"]

                # Wait a bit for the background task to start
                import time
                time.sleep(0.1)

                # Query the job
                get_response = client.get(f"/v1/ingest/{job_id}")

                assert get_response.status_code == 200
                data = get_response.json()
                assert data["job_id"] == job_id
                assert "state" in data
                assert "total" in data
                assert "processed" in data
                assert "chunks" in data

    async def test_concurrent_post_returns_409(self):
        """Concurrent POST → 409 Conflict."""
        from fastapi.testclient import TestClient

        from src.core.job_registry import JobRegistry
        from src.main import app

        test_registry = JobRegistry()

        with patch("src.api.ingestion.get_job_registry", return_value=test_registry):
            with patch("src.api.ingestion.get_ingestion_service") as mock_service:
                mock_svc = MagicMock()
                # Make the service run slowly so we can test concurrency
                async def slow_run(*args, **kwargs):
                    import asyncio
                    await asyncio.sleep(0.5)
                mock_svc.run = slow_run
                mock_service.return_value = mock_svc

                client = TestClient(app)

                # First POST should succeed
                response1 = client.post("/v1/ingest")
                assert response1.status_code == 202

                # Second POST while first is running → 409
                response2 = client.post("/v1/ingest")
                assert response2.status_code == 409
                data = response2.json()
                # FastAPI wraps detail in 'detail' key
                assert data["detail"]["error"] == "job_already_running"
                assert "job_id" in data["detail"]

    async def test_get_unknown_job_returns_404(self):
        """GET /v1/ingest/{unknown_id} → 404."""
        from fastapi.testclient import TestClient

        from src.core.job_registry import JobRegistry
        from src.main import app

        test_registry = JobRegistry()

        with patch("src.api.ingestion.get_job_registry", return_value=test_registry):
            client = TestClient(app)
            response = client.get("/v1/ingest/nonexistent-job-id")

            assert response.status_code == 404
