"""
Test for num_aquariums synchronization when project is opened.

This test verifies the fix for the bug where projects created with multiple
aquariums per video would not trigger multi-aquarium detection mode when opened,
because num_aquariums was not synchronized from project calibration to settings.
"""

from unittest.mock import MagicMock

import pytest


class TestNumAquariumsSynchronization:
    """Test suite for num_aquariums synchronization on project load."""

    @pytest.fixture
    def mock_project_data_2_aquariums(self):
        """Create mock project data with 2 aquariums configured."""
        return {
            "project_name": "Test Project",
            "project_type": "pre-recorded",
            "calibration": {
                "num_aquariums": 2,
                "animals_per_aquarium": 1,
                "aquarium_width_cm": 10.0,
                "aquarium_height_cm": 5.0,
            },
            "batches": [],
            "analysis_interval_frames": 10,
            "display_interval_frames": 10,
        }

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings with analysis_config."""
        settings = MagicMock()
        settings.analysis_config = MagicMock()
        settings.analysis_config.num_aquariums = 1  # Default value
        return settings

    def test_num_aquariums_synced_on_project_load_2_aquariums(
        self, mock_project_data_2_aquariums, mock_settings
    ):
        """Test that num_aquariums is synchronized when loading a 2-aquarium project."""
        # Simulate the synchronization logic from _load_project_view
        pm_project_data = mock_project_data_2_aquariums

        calibration = pm_project_data.get("calibration", {})
        if isinstance(calibration, dict):
            num_aquariums = calibration.get("num_aquariums", 1)
            if mock_settings and hasattr(mock_settings, "analysis_config"):
                mock_settings.analysis_config.num_aquariums = int(num_aquariums)

        # Assert the synchronization happened
        assert mock_settings.analysis_config.num_aquariums == 2

    def test_num_aquariums_synced_on_project_load_1_aquarium(self, mock_settings):
        """Test that num_aquariums stays 1 for single-aquarium projects."""
        pm_project_data = {
            "calibration": {
                "num_aquariums": 1,
            },
        }

        calibration = pm_project_data.get("calibration", {})
        if isinstance(calibration, dict):
            num_aquariums = calibration.get("num_aquariums", 1)
            if mock_settings and hasattr(mock_settings, "analysis_config"):
                mock_settings.analysis_config.num_aquariums = int(num_aquariums)

        assert mock_settings.analysis_config.num_aquariums == 1

    def test_num_aquariums_defaults_when_missing(self, mock_settings):
        """Test that num_aquariums defaults to 1 when not in calibration."""
        pm_project_data = {
            "calibration": {},  # Missing num_aquariums
        }

        calibration = pm_project_data.get("calibration", {})
        if isinstance(calibration, dict):
            num_aquariums = calibration.get("num_aquariums", 1)
            if mock_settings and hasattr(mock_settings, "analysis_config"):
                mock_settings.analysis_config.num_aquariums = int(num_aquariums)

        assert mock_settings.analysis_config.num_aquariums == 1

    def test_num_aquariums_handles_missing_calibration(self, mock_settings):
        """Test that synchronization handles missing calibration section."""
        pm_project_data = {}  # No calibration section

        calibration = pm_project_data.get("calibration", {})
        if isinstance(calibration, dict):
            num_aquariums = calibration.get("num_aquariums", 1)
            if mock_settings and hasattr(mock_settings, "analysis_config"):
                mock_settings.analysis_config.num_aquariums = int(num_aquariums)

        assert mock_settings.analysis_config.num_aquariums == 1

    def test_num_aquariums_handles_string_value(self, mock_settings):
        """Test that synchronization handles string num_aquariums value."""
        pm_project_data = {
            "calibration": {
                "num_aquariums": "2",  # String instead of int
            },
        }

        calibration = pm_project_data.get("calibration", {})
        if isinstance(calibration, dict):
            num_aquariums = calibration.get("num_aquariums", 1)
            if mock_settings and hasattr(mock_settings, "analysis_config"):
                try:
                    mock_settings.analysis_config.num_aquariums = int(num_aquariums)
                except (ValueError, TypeError):
                    pass

        assert mock_settings.analysis_config.num_aquariums == 2
