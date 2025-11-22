"""
Tests for ButtonFactory builder.
"""

from unittest.mock import Mock, patch

from zebtrack.ui.builders.button_factory import ButtonFactory

class TestButtonFactory:
    """Tests for ButtonFactory methods."""

    @patch("zebtrack.ui.builders.button_factory.ttk")
    def test_create_project_action_buttons(self, mock_ttk):
        """Test creating project action buttons."""
        parent = Mock()
        mock_frame = Mock()
        mock_ttk.LabelFrame.return_value = mock_frame
        mock_button = Mock()
        mock_ttk.Button.return_value = mock_button

        commands = {
            'calibration': Mock(),
            'single_analysis': Mock(),
            'create_project': Mock(),
            'open_project': Mock()
        }

        frame = ButtonFactory.create_project_action_buttons(parent, commands)

        mock_ttk.LabelFrame.assert_called_once()
        mock_frame.pack.assert_called_once()
        # Should create 4 buttons
        assert mock_ttk.Button.call_count == 4
        assert frame == mock_frame

    @patch("zebtrack.ui.builders.button_factory.ttk")
    def test_create_floating_drawing_buttons(self, mock_ttk):
        """Test creating floating drawing buttons."""
        parent = Mock()
        mock_frame = Mock()
        mock_ttk.Frame.return_value = mock_frame
        mock_button = Mock()
        mock_ttk.Button.return_value = mock_button

        commands = {
            'undo': Mock(),
            'redo': Mock()
        }

        frame = ButtonFactory.create_floating_drawing_buttons(parent, commands)

        mock_ttk.Frame.assert_called_once()
        # Should create 2 buttons
        assert mock_ttk.Button.call_count == 2
        assert frame == mock_frame
