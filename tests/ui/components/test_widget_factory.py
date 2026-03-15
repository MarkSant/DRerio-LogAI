"""Tests for WidgetFactory utility helpers."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from zebtrack.ui.components.widget_factory import STATUS_SYMBOLS, WidgetFactory


class _ValidationManagerStub:
    def _format_day_display(self, value):
        if value in (None, ""):
            return ""
        return str(value)


@pytest.fixture
def factory():
    gui = SimpleNamespace(validation_manager=_ValidationManagerStub())
    return WidgetFactory(gui)


def test_build_status_icon_legend_simple(factory):
    legend = factory.build_status_icon_legend_simple()
    assert STATUS_SYMBOLS["arena"] in legend
    assert STATUS_SYMBOLS["rois"] in legend
    assert STATUS_SYMBOLS["trajectory"] in legend
    assert STATUS_SYMBOLS["summary"] not in legend

    legend_with_summary = factory.build_status_icon_legend_simple(include_summary=True)
    assert STATUS_SYMBOLS["summary"] in legend_with_summary


def test_get_zone_summary_helper_text(factory):
    text = factory.get_zone_summary_helper_text()
    assert STATUS_SYMBOLS["summary"] in text
    assert "trajetórias" in text


@pytest.mark.parametrize(
    ("day_value", "metadata", "expected"),
    [
        ("1", {"day_label": "Dia Especial"}, "Dia Dia Especial"),
        ("2", {"day": "2"}, "Dia 2"),
        ("", {}, "Sem Dia"),
        (None, {}, "Sem Dia"),
        ("sem dia", {}, "Sem Dia"),
    ],
)
def test_build_day_title(factory, day_value, metadata, expected):
    assert factory.build_day_title(day_value, metadata) == expected


def test_build_processing_report_artifact_id(factory):
    artifact_a = factory.build_processing_report_artifact_id("parent", "a.csv")
    artifact_b = factory.build_processing_report_artifact_id("parent", "a.csv")
    artifact_c = factory.build_processing_report_artifact_id("parent", "b.csv")

    assert artifact_a == artifact_b
    assert artifact_a != artifact_c
    assert artifact_a.startswith("file_")


def test_build_track_options(factory):
    detections = [
        (0, 0, 0, 0, 0, 2),
        (0, 0, 0, 0, 0, "3"),
        (0, 0, 0, 0, 0, None),
        (0, 0, 0, 0, 0, " "),
        (0, 0, 0, 0, 0),
    ]

    options = factory.build_track_options(detections)

    assert options == ["Todos", "2", "3"]


def test_build_project_actions_calls_button_factory(monkeypatch):
    gui = SimpleNamespace(
        _open_global_calibration_window=Mock(),
        single_video_workflow=SimpleNamespace(on_analyze_single_video_clicked=Mock()),
        project_initializer=SimpleNamespace(
            create_project_workflow=Mock(),
            open_project_workflow=Mock(),
        ),
        controller=SimpleNamespace(start_live_camera_analysis=Mock()),
        validation_manager=_ValidationManagerStub(),
    )
    factory = WidgetFactory(gui)
    create_buttons = Mock()
    monkeypatch.setattr(
        "zebtrack.ui.builders.project_widgets.ButtonFactory.create_project_action_buttons",
        create_buttons,
    )

    factory.build_project_actions(parent=Mock())

    create_buttons.assert_called_once()
    commands = create_buttons.call_args.args[1]
    assert set(commands) == {
        "calibration",
        "single_analysis",
        "live_camera",
        "create_project",
        "open_project",
    }


def test_build_model_status_calls_panel_builder(monkeypatch):
    gui = SimpleNamespace(
        _active_weight_display_var=Mock(),
        _openvino_display_var=Mock(),
        _gpu_hardware_display_var=Mock(),
        validation_manager=_ValidationManagerStub(),
    )
    factory = WidgetFactory(gui)
    build_panel = Mock()
    monkeypatch.setattr(
        "zebtrack.ui.builders.project_widgets.PanelBuilder.build_model_status_panel",
        build_panel,
    )

    factory.build_model_status(parent=Mock())

    build_panel.assert_called_once()


def test_create_zone_summary_cards_section_updates_project_view_manager(monkeypatch):
    zone_summary_frame = Mock()
    zone_summary_frame.winfo_exists.return_value = True
    _vsm = Mock()
    gui = SimpleNamespace(
        zone_controls_frame=Mock(),
        zone_summary_frame=zone_summary_frame,
        zone_summary_cards=None,
        video_selector_manager=_vsm,
        project_view_manager=_vsm,
        validation_manager=_ValidationManagerStub(),
    )
    factory = WidgetFactory(gui)
    create_cards = Mock(return_value=(Mock(), {"arena": Mock()}))
    monkeypatch.setattr(
        "zebtrack.ui.builders.zone_widgets.PanelBuilder.create_zone_summary_cards",
        create_cards,
    )

    factory.create_zone_summary_cards_section()

    zone_summary_frame.destroy.assert_called_once()
    create_cards.assert_called_once()
    gui.video_selector_manager.update_zone_summary_cards.assert_called_once()


def test_create_drawing_buttons_builds_and_positions(monkeypatch):
    gui = SimpleNamespace(
        _drawing_buttons_frame=None,
        drawing_state_manager=SimpleNamespace(undo=Mock(return_value=True), redo=Mock()),
        canvas_manager=SimpleNamespace(renderer=SimpleNamespace(redraw_polygon_in_progress=Mock())),
        video_display=Mock(),
        viz_frame=Mock(),
        validation_manager=_ValidationManagerStub(),
    )
    factory = WidgetFactory(gui)
    frame = Mock()
    create_buttons = Mock(return_value=frame)
    monkeypatch.setattr(
        "zebtrack.ui.builders.zone_widgets.ButtonFactory.create_floating_drawing_buttons",
        create_buttons,
    )

    factory.create_drawing_buttons()

    create_buttons.assert_called_once()
    frame.place.assert_called_once_with(relx=1.0, rely=0.0, anchor="ne", x=-10, y=10)
