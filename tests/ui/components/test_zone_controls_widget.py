"""Tests for ZoneControlsWidget core behaviors."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from zebtrack.core.services.roi_rule_resolver import (
    DEFAULT_BUFFER_RADIUS_VALUE,
    DEFAULT_MIN_BBOX_OVERLAP_RATIO,
    DEFAULT_ROI_INCLUSION_RULE,
    RoiRuleConfig,
)
from zebtrack.ui import payloads
from zebtrack.ui.components.zone_controls import ZoneControlsWidget
from zebtrack.ui.event_bus_v2 import UIEvents


@pytest.fixture
def event_bus():
    bus = Mock()
    bus.publish = Mock()
    bus.subscribe = Mock()
    return bus


@pytest.fixture
def widget(tkinter_root, event_bus):
    zone_widget = ZoneControlsWidget(tkinter_root, event_bus=event_bus)
    tkinter_root.update_idletasks()
    event_bus.publish.reset_mock()
    return zone_widget


@pytest.mark.gui
def test_set_draw_roi_enabled(widget):
    widget.set_draw_roi_enabled(True)

    assert str(widget.draw_roi_button["state"]) == "normal"
    assert str(widget.conclude_video_btn["state"]) == "normal"

    widget.set_draw_roi_enabled(False)

    assert str(widget.draw_roi_button["state"]) == "disabled"
    assert str(widget.conclude_video_btn["state"]) == "disabled"


@pytest.mark.gui
def test_update_template_list(widget):
    widget.update_template_list(["A", "B"])

    assert widget.roi_template_combobox["values"] == ("A", "B")


@pytest.mark.gui
def test_add_and_clear_zone_list(widget):
    widget.add_zone_to_list("zone-1", "Arena", "Polígono", "Azul")
    widget.add_zone_to_list("zone-2", "ROI 1", "ROI", "Vermelho")

    assert len(widget.zone_listbox.get_children("")) == 2

    widget.clear_zone_list()

    assert widget.zone_listbox.get_children("") == ()


@pytest.mark.gui
def test_get_video_path_from_item(widget):
    item_id = widget.video_selector_tree.insert("", "end", tags=("C:/video.mp4",))

    assert widget._get_video_path_from_item(item_id) == "C:/video.mp4"

    no_path_id = widget.video_selector_tree.insert("", "end", tags=("not_a_path",))

    assert widget._get_video_path_from_item(no_path_id) is None


@pytest.mark.gui
def test_toggle_video_tree_label(widget):
    widget._video_tree_expanded = True
    widget._update_video_tree_toggle_label()
    assert widget.video_tree_toggle_btn.cget("text") == "Collapse all"

    widget._video_tree_expanded = False
    widget._update_video_tree_toggle_label()
    assert widget.video_tree_toggle_btn.cget("text") == "Expand all"


@pytest.mark.gui
def test_roi_shortcut_emits_open_advanced_settings(widget, event_bus):
    """A aba de Zonas só RESUME a regra; editar é na aba Advanced Settings.

    Duas UIs editando ``project_data["roi_settings"]`` é como as duas divergem —
    e a cópia daqui era a pior: omitia ``roi_bbox_overlap_basis`` (deixando o
    denominador do "Min. overlap" ambíguo) e o pré-requisito ``persist_masks``
    do ``seg_overlap``.
    """
    widget._on_open_roi_settings_clicked()

    event_bus.publish.assert_called_with(
        UIEvents.ZONE_OPEN_ROI_SETTINGS,
        payloads.EmptyPayload(),
    )


@pytest.mark.gui
def test_roi_summary_shows_only_the_parameter_the_rule_uses(tkinter_root, event_bus):
    """Mostrar todo parâmetro em toda regra era o que tornava o painel enganoso."""
    widget = ZoneControlsWidget(
        tkinter_root,
        event_bus=event_bus,
        roi_rule_config=RoiRuleConfig(rule="centroid_in"),
    )
    tkinter_root.update_idletasks()

    # ``centroid_in`` ignora buffer e overlap — nenhum dos dois pode aparecer.
    params = widget.roi_rule_params_var.get()
    assert "overlap" not in params.lower()
    assert "buffer" not in params.lower()


@pytest.mark.gui
def test_roi_summary_names_seg_overlap_prerequisites(tkinter_root, event_bus):
    """``seg_overlap`` degrada silenciosamente sem máscaras — o resumo tem de avisar."""
    widget = ZoneControlsWidget(
        tkinter_root,
        event_bus=event_bus,
        roi_rule_config=RoiRuleConfig(rule="seg_overlap"),
    )
    tkinter_root.update_idletasks()

    params = widget.roi_rule_params_var.get()
    assert "seg" in params.lower()
    assert "bbox_intersects" in params


@pytest.mark.gui
def test_on_video_search_changed_emits_event(widget, event_bus):
    widget.video_search_var.set("demo")
    widget._on_video_search_changed()

    event_bus.publish.assert_called_with(
        UIEvents.ZONE_VIDEO_SEARCH_CHANGED,
        {"search_text": "demo"},
    )


@pytest.mark.gui
def test_on_video_tree_double_click_emits_event(widget, event_bus):
    item_id = widget.video_selector_tree.insert("", "end")
    widget.video_selector_tree.selection_set(item_id)

    widget._on_video_tree_double_click(Mock())

    event_bus.publish.assert_called_with(
        UIEvents.ZONE_VIDEO_DOUBLE_CLICK,
        payloads.ZoneVideoDoubleClickPayload(item_id=item_id),
    )


@pytest.mark.gui
def test_reconfigure_subjects_updates_metadata_and_refreshes(widget, event_bus):
    project_manager = Mock()
    project_manager.project_data = {"calibration": {"num_aquariums": 1, "animals_per_aquarium": 1}}
    project_manager.find_video_entry.return_value = {
        "path": "C:/video.mp4",
        "metadata": {"group": "Controle", "day": 1, "subject": "S01"},
    }
    project_manager.get_available_groups.return_value = ["Controle", "Tratamento"]
    project_manager.update_video_metadata.return_value = True

    widget.parent = SimpleNamespace(controller=SimpleNamespace(project_manager=project_manager))
    widget._context_menu_video_path = "C:/video.mp4"

    with patch("zebtrack.ui.components.zone_controls.VideoMetadataDialog") as mock_dialog:
        mock_dialog.return_value.result = {
            "group": "Tratamento",
            "day": 2,
            "subject": "S02",
        }

        widget._on_reconfigure_subjects_clicked()

    project_manager.update_video_metadata.assert_called_once_with(
        "C:/video.mp4",
        {"group": "Tratamento", "day": 2, "subject": "S02"},
    )
    event_types = [call.args[0] for call in event_bus.publish.call_args_list]
    assert UIEvents.VIDEO_METADATA_UPDATED in event_types
    assert UIEvents.PROJECT_VIEWS_REFRESH_REQUESTED in event_types


@pytest.mark.gui
def test_roi_panel_shows_the_effective_settings_not_literals(tkinter_root, event_bus):
    """O painel exibe a regra EFETIVA recebida, não números escritos no widget.

    Regressão do bug que motivou este teste: a aba de Zonas mostrava 0.10
    (literal) enquanto a análise usava o valor do ``config.yaml``.
    """
    config = RoiRuleConfig(
        rule="centroid_in_on_buffered_roi",
        buffer_radius_value=2.5,
        min_bbox_overlap_ratio=0.42,
    )
    widget = ZoneControlsWidget(tkinter_root, event_bus=event_bus, roi_rule_config=config)
    tkinter_root.update_idletasks()

    assert "centroid_in_on_buffered_roi" in widget.roi_rule_summary_var.get()
    # A regra bufferizada usa o RAIO; o overlap não participa dela.
    assert "2.5" in widget.roi_rule_params_var.get()


@pytest.mark.gui
def test_roi_panel_without_config_uses_the_canonical_defaults(widget):
    """Sem config injetada, os defaults vêm do resolvedor — não de literais."""
    assert DEFAULT_ROI_INCLUSION_RULE in widget.roi_rule_summary_var.get()
    assert widget._roi_rule_config.buffer_radius_value == DEFAULT_BUFFER_RADIUS_VALUE
    assert widget._roi_rule_config.min_bbox_overlap_ratio == DEFAULT_MIN_BBOX_OVERLAP_RATIO


@pytest.mark.gui
def test_set_roi_rule_config_reseeds_the_panel(widget):
    widget.set_roi_rule_config(RoiRuleConfig("bbox_intersects", 1.0, 0.0))

    assert "bbox_intersects" in widget.roi_rule_summary_var.get()
    assert "0" in widget.roi_rule_params_var.get()


def test_tab_builder_resolves_the_effective_rule_for_the_panel():
    """A aba semeia o painel com projeto > global, via resolvedor canônico."""
    from zebtrack.ui.components.tab_builder import TabBuilder

    project_manager = SimpleNamespace(
        project_data={"roi_settings": {"roi_min_bbox_overlap_ratio": 0.42}}
    )
    settings = SimpleNamespace(
        roi_inclusion_rule="bbox_intersects",
        roi_buffer_radius_value=1.5,
        roi_min_bbox_overlap_ratio=0.10,
        roi_bbox_overlap_basis="max",
    )
    gui = SimpleNamespace(
        project_manager=project_manager,
        controller=SimpleNamespace(settings=settings),
    )

    config = TabBuilder(gui)._resolve_roi_rule_for_panel()  # type: ignore[arg-type]

    assert config.min_bbox_overlap_ratio == 0.42  # projeto vence
    assert config.bbox_overlap_basis == "max"  # global preenche o resto


# NOTA: os testes do hint de overlap por regra e da ajuda do ``seg_overlap``
# saíram daqui junto com o editor duplicado. Esse comportamento agora pertence à
# aba Advanced Settings, o editor único, e está coberto em
# ``tests/ui/components/test_config_editor.py``
# (``test_seg_overlap_warning_appears_only_when_masks_are_off`` e o teste de
# ajuda que exige ``persist_masks`` + ``animal_method``). O lado do resumo desta
# aba está em ``test_roi_summary_names_seg_overlap_prerequisites``.
