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
    assert widget.video_tree_toggle_btn.cget("text") == "Recolher tudo"

    widget._video_tree_expanded = False
    widget._update_video_tree_toggle_label()
    assert widget.video_tree_toggle_btn.cget("text") == "Expandir tudo"


@pytest.mark.gui
def test_on_roi_rule_changed_only_updates_the_help_text(widget, event_bus):
    """Trocar o combo é feedback visual; nada é aplicado até o "Aplicar".

    O evento que este handler publicava (``DETECTOR_UPDATE_PARAMETERS``) tem um
    pipeline que descarta as chaves de ROI e loga sucesso — um no-op enganoso.
    """
    widget.roi_inclusion_rule_var.set("centroid_in_on_buffered_roi")
    widget._on_roi_rule_changed(None)

    assert "centroide" in widget.rule_help_label.cget("text")
    event_bus.publish.assert_not_called()


@pytest.mark.gui
def test_apply_roi_settings_emits_persisting_event(widget, event_bus):
    """O botão "Aplicar" precisa emitir o evento QUE PERSISTE, não o do detector.

    ``DETECTOR_UPDATE_PARAMETERS`` descarta ``rule``/``buffer_radius``/
    ``overlap_ratio`` em silêncio e ainda loga sucesso.
    """
    widget.roi_inclusion_rule_var.set("bbox_intersects")
    widget.roi_buffer_radius_var.set("1.2")
    widget.roi_overlap_ratio_var.set("0.25")

    widget._on_apply_roi_settings_clicked()

    event_bus.publish.assert_called_with(
        UIEvents.ZONE_APPLY_ROI_SETTINGS,
        payloads.RoiSettingsApplyPayload(
            rule="bbox_intersects", buffer_radius="1.2", overlap_ratio="0.25"
        ),
    )


@pytest.mark.gui
def test_apply_roi_settings_with_invalid_text_does_not_raise(widget, event_bus):
    """``float()`` no callback do Tk mataria o clique com texto inválido."""
    widget.roi_inclusion_rule_var.set("centroid_in")
    widget.roi_buffer_radius_var.set("abc")
    widget.roi_overlap_ratio_var.set("")

    widget._on_apply_roi_settings_clicked()  # não pode levantar

    event_bus.publish.assert_called_with(
        UIEvents.ZONE_APPLY_ROI_SETTINGS,
        payloads.RoiSettingsApplyPayload(rule="centroid_in", buffer_radius="abc", overlap_ratio=""),
    )


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

    assert widget.roi_inclusion_rule_var.get() == "centroid_in_on_buffered_roi"
    assert widget.roi_buffer_radius_var.get() == "2.5"
    assert widget.roi_overlap_ratio_var.get() == "0.42"


@pytest.mark.gui
def test_roi_panel_without_config_uses_the_canonical_defaults(widget):
    """Sem config injetada, os defaults vêm do resolvedor — não de literais."""
    assert widget.roi_inclusion_rule_var.get() == DEFAULT_ROI_INCLUSION_RULE
    assert float(widget.roi_buffer_radius_var.get()) == DEFAULT_BUFFER_RADIUS_VALUE
    assert float(widget.roi_overlap_ratio_var.get()) == DEFAULT_MIN_BBOX_OVERLAP_RATIO


@pytest.mark.gui
def test_set_roi_rule_config_reseeds_the_panel(widget):
    widget.set_roi_rule_config(RoiRuleConfig("bbox_intersects", 1.0, 0.0))

    assert widget.roi_inclusion_rule_var.get() == "bbox_intersects"
    assert widget.roi_overlap_ratio_var.get() == "0"


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


@pytest.mark.gui
@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        ("bbox_intersects", "0 = qualquer sobreposição real."),
        ("seg_overlap", "Deve ser maior que 0."),
    ],
)
def test_overlap_hint_depends_on_the_selected_rule(widget, rule, expected):
    """O 0 vale só em ``bbox_intersects``; em ``seg_overlap`` o validador recusa.

    Um texto fixo "0 = qualquer sobreposição real" induzia ao erro com
    ``seg_overlap`` selecionada.
    """
    widget.roi_inclusion_rule_var.set(rule)
    widget._on_roi_rule_changed(None)

    assert widget.overlap_hint_label.cget("text") == expected


@pytest.mark.gui
def test_seg_overlap_help_names_the_two_missing_prerequisites(widget):
    """A ajuda de ``seg_overlap`` nomeia as chaves que faltam, não só "requer máscaras".

    Dizer "requer dados de máscara" deixava o operador num beco sem saída: a
    regra é selecionável, mas sem ``recorder.persist_masks`` e sem um modelo de
    segmentação a análise degrada para ``bbox_intersects`` toda vez.
    """
    widget.roi_inclusion_rule_var.set("seg_overlap")
    widget._on_roi_rule_changed(None)

    help_text = widget.rule_help_label.cget("text")
    assert "persist_masks" in help_text
    assert "animal_method" in help_text
    assert "seg" in help_text
    assert "bbox_intersects" in help_text
