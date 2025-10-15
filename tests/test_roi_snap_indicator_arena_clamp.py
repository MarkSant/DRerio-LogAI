"""Test that ROI snap indicator clamping logic is implemented."""

import os


def test_roi_snap_indicator_arena_clamp_implementation():
    """Verify that ROI snap indicator arena clamping logic exists in gui.py."""
    gui_file_path = os.path.join(os.path.dirname(__file__), "..", "src", "zebtrack", "ui", "gui.py")

    with open(gui_file_path, encoding="utf-8") as f:
        gui_code = f.read()

    # Find the _on_canvas_motion method
    assert "def _on_canvas_motion(self, event):" in gui_code, (
        "_on_canvas_motion method should exist"
    )

    # Extract the method body
    motion_section = gui_code.split("def _on_canvas_motion(self, event):")[1]
    # Find the next method to limit the section
    next_method_markers = [
        "def _on_canvas_double_click",
        "def update_zone_listbox",
    ]
    for marker in next_method_markers:
        if marker in motion_section:
            motion_section = motion_section.split(marker)[0]
            break

    # Verify arena clamping logic is present when drawing ROI
    assert 'if self.current_drawing_type == "roi":' in motion_section, "Should check if drawing ROI"

    arena_lookup = "main_arena_poly = self.controller.project_manager.get_zone_data().polygon"
    assert arena_lookup in motion_section, "Should get arena polygon when drawing ROI"

    assert "cv2.pointPolygonTest" in motion_section, (
        "Should use pointPolygonTest to check if point is inside arena"
    )

    assert "if result < 0:" in motion_section, (
        "Should handle case when display point is outside arena"
    )

    assert (
        "closest_point on the arena boundary" in motion_section
        or "closest point on the arena boundary" in motion_section
    ), "Should find closest point on arena boundary"

    assert "self._point_to_segment_distance" in motion_section, (
        "Should use _point_to_segment_distance to find closest boundary point"
    )

    # Verify the indicator is drawn with the clamped position
    assert "self.roi_canvas.create_oval(" in motion_section, "Should create snap indicator oval"

    assert "display_x" in motion_section and "display_y" in motion_section, (
        "Should use display_x and display_y variables for indicator position"
    )


def test_roi_vertex_editing_arena_clamp_implementation():
    """Verify that ROI vertex editing also clamps to arena boundaries."""
    gui_file_path = os.path.join(os.path.dirname(__file__), "..", "src", "zebtrack", "ui", "gui.py")

    with open(gui_file_path, encoding="utf-8") as f:
        gui_code = f.read()

    # Find the _on_handle_drag method (used for editing vertices)
    assert "def _on_handle_drag(self, event):" in gui_code, "_on_handle_drag method should exist"

    # Extract the method body
    drag_section = gui_code.split("def _on_handle_drag(self, event):")[1]
    # Find the next method to limit the section
    next_method_markers = [
        "def _on_handle_drag_global",
        "def _on_handle_release",
    ]
    for marker in next_method_markers:
        if marker in drag_section:
            drag_section = drag_section.split(marker)[0]
            break

    # Verify arena clamping logic is present when editing ROI
    assert "current_editing_zone" in drag_section, "Should check if editing a zone"

    assert "isinstance(self.current_editing_zone, tuple)" in drag_section, (
        "Should check if editing_zone is a tuple (for ROI)"
    )

    assert 'current_editing_zone[0] == "roi"' in drag_section, (
        "Should check if editing an ROI specifically"
    )

    assert "cv2.pointPolygonTest" in drag_section, (
        "Should use pointPolygonTest to check if vertex is inside arena"
    )

    assert "if result < 0:" in drag_section, (
        "Should handle case when dragged vertex is outside arena"
    )

    assert (
        "closest_point on the arena boundary" in drag_section
        or "closest point on the arena boundary" in drag_section
    ), "Should find closest point on arena boundary when outside"

    assert "self._point_to_segment_distance" in drag_section, (
        "Should use _point_to_segment_distance to find closest boundary point"
    )

    # Verify the position is updated to clamped value (not just returning)
    assert "canvas_x, canvas_y = closest_point" in drag_section, (
        "Should update canvas_x, canvas_y to clamped position"
    )

    # Check that _draw_interactive_polygon has visual feedback for clamped vertices
    assert "def _draw_interactive_polygon(self):" in gui_code, (
        "_draw_interactive_polygon method should exist"
    )

    draw_poly_section = gui_code.split("def _draw_interactive_polygon(self):")[1]
    draw_poly_section = draw_poly_section.split("def _on_handle_press")[0]

    assert "is_on_boundary" in draw_poly_section, "Should detect vertices on arena boundary"

    assert "orange" in draw_poly_section or "Orange" in draw_poly_section, (
        "Should use different color for clamped vertices"
    )

    assert "edit_clamp_indicator" in draw_poly_section, (
        "Should create visual indicator for clamped vertices"
    )
