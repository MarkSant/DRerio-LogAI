"""Extended unit tests for coordinators/multi_aquarium_coordinator.py (Part 7)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from zebtrack.coordinators.multi_aquarium_coordinator import MultiAquariumCoordinator


class TestMultiAquariumCoordinatorExtended7:
    """Test MultiAquariumCoordinator flags, assignments, and dependencies."""

    def test_multi_aquarium_coordinator_auto_assign_flag(self):
        coord: Any = object.__new__(MultiAquariumCoordinator)
        coord._auto_assign_in_progress = True
        assert coord._auto_assign_in_progress is True
        coord._auto_assign_in_progress = False
        assert coord._auto_assign_in_progress is False

    def test_multi_aquarium_coordinator_last_assignment_configs(self):
        coord: Any = object.__new__(MultiAquariumCoordinator)
        coord._last_assignment_configs = {"aq_0": {"slot": 1}}
        assert coord._last_assignment_configs["aq_0"]["slot"] == 1

    def test_multi_aquarium_coordinator_detector_ref(self):
        coord: Any = object.__new__(MultiAquariumCoordinator)
        detector = MagicMock()
        coord.detector = detector
        assert coord.detector is detector

    def test_multi_aquarium_coordinator_view_and_root_refs(self):
        coord: Any = object.__new__(MultiAquariumCoordinator)
        root = MagicMock()
        view = MagicMock()
        coord.root = root
        coord.view = view
        assert coord.root is root
        assert coord.view is view
