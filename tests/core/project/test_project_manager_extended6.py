"""Extended unit tests for core/project/project_manager.py (Part 6)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.core.project.project_manager import ProjectManager


class TestProjectManagerExtended6:
    """Test ProjectManager template saving, project type, and groups caching."""

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
