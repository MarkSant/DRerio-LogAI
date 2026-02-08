# ÍNDICE DE MÉTODOS POR COMPONENTE - gui.py

Referência rápida para localizar os métodos a extrair. Use com `git blame` ou editor de texto.

## DIALOG MANAGER

Métodos para extrair diretamente (20):

```
  539  _update_window_title()
  843  _open_global_calibration_window()
  847  _open_project_calibration_window()
 1749  show_external_trigger_notice()
 1781  clear_external_trigger_notice()
 3837  _maybe_offer_zone_reuse()
 4785  _open_path_in_explorer()
 5628  _show_template_save_dialog()
 7164  _open_project_workflow()
 7443  show_progress_bar()
 7889  show_error()
 7893  show_warning()
 7897  show_info()
 7901  show_pending_videos_dialog()
 7929  ask_ok_cancel()
 7933  ask_string()
 7937  ask_directory()
 7941  ask_open_filenames()
 8143  ask_save_filename()
 8158  ask_recording_details_unified()
 8172  ask_missing_metadata()
```

Métodos com lógica de diálogos para refatorar:

```
 5407  _on_save_roi_template()
 5649  _on_delete_roi_template()
 5713  _on_import_roi_template()
 5742  _on_import_and_apply_roi_template()
 6529  _run_center_periphery_analysis()
 6546  _create_template_rois()
 7172  _on_analyze_single_video_clicked()
 7382  _on_start_single_video_processing_clicked()
```

---

## VALIDATION MANAGER

Métodos base para extrair (5):

```
 1416  _compose_overview_status_line()
 1490  _prepare_overview_hierarchy_for_widget()
 6803  _check_live_project_calibration()
 7254  _prepare_single_video_ui_state()
 7294  _compose_single_video_runtime_config()
```

Métodos com lógica de validação para refatorar:

```
 7339  _on_auto_detect_clicked()
 5542  _get_zone_data_for_active_context()
```

---

## WIDGET FACTORY

Métodos de criação de frames/widgets (27+):

```
  426  _build_status_icon_legend()
  592  _create_welcome_frame()
  632  _build_project_actions()
  658  _build_model_status()
  882  _create_main_control_frame()
  924  _create_configuration_tab_widget()
  953  _reload_config_editor_values_widget()
 1004  _on_reset_global_config_form_widget()
 1012  _on_save_global_config_from_widget()
 1099  _on_roi_rule_change_widget()
 1105  _create_main_controls_tab()
 1223  _create_project_overview_panel()
 1802  _create_roi_analysis_tab()
 1990  _create_zone_control_widgets()
 2376  _create_zone_summary_cards_section()
 2450  _create_pipeline_processing_tab()
 2967  _create_analysis_tab_widget()
 3003  _create_scrollable_controls_frame()
 3443  _build_day_title()
 3460  _build_video_hierarchy_data()
 3526  _build_video_hierarchy_snapshot()
 3902  _create_reports_tab()
 3967  _create_processing_reports_tab()
 4307  _build_processing_report_artifact_id()
 4453  _build_report_hierarchy()
 4983  _create_drawing_buttons()
 5495  _build_roi_template_identifier()
 6546  _create_template_rois()
 6786  _create_progress_grid_tab()
 7139  _create_project_workflow()
 7681  _build_track_options()
```

Métodos auxiliares (configure handlers):

```
 1860  _on_pane_configure()
 1962  _on_canvas_configure()
 3035  _on_frame_configure()
 3039  _on_canvas_configure_scroll()
 3083  _on_roi_rule_change()
```

---

## PROJECT VIEW MANAGER

Métodos de atualização de views (28+):

```
 1274  _navigate_to_processing_reports_tab()
 1303  _request_overview_refresh()
 1330  refresh_project_views()
 1363  _refresh_project_overview()
 1433  _update_project_overview_summary()
 1468  _update_project_overview_tree()
 1603  _format_status_label()
 1607  _format_status_summary()
 1622  _format_status_ratio()
 1630  _summarize_batch_data()
 1652  _format_data_badges()
 1668  _format_video_metadata()
 1688  _on_project_overview_tree_double_click()
 1699  _on_project_overview_tree_double_click_impl()
 1732  _on_project_overview_right_click()
 2633  _refresh_pipeline_video_table()
 2856  _resolve_processing_reports_video_paths()
 2894  _update_pipeline_buttons_state()
 3585  _format_status_token()
 3589  _populate_video_selector_tree()
 3720  _refresh_video_selector_tree()
 4011  _on_processing_reports_item_double_click()
 4056  _on_processing_reports_generate_partial()
 4087  _refresh_processing_reports_tab()
 4313  _append_processing_reports_artifacts()
 4379  update_reports_tree()
 4453  _build_report_hierarchy()
 4503  _populate_reports_tree_from_hierarchy()
 4614  _append_report_artifacts()
 4670  _on_report_item_select()
 4686  _on_report_item_double_click()
 4718  _handle_report_file_node()
 4731  _handle_report_video_node()
 5853  _update_delete_template_button_state()
 7095  _refresh_openvino_summary()
```

Métodos auxiliares:

```
 1290  _get_status_meta()
 1490  _prepare_overview_hierarchy_for_widget()
 1590  _build_status_token()
 3395  _video_sort_key()
 3403  _format_subject_label()
 3421  _format_day_display()
 3443  _build_day_title()
 4284  _determine_status_tag()
 4307  _build_processing_report_artifact_id()
 4329  _resolve_artifact()
 4429  _sort_key_for_reports()
 4436  _format_subject_for_reports()
 4627  _resolve_artifact()
```

---

## MÉTODOS JÁ EXTRAÍDOS (NÃO INCLUIR)

### MenuManager
- Métodos de criação de menus
- Context menus
- Métodos de menu bar

### CanvasManager
- `_on_canvas_click()`
- `_on_canvas_motion()`
- `_on_canvas_double_click()`
- `_on_handle_press()`
- `_on_handle_drag()`
- `_on_handle_release()`
- `_on_vertex_drag_motion()`
- `_on_vertex_drag_end()`
- `_on_drawing_undo()`
- `_on_drawing_redo()`
- Canvas transformations
- Drawing modes

### StateSynchronizer
- State observation
- State update callbacks

### EventDispatcher
- Event bus subscriptions
- Event handlers

---

## DICAS DE REFATORAÇÃO

1. **Começar por DialogManager**: Menos dependências, mais simples
2. **Depois ValidationManager**: Será usado por Dialog e Widget Factory
3. **WidgetFactory**: Maior impacto, mas depois que Dialog/Validation estão prontos
4. **ProjectViewManager**: Bastante autossuficiente

### Dependências Entre Componentes

```
ValidationManager
├─ usado por: DialogManager, WidgetFactory, ProjectViewManager
└─ depende de: nada (clean)

DialogManager
├─ usado por: WidgetFactory, handlers de UI
├─ depende de: ValidationManager (para validações de diálogos)
└─ depende de: ui/dialogs/* (já existentes)

WidgetFactory
├─ usado por: ApplicationGUI.__init__
├─ depende de: DialogManager, ValidationManager
└─ depende de: ui/components/* (já existentes)

ProjectViewManager
├─ usado por: event handlers, refresh calls
├─ depende de: ValidationManager, DialogManager (algumas views)
└─ depende de: models, project_manager
```
