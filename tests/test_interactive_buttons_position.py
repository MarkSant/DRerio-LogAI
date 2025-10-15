"""Test that interactive edit buttons are positioned correctly."""

import os


def test_interactive_buttons_positioned_after_zone_list():
    """
    Verify that interactive_buttons_frame is created after zone list
    and before ROI Inclusion Rule Panel.
    """
    gui_file_path = os.path.join(os.path.dirname(__file__), "..", "src", "zebtrack", "ui", "gui.py")

    with open(gui_file_path, encoding="utf-8") as f:
        gui_code = f.read()

    # Find the _create_zone_control_widgets method
    assert "def _create_zone_control_widgets(self):" in gui_code, (
        "_create_zone_control_widgets method should exist"
    )

    # Extract the method body
    zone_controls_section = gui_code.split("def _create_zone_control_widgets(self):")[1]
    # Find the next method to limit the section
    zone_controls_section = zone_controls_section.split(
        "def _create_zone_summary_cards_section(self):"
    )[0]

    # Find the positions of key components
    zone_list_pos = zone_controls_section.find("--- Zone List ---")
    interactive_buttons_pos = zone_controls_section.find("--- Interactive Buttons")
    roi_inclusion_pos = zone_controls_section.find("--- ROI Inclusion Rule Panel ---")

    assert zone_list_pos > 0, "Zone List section should exist"
    assert interactive_buttons_pos > 0, "Interactive Buttons section should exist"
    assert roi_inclusion_pos > 0, "ROI Inclusion Rule Panel section should exist"

    # Verify the order: Zone List < Interactive Buttons < ROI Inclusion Rule
    assert zone_list_pos < interactive_buttons_pos, (
        "Interactive Buttons should come after Zone List"
    )

    assert interactive_buttons_pos < roi_inclusion_pos, (
        "Interactive Buttons should come before ROI Inclusion Rule Panel"
    )

    # Verify the button frame is created correctly
    assert (
        "self.interactive_buttons_frame = ttk.Frame(self.zone_controls_frame)"
        in zone_controls_section
    ), "interactive_buttons_frame should be created"

    # Verify it contains save and discard buttons
    assert "self.save_arena_btn = ttk.Button" in zone_controls_section, (
        "Save button should be created"
    )

    assert 'text="✅ Salvar Edição"' in zone_controls_section, (
        "Save button should have correct label"
    )

    assert "self.discard_arena_btn = ttk.Button" in zone_controls_section, (
        "Discard button should be created"
    )

    assert 'text="❌ Descartar"' in zone_controls_section, (
        "Discard button should have correct label"
    )

    # Verify there's only ONE definition of interactive_buttons_frame
    # (not duplicated)
    count = zone_controls_section.count(
        "self.interactive_buttons_frame = ttk.Frame(self.zone_controls_frame)"
    )
    assert count == 1, (
        f"interactive_buttons_frame should be defined exactly once, found {count} times"
    )

    # Verify the comment about positioning
    assert (
        "Positioned right after zone list" in zone_controls_section
        or "right after zone list" in zone_controls_section.lower()
    ), "Should have comment explaining button position"


def test_interactive_buttons_not_packed_initially():
    """
    Verify that interactive buttons frame is created but not packed initially.
    It should be packed dynamically when entering edit mode.
    """
    gui_file_path = os.path.join(os.path.dirname(__file__), "..", "src", "zebtrack", "ui", "gui.py")

    with open(gui_file_path, encoding="utf-8") as f:
        gui_code = f.read()

    zone_controls_section = gui_code.split("def _create_zone_control_widgets(self):")[1]
    zone_controls_section = zone_controls_section.split(
        "def _create_zone_summary_cards_section(self):"
    )[0]

    # Get the section after interactive_buttons_frame creation
    buttons_section = zone_controls_section.split("self.interactive_buttons_frame = ttk.Frame")[1]
    buttons_section = buttons_section.split("--- ROI Inclusion Rule Panel ---")[0]

    # The frame itself should NOT have .pack() called in _create_zone_control_widgets
    # Only the buttons inside it should be packed
    assert "self.interactive_buttons_frame.pack(" not in buttons_section, (
        "interactive_buttons_frame should not be packed in _create_zone_control_widgets"
    )

    # But the buttons inside should be packed
    assert "self.save_arena_btn.pack(" in buttons_section, (
        "Save button should be packed inside the frame"
    )

    assert "self.discard_arena_btn.pack(" in buttons_section, (
        "Discard button should be packed inside the frame"
    )

    # There should be a comment explaining it's packed later
    assert "packed later" in buttons_section or "pack() in" in buttons_section, (
        "Should have comment explaining frame is packed later dynamically"
    )
