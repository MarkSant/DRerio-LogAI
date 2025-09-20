#!/usr/bin/env python3
"""
Test script for GUI zone configuration regression fixes.
"""

import pytest
import os


def test_gui_zone_config_structure():
    """Test that the GUI zone configuration structure has been correctly fixed."""
    gui_file_path = os.path.join(os.path.dirname(__file__), "..", "src", "zebtrack", "ui", "gui.py")
    
    with open(gui_file_path, 'r') as f:
        gui_code = f.read()
    
    # Test that viz_frame is now self.viz_frame
    assert 'self.viz_frame = ttk.Frame(' in gui_code, "viz_frame should be stored as self.viz_frame"
    
    # Test that analysis overlay is created in _create_roi_analysis_tab, not in _on_canvas_configure
    create_roi_section = gui_code.split('def _create_roi_analysis_tab(self):')[1].split('def _on_canvas_configure(self, event=None):')[0]
    assert 'self.analysis_overlay_frame = Frame(' in create_roi_section, "analysis_overlay_frame should be created in _create_roi_analysis_tab"
    
    # Test that _on_canvas_configure is clean and only handles resizing
    on_canvas_section = gui_code.split('def _on_canvas_configure(self, event=None):')[1].split('def _create_zone_control_widgets(self):')[0]
    assert 'Drawing Actions' not in on_canvas_section, "_on_canvas_configure should not create Drawing Actions"
    assert 'Zone List' not in on_canvas_section, "_on_canvas_configure should not create Zone List"
    assert 'analysis_overlay_frame' not in on_canvas_section, "_on_canvas_configure should not create analysis_overlay_frame"
    
    # Test that _create_zone_control_widgets method exists and contains all UI elements
    assert 'def _create_zone_control_widgets(self):' in gui_code, "_create_zone_control_widgets method should exist"
    zone_widgets_section = gui_code.split('def _create_zone_control_widgets(self):')[1].split('def _create_scrollable_controls_frame(self, parent):')[0]
    assert 'Drawing Actions' in zone_widgets_section, "_create_zone_control_widgets should create Drawing Actions"
    assert 'Zone List' in zone_widgets_section, "_create_zone_control_widgets should create Zone List" 
    assert 'Properties Panel' in zone_widgets_section, "_create_zone_control_widgets should create Properties Panel"
    assert 'ROI Inclusion Rule Panel' in zone_widgets_section, "_create_zone_control_widgets should create ROI Inclusion Rule Panel"


def test_gui_attribute_guards():
    """Test that proper attribute guards have been added."""
    gui_file_path = os.path.join(os.path.dirname(__file__), "..", "src", "zebtrack", "ui", "gui.py")
    
    with open(gui_file_path, 'r') as f:
        gui_code = f.read()
    
    # Test that update_zone_listbox has guards
    update_zone_section = gui_code.split('def update_zone_listbox(self):')[1].split('def redraw_zones_from_project_data(self):')[0]
    assert "hasattr(self, 'zone_listbox')" in update_zone_section, "update_zone_listbox should have zone_listbox guard"


def test_treeview_column_proportions():
    """Test that TreeView columns have correct proportions."""
    gui_file_path = os.path.join(os.path.dirname(__file__), "..", "src", "zebtrack", "ui", "gui.py")
    
    with open(gui_file_path, 'r') as f:
        gui_code = f.read()
    
    # Test TreeView column configuration
    assert 'self.zone_listbox.column("name", width=240, minwidth=160, stretch=True)' in gui_code, "Nome column should stretch"
    assert 'self.zone_listbox.column("type", width=90, minwidth=80, stretch=False)' in gui_code, "Tipo column should not stretch"
    assert 'self.zone_listbox.column("color", width=70, minwidth=60, stretch=False)' in gui_code, "Cor column should not stretch"


def test_button_placement_in_fixed_frame():
    """Test that the analysis button is correctly placed in the fixed frame."""
    gui_file_path = os.path.join(os.path.dirname(__file__), "..", "src", "zebtrack", "ui", "gui.py")
    
    with open(gui_file_path, 'r') as f:
        gui_code = f.read()
    
    # Find setup_zone_definition_for_single_video method
    method_start = gui_code.find('def setup_zone_definition_for_single_video(self, video_path: str, config: dict):')
    method_end = gui_code.find('def setup_zone_configuration_for_video(', method_start)
    method_code = gui_code[method_start:method_end]
    
    # Test button placement
    assert 'self.fixed_button_frame,' in method_code, "Analysis button should be in fixed_button_frame"
    assert 'text="Iniciar Análise de Vídeo Único"' in method_code, "Button should have correct text"
    
    # Test fixed button frame positioning
    scrollable_method_start = gui_code.find('def _create_scrollable_controls_frame(self, parent):')
    scrollable_method_end = gui_code.find('def _on_frame_configure(self, event=None):', scrollable_method_start)
    scrollable_code = gui_code[scrollable_method_start:scrollable_method_end]
    
    assert 'self.fixed_button_frame.pack(side="bottom", fill="x", padx=5, pady=5)' in scrollable_code, "Fixed button frame should be at bottom"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])