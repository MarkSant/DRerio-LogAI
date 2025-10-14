#!/usr/bin/env python3
"""Test the analysis view toggle functionality."""

import unittest
from typing import Callable
from unittest.mock import Mock

from zebtrack.core.processing_mode import ProcessingMode, ProcessingReport


class MockVar:
    """Simple stand-in for tkinter.StringVar used in tests."""

    def __init__(self, value="-"):
        self._value = value

    def set(self, value):
        self._value = value

    def get(self):
        return self._value


class MockFrame:
    """Frame that tracks visibility through pack operations."""

    def __init__(self):
        self.visible = False

    def pack(self, *_, **__):
        self.visible = True

    def pack_forget(self):
        self.visible = False

    def winfo_viewable(self):
        return self.visible


class MockProgressBar:
    """Progress bar that stores its numeric value."""

    def __init__(self):
        self.value = 0

    def __setitem__(self, key, val):
        if key == "value":
            self.value = val

    def __getitem__(self, key):
        if key == "value":
            return self.value
        raise KeyError(key)


class MockNotebook:
    """Notebook that only tracks the selected tab."""

    def __init__(self, zone_id, analysis_id):
        self.selected = str(zone_id)
        self.zone_id = str(zone_id)
        self.analysis_id = str(analysis_id)

    def select(self, tab=None):
        if tab is None:
            return self.selected
        self.selected = str(tab)
        return self.selected


class DummyCombobox:
    def __init__(self):
        self.values: list[str] = []
        self._callbacks: dict[str, Callable] = {}
        self.state: str = "readonly"

    def configure(self, **kwargs):
        if "values" in kwargs:
            self.values = list(kwargs["values"])
        if "state" in kwargs:
            self.state = kwargs["state"]

    def bind(self, event, callback):
        self._callbacks[event] = callback


