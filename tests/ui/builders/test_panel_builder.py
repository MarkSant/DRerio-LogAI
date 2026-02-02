"""
Tests for PanelBuilder builder.
"""

from tkinter import StringVar
from typing import cast
from unittest.mock import Mock, patch

from zebtrack.ui.builders.panel_builder import PanelBuilder


class TestPanelBuilder:
    """Tests for PanelBuilder methods."""

    @patch("zebtrack.ui.builders.panel_builder.ttk")
    def test_build_model_status_panel(self, mock_ttk):
        """Test building model status panel."""
        parent = Mock()
        mock_frame = Mock()
        mock_ttk.LabelFrame.return_value = mock_frame
        mock_label = Mock()
        mock_ttk.Label.return_value = mock_label

        status_vars = {
            "active_weight": cast(StringVar, Mock()),
            "openvino_status": cast(StringVar, Mock()),
            "hardware_status": cast(StringVar, Mock()),
        }

        frame = PanelBuilder.build_model_status_panel(parent, status_vars)

        mock_ttk.LabelFrame.assert_called_once()
        mock_frame.pack.assert_called_once()
        # Should create 3 labels
        assert mock_ttk.Label.call_count == 3
        assert frame == mock_frame

    @patch("zebtrack.ui.builders.panel_builder.StringVar")
    @patch("zebtrack.ui.builders.panel_builder.ttk")
    def test_create_zone_summary_cards(self, mock_ttk, mock_stringvar):
        """Test creating zone summary cards."""
        parent = Mock()
        mock_frame = Mock()
        mock_ttk.LabelFrame.return_value = mock_frame
        mock_ttk.Frame.return_value = mock_frame  # Reuse frame mock for simplicity
        mock_label = Mock()
        mock_ttk.Label.return_value = mock_label

        mock_var = Mock()
        mock_stringvar.return_value = mock_var

        helper_text = "Test helper text"

        frame, cards_data = PanelBuilder.create_zone_summary_cards(parent, helper_text)

        mock_ttk.LabelFrame.assert_called_once()
        assert frame == mock_frame

        # Check returned data structure
        assert "arena_missing" in cards_data
        assert "rois_missing" in cards_data
        assert "ready_for_processing" in cards_data
        assert cards_data["arena_missing"]["value"] == mock_var
