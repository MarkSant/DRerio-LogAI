"""Unit tests for :mod:`zebtrack.orchestrators.zone_arena_orchestrator`."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.core.detector import ZoneData
from zebtrack.orchestrators.zone_arena_orchestrator import ZoneArenaOrchestrator
from zebtrack.ui.events import Events


class DummyEventBus:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def publish_event(self, event: str, payload: dict):
        self.events.append((event, payload))


class DummyProjectManager:
    def __init__(self):
        self.project_path: str | None = None
        self.project_data: dict = {}
        self.saved_zone_data = None
        self.updated_polygons: list[list] = []

    def update_main_polygon(self, points):
        self.updated_polygons.append(points)

    def save_zone_data(self, zone_data, persist=True):
        self.saved_zone_data = zone_data
        return zone_data

    def get_zone_data(self):
        return self.saved_zone_data


class DummyMainViewModel:
    def __init__(self):
        self.view = MagicMock()
        self.project_manager = DummyProjectManager()
        self.ui_event_bus = DummyEventBus()
        self.setup_detector_zones = MagicMock()
        self.update_main_arena = MagicMock()


@pytest.fixture()
def orchestrator_setup():
    vm = DummyMainViewModel()
    orch = ZoneArenaOrchestrator(vm)
    return orch, vm


def test_set_main_arena_polygon_creates_temp_project_for_single_video(orchestrator_setup):
    orchestrator, vm = orchestrator_setup
    vm.view.pending_single_video_path = "C:/tmp/video.mp4"

    assert orchestrator.set_main_arena_polygon([[0, 0], [10, 0], [10, 10]]) is True
    assert vm.project_manager.project_path is not None
    assert vm.project_manager.project_data["project_type"] == "single_video"
    redraw_events = [evt for evt in vm.ui_event_bus.events if evt[0] == Events.UI_REDRAW_ZONES]
    assert redraw_events, "expected redraw event"


def test_set_main_arena_polygon_rejects_invalid_points(orchestrator_setup):
    orchestrator, vm = orchestrator_setup
    assert orchestrator.set_main_arena_polygon([]) is False
    assert orchestrator.set_main_arena_polygon([[0, 0]]) is False
    assert vm.project_manager.updated_polygons == []


def test_add_roi_polygon_validates_project_presence(orchestrator_setup):
    orchestrator, vm = orchestrator_setup
    result = orchestrator.add_roi_polygon([[0, 0], [1, 0], [1, 1]], "roi", (255, 0, 0))

    assert result is False
    assert vm.project_manager.saved_zone_data is None


def test_add_roi_polygon_adjusts_points_and_saves(orchestrator_setup):
    orchestrator, vm = orchestrator_setup
    vm.project_manager.project_path = "project"
    zone_data = ZoneData()
    zone_data.polygon = [[0, 0], [10, 0], [10, 10], [0, 10]]
    zone_data.roi_polygons = []
    zone_data.roi_names = []
    zone_data.roi_colors = []
    vm.project_manager.get_zone_data = MagicMock(return_value=zone_data)

    roi_points = [[-1, -1], [5, 5], [6, 4]]
    result = orchestrator.add_roi_polygon(roi_points, "ROI 1", (255, 0, 0))

    assert result is True
    assert zone_data.roi_names == ["ROI 1"]
    assert vm.setup_detector_zones.called


def test_add_roi_polygon_prompts_on_overlap(orchestrator_setup):
    orchestrator, vm = orchestrator_setup
    vm.project_manager.project_path = "project"
    zone_data = ZoneData()
    zone_data.polygon = [[0, 0], [10, 0], [10, 10], [0, 10]]
    zone_data.roi_polygons = [[[2, 2], [4, 2], [4, 4], [2, 4]]]
    zone_data.roi_names = ["Base"]
    zone_data.roi_colors = [(255, 255, 255)]
    vm.project_manager.get_zone_data = MagicMock(return_value=zone_data)
    vm.view.ask_ok_cancel.return_value = False

    roi_points = [[3, 3], [5, 3], [5, 5], [3, 5]]
    result = orchestrator.add_roi_polygon(roi_points, "ROI 2", (0, 255, 0))

    assert result is False
    assert len(zone_data.roi_polygons) == 1
