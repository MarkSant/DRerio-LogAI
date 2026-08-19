"""Extended unit tests for ProjectManager in core/project/project_manager.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.core.detection import ZoneData
from zebtrack.core.project.project_manager import CONFIG_FILE_NAME, ProjectManager, _threadsafe
from zebtrack.core.state_manager import StateManager


class TestProjectManagerExtended:
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


class TestProjectManagerExtended2:
    def test_constants(self):
        assert CONFIG_FILE_NAME == "project_config.json"

    def test_threadsafe_decorator(self):
        class Dummy:
            def __init__(self):
                self._lock = MagicMock()
                self.called = False

            @_threadsafe
            def safe_method(self, arg):
                self.called = True
                return arg * 2

        d = Dummy()
        res = d.safe_method(21)
        assert res == 42
        assert d.called is True
        d._lock.__enter__.assert_called_once()
        d._lock.__exit__.assert_called_once()

    def test_save_roi_template_no_project_loaded_raises(self):
        pm = ProjectManager()
        pm.project_path = None
        zone = ZoneData(polygon=[[0, 0], [10, 0], [10, 10], [0, 10]])

        with pytest.raises(ValueError, match="no project loaded"):
            pm.save_roi_template("MyTemplate", zone, save_location="project")

    def test_zone_data_serialization_delegation(self):
        pm = ProjectManager()
        zone = ZoneData(
            polygon=[[0, 0], [10, 0], [10, 10], [0, 10]],
            roi_polygons=[[[1, 1], [2, 2], [1, 2]]],
            roi_names=["R1"],
        )
        d = pm._zone_data_to_dict(zone)
        assert "polygon" in d
        assert "roi_names" in d

        restored = pm._zone_data_from_dict(d)
        assert list(restored.polygon) == [[0, 0], [10, 0], [10, 10], [0, 10]]
        assert "R1" in list(restored.roi_names)

    def test_get_aquarium_asset_flags_none_path(self):
        pm = ProjectManager()
        flags = pm.get_aquarium_asset_flags(None, 0)
        assert flags["has_arena"] is False
        assert flags["has_rois"] is False
        assert flags["has_trajectory"] is False
        assert flags["has_summary"] is False
        assert flags["has_complete_data"] is False

    def test_has_assets_none_path(self):
        pm = ProjectManager()
        pm.find_video_entry = MagicMock(return_value=None)  # type: ignore[method-assign]

        assert pm.has_arena_data(None) is False
        assert pm.has_roi_data(None) is False
        assert pm.has_trajectory_data(None) is False
        assert pm.has_summary_data(None) is False


class TestProjectManagerExtended6:
    def test_save_roi_template_no_project_raises(self):
        pm = ProjectManager()
        pm.project_path = None
        zone_data = MagicMock()

        with pytest.raises(ValueError, match="no project loaded"):
            pm.save_roi_template("Template1", zone_data, save_location="project")

    def test_project_manager_initial_cache_state(self):
        pm = ProjectManager()
        assert pm._groups_cache is None
        assert pm._groups_cache_valid is False

    def test_get_available_groups_cached(self):
        pm = ProjectManager()
        pm._groups_cache = ["Control", "Treated"]
        pm._groups_cache_valid = True

        assert pm.get_available_groups() == ["Control", "Treated"]

    def test_invalidate_groups_cache(self):
        pm = ProjectManager()
        pm._groups_cache = ["Control", "Treated"]
        pm._groups_cache_valid = True

        pm.invalidate_groups_cache()
        assert pm._groups_cache is None
        assert pm._groups_cache_valid is False

    def test_get_project_type(self):
        pm = ProjectManager()
        pm.project_data = {"project_type": "live"}
        assert pm.get_project_type() == "live"

        pm.project_data = {}
        assert pm.get_project_type() is None


class TestProjectManagerExtended7:
    def test_is_multi_aquarium_video_none(self):
        pm = ProjectManager()
        assert pm.is_multi_aquarium_video(None) is False

    def test_is_multi_aquarium_video_true(self):
        pm = ProjectManager()
        pm.zone_manager = MagicMock()
        pm.zone_manager.is_multi_aquarium_video.return_value = True
        assert pm.is_multi_aquarium_video("/videos/video1.mp4") is True

    def test_get_aquarium_count_none(self):
        pm = ProjectManager()
        assert pm.get_aquarium_count(None) == 1

    def test_get_aquarium_count_two(self):
        pm = ProjectManager()
        pm.zone_manager = MagicMock()
        pm.zone_manager.get_aquarium_count.return_value = 2
        assert pm.get_aquarium_count("/videos/video1.mp4") == 2

    def test_clear_multi_aquarium_zone_data_none(self):
        pm = ProjectManager()
        pm.clear_multi_aquarium_zone_data(None)

    def test_update_main_polygon_delegates_to_zone_manager(self):
        pm = ProjectManager()
        pm.zone_manager = MagicMock()
        pm.project_data = {"zones": {}}

        points = [(10, 10), (20, 20), (30, 10)]
        pm.update_main_polygon(points)
        pm.zone_manager.update_main_polygon.assert_called_once_with(
            pm.project_data, points, persist_callback=pm.save_project
        )


class TestProjectManagerExtended8:
    def test_register_multi_aquarium_outputs_empty(self):
        pm = ProjectManager()
        pm.project_data = {"outputs": {}}

        pm.register_multi_aquarium_outputs("/videos/video1.mp4", {})
        assert pm.project_data["outputs"] == {}

    def test_project_manager_initial_state(self):
        pm = ProjectManager()
        assert pm.project_path is None
        assert pm.project_data == {}
        assert pm.metadata is None
        assert pm._groups_cache is None
        assert pm._groups_cache_valid is False

    def test_list_roi_templates_delegates_to_asset_manager(self):
        pm = ProjectManager()
        pm.asset_manager = MagicMock()
        pm.asset_manager.list_roi_templates.return_value = [{"name": "Template1"}]

        res = pm.list_roi_templates(include_global=True)
        assert res == [{"name": "Template1"}]
        pm.asset_manager.list_roi_templates.assert_called_once_with(
            pm.project_data, include_global=True
        )

    def test_clear_multi_aquarium_zone_data_none_safe(self):
        pm = ProjectManager()
        # Passing None should return immediately without accessing zone_manager
        pm.clear_multi_aquarium_zone_data(None)


class TestProjectManagerExtended9:
    def test_update_main_polygon_delegates_to_zone_manager(self):
        pm = ProjectManager()
        pm.zone_manager = MagicMock()
        pm.project_data = {}

        points = [(0, 0), (10, 0), (10, 10), (0, 10)]
        pm.update_main_polygon(points)

        pm.zone_manager.update_main_polygon.assert_called_once_with(
            pm.project_data, points, persist_callback=pm.save_project
        )

    def test_metadata_manager_initialized(self):
        pm = ProjectManager()
        assert pm.metadata_manager is not None
        assert pm.lifecycle_manager is not None

    def test_get_aquarium_count_none_safe(self):
        pm = ProjectManager()
        assert pm.get_aquarium_count(None) == 1


class TestProjectManagerExtended10:
    def test_project_manager_get_zone_data_delegation(self):
        pm = ProjectManager()
        pm.zone_manager = MagicMock()
        pm.project_data = {"test": True}

        pm.get_zone_data(video_path="/path/vid.mp4", fallback_to_global=False)
        pm.zone_manager.get_zone_data.assert_called_once_with(
            pm.project_data, video_path="/path/vid.mp4", fallback_to_global=False
        )

    def test_project_manager_get_multi_aquarium_zone_data_delegation(self):
        pm = ProjectManager()
        pm.zone_manager = MagicMock()
        pm.project_data = {"test": True}

        pm.get_multi_aquarium_zone_data(video_path="/path/vid.mp4")
        pm.zone_manager.get_multi_aquarium_zone_data.assert_called_once_with(
            pm.project_data, "/path/vid.mp4"
        )

    def test_project_manager_config_file_name_constant(self):
        assert CONFIG_FILE_NAME == "project_config.json"

    def test_project_manager_default_project_data(self):
        pm = ProjectManager()
        assert isinstance(pm.project_data, dict)
        assert pm.asset_manager is not None
        assert pm.zone_manager is not None
