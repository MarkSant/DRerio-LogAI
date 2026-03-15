"""
Tests for AnalysisDisplayWidget component.

Covers widget initialization, event emission, public API methods, and error handling
as required by CLAUDE.md for all public API changes (minimum 70% coverage).
"""

from unittest.mock import MagicMock

import pytest
from PIL import Image, ImageTk

from zebtrack.ui.components.analysis_display import AnalysisDisplayWidget
from zebtrack.ui.event_bus_v2 import EventBusV2, UIEvents


@pytest.mark.gui
class TestAnalysisDisplayWidget:
    """Test suite for AnalysisDisplayWidget component."""

    @pytest.fixture
    def event_bus(self):
        """Create a mock event bus for testing."""
        bus = MagicMock(spec=EventBusV2)
        bus.subscribe = MagicMock()
        return bus

    @pytest.fixture
    def widget(self, tkinter_root, event_bus):
        """Create an AnalysisDisplayWidget instance for testing."""
        widget = AnalysisDisplayWidget(
            tkinter_root,
            event_bus=event_bus,
            available_track_options=["Todos", "1", "2"],
        )
        tkinter_root.update_idletasks()
        return widget

    # --- Initialization Tests ---

    def test_widget_initialization(self, tkinter_root, event_bus):
        """Test widget initializes with correct default values."""
        widget = AnalysisDisplayWidget(
            tkinter_root,
            event_bus=event_bus,
        )
        tkinter_root.update_idletasks()

        # Verify default state variables
        assert widget.status_var.get() == "Nenhuma análise em andamento."
        assert widget.task_var.get() == "Nenhuma tarefa em andamento."
        assert widget.group_var.get() == "Grupo: --"
        assert widget.day_var.get() == "Dia: --"
        assert widget.subject_var.get() == "Indivíduo: --"
        assert widget.profile_var.get() == "Perfil de análise: default"
        assert widget.tracking_mode_var.get() == "Modo de rastreamento: --"
        assert widget.track_selector_var.get() == "Todos"

        # Verify widget references are created
        assert widget.status_label is not None
        assert widget.task_label is not None
        assert widget.track_selector_widget is not None
        assert widget.progress_bar is not None
        assert widget.video_label is not None

    def test_widget_with_custom_track_options(self, tkinter_root, event_bus):
        """Test widget accepts custom track options."""
        custom_tracks = ["Todos", "1", "2", "3", "4"]
        widget = AnalysisDisplayWidget(
            tkinter_root,
            event_bus=event_bus,
            available_track_options=custom_tracks,
        )
        tkinter_root.update_idletasks()

        assert widget._available_track_options == custom_tracks
        assert widget.track_selector_widget is not None
        assert widget.track_selector_widget["values"] == tuple(custom_tracks)

    def test_widget_without_event_bus(self, tkinter_root):
        """Test widget can be created without event bus (no crashes)."""
        widget = AnalysisDisplayWidget(tkinter_root, event_bus=None)
        tkinter_root.update_idletasks()

        assert widget.event_bus is None
        # Should not crash when emitting events
        widget._on_cancel_clicked()

    # --- Public API Tests ---

    def test_set_status(self, widget):
        """Test set_status updates status label."""
        widget.set_status("Analisando vídeo...")
        assert widget.status_var.get() == "Analisando vídeo..."

    def test_set_task(self, widget):
        """Test set_task updates task label."""
        widget.set_task("Processando: video1.mp4")
        assert widget.task_var.get() == "Processando: video1.mp4"

    def test_set_metadata(self, widget):
        """Test set_metadata updates all metadata labels."""
        widget.set_metadata(
            group="Grupo A",
            day="Dia 1",
            subject="Peixe 1",
            profile="custom_profile",
        )

        assert widget.group_var.get() == "Grupo: Grupo A"
        assert widget.day_var.get() == "Dia: Dia 1"
        assert widget.subject_var.get() == "Indivíduo: Peixe 1"
        assert widget.profile_var.get() == "Perfil de análise: custom_profile"

    def test_set_metadata_without_profile(self, widget):
        """Test set_metadata works without profile parameter."""
        widget.set_metadata(group="Grupo B", day="Dia 2", subject="Peixe 2")

        assert widget.group_var.get() == "Grupo: Grupo B"
        assert widget.day_var.get() == "Dia: Dia 2"
        assert widget.subject_var.get() == "Indivíduo: Peixe 2"
        # Profile should not change
        assert "Perfil de análise:" in widget.profile_var.get()

    def test_set_tracking_mode(self, widget):
        """Test set_tracking_mode updates tracking mode label."""
        widget.set_tracking_mode("Single-subject")
        assert widget.tracking_mode_var.get() == "Modo de rastreamento: Single-subject"

    def test_set_profile(self, widget):
        """Test set_profile updates profile label."""
        widget.set_profile("advanced")
        assert widget.profile_var.get() == "Perfil de análise: advanced"

    def test_set_social_summary(self, widget):
        """Test set_social_summary updates social summary text."""
        widget.set_social_summary("3 interações detectadas")
        assert widget.social_summary_var.get() == "3 interações detectadas"

    def test_update_track_options(self, widget):
        """Test update_track_options updates combobox values."""
        new_tracks = ["Todos", "10", "20", "30"]
        widget.update_track_options(new_tracks)

        assert widget._available_track_options == new_tracks
        assert widget.track_selector_widget["values"] == tuple(new_tracks)

    def test_show_progress(self, widget):
        """Test show_progress packs progress frame."""
        # Verify progress frame exists
        assert widget.progress_frame is not None

        # Call show_progress (it uses pack())
        widget.show_progress()

        # Verify the method doesn't crash
        # Note: In tests, we can't reliably test winfo_ismapped() without a visible window
        assert widget.progress_frame.winfo_exists()

    def test_hide_progress(self, widget):
        """Test hide_progress unpacks progress frame."""
        widget.show_progress()

        # Call hide_progress (it uses pack_forget())
        widget.hide_progress()

        # Verify the method doesn't crash
        assert widget.progress_frame.winfo_exists()

    def test_update_progress(self, widget):
        """Test update_progress updates progress bar value."""
        widget.update_progress(0.5)
        assert widget.progress_bar["value"] == 50.0

        widget.update_progress(0.75)
        assert widget.progress_bar["value"] == 75.0

        widget.update_progress(1.0)
        assert widget.progress_bar["value"] == 100.0

    def test_update_progress_stats(self, widget):
        """Test update_progress_stats updates all statistics labels."""
        widget.update_progress_stats(
            total_frames=1000,
            processed_frames=500,
            detected_frames=480,
            percent="50%",
            elapsed="00:02:30",
            eta="00:02:30",
        )

        assert widget.progress_labels["total"].get() == "1000"
        assert widget.progress_labels["processed"].get() == "500"
        assert widget.progress_labels["detected"].get() == "480"
        assert widget.progress_labels["percent"].get() == "50%"
        assert widget.progress_labels["elapsed"].get() == "00:02:30"
        assert widget.progress_labels["eta"].get() == "00:02:30"

    def test_update_progress_stats_partial(self, widget):
        """Test update_progress_stats with only some parameters."""
        widget.update_progress_stats(
            processed_frames=250,
            percent="25%",
        )

        assert widget.progress_labels["processed"].get() == "250"
        assert widget.progress_labels["percent"].get() == "25%"
        # Other values should remain at default "-"
        assert widget.progress_labels["total"].get() == "-"

    def test_enable_cancel_button(self, widget):
        """Test enable_cancel_button enables the cancel button."""
        widget.enable_cancel_button()
        assert str(widget.cancel_btn["state"]) == "normal"

    def test_disable_cancel_button(self, widget):
        """Test disable_cancel_button disables the cancel button."""
        widget.enable_cancel_button()
        widget.disable_cancel_button()
        assert str(widget.cancel_btn["state"]) == "disabled"

    def test_clear_video_display(self, widget):
        """Test clear_video_display clears the video label."""
        # Set a mock image attribute (not actual Tk image)
        widget.video_label.image = "mock_image"

        widget.clear_video_display()

        assert widget.video_label.cget("image") == ""
        assert widget.video_label.image is None

    def test_update_frame_with_pil_image(self, widget):
        """Test update_frame accepts a PIL Image and stores a PhotoImage."""
        image = Image.new("RGB", (16, 12), color=(120, 10, 10))

        widget.update_frame(image)

        assert isinstance(widget.video_label.image, ImageTk.PhotoImage)

    def test_update_frame_with_photoimage(self, widget):
        """Test update_frame accepts an ImageTk.PhotoImage directly."""
        image = Image.new("RGB", (16, 12), color=(10, 120, 10))
        photo = ImageTk.PhotoImage(image)

        widget.update_frame(photo)

        assert widget.video_label.image is photo

    def test_reset_to_defaults(self, widget):
        """Test reset_to_defaults resets all values to initial state."""
        # Change some values first
        widget.set_status("Custom status")
        widget.set_task("Custom task")
        widget.set_metadata("GroupX", "DayX", "SubjectX", "ProfileX")
        widget.show_progress()
        widget.enable_cancel_button()
        widget.update_progress(0.5)

        # Reset to defaults
        widget.reset_to_defaults()
        widget.winfo_toplevel().update_idletasks()

        # Verify all defaults
        assert widget.status_var.get() == "Nenhuma análise em andamento."
        assert widget.task_var.get() == "Nenhuma tarefa em andamento."
        assert widget.group_var.get() == "Grupo: --"
        assert widget.day_var.get() == "Dia: --"
        assert widget.subject_var.get() == "Indivíduo: --"
        assert widget.tracking_mode_var.get() == "Modo de rastreamento: --"
        assert widget.profile_var.get() == "Perfil de análise: default"
        assert widget.track_selector_var.get() == "Todos"
        assert not widget.progress_frame.winfo_ismapped()
        assert str(widget.cancel_btn["state"]) == "disabled"

        # Progress stats should be reset
        for var in widget.progress_labels.values():
            assert var.get() == "-"

    # --- Event Emission Tests ---

    def test_track_selection_emits_event(self, widget, event_bus):
        """Test track selection emits analysis.track_selected event."""
        widget.track_selector_var.set("2")
        widget._on_track_selection_changed()

        event_bus.publish.assert_called_once_with(
            UIEvents.ANALYSIS_TRACK_SELECTED,
            {"track_id": "2"},
        )

    def test_cancel_button_emits_event(self, widget, event_bus):
        """Test cancel button emits analysis.cancel_requested event."""
        widget._on_cancel_clicked()

        event_bus.publish.assert_called_once_with(
            UIEvents.ANALYSIS_CANCEL_REQUESTED,
            {},
        )

    def test_event_emission_without_bus(self, tkinter_root):
        """Test events don't crash when event bus is None."""
        widget = AnalysisDisplayWidget(tkinter_root, event_bus=None)
        tkinter_root.update_idletasks()

        # Should not raise exceptions
        widget._on_track_selection_changed()
        widget._on_cancel_clicked()

    # --- Error Handling Tests ---

    def test_handles_none_values_gracefully(self, widget):
        """Test widget handles None values in update methods."""
        # Should not crash with None values
        widget.update_progress_stats(
            total_frames=None,
            processed_frames=None,
        )
        # Values should remain unchanged
        assert widget.progress_labels["total"].get() == "-"

    def test_handles_empty_track_list(self, tkinter_root, event_bus):
        """Test widget handles empty track list (gets defaulted to ['Todos'])."""
        widget = AnalysisDisplayWidget(
            tkinter_root,
            event_bus=event_bus,
            available_track_options=[],
        )
        tkinter_root.update_idletasks()

        # Empty list gets defaulted to ["Todos"] by the `or` operator in constructor
        assert widget._available_track_options == ["Todos"]
        # Widget should still be functional
        widget.update_track_options(["Todos", "1", "2"])
        assert widget._available_track_options == ["Todos", "1", "2"]

    def test_progress_updates_with_invalid_values(self, widget):
        """Test progress bar handles edge case values."""
        # Test boundary values
        widget.update_progress(0.0)
        assert widget.progress_bar["value"] == 0.0

        widget.update_progress(1.0)
        assert widget.progress_bar["value"] == 100.0

        # Should clamp or handle values outside [0, 1]
        widget.update_progress(1.5)
        assert widget.progress_bar["value"] >= 0.0  # Should not crash

    def test_multiple_show_hide_progress(self, widget):
        """Test multiple show/hide operations don't break widget."""
        for i in range(3):
            widget.show_progress()
            widget.winfo_toplevel().update_idletasks()
            # Frame should still exist after show
            assert widget.progress_frame.winfo_exists(), f"Show iteration {i} failed"

            widget.hide_progress()
            widget.winfo_toplevel().update_idletasks()
            # Frame should still exist after hide (just not packed)
            assert widget.progress_frame.winfo_exists(), f"Hide iteration {i} failed"

    # --- Integration Tests ---

    def test_complete_analysis_workflow(self, widget, event_bus):
        """Test a complete analysis workflow simulation."""
        # Start analysis
        widget.set_status("Iniciando análise...")
        widget.set_task("Processando: test_video.mp4")
        widget.set_metadata("Grupo A", "Dia 1", "Peixe 1", "default")
        widget.show_progress()
        widget.enable_cancel_button()

        # Progress updates
        widget.update_progress(0.25)
        widget.update_progress_stats(
            total_frames=1000,
            processed_frames=250,
            detected_frames=240,
            percent="25%",
            elapsed="00:01:00",
            eta="00:03:00",
        )

        # Continue to completion
        widget.update_progress(1.0)
        widget.update_progress_stats(
            total_frames=1000,
            processed_frames=1000,
            detected_frames=960,
            percent="100%",
            elapsed="00:04:00",
            eta="00:00:00",
        )

        # Finish
        widget.set_status("Análise concluída")
        widget.disable_cancel_button()

        # Verify final state
        assert widget.progress_bar["value"] == 100.0
        assert str(widget.cancel_btn["state"]) == "disabled"
        assert widget.status_var.get() == "Análise concluída"

        # Reset for next analysis
        widget.reset_to_defaults()
        assert widget.status_var.get() == "Nenhuma análise em andamento."
