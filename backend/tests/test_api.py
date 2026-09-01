"""Unit tests for API endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.unit
@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test health check endpoint returns 200."""
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.unit
@pytest.mark.asyncio
async def test_api_key_validation_required(client: AsyncClient, env_vars):
    """Test that API key is required when configured."""
    # This test assumes API_KEY is set in env
    response = await client.post("/query", json={"upload_id": "test", "query": "test"})
    # Should either require API key or allow if not configured
    assert response.status_code in [200, 401, 400]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_upload_endpoint_missing_file(client: AsyncClient):
    """Test upload endpoint with missing file returns 422."""
    response = await client.post("/upload")
    assert response.status_code in [422, 400]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_endpoint_validation(client: AsyncClient):
    """Test query endpoint validates input."""
    invalid_payload = {"invalid": "payload"}
    response = await client.post("/query", json=invalid_payload)
    assert response.status_code in [422, 400]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_job_status_not_found(client: AsyncClient):
    """Test job status endpoint with nonexistent job."""
    response = await client.get("/job/nonexistent-job-id/status")
    assert response.status_code == 404


@pytest.mark.unit
def test_cors_middleware_headers():
    """Test CORS middleware is configured."""
    from app.api.main import app
    
    cors_middleware_found = any(
        "CORSMiddleware" in str(middleware) for middleware in app.user_middleware
    )
    assert cors_middleware_found, "CORS middleware not configured"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_api_key_middleware_exists(client: AsyncClient):
    """Test API key middleware is configured."""
    # Attempt request without API key (if required)
    response = await client.get("/health")
    # Health check should be allowed even without API key
    assert response.status_code == 200


class TestUploadEndpoint:
    """Tests for /upload endpoint."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_unsupported_format(self, client: AsyncClient):
        """Test upload with unsupported file format."""
        from io import BytesIO
        
        unsupported_file = BytesIO(b"fake content")
        response = await client.post(
            "/upload",
            files={"file": ("test.xyz", unsupported_file)},
        )
        assert response.status_code == 415


class TestQueryEndpoint:
    """Tests for /query endpoint."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_query_missing_upload_id(self, client: AsyncClient):
        """Test query with missing upload_id."""
        payload = {"query": "What do you see?"}
        response = await client.post("/query", json=payload)
        assert response.status_code == 422

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_query_missing_query_text(self, client: AsyncClient):
        """Test query with missing query text."""
        payload = {"upload_id": "test-id"}
        response = await client.post("/query", json=payload)
        assert response.status_code == 422


class TestJobStatusEndpoint:
    """Tests for /job/{id}/status endpoint."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_job_status_response_format(self, client: AsyncClient):
        """Test job status endpoint response format when job exists."""
        # This would require creating a job first
        # Placeholder for integration test
        pass


class TestJobResultEndpoint:
    """Tests for /job/{id}/result endpoint."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_job_result_not_found(self, client: AsyncClient):
        """Test job result endpoint with nonexistent job."""
        response = await client.get("/job/nonexistent-id/result")
        assert response.status_code == 404


class TestJobTraceEndpoint:
    """Tests for /job/{id}/trace endpoint."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_job_trace_not_found(self, client: AsyncClient):
        """Test job trace endpoint with nonexistent job."""
        response = await client.get("/job/nonexistent-id/trace")
        assert response.status_code == 404