class MockApplicationGUI:
    """Mock ApplicationGUI for testing the tab-based analysis view."""

    def __init__(self):
        self.zone_tab_frame = "zone"
        self.analysis_tab_frame = "analysis"
        self.notebook = MockNotebook(self.zone_tab_frame, self.analysis_tab_frame)

        self.canvas_view_mode = "zones"
        self.analysis_active = False

        self.toggle_view_btn = Mock()
        self.cancel_proc_btn = Mock()
        self.analysis_status_var = MockVar("Nenhuma análise em andamento.")
        self.analysis_metadata_var = MockVar(
            "Grupo: Sem Grupo | Dia: Sem Dia | Indivíduo: Não informado"
        )
        self.analysis_task_var = MockVar("Nenhuma tarefa em andamento.")

        self.progress_frame = MockFrame()
        self.progress_bar = MockProgressBar()
        self.progress_labels = {
            key: MockVar("-")
            for key in ["total", "processed", "detected", "percent", "elapsed", "eta"]
        }

        self.analysis_video_label = Mock()

        self._active_processing_mode = ProcessingMode.MULTI_TRACK
        self.tracking_mode_var = MockVar("Modo de rastreamento: Multi-indivíduos")
        self.track_selector_var = MockVar("Todos")
        self.track_selector_widget = DummyCombobox()
        self._available_track_options = ("Todos",)
        self._current_detections = []
        self._last_analysis_frame = None
        self._analysis_overlay_image = None

        # Zone editing hooks (overridden in tests when needed)
        self._start_main_arena_drawing = Mock(return_value=True)
        self._start_roi_drawing = Mock(return_value=True)
        self._on_auto_detect_clicked = Mock(return_value=True)

        self._reset_analysis_controls()

    def _update_track_options(self, options):
        normalized = tuple(options)
        self._available_track_options = normalized
        self.track_selector_widget.configure(values=list(normalized))
        if self.track_selector_var.get() not in normalized:
            self.track_selector_var.set(normalized[0] if normalized else "Todos")

    def _reset_analysis_controls(self):
        self._current_detections = []
        self._last_analysis_frame = None
        self._analysis_overlay_image = None
        self._update_track_options(["Todos"])
        self.track_selector_var.set("Todos")
        state = (
            "disabled"
            if self._active_processing_mode is ProcessingMode.SINGLE_SUBJECT
            else "readonly"
        )
        self.track_selector_widget.configure(state=state)

    def update_processing_mode(self, report: ProcessingReport | None):
        if report is None:
            return

        previous_mode = self._active_processing_mode
        self._active_processing_mode = report.mode
        self.tracking_mode_var.set(
            f"Modo de rastreamento: {report.mode.display_name}"
        )

        state = (
            "disabled"
            if report.mode is ProcessingMode.SINGLE_SUBJECT
            else "readonly"
        )
        self.track_selector_widget.configure(state=state)

        if report.mode is ProcessingMode.SINGLE_SUBJECT:
            self.track_selector_var.set("Todos")
            self._update_track_options(["Todos"])
        elif previous_mode is ProcessingMode.SINGLE_SUBJECT:
            observed = set()
            for det in self._current_detections:
                if len(det) >= 6 and det[5] is not None:
                    observed.add(str(det[5]))
            options = ["Todos"] + sorted(observed)
            self._update_track_options(options)

    def show_progress_bar(self):
        if not self.progress_frame.winfo_viewable():
            self.progress_frame.pack()
            self.progress_bar["value"] = 0

    def hide_progress_bar(self):
        if self.progress_frame.winfo_viewable():
            self.progress_frame.pack_forget()
            self.progress_bar["value"] = 0

    def _switch_to_analysis_view(self):
        self.canvas_view_mode = "analysis"
        self.notebook.select(self.analysis_tab_frame)
        self.toggle_view_btn.config(text="Ver Configuração de Zonas")

    def _switch_to_zones_view(self):
        self.canvas_view_mode = "zones"
        self.notebook.select(self.zone_tab_frame)
        self.toggle_view_btn.config(text="Ver Análise em Progresso")

    def _toggle_canvas_view(self):
        if self.notebook.select() != str(self.analysis_tab_frame):
            self._switch_to_analysis_view()
        else:
            self._switch_to_zones_view()

    def start_analysis_view_mode(self):
        self.analysis_active = True
        self.analysis_status_var.set("Preparando análise...")
        self.analysis_task_var.set("Preparando fila de análise...")
        self.show_progress_bar()
        self.toggle_view_btn.config(state="normal")
        self.cancel_proc_btn.config(state="normal")
        self._switch_to_analysis_view()

    def stop_analysis_view_mode(self):
        self.analysis_active = False
        self.hide_progress_bar()
        self.analysis_status_var.set("Nenhuma análise em andamento.")
        self.analysis_task_var.set("Nenhuma tarefa em andamento.")
        self.analysis_metadata_var.set(
            "Grupo: Sem Grupo | Dia: Sem Dia | Indivíduo: Não informado"
        )
        self.toggle_view_btn.config(state="disabled")
        self.cancel_proc_btn.config(state="disabled")
        self._switch_to_zones_view()

    def show_warning(self, _title, _message):
        pass


