"""Extended unit tests for core/project/project_manager.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.core.detection import ZoneData
from zebtrack.core.project.project_manager import (
    CONFIG_FILE_NAME,
    ProjectManager,
    _threadsafe,
)


class TestProjectManagerExtended2:
    """Test ProjectManager thread safety, constants, serialization, and template guards."""

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
