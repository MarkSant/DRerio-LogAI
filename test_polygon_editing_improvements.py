#!/usr/bin/env python3
"""
Test script for polygon editing improvements.
"""

import pytest
import os


def test_finish_edit_button_added():
    """Test that the finish edit button has been added to the GUI."""
    gui_file_path = os.path.join(os.path.dirname(__file__), "src", "zebtrack", "ui", "gui.py")
    
    with open(gui_file_path, 'r') as f:
        gui_code = f.read()
    
    # Test that finish edit button is created
    assert 'self.finish_edit_btn = ttk.Button(' in gui_code, "Finish edit button should be created"
    assert '"🏁 Concluir Edição (Enter)"' in gui_code, "Finish edit button should have correct text"
    assert 'command=self._on_finish_edit' in gui_code, "Finish edit button should have correct command"
    

def test_on_finish_edit_method_exists():
    """Test that the _on_finish_edit method exists."""
    gui_file_path = os.path.join(os.path.dirname(__file__), "src", "zebtrack", "ui", "gui.py")
    
    with open(gui_file_path, 'r') as f:
        gui_code = f.read()
    
    # Test that _on_finish_edit method exists
    assert 'def _on_finish_edit(self):' in gui_code, "_on_finish_edit method should exist"
    
    # Test that it handles empty polygon points
    finish_edit_section = gui_code.split('def _on_finish_edit(self):')[1].split('def _on_save_arena(self):')[0]
    assert 'if not self.edited_polygon_points:' in finish_edit_section, "Should handle empty polygon points"
    assert 'self.finish_edit_btn.config(state=\'disabled\')' in finish_edit_section, "Should disable finish button"


def test_handle_release_improvements():
    """Test that _on_handle_release method has been improved."""
    gui_file_path = os.path.join(os.path.dirname(__file__), "src", "zebtrack", "ui", "gui.py")
    
    with open(gui_file_path, 'r') as f:
        gui_code = f.read()
    
    # Test that _on_handle_release ensures final position is recorded
    handle_release_section = gui_code.split('def _on_handle_release(self, event):')[1].split('def _on_finish_edit(self):')[0]
    assert 'canvas_x = self.roi_canvas.canvasx(event.x)' in handle_release_section, "Should use canvasx for final position"
    assert 'self.edited_polygon_points[self._dragged_handle_index] = [video_point[0], video_point[1]]' in handle_release_section, "Should update edited_polygon_points"


def test_clear_interactive_polygon_improvements():
    """Test that _clear_interactive_polygon method properly clears handles."""
    gui_file_path = os.path.join(os.path.dirname(__file__), "src", "zebtrack", "ui", "gui.py")
    
    with open(gui_file_path, 'r') as f:
        gui_code = f.read()
    
    # Test that _clear_interactive_polygon clears handles and unbinds keyboard shortcuts
    clear_section = gui_code.split('def _clear_interactive_polygon(self):')[1].split('def display_roi_video_frame(self, video_path):')[0]
    assert 'self.polygon_handles = []  # Explicitly clear handle references' in clear_section, "Should explicitly clear handles"
    assert 'self.root.unbind(\'<Return>\')' in clear_section, "Should unbind Enter key"
    assert 'self.root.unbind(\'<KP_Enter>\')' in clear_section, "Should unbind numpad Enter key"


def test_keyboard_shortcuts_added():
    """Test that keyboard shortcuts have been added for finishing edit."""
    gui_file_path = os.path.join(os.path.dirname(__file__), "src", "zebtrack", "ui", "gui.py")
    
    with open(gui_file_path, 'r') as f:
        gui_code = f.read()
    
    # Test that keyboard shortcuts are bound in setup_interactive_polygon
    setup_section = gui_code.split('def setup_interactive_polygon(self, polygon: np.ndarray):')[1].split('def _draw_interactive_polygon(self):')[0]
    assert 'self.root.bind(\'<Return>\', lambda e: self._on_finish_edit())' in setup_section, "Should bind Enter key"
    assert 'self.root.bind(\'<KP_Enter>\', lambda e: self._on_finish_edit())' in setup_section, "Should bind numpad Enter key"


def test_save_manual_arena_improvements():
    """Test that save_manual_arena method has been improved."""
    controller_file_path = os.path.join(os.path.dirname(__file__), "src", "zebtrack", "core", "controller.py")
    
    with open(controller_file_path, 'r') as f:
        controller_code = f.read()
    
    # Test that save_manual_arena validates points and returns success
    save_manual_section = controller_code.split('def save_manual_arena(self, polygon_points: list[list[int]]):')[1].split('def update_main_arena(self, polygon_points: list[list[int]]):')[0]
    assert 'if not polygon_points or len(polygon_points) < 3:' in save_manual_section, "Should validate polygon points"
    assert 'return False' in save_manual_section, "Should return False on invalid points"
    assert 'return success' in save_manual_section, "Should return success status"


def test_update_main_arena_returns_success():
    """Test that update_main_arena method returns success status."""
    controller_file_path = os.path.join(os.path.dirname(__file__), "src", "zebtrack", "core", "controller.py")
    
    with open(controller_file_path, 'r') as f:
        controller_code = f.read()
    
    # Test that update_main_arena returns success/failure
    update_main_section = controller_code.split('def update_main_arena(self, polygon_points: list[list[int]]):')[1].split('def add_roi_polygon(')[0]
    assert 'return True' in update_main_section, "Should return True on success"
    assert 'return False' in update_main_section, "Should return False on error"
    assert 'except Exception as e:' in update_main_section, "Should handle exceptions"


def test_button_layout_improvements():
    """Test that button layout has been improved with separate sections."""
    gui_file_path = os.path.join(os.path.dirname(__file__), "src", "zebtrack", "ui", "gui.py")
    
    with open(gui_file_path, 'r') as f:
        gui_code = f.read()
    
    # Test that secondary buttons frame is created
    assert 'self.secondary_buttons_frame = ttk.Frame(self.interactive_buttons_frame)' in gui_code, "Should create secondary buttons frame"
    assert 'self.finish_edit_btn.pack(side="top", fill="x", pady=(0, 2))' in gui_code, "Finish button should be at top"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])