class TestAnalysisViewToggle(unittest.TestCase):
    """Test cases for the tab-based analysis view toggle functionality."""

    def setUp(self):
        self.gui = MockApplicationGUI()

    def test_initial_state(self):
        self.assertEqual(self.gui.canvas_view_mode, "zones")
        self.assertFalse(self.gui.analysis_active)
        self.assertEqual(self.gui.notebook.select(), str(self.gui.zone_tab_frame))
        self.assertFalse(self.gui.progress_frame.winfo_viewable())
        self.assertEqual(
            self.gui.analysis_status_var.get(),
            "Nenhuma análise em andamento.",
        )

    def test_start_analysis_mode(self):
        self.gui.start_analysis_view_mode()

        self.assertTrue(self.gui.analysis_active)
        self.assertEqual(self.gui.canvas_view_mode, "analysis")
        self.assertEqual(self.gui.notebook.select(), str(self.gui.analysis_tab_frame))
        self.assertTrue(self.gui.progress_frame.winfo_viewable())
        self.assertEqual(self.gui.progress_bar["value"], 0)
        self.assertEqual(self.gui.analysis_status_var.get(), "Preparando análise...")
        self.assertEqual(self.gui.track_selector_var.get(), "Todos")
        self.assertEqual(self.gui.track_selector_widget.values, ["Todos"])
        self.assertEqual(self.gui.track_selector_widget.state, "readonly")

        # Last call should set tab text
        self.assertEqual(
            self.gui.toggle_view_btn.config.call_args_list[-1].kwargs["text"],
            "Ver Configuração de Zonas",
        )

    def test_stop_analysis_mode(self):
        self.gui.start_analysis_view_mode()
        self.gui.stop_analysis_view_mode()

        self.assertFalse(self.gui.analysis_active)
        self.assertEqual(self.gui.canvas_view_mode, "zones")
        self.assertEqual(self.gui.notebook.select(), str(self.gui.zone_tab_frame))
        self.assertFalse(self.gui.progress_frame.winfo_viewable())
        self.assertEqual(
            self.gui.analysis_status_var.get(), "Nenhuma análise em andamento."
        )
        self.assertEqual(self.gui.track_selector_var.get(), "Todos")
        self.assertEqual(self.gui.track_selector_widget.values, ["Todos"])
        self.assertEqual(self.gui.track_selector_widget.state, "readonly")

        states = [
            call.kwargs
            for call in self.gui.toggle_view_btn.config.call_args_list
            if "state" in call.kwargs
        ]
        self.assertIn({"state": "disabled"}, states)

    def test_toggle_during_analysis(self):
        self.gui.start_analysis_view_mode()
        self.gui._toggle_canvas_view()
        self.assertEqual(self.gui.canvas_view_mode, "zones")
        self.assertEqual(self.gui.notebook.select(), str(self.gui.zone_tab_frame))

        self.gui._toggle_canvas_view()
        self.assertEqual(self.gui.canvas_view_mode, "analysis")
        self.assertEqual(self.gui.notebook.select(), str(self.gui.analysis_tab_frame))

    def test_toggle_button_text_changes(self):
        self.gui.start_analysis_view_mode()
        self.assertEqual(
            self.gui.toggle_view_btn.config.call_args_list[-1].kwargs["text"],
            "Ver Configuração de Zonas",
        )

        self.gui._toggle_canvas_view()
        self.assertEqual(
            self.gui.toggle_view_btn.config.call_args_list[-1].kwargs["text"],
            "Ver Análise em Progresso",
        )

    def test_analysis_state_persistence(self):
        self.assertFalse(self.gui.analysis_active)
        self.gui.start_analysis_view_mode()
        self.assertTrue(self.gui.analysis_active)

        self.gui._toggle_canvas_view()
        self.assertTrue(self.gui.analysis_active)

        self.gui._toggle_canvas_view()
        self.assertTrue(self.gui.analysis_active)

        self.gui.stop_analysis_view_mode()
        self.assertFalse(self.gui.analysis_active)

    def test_processing_mode_updates_track_selector(self):
        single_report = ProcessingReport(ProcessingMode.SINGLE_SUBJECT, "test")
        self.gui.update_processing_mode(single_report)
        self.assertEqual(self.gui.track_selector_widget.state, "disabled")
        self.assertEqual(self.gui.track_selector_widget.values, ["Todos"])
        expected_label = "Modo de rastreamento: Individual"
        self.assertEqual(self.gui.tracking_mode_var.get(), expected_label)

        self.gui._current_detections = [(0, 0, 0, 0, 0.9, "42")]
        multi_report = ProcessingReport(ProcessingMode.MULTI_TRACK, "test")
        self.gui.update_processing_mode(multi_report)
        self.assertEqual(self.gui.track_selector_widget.state, "readonly")
        self.assertIn("42", self.gui.track_selector_widget.values)


class TestZoneEditingPrevention(unittest.TestCase):
    """Ensure zone editing actions are blocked while analysis is active."""

    def setUp(self):
        self.gui = MockApplicationGUI()

        def mock_start_drawing_method():
            if self.gui.analysis_active:
                self.gui.show_warning(
                    "Análise em Progresso", "Cannot edit during analysis"
                )
                return False
            return True

        self.gui._start_main_arena_drawing.side_effect = mock_start_drawing_method
        self.gui._start_roi_drawing.side_effect = mock_start_drawing_method
        self.gui._on_auto_detect_clicked.side_effect = mock_start_drawing_method

    def test_zone_editing_allowed_when_not_analyzing(self):
        self.assertTrue(self.gui._start_main_arena_drawing())
        self.assertTrue(self.gui._start_roi_drawing())
        self.assertTrue(self.gui._on_auto_detect_clicked())

    def test_zone_editing_prevented_during_analysis(self):
        self.gui.start_analysis_view_mode()

        self.assertFalse(self.gui._start_main_arena_drawing())
        self.assertFalse(self.gui._start_roi_drawing())
        self.assertFalse(self.gui._on_auto_detect_clicked())


if __name__ == '__main__':
    unittest.main()
