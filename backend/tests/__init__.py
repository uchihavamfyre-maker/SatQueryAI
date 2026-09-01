"""SatQuery AI Backend Tests

This package contains unit, integration, and end-to-end tests for the SatQuery AI backend.

Test Organization:
- test_api.py: FastAPI endpoint tests
- test_preprocessing.py: Image preprocessing pipeline tests
- test_agent.py: Agent orchestration tests
- test_fusion.py: Evidence fusion and confidence tests
- integration/: Full pipeline integration tests
- fixtures/: Test data and mock objects
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

__all__ = [
    "test_api",
    "test_preprocessing",
    "test_agent",
    "test_fusion",
]
