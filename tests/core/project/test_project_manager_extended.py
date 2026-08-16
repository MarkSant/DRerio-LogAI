"""Extended unit tests for ProjectManager in core/project/project_manager.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.core.detection import ZoneData
from zebtrack.core.project.project_manager import CONFIG_FILE_NAME, ProjectManager, _threadsafe
from zebtrack.core.state_manager import StateManager


class TestProjectManagerExtended:
    """Test ProjectManager initialization, thread safety, and zone serialization."""

    def test_config_file_name_constant(self):
        assert CONFIG_FILE_NAME == "project_config.json"

    def test_initialization_with_dependencies(self):
        state_mgr = StateManager()
        settings_mock = MagicMock()
        pm = ProjectManager(state_manager=state_mgr, settings_obj=settings_mock)

        assert pm.state_manager is state_mgr
        assert pm.settings is settings_mock
        assert pm.project_path is None
        assert pm.project_data == {}
        assert pm._groups_cache_valid is False

    def test_threadsafe_decorator(self):
        class Dummy:
            def __init__(self):
                import threading

                self._lock = threading.RLock()
                self.calls = 0

            @_threadsafe
            def increment(self):
                self.calls += 1
                return self.calls

        d = Dummy()
        assert d.increment() == 1
        assert d.increment() == 2

    def test_save_roi_template_without_project_raises(self):
        pm = ProjectManager()
        pm.project_path = None
        zone_data = ZoneData(polygon=[[0, 0], [100, 0], [100, 100], [0, 100]])

        with pytest.raises(ValueError, match="Cannot save the template into the current project"):
            pm.save_roi_template("my_template", zone_data, save_location="project")

    def test_zone_data_to_and_from_dict_delegation(self):
        pm = ProjectManager()
        zone_data = ZoneData(
            polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
            roi_polygons=[[[10, 10], [20, 10], [20, 20], [10, 20]]],
            roi_names=["zone1"],
            roi_colors=[(255, 0, 0)],
        )
        serialized = pm._zone_data_to_dict(zone_data)
        assert "polygon" in serialized or "arena" in serialized or "roi_polygons" in serialized

        restored = pm._zone_data_from_dict(serialized)
        assert restored is not None
        assert len(restored.polygon) == 4
        assert "zone1" in restored.roi_names
