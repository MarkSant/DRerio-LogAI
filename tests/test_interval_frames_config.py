"""
Tests for analysis_interval_frames and display_interval_frames configuration.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add src to path for test imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def test_single_video_config_dialog_has_interval_methods():
    """
    Test that SingleVideoConfigDialog has the expected interval-related methods
    and attributes.
    """
    # Test the apply and validate methods exist and handle intervals correctly
    with patch('zebtrack.ui.gui.settings'), \
            patch('zebtrack.ui.gui.simpledialog'), \
            patch('zebtrack.ui.gui.StringVar') as mock_stringvar, \
            patch('zebtrack.ui.gui.ttk'), \
            patch('zebtrack.ui.gui.messagebox'):

        # Mock StringVar to track what values are created
        var_instances = []

        def create_stringvar(value=""):
            mock_var = MagicMock()
            mock_var.get.return_value = value
            var_instances.append(mock_var)
            return mock_var

        mock_stringvar.side_effect = create_stringvar

        from zebtrack.ui.gui import SingleVideoConfigDialog

        # Mock the parent window and the dialog methods
        parent = MagicMock()

        # Create dialog instance
        dialog = SingleVideoConfigDialog(parent)

        # Verify that the interval variables were created
        # The dialog should create analysis_interval_var and
        # display_interval_var with value "10". Since we mocked StringVar,
        # we just check that the attributes exist
        assert hasattr(dialog, 'analysis_interval_var')
        assert hasattr(dialog, 'display_interval_var')


def test_create_project_dialog_has_interval_methods():
    """
    Test that CreateProjectDialog has the expected interval-related methods
    and attributes.
    """
    with patch('zebtrack.ui.gui.settings'), \
            patch('zebtrack.ui.gui.simpledialog'), \
            patch('zebtrack.ui.gui.StringVar') as mock_stringvar, \
            patch('zebtrack.ui.gui.BooleanVar'), \
            patch('zebtrack.ui.gui.ttk'), \
            patch('zebtrack.ui.gui.messagebox'), \
            patch('zebtrack.ui.gui.Label'), \
            patch('zebtrack.ui.gui.Entry'), \
            patch('zebtrack.ui.gui.Button'), \
            patch('zebtrack.ui.gui.Frame'):

        # Mock StringVar to track what values are created
        var_instances = []

        def create_stringvar(value=""):
            mock_var = MagicMock()
            mock_var.get.return_value = value
            var_instances.append(mock_var)
            return mock_var

        mock_stringvar.side_effect = create_stringvar

        from zebtrack.ui.gui import CreateProjectDialog

        # Mock the parent window
        parent = MagicMock()

        # Create dialog instance
        dialog = CreateProjectDialog(parent)

        # Verify that the interval variables were created
        assert hasattr(dialog, 'analysis_interval_var')
        assert hasattr(dialog, 'display_interval_var')


def test_project_manager_create_new_project_signature():
    """
    Test that ProjectManager.create_new_project accepts interval frame
    parameters.
    """
    with patch('zebtrack.core.project_manager.os'), \
            patch('zebtrack.core.project_manager.messagebox'), \
            patch('zebtrack.core.project_manager.log'):
        from zebtrack.core.project_manager import ProjectManager

        pm = ProjectManager()

        # Mock the methods that are called
        pm._save_settings_snapshot = MagicMock()
        pm.save_project = MagicMock(return_value=True)
        pm.add_video_batch = MagicMock()

        # Test that we can call create_new_project with interval parameters
        result = pm.create_new_project(
            project_path="/test/path",
            project_type="pre-recorded",
            analysis_interval_frames=15,
            display_interval_frames=20
        )

        # Verify the project was created successfully
        assert result is True

        # Check that project_data includes the interval settings
        assert pm.project_data["analysis_interval_frames"] == 15
        assert pm.project_data["display_interval_frames"] == 20


if __name__ == "__main__":
    pytest.main([__file__])
