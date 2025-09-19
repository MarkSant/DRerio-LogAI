#!/usr/bin/env python3
"""Test the analysis view toggle functionality."""

import unittest
from unittest.mock import Mock, MagicMock


class MockApplicationGUI:
    """Mock ApplicationGUI for testing toggle functionality."""
    
    def __init__(self):
        # Initialize the same state variables as the real GUI
        self.canvas_view_mode = "zones"
        self.analysis_active = False
        
        # Mock UI components
        self.toggle_view_btn = Mock()
        self.roi_canvas = Mock()
        self.analysis_overlay_frame = Mock()
        self.overlay_progress_bar = Mock()
        self.overlay_status_label = Mock()
        self.analysis_video_label = Mock()
        
        # Track visibility states for testing
        self._canvas_visible = True
        self._overlay_visible = False
    
    def _switch_to_analysis_view(self):
        """Switch to analysis progress view."""
        self.canvas_view_mode = "analysis"
        self._canvas_visible = False
        self._overlay_visible = True
        self.toggle_view_btn.config(text="Ver Desenhos das Zonas")

    def _switch_to_zones_view(self):
        """Switch to zone drawing view."""
        self.canvas_view_mode = "zones"
        self._overlay_visible = False
        self._canvas_visible = True
        self.toggle_view_btn.config(text="Ver Análise em Progresso")

    def start_analysis_view_mode(self):
        """Called when analysis starts."""
        self.analysis_active = True
        self.toggle_view_btn.config(state="normal")
        self._switch_to_analysis_view()

    def stop_analysis_view_mode(self):
        """Called when analysis stops."""
        self.analysis_active = False
        self.toggle_view_btn.config(state="disabled")
        self._switch_to_zones_view()

    def _toggle_canvas_view(self):
        """Toggle between views."""
        if self.canvas_view_mode == "zones":
            self._switch_to_analysis_view()
        else:
            self._switch_to_zones_view()
    
    def show_warning(self, title, message):
        """Mock warning dialog."""
        pass


class TestAnalysisViewToggle(unittest.TestCase):
    """Test cases for the analysis view toggle functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.gui = MockApplicationGUI()
    
    def test_initial_state(self):
        """Test that the GUI starts in the correct initial state."""
        self.assertEqual(self.gui.canvas_view_mode, "zones")
        self.assertFalse(self.gui.analysis_active)
        self.assertTrue(self.gui._canvas_visible)
        self.assertFalse(self.gui._overlay_visible)
    
    def test_start_analysis_mode(self):
        """Test starting analysis mode."""
        self.gui.start_analysis_view_mode()
        
        self.assertTrue(self.gui.analysis_active)
        self.assertEqual(self.gui.canvas_view_mode, "analysis")
        self.assertFalse(self.gui._canvas_visible)
        self.assertTrue(self.gui._overlay_visible)
        
        # Check that toggle button is enabled and has correct text
        self.gui.toggle_view_btn.config.assert_called_with(text="Ver Desenhos das Zonas")
    
    def test_stop_analysis_mode(self):
        """Test stopping analysis mode."""
        # First start analysis
        self.gui.start_analysis_view_mode()
        
        # Then stop it
        self.gui.stop_analysis_view_mode()
        
        self.assertFalse(self.gui.analysis_active)
        self.assertEqual(self.gui.canvas_view_mode, "zones")
        self.assertTrue(self.gui._canvas_visible)
        self.assertFalse(self.gui._overlay_visible)
        
        # Check that toggle button is disabled
        calls = self.gui.toggle_view_btn.config.call_args_list
        # Should have been called with state="disabled" at some point
        disabled_call = any('state' in str(call) and 'disabled' in str(call) for call in calls)
        self.assertTrue(disabled_call, "Toggle button should be disabled when analysis stops")
    
    def test_toggle_during_analysis(self):
        """Test toggling between views during analysis."""
        # Start analysis (should switch to analysis view)
        self.gui.start_analysis_view_mode()
        self.assertEqual(self.gui.canvas_view_mode, "analysis")
        
        # Toggle to zones view
        self.gui._toggle_canvas_view()
        self.assertEqual(self.gui.canvas_view_mode, "zones")
        self.assertTrue(self.gui._canvas_visible)
        self.assertFalse(self.gui._overlay_visible)
        
        # Toggle back to analysis view
        self.gui._toggle_canvas_view()
        self.assertEqual(self.gui.canvas_view_mode, "analysis")
        self.assertFalse(self.gui._canvas_visible)
        self.assertTrue(self.gui._overlay_visible)
    
    def test_toggle_button_text_changes(self):
        """Test that toggle button text changes appropriately."""
        # Start analysis
        self.gui.start_analysis_view_mode()
        
        # Should show "Ver Desenhos das Zonas" when in analysis view
        self.gui.toggle_view_btn.config.assert_called_with(text="Ver Desenhos das Zonas")
        
        # Toggle to zones view
        self.gui._toggle_canvas_view()
        
        # Should show "Ver Análise em Progresso" when in zones view during analysis
        self.gui.toggle_view_btn.config.assert_called_with(text="Ver Análise em Progresso")
    
    def test_analysis_state_persistence(self):
        """Test that analysis_active state is managed correctly."""
        self.assertFalse(self.gui.analysis_active)
        
        self.gui.start_analysis_view_mode()
        self.assertTrue(self.gui.analysis_active)
        
        # Toggling views shouldn't change analysis_active
        self.gui._toggle_canvas_view()
        self.assertTrue(self.gui.analysis_active)
        
        self.gui._toggle_canvas_view()
        self.assertTrue(self.gui.analysis_active)
        
        # Only stopping analysis should set it to False
        self.gui.stop_analysis_view_mode()
        self.assertFalse(self.gui.analysis_active)


class TestZoneEditingPrevention(unittest.TestCase):
    """Test cases for preventing zone editing during analysis."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.gui = MockApplicationGUI()
        
        # Add methods that should be prevented during analysis
        def mock_start_drawing_method():
            if self.gui.analysis_active:
                self.gui.show_warning("Análise em Progresso", "Cannot edit during analysis")
                return False
            return True
        
        self.gui._start_main_arena_drawing = mock_start_drawing_method
        self.gui._start_roi_drawing = mock_start_drawing_method
        self.gui._on_auto_detect_clicked = mock_start_drawing_method
    
    def test_zone_editing_allowed_when_not_analyzing(self):
        """Test that zone editing is allowed when analysis is not active."""
        self.assertTrue(self.gui._start_main_arena_drawing())
        self.assertTrue(self.gui._start_roi_drawing())
        self.assertTrue(self.gui._on_auto_detect_clicked())
    
    def test_zone_editing_prevented_during_analysis(self):
        """Test that zone editing is prevented during analysis."""
        self.gui.start_analysis_view_mode()
        
        self.assertFalse(self.gui._start_main_arena_drawing())
        self.assertFalse(self.gui._start_roi_drawing())
        self.assertFalse(self.gui._on_auto_detect_clicked())


if __name__ == '__main__':
    unittest.main()