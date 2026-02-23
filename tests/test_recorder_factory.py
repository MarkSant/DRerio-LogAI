"""Tests for RecorderFactory lazy-loading functionality."""

import sys

import pytest

from zebtrack.core.detection import ZoneData
from zebtrack.io.recorder_factory import RecorderFactory
from zebtrack.settings import load_settings


@pytest.fixture
def settings_obj():
    """Create a Settings instance for testing."""
    return load_settings()


@pytest.fixture
def mock_zones():
    """Create a ZoneData instance for testing."""
    return ZoneData()


def test_recorder_factory_creation(settings_obj):
    """Test that RecorderFactory can be created without loading pandas."""
    # Track modules before creation
    pandas_loaded_before = "pandas" in sys.modules

    # Create factory
    factory = RecorderFactory(settings_obj)

    # Pandas should not be loaded yet
    pandas_loaded_after = "pandas" in sys.modules

    assert factory._recorder is None
    # If pandas wasn't loaded before, it shouldn't be loaded now
    if not pandas_loaded_before:
        assert not pandas_loaded_after, "Pandas should not be loaded during factory creation"


def test_lazy_initialization(settings_obj):
    """Test that Recorder is only created on first access."""
    factory = RecorderFactory(settings_obj)

    # Not initialized yet
    assert factory._recorder is None

    # Access via get_recorder()
    recorder = factory.get_recorder()

    # Now initialized
    assert factory._recorder is not None
    assert recorder is factory._recorder


def test_get_recorder_returns_same_instance(settings_obj):
    """Test that multiple calls to get_recorder() return the same instance."""
    factory = RecorderFactory(settings_obj)

    recorder1 = factory.get_recorder()
    recorder2 = factory.get_recorder()

    assert recorder1 is recorder2


def test_property_access(settings_obj):
    """Test that .recorder property works correctly."""
    factory = RecorderFactory(settings_obj)

    # Access via property
    recorder = factory.recorder

    assert factory._recorder is not None
    assert recorder is factory._recorder

    # Property returns same instance
    assert factory.recorder is recorder


def test_attribute_delegation(settings_obj):
    """Test that attributes are delegated to underlying Recorder."""
    factory = RecorderFactory(settings_obj)

    # Access an attribute that exists on Recorder
    # This should trigger lazy initialization
    is_recording = factory.is_recording

    # Factory should be initialized now
    assert factory._recorder is not None

    # Should get the attribute from the actual Recorder
    assert isinstance(is_recording, bool)


def test_method_delegation(settings_obj):
    """Test that methods are delegated to underlying Recorder."""
    factory = RecorderFactory(settings_obj)

    # Call a method that exists on Recorder
    # start_recording requires parameters, so just check the method exists
    assert hasattr(factory, "start_recording")
    assert callable(factory.start_recording)


def test_context_manager_support(settings_obj, mock_zones, tmp_path):
    """Test that RecorderFactory supports context manager protocol."""
    factory = RecorderFactory(settings_obj)

    # Use as context manager
    with factory as recorder:
        assert recorder is not None
        assert factory._recorder is not None

        # Start recording with minimal setup
        output_folder = str(tmp_path / "test_context")
        recorder.start_recording(
            output_folder=output_folder,
            frame_width=640,
            frame_height=480,
            zones=mock_zones,
        )

        assert recorder.is_recording is True

    # After exiting context, recording should be stopped
    assert factory._recorder.is_recording is False


def test_context_manager_cleanup_on_exception(settings_obj, mock_zones, tmp_path):
    """Test that context manager properly cleans up on exception."""
    factory = RecorderFactory(settings_obj)

    try:
        with factory as recorder:
            # Start recording
            output_folder = str(tmp_path / "test_exception")
            recorder.start_recording(
                output_folder=output_folder,
                frame_width=640,
                frame_height=480,
                zones=mock_zones,
            )

            # Raise an exception
            raise ValueError("Test exception")
    except ValueError:
        pass  # Expected

    # Recording should be cleaned up even after exception
    assert factory._recorder is not None
    assert factory._recorder.is_recording is False


def test_settings_injection(settings_obj):
    """Test that settings are properly injected into Recorder."""
    factory = RecorderFactory(settings_obj)
    recorder = factory.get_recorder()

    # Recorder should have been initialized with settings
    # It extracts values from settings but doesn't store the object itself
    assert hasattr(recorder, "_flush_interval_seconds")
    assert hasattr(recorder, "_flush_row_threshold")


def test_multiple_factories_independent():
    """Test that multiple RecorderFactory instances are independent."""
    settings1 = load_settings()
    settings2 = load_settings()

    factory1 = RecorderFactory(settings1)
    factory2 = RecorderFactory(settings2)

    recorder1 = factory1.get_recorder()
    recorder2 = factory2.get_recorder()

    # Each factory should have its own recorder instance
    assert recorder1 is not recorder2
    assert factory1._recorder is not factory2._recorder


def test_concurrent_initialization(settings_obj):
    """Test that concurrent calls to get_recorder don't create duplicate recorders.

    Verifies thread-safety of the double-checked locking pattern.
    """
    import threading

    factory = RecorderFactory(settings_obj)
    recorders = []

    def get_and_store():
        recorders.append(factory.get_recorder())

    # Create multiple threads that will all try to initialize simultaneously
    threads = [threading.Thread(target=get_and_store) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All threads should get the same instance (thread-safe singleton per factory)
    assert len(recorders) == 10
    assert all(r is recorders[0] for r in recorders), (
        "All threads should get same Recorder instance"
    )
