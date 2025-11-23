"""
Tests for ZoneControlBuilder.
"""

from unittest.mock import Mock, patch

import pytest

from zebtrack.ui.builders.zone_control_builder import ZoneControlBuilder


class TestZoneControlBuilder:
    """Tests for ZoneControlBuilder methods."""

    @pytest.fixture
    def mock_gui(self):
        gui = Mock()
        gui.zone_controls_frame = Mock()
        gui.single_analysis_options_frame = None
        gui.roi_choice_var = None
        gui.analysis_interval_var = Mock()
        gui.display_interval_var = Mock()
        gui.stabilization_frames_var = Mock()
        gui.video_search_var = None
        gui.roi_template_var = Mock()
        gui.roi_inclusion_rule_var = Mock()
        gui.roi_buffer_radius_var = Mock()
        gui.roi_overlap_ratio_var = Mock()
        gui.zone_listbox = None
        gui.video_selector_tree = None
        return gui

    @patch("zebtrack.ui.builders.zone_control_builder.create_scrollbar")
    @patch("zebtrack.ui.builders.zone_control_builder.ttk")
    @patch("zebtrack.ui.builders.zone_control_builder.StringVar")
    def test_create_zone_control_widgets(self, mock_stringvar, mock_ttk, mock_create_scrollbar, mock_gui):
        """Test creating all zone control widgets."""
        # Setup mocks
        mock_frame = Mock()
        mock_ttk.LabelFrame.return_value = mock_frame
        mock_ttk.Frame.return_value = mock_frame
        mock_entry = Mock()
        mock_ttk.Entry.return_value = mock_entry
        from unittest.mock import MagicMock
        mock_button = MagicMock()
        mock_button.__getitem__.return_value = "disabled"
        mock_ttk.Button.return_value = mock_button
        mock_label = Mock()
        mock_ttk.Label.return_value = mock_label
        mock_combobox = Mock()
        mock_ttk.Combobox.return_value = mock_combobox
        mock_radio = Mock()
        mock_ttk.Radiobutton.return_value = mock_radio
        mock_tree = Mock()
        mock_ttk.Treeview.return_value = mock_tree
        mock_scrollbar = Mock()
        mock_ttk.Scrollbar.return_value = mock_scrollbar
        mock_create_scrollbar.return_value = mock_scrollbar

        mock_stringvar.return_value = Mock()

        builder = ZoneControlBuilder(mock_gui)
        builder.create_zone_control_widgets()

        # Verify calls
        mock_gui._create_zone_summary_cards_section.assert_called_once()

        # Verify major sections created (by checking LabelFrame creation)
        # We expect LabelFrames for: Drawing Actions, Single Analysis, Templates, Video Selector, Zone List, Inclusion Rule
        assert mock_ttk.LabelFrame.call_count >= 6

        # Verify variables initialized
        assert mock_gui.roi_choice_var is not None
        assert mock_gui.video_search_var is not None

        # Verify population calls
        mock_gui._refresh_roi_templates.assert_called_once()
        # mock_gui._populate_video_selector_tree.assert_called_once() # Replaced by event
        mock_gui._on_roi_rule_change.assert_called_once()
