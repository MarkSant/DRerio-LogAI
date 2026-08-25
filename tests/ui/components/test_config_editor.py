"""
Tests for ConfigEditorWidget component.
"""

from unittest.mock import Mock, patch

import pytest

from zebtrack.core.services.roi_rule_resolver import (
    DEFAULT_BBOX_OVERLAP_BASIS,
    DEFAULT_BUFFER_RADIUS_VALUE,
    DEFAULT_MIN_BBOX_OVERLAP_RATIO,
    DEFAULT_ROI_INCLUSION_RULE,
)
from zebtrack.ui.components.config_editor import ConfigEditorWidget
from zebtrack.ui.event_bus_v2 import EventBusV2, UIEvents

pytestmark = pytest.mark.gui


@pytest.fixture
def event_bus():
    """Create an EventBusV2 instance."""
    return EventBusV2()


@pytest.fixture
def config_widget(tkinter_root, event_bus):
    """Create a ConfigEditorWidget instance for testing."""
    widget = ConfigEditorWidget(tkinter_root, event_bus=event_bus)
    widget.pack()
    tkinter_root.update()
    return widget


def test_widget_initialization(config_widget):
    """Test that widget initializes with default values."""
    assert config_widget.fps_var.get() == "30"
    assert config_widget.processing_interval_var.get() == "10"
    assert config_widget.processing_offset_var.get() == "0"
    assert config_widget.window_length_var.get() == "7"
    assert config_widget.polyorder_var.get() == "3"
    assert config_widget.flush_interval_var.get() == "5.0"
    assert config_widget.flush_rows_var.get() == "500"
    # Defaults da fonte canônica (roi_rule_resolver), não literais do widget.
    assert config_widget.roi_inclusion_rule_var.get() == DEFAULT_ROI_INCLUSION_RULE
    assert float(config_widget.roi_buffer_radius_var.get()) == DEFAULT_BUFFER_RADIUS_VALUE
    assert float(config_widget.roi_overlap_ratio_var.get()) == DEFAULT_MIN_BBOX_OVERLAP_RATIO
    assert config_widget.roi_overlap_basis_var.get() == DEFAULT_BBOX_OVERLAP_BASIS


def test_get_values_returns_correct_structure(config_widget):
    """Test that get_values returns correctly structured dict."""
    values = config_widget.get_values()

    assert "video_processing" in values
    assert "trajectory_smoothing" in values
    assert "recorder" in values
    assert "roi_inclusion_rule" in values
    assert "roi_buffer_radius_value" in values
    assert "roi_min_bbox_overlap_ratio" in values
    assert "roi_bbox_overlap_basis" in values

    assert values["video_processing"]["fps"] == 30
    assert values["video_processing"]["processing_interval"] == 10
    assert values["video_processing"]["processing_offset"] == 0
    assert values["trajectory_smoothing"]["window_length"] == 7
    assert values["trajectory_smoothing"]["polyorder"] == 3
    assert values["recorder"]["flush_interval_seconds"] == 5.0
    assert values["recorder"]["flush_row_threshold"] == 500
    assert values["roi_inclusion_rule"] == DEFAULT_ROI_INCLUSION_RULE
    assert values["roi_buffer_radius_value"] == DEFAULT_BUFFER_RADIUS_VALUE
    assert values["roi_min_bbox_overlap_ratio"] == DEFAULT_MIN_BBOX_OVERLAP_RATIO
    assert values["roi_bbox_overlap_basis"] == DEFAULT_BBOX_OVERLAP_BASIS


