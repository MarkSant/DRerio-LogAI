import pytest
from unittest.mock import MagicMock

@pytest.fixture
def view_model():
    """Provides a mock MainViewModel for core tests."""
    return MagicMock()
