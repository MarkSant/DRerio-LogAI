"""
Extended unit tests for RecorderFactory in io/recorder_factory.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.io.recorder_factory import RecorderFactory
from zebtrack.settings import load_settings


class TestRecorderFactoryExtended:
    """Test RecorderFactory lazy-loading, attribute delegation, and context management."""

    @pytest.fixture
    def settings_obj(self):
        return load_settings()

    def test_init_lazy_state(self, settings_obj):
        factory = RecorderFactory(settings_obj=settings_obj)
        assert factory._settings_obj is settings_obj
        assert factory._recorder is None

    def test_get_recorder_instantiates_once(self, settings_obj):
        factory = RecorderFactory(settings_obj=settings_obj)
        rec1 = factory.get_recorder()
        assert rec1 is not None
        assert factory._recorder is rec1

        # Second call returns same instance (fast path)
        rec2 = factory.get_recorder()
        assert rec2 is rec1

    def test_recorder_property_delegates(self, settings_obj):
        factory = RecorderFactory(settings_obj=settings_obj)
        assert factory.recorder is factory._recorder

    def test_getattr_delegation(self, settings_obj):
        factory = RecorderFactory(settings_obj=settings_obj)
        mock_rec = MagicMock()
        mock_rec.record_frame = MagicMock(return_value=True)
        factory._recorder = mock_rec

        assert factory.record_frame() is True
        mock_rec.record_frame.assert_called_once()

    def test_context_manager_delegation(self, settings_obj):
        factory = RecorderFactory(settings_obj=settings_obj)
        mock_rec = MagicMock()
        mock_rec.__enter__.return_value = mock_rec
        mock_rec.__exit__.return_value = None
        factory._recorder = mock_rec

        with factory as rec:
            assert rec is mock_rec
        mock_rec.__enter__.assert_called_once()
        mock_rec.__exit__.assert_called_once()