def test_set_values_populates_form_correctly(config_widget):
    """Test that set_values correctly populates all form fields."""
    test_values = {
        "video_processing": {
            "fps": 60,
            "processing_interval": 5,
            "processing_offset": 10,
        },
        "trajectory_smoothing": {
            "window_length": 9,
            "polyorder": 4,
        },
        "recorder": {
            "flush_interval_seconds": 10.0,
            "flush_row_threshold": 1000,
        },
        "roi_inclusion_rule": "bbox_intersects",
        "roi_buffer_radius_value": 5.0,
        "roi_min_bbox_overlap_ratio": 0.7,
    }

    config_widget.set_values(test_values)

    assert config_widget.fps_var.get() == "60"
    assert config_widget.processing_interval_var.get() == "5"
    assert config_widget.processing_offset_var.get() == "10"
    assert config_widget.window_length_var.get() == "9"
    assert config_widget.polyorder_var.get() == "4"
    assert config_widget.flush_interval_var.get() == "10.0"
    assert config_widget.flush_rows_var.get() == "1000"
    assert config_widget.roi_inclusion_rule_var.get() == "bbox_intersects"
    assert config_widget.roi_buffer_radius_var.get() == "5.0"
    assert config_widget.roi_overlap_ratio_var.get() == "0.7"


def test_event_emission_on_save(config_widget, event_bus):
    """Test that save button emits CONFIG_SAVE_REQUESTED event."""
    events_received = []

    def handler(data):
        events_received.append(data)

    event_bus.subscribe(UIEvents.CONFIG_SAVE_REQUESTED, handler)

    # Trigger save
    config_widget._on_save_clicked()

    # Handler should have been called synchronously
    assert len(events_received) == 1
    assert events_received[0].get("values") is not None


def test_event_emission_on_reset(config_widget, event_bus):
    """Test that reset button emits CONFIG_RESET_REQUESTED event."""
    events_received = []

    def handler(data):
        events_received.append(data)

    event_bus.subscribe(UIEvents.CONFIG_RESET_REQUESTED, handler)

    # Trigger reset
    config_widget._on_reset_clicked()

    # Handler should have been called synchronously
    assert len(events_received) == 1


def test_event_emission_on_roi_rule_change(config_widget, event_bus):
    """Test that ROI rule change emits CONFIG_ROI_RULE_CHANGED event."""
    events_received = []

    def handler(data):
        events_received.append(data)

    event_bus.subscribe(UIEvents.CONFIG_ROI_RULE_CHANGED, handler)

    # Change rule
    config_widget.roi_inclusion_rule_var.set("seg_overlap")
    config_widget._on_roi_rule_changed()

    # Handler should have been called synchronously
    assert len(events_received) == 1
    assert events_received[0].get("rule") == "seg_overlap"


def test_invalid_input_handling(config_widget):
    """Test that invalid inputs raise ValueError when getting values."""
    config_widget.fps_var.set("invalid")

    with pytest.raises(ValueError):
        config_widget.get_values()


def test_partial_set_values(config_widget):
    """Test that set_values works with partial dict."""
    partial_values = {
        "video_processing": {
            "fps": 45,
        },
    }

    config_widget.set_values(partial_values)

    # Updated value
    assert config_widget.fps_var.get() == "45"

    # Unchanged values remain default
    assert config_widget.processing_interval_var.get() == "10"
    assert config_widget.window_length_var.get() == "7"


def test_widget_without_event_bus(tkinter_root):
    """Test that widget works without event bus."""
    widget = ConfigEditorWidget(tkinter_root, event_bus=None)
    widget.pack()
    tkinter_root.update()

    # Should not crash
    widget._on_save_clicked()
    widget._on_reset_clicked()
    widget._on_roi_rule_changed()

    # get_values should still work
    values = widget.get_values()
    assert "video_processing" in values


