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
    Test that SingleVideoConfigDialog creates interval-related variables.
    """
    # Read the source code to verify the dialog creates the interval variables
    import os
    gui_file = os.path.join(
        os.path.dirname(__file__), '..', 'src', 'zebtrack', 'ui', 'gui.py'
    )
    with open(gui_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the SingleVideoConfigDialog.body method
    assert 'class SingleVideoConfigDialog' in content
    assert 'self.analysis_interval_var = StringVar(value="10")' in content
    assert 'self.display_interval_var = StringVar(value="10")' in content


def test_create_project_dialog_has_interval_methods():
    """
    Test that CreateProjectDialog creates interval-related variables.
    """
    # Read the source code to verify the dialog creates the interval variables
    import os
    gui_file = os.path.join(
        os.path.dirname(__file__), '..', 'src', 'zebtrack', 'ui', 'gui.py'
    )
    with open(gui_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the CreateProjectDialog class and verify it has interval variables
    assert 'class CreateProjectDialog' in content
    # The dialog should initialize these variables in its __init__ or body
    # method
    parts = content.split('class CreateProjectDialog')[1].split('class ')
    create_proj_section = parts[0]
    assert 'analysis_interval_var' in create_proj_section
    assert 'display_interval_var' in create_proj_section


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
            video_files=["/test/video1.mp4", "/test/video2.mp4"],
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
