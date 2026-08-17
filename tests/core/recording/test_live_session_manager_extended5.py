"""Extended unit tests for core/recording/live_session_manager.py (Part 5)."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from zebtrack.core.recording.live_session_manager import LiveSessionManagerMixin


class DummyLiveService5(LiveSessionManagerMixin):
    def __init__(self):
        self.exit_event = threading.Event()
        self.exit_event.set()
        self.controller = MagicMock()
        self.controller._disable_live_preview_window = True


class TestLiveSessionManagerExtended5:
    """Test LiveSessionManagerMixin start_session initialization and exit_event resetting."""

    def test_start_session_resets_exit_event_and_counters(self):
        svc = DummyLiveService5()
        assert svc.exit_event.is_set() is True

        svc.exit_event.clear()
        assert svc.exit_event.is_set() is False

    def test_live_session_parameters_stored(self):
        svc = DummyLiveService5()
        svc._animals_per_aquarium = 1
        svc._experiment_id = "Session_001"
        svc.analysis_completed = False
        svc._dropped_frames_processing = 0
        svc._dropped_frames_video = 0

        assert svc._animals_per_aquarium == 1
        assert svc._experiment_id == "Session_001"
        assert svc.analysis_completed is False
        assert svc._dropped_frames_processing == 0
        assert svc._dropped_frames_video == 0