def test_get_values_includes_behavioral_analysis(config_widget):
    """Test behavioral analysis values are mapped into output."""
    config_widget.behavioral_config_widget = Mock()
    config_widget.behavioral_config_widget.get_values.return_value = {
        "thigmotaxis_distance_cm": 2.5,
        "geotaxis_distance_cm": 3.0,
        "geotaxis_num_zones": 4,
        "geotaxis_bottom_zones": 1,
        "aquarium_perspective": "top",
        "geotaxis_mode": "zones",
    }

    values = config_widget.get_values()

    assert values["behavioral_analysis"]["default_thigmotaxis_distance_cm"] == 2.5
    assert values["behavioral_analysis"]["default_geotaxis_distance_cm"] == 3.0
    assert values["behavioral_analysis"]["default_geotaxis_num_zones"] == 4
    assert values["behavioral_analysis"]["default_geotaxis_bottom_zones"] == 1
    assert values["behavioral_analysis"]["aquarium_perspective"] == "top"
    assert values["behavioral_analysis"]["geotaxis_mode"] == "zones"


def test_set_values_behavioral_analysis_mapping(config_widget):
    """Test behavioral analysis values are mapped to widget values."""
    config_widget.behavioral_config_widget = Mock()

    config_widget.set_values(
        {
            "behavioral_analysis": {
                "default_thigmotaxis_distance_cm": 1.5,
                "default_geotaxis_distance_cm": 2.5,
                "default_geotaxis_num_zones": 3,
                "default_geotaxis_bottom_zones": 2,
                "aquarium_perspective": "lateral",
                "geotaxis_mode": "lines",
            }
        }
    )

    config_widget.behavioral_config_widget.set_values.assert_called_once_with(
        {
            "thigmotaxis_distance_cm": 1.5,
            "geotaxis_distance_cm": 2.5,
            "geotaxis_num_zones": 3,
            "geotaxis_bottom_zones": 2,
            "aquarium_perspective": "lateral",
            "geotaxis_mode": "lines",
            "geotaxis_enabled": True,
        }
    )


def test_detection_summary_visibility_can_toggle(config_widget):
    """Test that the global-only detection summary can be hidden in project context."""
    assert config_widget._detection_summary_frame is not None
    assert config_widget._detection_summary_frame.winfo_manager() == "pack"

    config_widget.set_detection_summary_visible(False)

    assert config_widget._detection_summary_frame.winfo_manager() == ""

    config_widget.set_detection_summary_visible(True)

    assert config_widget._detection_summary_frame.winfo_manager() == "pack"


def test_persist_masks_round_trip(config_widget):
    """``recorder.persist_masks`` é lido e escrito pelo formulário.

    Sem widget, a única forma de habilitar o pré-requisito de ``seg_overlap``
    era editar ``config.yaml`` à mão.
    """
    assert config_widget.get_values()["recorder"]["persist_masks"] is False

    config_widget.set_values({"recorder": {"persist_masks": True}})

    assert config_widget.persist_masks_var.get() is True
    assert config_widget.get_values()["recorder"]["persist_masks"] is True

    config_widget.set_values({"recorder": {"persist_masks": False}})

    assert config_widget.get_values()["recorder"]["persist_masks"] is False


def test_persist_masks_help_names_the_other_two_prerequisites(tkinter_root, event_bus):
    """A ajuda avisa que ligar só esta chave não habilita ``seg_overlap``.

    Os textos são capturados na construção porque o tooltip vive num objeto
    ``ToolTip`` que o label não referencia de volta.
    """
    import zebtrack.ui.components.config_editor as config_editor_module

    captured: list[str] = []
    real_create_help_label = config_editor_module.create_help_label

    def _spy(parent, text):
        captured.append(text)
        return real_create_help_label(parent, text)

    with patch.object(config_editor_module, "create_help_label", _spy):
        ConfigEditorWidget(tkinter_root, event_bus=event_bus)
    tkinter_root.update_idletasks()

    persist_help = [t for t in captured if "persist_masks" in t]
    assert persist_help, "nenhuma ajuda menciona persist_masks"
    assert any("animal_method" in t and "seg_overlap" in t for t in persist_help)


