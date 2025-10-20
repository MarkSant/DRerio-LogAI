from unittest.mock import MagicMock

import pytest


@pytest.fixture
def view_model():
    """Provides a mock MainViewModel for core tests."""
    return MagicMock()
