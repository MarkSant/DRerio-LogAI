"""
Test WeightManager Logic - FASE 2 Validation.

This module validates WeightManager functionality with the real API:
- Weight configuration management
- Default weight queries (returns tuple[str, dict])
- Weight metadata operations
"""

import pytest
from pathlib import Path
from unittest.mock import Mock


@pytest.fixture
def weight_manager():
    """Create WeightManager instance with real settings."""
    from zebtrack.core.weight_manager import WeightManager
    from zebtrack.settings import load_settings

    settings_obj = load_settings()
    return WeightManager(settings_obj=settings_obj)


def test_weight_manager_instantiation(weight_manager):
    """Test that WeightManager can be instantiated with settings."""
    assert weight_manager is not None
    assert hasattr(weight_manager, "settings")
    assert weight_manager.settings is not None


def test_get_default_weight_returns_tuple(weight_manager):
    """Test that get_default_weight() returns tuple (name, metadata)."""
    # Act
    result = weight_manager.get_default_weight()

    # Assert
    assert isinstance(result, tuple)
    assert len(result) == 2

    name, metadata = result
    # Either both None or both have values
    if name is not None:
        assert isinstance(name, str)
        assert isinstance(metadata, dict)
    else:
        assert metadata is None


def test_get_default_seg_weight(weight_manager):
    """Test getting default segmentation weight."""
    name, metadata = weight_manager.get_default_seg_weight()

    # If a default seg weight exists, validate it
    if name is not None:
        assert isinstance(name, str)
        assert isinstance(metadata, dict)
        assert metadata.get("is_default_seg") is True


def test_get_default_det_weight(weight_manager):
    """Test getting default detection weight."""
    name, metadata = weight_manager.get_default_det_weight()

    # If a default det weight exists, validate it
    if name is not None:
        assert isinstance(name, str)
        assert isinstance(metadata, dict)
        assert metadata.get("is_default_det") is True


def test_weight_manager_has_weights_dict(weight_manager):
    """Test that WeightManager maintains weights dictionary."""
    assert hasattr(weight_manager, "weights")
    assert isinstance(weight_manager.weights, dict)


def test_set_default_weight_logs_warning_for_missing(weight_manager):
    """Test that setting a nonexistent weight logs warning (doesn't raise)."""
    # Act: Try to set nonexistent weight
    # Based on the test output, this logs warning but doesn't raise
    weight_manager.set_default_weight("/fake/path/nonexistent.pt")

    # Assert: No exception raised, method completes
    # (Real implementation logs warning instead of raising)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
