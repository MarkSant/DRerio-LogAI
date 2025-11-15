"""Unit tests for :mod:`zebtrack.orchestrators.video_processing_orchestrator`."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from zebtrack.orchestrators.video_processing_orchestrator import (
    VideoProcessingOrchestrator,
)
from zebtrack.ui.events import Events


class DummyEventBus:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def publish_event(self, event: str, payload: dict):
        self.events.append((event, payload))


class DummyView:
    def __init__(self):
        self.dialog_response: dict | None = None
        self.dialog_calls: list[dict] = []

    def show_pending_videos_dialog(self, **kwargs):
        self.dialog_calls.append(kwargs)
        return self.dialog_response


class DummyMainViewModel:
    def __init__(self):
        self.state_manager = MagicMock()
        self.ui_coordinator = MagicMock()
        self.project_manager = MagicMock()
        self.view = DummyView()
        self.ui_event_bus = DummyEventBus()
        self.cancel_event = MagicMock()
        self.detector = MagicMock()
        self.root = MagicMock()
        self.processing_coordinator = MagicMock()
        self.video_selection_service = MagicMock()
        self.video_validation_service = MagicMock()
        self.video_classification_service = MagicMock()
        self._publish_processing_mode = MagicMock()
        self._cancel_feedback_displayed = False
        self._determine_processing_intervals = MagicMock()
        self.apply_project_settings_to_batch = MagicMock()
        self._process_single_video = MagicMock()
        self.refresh_project_views = MagicMock()
        self.settings = SimpleNamespace(
            video_processing=SimpleNamespace(batch_retry_strategy="immediate")
        )


@pytest.fixture()
def orchestrator_setup():
    main_view_model = DummyMainViewModel()
    orchestrator = VideoProcessingOrchestrator(main_view_model)
    return orchestrator, main_view_model


def test_select_eligible_videos_skip_dialog_warns_about_arena_only(orchestrator_setup):
    orchestrator, main_view_model = orchestrator_setup
    ready_with_trajectory = [{"path": "ready_a.mp4"}]
    ready_with_zones = [{"path": "ready_b.mp4"}]
    arena_only = [{"path": f"arena_{idx}.mp4"} for idx in range(7)]

    eligible = orchestrator.select_eligible_videos(
        True,
        ready_with_trajectory,
        ready_with_zones,
        arena_only,
        without_arena=[],
    )

    assert eligible == ready_with_trajectory + ready_with_zones
    warning_events = [
        evt
        for evt in main_view_model.ui_event_bus.events
        if evt[0] == Events.UI_SHOW_WARNING
    ]
    assert len(warning_events) == 1
    assert "(+2)" in warning_events[0][1]["message"]


def test_select_eligible_videos_skip_dialog_returns_none_when_empty(orchestrator_setup):
    orchestrator, main_view_model = orchestrator_setup

    eligible = orchestrator.select_eligible_videos(
        True,
        ready_with_trajectory=[],
        ready_with_zones=[],
        arena_only=[],
        without_arena=[],
    )

    assert eligible is None
    info_events = [
        evt for evt in main_view_model.ui_event_bus.events if evt[0] == Events.UI_SHOW_INFO
    ]
    assert len(info_events) == 1


@pytest.mark.parametrize("include_arena_only, expected_count", [(True, 2), (False, 1)])
def test_select_eligible_videos_dialog_flow(orchestrator_setup, include_arena_only, expected_count):
    orchestrator, main_view_model = orchestrator_setup
    main_view_model.view.dialog_response = {
        "confirmed": True,
        "include_arena_only": include_arena_only,
    }
    ready_with_trajectory = [{"path": "ready_a.mp4"}]
    arena_only = [{"path": "arena_0.mp4"}]

    eligible = orchestrator.select_eligible_videos(
        False,
        ready_with_trajectory=ready_with_trajectory,
        ready_with_zones=[],
        arena_only=arena_only,
        without_arena=[],
    )

    assert len(eligible) == expected_count
    assert main_view_model.view.dialog_calls  # dialog shown


def test_select_eligible_videos_dialog_cancelled(orchestrator_setup):
    orchestrator, main_view_model = orchestrator_setup
    main_view_model.view.dialog_response = {"confirmed": False}

    result = orchestrator.select_eligible_videos(
        False,
        ready_with_trajectory=[{"path": "ready_a.mp4"}],
        ready_with_zones=[],
        arena_only=[],
        without_arena=[],
    )

    assert result is None
