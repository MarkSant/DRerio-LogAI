"""
Extended unit tests for RecordingService.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from zebtrack.core.recording.recording_service import RecordingService


class TestRecordingServiceExtended:
    """Test RecordingService controller accessors and UI callbacks."""

    def test_recorder_property_controller_none_raises(self):
        service = RecordingService(
            state_manager=MagicMock(),
            project_manager=MagicMock(),
            controller=None,
        )
        with pytest.raises(RuntimeError, match="controller not yet set"):
            _ = service.recorder

    def test_arduino_manager_property_controller_none_raises(self):
        service = RecordingService(
            state_manager=MagicMock(),
            project_manager=MagicMock(),
            controller=None,
        )
        with pytest.raises(RuntimeError, match="controller not yet set"):
            _ = service.arduino_manager

    def test_properties_with_controller(self):
        mock_controller = MagicMock()
        mock_controller.recorder = "mock_recorder"
        mock_controller.arduino_manager = "mock_arduino"

        service = RecordingService(
            state_manager=MagicMock(),
            project_manager=MagicMock(),
            controller=mock_controller,
        )
        assert service.recorder == "mock_recorder"
        assert service.arduino_manager == "mock_arduino"

    def test_set_ui_callbacks(self):
        service = RecordingService(
            state_manager=MagicMock(),
            project_manager=MagicMock(),
        )
        cb: dict[str, Callable[..., Any]] = {"show_error": MagicMock()}
        service.set_ui_callbacks(cb)
        assert service._ui_callbacks == cb