def test_seg_overlap_warning_appears_only_when_masks_are_off(config_widget):
    """Selecionar ``seg_overlap`` com máscaras desligadas avisa na hora."""
    config_widget.roi_inclusion_rule_var.set("seg_overlap")
    config_widget._on_roi_rule_changed()

    assert "bbox_intersects" in config_widget._seg_overlap_warning_label.cget("text")

    config_widget.persist_masks_var.set(True)

    assert config_widget._seg_overlap_warning_label.cget("text") == ""

    config_widget.persist_masks_var.set(False)
    config_widget.roi_inclusion_rule_var.set("bbox_intersects")
    config_widget._on_roi_rule_changed()

    assert config_widget._seg_overlap_warning_label.cget("text") == ""


class TestSaveClickSurfacesFailures:
    """O clique em Salvar precisa DIZER o que houve, nunca ficar inerte.

    ``_on_save_clicked`` capturava só ``ValueError`` e publicava
    ``CONFIG_VALIDATION_ERROR``, que não tinha assinante — o bus descarta
    evento sem assinante em silêncio, então o botão não fazia absolutamente
    nada com um campo vazio. E os ``Spinbox`` do widget comportamental falham
    com ``TclError``, que nem sequer era capturado.
    """

    @staticmethod
    def _captured(event_bus, event):
        received: list = []
        event_bus.subscribe(event, received.append)
        return received

    def test_empty_numeric_field_reports_instead_of_going_silent(self, config_widget, event_bus):
        errors = self._captured(event_bus, UIEvents.CONFIG_VALIDATION_ERROR)
        saves = self._captured(event_bus, UIEvents.CONFIG_SAVE_REQUESTED)

        config_widget.fps_var.set("")
        config_widget._on_save_clicked()

        assert len(errors) == 1, "campo vazio precisa gerar CONFIG_VALIDATION_ERROR"
        assert not saves, "não pode salvar com campo ilegível"

    def test_text_in_numeric_field_reports(self, config_widget, event_bus):
        errors = self._captured(event_bus, UIEvents.CONFIG_VALIDATION_ERROR)
        saves = self._captured(event_bus, UIEvents.CONFIG_SAVE_REQUESTED)

        config_widget.fps_var.set("trinta")
        config_widget._on_save_clicked()

        assert len(errors) == 1
        assert not saves

    def test_text_in_behavioral_spinbox_is_caught_not_raised(self, config_widget, event_bus):
        """``TclError`` do ``DoubleVar`` não pode escapar para a rede do Tk."""
        errors = self._captured(event_bus, UIEvents.CONFIG_VALIDATION_ERROR)
        saves = self._captured(event_bus, UIEvents.CONFIG_SAVE_REQUESTED)

        spinbox = config_widget.behavioral_config_widget.thigmotaxis_spinbox
        spinbox.delete(0, "end")
        spinbox.insert(0, "xyz")

        # Sem a captura de TclError isto levantava e o teste falharia aqui.
        config_widget._on_save_clicked()

        assert len(errors) == 1, "TclError precisa virar CONFIG_VALIDATION_ERROR"
        assert not saves

    def test_out_of_range_behavioral_value_is_rejected_with_the_widget_message(
        self, config_widget, event_bus
    ):
        """A aba nunca chamava ``BehavioralConfigWidget.validate()``."""
        errors = self._captured(event_bus, UIEvents.CONFIG_VALIDATION_ERROR)
        saves = self._captured(event_bus, UIEvents.CONFIG_SAVE_REQUESTED)

        config_widget.behavioral_config_widget.thigmotaxis_distance_var.set(99.0)
        config_widget._on_save_clicked()

        assert len(errors) == 1
        assert not saves
        assert "0.1" in errors[0].error and "10.0" in errors[0].error

    def test_valid_form_still_saves(self, config_widget, event_bus):
        """A guarda nova não pode bloquear o caminho feliz."""
        errors = self._captured(event_bus, UIEvents.CONFIG_VALIDATION_ERROR)
        saves = self._captured(event_bus, UIEvents.CONFIG_SAVE_REQUESTED)

        config_widget._on_save_clicked()

        assert not errors
        assert len(saves) == 1
        assert saves[0].values["video_processing"]["fps"] == 30
