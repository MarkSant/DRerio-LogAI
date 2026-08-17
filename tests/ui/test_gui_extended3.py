"""Extended unit tests for ui/gui.py (Part 3)."""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.ui.gui import ApplicationGUI


class TestGuiExtended3:
    """Test ApplicationGUI frame references and initial state."""

    def test_gui_initial_frames_none(self):
        gui = object.__new__(ApplicationGUI)
        gui.notebook = None
        gui.welcome_frame = None
        gui.main_controls_frame = None
        gui.status_frame = None

        assert gui.notebook is None
        assert gui.welcome_frame is None
        assert gui.main_controls_frame is None
        assert gui.status_frame is None

    def test_gui_project_view_manager_alias(self):
        gui = object.__new__(ApplicationGUI)
        mock_tree = MagicMock()
        gui.video_selector_manager = mock_tree
        gui.project_view_manager = gui.video_selector_manager

        assert gui.project_view_manager is mock_tree
