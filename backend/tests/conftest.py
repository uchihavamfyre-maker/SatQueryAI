"""Pytest configuration and fixtures for SatQuery AI tests."""
import asyncio
import os
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add backend to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_db():
    """Create a temporary in-memory SQLite database for testing."""
    from app.storage.schema import Base
    
    database_url = "sqlite:///:memory:"
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    yield SessionLocal
    
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
async def client():
    """Create an async test client for the FastAPI app."""
    from app.api.main import app
    
    async with AsyncClient(app=app, base_url="http://test") as test_client:
        yield test_client


@pytest.fixture
def sample_geotiff_path():
    """Return path to sample GeoTIFF for testing."""
    test_data_dir = Path(__file__).parent / "data"
    test_data_dir.mkdir(exist_ok=True)
    sample_file = test_data_dir / "sample.tif"
    
    if not sample_file.exists():
        pytest.skip("Sample GeoTIFF not found. Place test data in tests/data/")
    
    return sample_file


@pytest.fixture
def mock_controller(mocker):
    """Mock the agent controller for testing."""
    return mocker.MagicMock()


@pytest.fixture
def env_vars(monkeypatch):
    """Set up test environment variables."""
    test_env = {
        "API_KEY": "test-api-key-123",
        "CORS_ORIGINS": "http://localhost:3000",
        "MAX_IMAGE_BYTES": "104857600",  # 100 MB
        "DATA_DIR": "/tmp/satquery-test",
    }
    
    for key, value in test_env.items():
        monkeypatch.setenv(key, value)
    
    return test_env


# Markers for organizing tests
def pytest_configure(config):
    """Register pytest markers."""
    config.addinivalue_line("markers", "unit: mark test as a unit test")
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "e2e: mark test as an end-to-end test")
