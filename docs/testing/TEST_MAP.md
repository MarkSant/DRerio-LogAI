# Test Map: source → tests

Quick lookup for which tests cover which source area. Use this **before** modifying
production code to know which tests to run / extend.

> Last refreshed: 2026-11-04 (v8.0.0). Counts may drift; pattern column stays accurate.

## Top-level rule

The test tree mirrors `src/zebtrack/`, with two exceptions:

1. **88 legacy `tests/test_*.py`** at the root — pre-reorganization tests covering
   `core/`, `io/`, `analysis/`, `tracker/`, `state_manager`, `settings`, etc. When
   touching code without an obvious mirror, **also grep `tests/test_*.py`**.
2. **`tests/integration/`** — cross-component E2E tests (wizard, multi-aquarium,
   live camera). Run when changing public flow boundaries.

## Layer mapping

| Source area                           | Files | Test location                                   | Files |
| ------------------------------------- | ----- | ----------------------------------------------- | ----- |
| `src/zebtrack/coordinators/`          | 23    | `tests/coordinators/test_*.py`                  | 13    |
| `src/zebtrack/analysis/`              | 11    | `tests/analysis/test_*.py`                      | 21    |
| `src/zebtrack/analysis/reporters/`    | 7     | `tests/analysis/test_*reporter*.py`             | (in analysis/) |
| `src/zebtrack/core/detection/`        | 8     | `tests/core/test_*detect*.py`, `test_tracker_*` | (mixed) |
| `src/zebtrack/core/project/`          | 14    | `tests/core/test_project_*.py`, `test_*_manager*` | (mixed) |
| `src/zebtrack/core/recording/`        | 7     | `tests/core/test_*recording*`, `test_live_*`    | (mixed) |
| `src/zebtrack/core/services/`         | 7     | `tests/core/test_*service*.py`                  | (mixed) |
| `src/zebtrack/core/conditions/`       | 3     | `tests/core/conditions/test_*.py`               | 3     |
| `src/zebtrack/core/video/`            | 14    | `tests/core/test_video_*.py`, `tests/core/video/test_*.py` | (mixed) |
| `src/zebtrack/core/viewmodels/`       | 4     | `tests/core/test_*view_model*.py`               | (mixed) |
| `src/zebtrack/io/`                    | 10    | `tests/io/test_*.py` + root `tests/test_io_*.py`| 8 + 3 |
| `src/zebtrack/plugins/`               | 3     | `tests/test_plugins_*.py`                       | (root) |
| `src/zebtrack/tracker/`               | 4     | `tests/test_*tracker*.py`, `test_hybrid_matching` | (root) |
| `src/zebtrack/ui/builders/`           | 7     | `tests/ui/builders/test_*.py`                   | 3     |
| `src/zebtrack/ui/components/`         | 28    | `tests/ui/components/test_*.py`                 | 27    |
| `src/zebtrack/ui/components/canvas/`  | 5     | `tests/ui/components/test_canvas*.py`           | (in components/) |
| `src/zebtrack/ui/components/project_views/` | 6 | `tests/ui/components/test_project_view*`       | (in components/) |
| `src/zebtrack/ui/dialogs/`            | 25    | `tests/ui/dialogs/test_*.py` + `test_dialogs_batch*.py` | 10 |
| `src/zebtrack/ui/wizard/`             | 18    | `tests/ui/wizard/test_*.py`                     | 13    |
| `src/zebtrack/ui/` (root)             | 11    | `tests/ui/test_*.py`                            | 16    |
| `src/zebtrack/utils/`                 | 10    | `tests/utils/test_*.py`                         | 10    |

**Cross-cutting (no source mirror):**

- `tests/integration/` (14) — E2E flows: wizard, multi-aquarium, and the two
  cross-flow guards below
- `tests/quality/` (3) — AST meta-tests over the suite and the source itself:
  hollow tests, orphan UI events, shared-`Settings` writes
- `tests/i18n/` (7) — catalogue integrity, `.pot` in sync with the source, and the
  untranslated-literal ratchet
- `tests/helpers/` — shared drivers, not tests. `prerecorded_pipeline.py` runs the
  real pre-recorded worker in-process and is imported by both guards below
- `tests/benchmarks/` (2) — perf checks
- `tests/performance/` (1) — perf regressions
- `tests/orchestrators/` (0 currently — placeholder)

### The cross-flow regression net

The pre-recorded flows were validated end to end in v6.1.0. These three files
exist so that work on the LIVE flows cannot silently move those numbers — the
failure mode that produced four repair PRs (#522, #523, #524, #527) last time.

| File | What it proves |
| --- | --- |
| `tests/integration/test_prerecorded_golden.py` | The pre-recorded pipeline still computes the numbers signed off in v6.1.0. Compares the full trajectory and the whole analysis report against `tests/fixtures/golden/`. Re-record deliberately with `ZEBTRACK_UPDATE_GOLDEN=1`. |
| `tests/integration/test_flow_isolation.py` | A live-dialog run does not change what the pre-recorded pipeline computes — flow A then flow B **in the same process**, which is where this defect class lives and where nothing else in the suite looks. Includes a negative control that fails if the guard stops being load-bearing. |
| `tests/quality/test_shared_settings_mutations.py` | No NEW assignment into the shared `Settings` object appears without a decision. Allowlist: `tests/quality/shared_settings_allowlist.txt`. |

## High-traffic files → quick lookup

When changing one of these, run the listed test files **specifically** before the
broader suite:

| Changed file | Run these tests first |
| --- | --- |
| `coordinators/multi_aquarium_coordinator.py` | `tests/coordinators/test_multi_aquarium*.py`, `tests/integration/test_multi_aquarium_e2e.py` |
| `coordinators/video_processing_coordinator.py` | `tests/coordinators/test_video_processing*.py` |
| `coordinators/sequential_processing_coordinator.py` | `tests/coordinators/test_sequential*.py` |
| `coordinators/report_generation_coordinator.py` | `tests/coordinators/test_*report*.py`, `tests/analysis/test_reporter*.py` |
| `core/recording/live_camera_service.py` | `tests/core/test_live_camera*.py`, `tests/test_live_camera_workflow_e2e.py` |
| **Anything on a LIVE path, before pushing** | `tests/integration/test_flow_isolation.py`, `tests/integration/test_prerecorded_golden.py`, `tests/quality/test_shared_settings_mutations.py` — the pre-recorded flows must still compute the v6.1.0 numbers |
| `ui/dialogs/live_analysis_dialog.py`, `ui/dialogs/single_video_config_dialog.py` (they write into the SHARED `Settings`) | `tests/quality/test_shared_settings_mutations.py`, `tests/integration/test_flow_isolation.py` |
| `core/services/project_settings_snapshot.py` | `tests/core/test_project_settings_snapshot.py`, `tests/integration/test_flow_isolation.py` |
| `core/video/processing_worker.py` | `tests/core/test_processing_worker_unit.py`, `tests/core/video/test_processing_worker_extended.py`, `tests/integration/test_prerecorded_golden.py` |
| `analysis/analysis_service.py` | `tests/analysis/test_analysis_service*.py`, `tests/integration/test_prerecorded_golden.py` |
| `analysis/analysis_service.resolve_sharp_turn_threshold` (limiar de curvas) | `tests/analysis/test_sharp_turn_threshold_resolver.py` + `scripts/mutation_check.py --module sharp_turn_threshold`. A tabela do `.docx` e o **gráfico** têm de usar o MESMO limiar — eram 90 e 45 |
| `core/recording/frame_processing_pipeline.py`, `core/recording/frame_ledger.py` | `tests/core/recording/`, `tests/core/test_closed_loop_latency.py`, `tests/core/test_arduino_zone_dispatch.py` |
| `core/recording/live_session_manager.py` (parada, limpeza de pastas, status de start) | `tests/core/recording/test_live_session_manager_extended.py`, `tests/core/recording/test_live_session_stop_intent.py` (intenção de parada: descartar × preservar) |
| `core/recording/live_analysis_post_processor.py` (escala px→cm, pós-análise) | `tests/core/recording/test_live_analysis_post_processor.py`, `tests/core/services/test_live_calibration_scale.py` |
| `core/services/live_calibration_scale.py` (px→cm ao vivo) | `tests/core/services/test_live_calibration_scale.py` + `scripts/mutation_check.py --module live_calibration_scale` |
| `scripts/mutation_check.py`, `scripts/mutation_catalog.yaml` | `tests/quality/test_mutation_check.py`. O CI roda `--changed-since HEAD^ --jobs 4`: um mapeamento arquivo→módulo errado não falha, ele **deixa de checar em silêncio**. O mesmo arquivo prova o isolamento: o mutante vive numa cópia, o pytest da cópia importa a cópia (`PYTHONPATH`), e um ou vários workers geram o mesmo relatório |
| `core/recording/live_output_paths.py` (pasta padrão sem projeto) | `tests/core/recording/test_live_output_paths.py`, `tests/test_live_analysis_ui.py` |
| `ui/builders/analysis_widgets.py` (cancelar × encerrar-e-salvar) | `tests/ui/builders/test_analysis_widgets.py` |
| `core/services/closed_loop_latency.py` | `tests/core/test_closed_loop_latency.py` (CSV columns are append-only!) |
| `core/services/wizard_service.py` | `tests/test_wizard_*.py`, `tests/ui/wizard/`, `tests/integration/test_wizard*` |
| `core/state_manager.py` | `tests/test_state_manager*.py` (4 files) |
| `core/project/project_manager.py` (or any project/ module) | `tests/test_project_manager.py`, `tests/core/test_project_*` |
| `io/recorder.py` | `tests/test_recorder.py` (immutable schema!) |
| `io/camera.py`, `io/live_stream_source.py` | `tests/io/test_camera*.py`, `tests/io/test_live_stream_source.py` |
| `analysis/reporters/*` | `tests/analysis/test_reporter*.py`, `test_*_reporter.py` |
| `analysis/behavior*.py`, `analysis/roi.py` | `tests/test_behavior_geotaxis.py`, `tests/analysis/test_roi*.py` |
| `core/services/roi_rule_resolver.py` (regra de ROI) | `tests/core/services/test_roi_rule_resolver.py`, `tests/coordinators/test_roi_rule_propagation.py`, `tests/core/test_arduino_roi_evaluator.py`, `tests/ui/components/test_roi_settings_persistence.py`, `tests/ui/components/test_zone_controls_widget.py` |
| `core/services/arena_detection_policy.py` (método seg/det + forma da máscara da arena) | `tests/core/test_arena_detection_policy.py`, `tests/coordinators/test_multi_aquarium_coordinator.py`, `tests/coordinators/test_live_calibration_coordinator.py` |
| `core/services/zone_autoimport_policy.py` (adotar ou não os parquets de zona achados em disco) | `tests/core/services/test_zone_autoimport_policy.py`, `tests/ui/components/test_dialog_manager.py` (marcador `gui`, `-k zone_reuse`) |
| `core/project/zone_manager.py` → `should_mirror_to_global` (espelho `detection_zones`) | `tests/core/test_project_manager_core.py` (um teste por fluxo: pré-gravado, live, sem tipo declarado) |
| Troca de projeto (`PROJECT_MANAGER_REPLACED`, `PROJECT_OPENED`) | `tests/core/test_project_manager_replaced_event.py`, `tests/core/test_zone_context_service.py`, `tests/coordinators/test_project_lifecycle_coordinator_unit.py`, `tests/ui/components/test_project_model_configuration_panel.py` (marcador `gui`) |
| `analysis/data_transformer.py` (colunas do resumo, tabela `por_animal`) | `tests/analysis/test_data_transformer.py`, `tests/analysis/test_data_transformer_roi_metrics.py` (regressão das colunas antigas!) |
| `analysis/reporters/excel_reporter.py` (abas do `.xlsx`) | `tests/analysis/reporters/test_excel_reporter.py`, `tests/analysis/reporters/test_excel_reporter_sheets.py` |
| `ui/components/config_editor.py` (formulário global, `recorder.persist_masks`) | `tests/ui/components/test_config_editor.py` (marcador `gui`) |
| `analysis/roi.py` (fração de sobreposição, base e limiar 0) | `tests/analysis/test_roi_analyzer.py` (`TestBboxOverlapBasis`, `TestZeroThresholdIsPureIntersection`), `tests/analysis/test_roi_invariants.py` |
| `tracker/byte_tracker.py` | `tests/test_byte_tracker_single_animal.py`, `test_tracker_threading_stress.py` |
| `ui/wizard/*` | `tests/ui/wizard/` (13 files) + `tests/test_wizard_*.py` |
| `ui/dialogs/*` | `tests/ui/dialogs/` + `tests/test_aquarium_dialogs.py` |
| `ui/event_bus_v2.py` (UIEvents) | `tests/ui/test_*event*.py`, `tests/test_ui_*` |
| `settings.py` | `tests/test_settings.py`, `tests/test_settings_injection.py` |

## v8.0.0 modules (class roles, object sidecar, analysis window, time base)

Rows merged from the front fragments in `docs/tasks/v8/changelog/`. `--module <name>` is the
block in `scripts/mutation_catalog.yaml`; run it with
`python scripts/mutation_check.py --module <name>`.

| Source | Tests |
| --- | --- |
| `analysis/time_base.py` | `tests/analysis/test_time_base.py` + `--module time_base` |
| `analysis/roi.py` (latency, rising edge, `t0`, censoring) | `tests/analysis/test_roi_analyzer.py` (`TestLatencyRisingEdge`, `TestExplicitT0`, `TestLatencyWithDebounce`, `TestLatencyPerAnimal`), `tests/test_property_roi.py::TestLatencyProperties` + `--module roi_latency` |
| `analysis/analysis_service.py` (`duracao_video_s`, `analysis_window`) | `tests/analysis/test_analysis_service.py` + `--module video_duration` |
| `coordinators/report_generation_coordinator.py` (real fps, ledger re-timing) | `tests/coordinators/test_report_generation_coordinator.py::TestRealTimeBase` + `--module report_fps` |
| v7.2 → v8 report diff (ADR-013) | `tests/integration/test_prerecorded_golden.py::test_v8_report_differs_from_v72_only_where_declared` (`EXPECTED_V8_CHANGES`) |
| `core/detection/class_roles.py` | `tests/core/detection/test_class_roles.py` + `--module class_roles` |
| `core/services/worker_model_resolution.py` | `tests/core/services/test_worker_model_resolution.py`, `tests/core/test_processing_worker_unit.py` + `--module worker_model_resolution` |
| `core/services/weight_manager.py` (class roles, sha256, OpenVINO cache) | `tests/core/services/test_weight_manager_extended.py` + `--module weight_manager` |
| `core/detection/single_detector.py` (roles, context crop, observations) | `tests/core/detection/test_single_detector_extended.py` + `--module single_detector_class_roles` |
| `core/detection/multi_aquarium_detector.py` (roles) | `tests/core/detection/test_multi_aquarium_detector_extended.py` + `--module multi_aquarium_detector_class_roles` |
| `core/detection/detection_post_processor.py` (context helpers) | `tests/core/detection/test_detection_post_processor_extended.py` + `--module detection_post_processor_class_roles` |
| `core/services/detector_service.py` (role gate) | `tests/core/test_detector_service.py`, `tests/test_class_names_validation.py` + `--module detector_service_class_roles` |
| `plugins/openvino_detector.py` (NMS per class) | `tests/plugins/test_openvino_detector_extended.py` + `--module openvino_nms` |
| `core/project/project_lifecycle_manager.py` (v8 migrations) | `tests/core/project/test_project_lifecycle_manager_extended.py`, `tests/integration/test_legacy_project_7_2_0.py` + `--module project_v8_migrations` |
| `core/project/project_workflow_service.py` (`model_selection`, wizard class roles) | `tests/core/test_project_workflow_service.py` (`TestWizardClassRoles`) + `--module project_workflow_model_selection` |
| 7.2.0 compatibility (ADR-013 invariant 4) | `tests/integration/test_legacy_project_7_2_0.py` |
| `core/services/object_capture.py` | `tests/core/services/test_object_capture.py` + `--module object_capture` |
| `io/object_sidecar.py` | `tests/io/test_object_sidecar.py` + `--module object_sidecar` |
| `io/recorder.py` (object sidecar, stale cleanup) | `tests/test_recorder.py` + `--module recorder_object_sidecar` |
| `core/video/processing_worker.py` (model spec, object sidecar writes) | `tests/core/test_processing_worker_unit.py` + `--module processing_worker_model_spec`, `--module processing_worker_object_sidecar` |
| `core/video/tracking_session_runner.py` (object sidecar writes) | `tests/core/test_video_processing_service_tracking.py` |
| `core/project/parquet_io_manager.py` (sidecar set on import) | `tests/test_parquet_import.py` + `--module parquet_import_sidecars` |
| `utils/report_files.py` (`3c_`/`7_` labels) | `tests/utils/test_session_output_listing.py` + `--module session_output_labels` |
| `core/conditions/*.py` | `tests/core/conditions/` (unit + Barnes VFR + hypothesis properties: batch ≡ online, back-dating, STOP ≥ START, duplicates) + `--module conditions_model`, `conditions_evaluator`, `conditions_artifact` |
| `core/conditions/presets.py` | `tests/core/conditions/test_presets.py` (Barnes preset ≡ acceptance fixture by hash; legacy-trigger preset) + `--module conditions_presets` |
| `analysis/window_observations.py` | `tests/analysis/test_window_observations.py` (3c heartbeat → observations, report ROI rule, external events, trajectory-only fallback, `missing_inputs`) + `--module window_observations` |
| `analysis/analysis_window_service.py` | `tests/analysis/test_analysis_window_service.py` (reuse by spec/input hashes, offline vs online, external events kept, not-met policies, spec lookup) + `--module analysis_window_service` |
| `analysis/behavior.py` (`restrict_to_window`) | `tests/analysis/test_behavior.py::TestRestrictToWindow` + hypothesis properties + `--module analysis_window_cut` |
| `analysis/behavior.py` + `analysis/gap_policy.py` (tracking gaps, episodes per subject) | `tests/analysis/test_behavior.py::TestTrackingGaps` + `--module behavior_tracking_gaps` |
| `analysis/analysis_service.py` (gap-cut distance, `roi_max_gap_s` → behaviour) | `tests/analysis/test_analysis_service.py` (`*tracking_gap*`, `*roi_cap*`) + `--module analysis_service_tracking_gaps` |
| `analysis/trajectory_validator.py` (`total_frames`, `temporal_coverage`, `count_unique_frames`) | `tests/analysis/test_trajectory_validator.py::TestFramesAndCoverageCountFrames` + `--module frames_not_rows_validator` |
| `analysis/analysis_service.py` (`total_frames_analisados` with a window) | `tests/analysis/test_analysis_service.py` (`*frames_analysed*`) + `--module frames_not_rows_service` |
| `analysis/roi.py` (`restrict_to_window`, `from_rule`, `presence_timeline`) | `tests/analysis/test_roi_analyzer.py::TestRestrictToWindow*` + `--module analysis_window_cut_roi` |
| `analysis/analysis_service.py` (`window=`) | `tests/analysis/test_analysis_service.py` (window block) + `--module analysis_window_cut_service` |
| `analysis/metrics_cache.py` (window key) | `tests/analysis/test_metrics_cache.py` + `--module metrics_cache_window` |
| `analysis/data_transformer.py` (`window_*`, latency flags) | `tests/analysis/test_data_transformer.py`, `tests/analysis/test_data_transformer_roi_metrics.py` + `--module report_window_columns` |
| `analysis/reporters/html_reporter.py`, `analysis/time_axis.py` (time axis, freezing keys, window) | `tests/analysis/reporters/test_html_reporter.py::TestHtmlReporterTimeAndFreezing` + `--module html_report_time`, `report_time_axis` |
| `analysis/reporters/word_reporter.py` (window note, event log) | `tests/analysis/reporters/test_word_reporter.py::TestAnalysisWindowSection` + `--module word_report_window` |
| `analysis/visualization_generator.py` (time axes) | `tests/analysis/test_visualization_generator.py::TestWindowTimeAxes` + `--module visualization_window_axes` |
| `analysis/reporters/reporter_context.py` (`window=`) | `tests/analysis/reporters/test_reporter_context.py::TestReporterContextWindow` + `--module reporter_context_window` |
| `coordinators/report_generation_coordinator.py` (window wiring) | `tests/coordinators/test_report_generation_coordinator.py::TestAnalysisWindowWiring` + `--module report_window_wiring` |
| `core/video/analysis_pipeline_runner.py` (window wiring) | `tests/core/video/test_analysis_pipeline_runner.py::TestAnalysisWindowResolution` + `--module pipeline_runner_window` |
| `core/recording/condition_runtime.py` | `tests/core/recording/test_condition_runtime.py` + `--module condition_runtime` |
| `core/recording/frame_processing_pipeline.py` (window, 3c, Arduino inside the window) | `tests/core/recording/test_frame_processing_pipeline_extended.py` (`TestObjectSidecarLive`, `TestAnalysisWindowLive`, `TestArduinoCommandsInsideTheWindow`, real `_processing_loop`) + `--module live_window_pipeline` |
| `core/recording/frame_ledger.py` (`pin_origin`, `origin_perf`) | `tests/core/recording/test_frame_ledger.py` |
| `core/recording/live_analysis_post_processor.py` (ledger retime, multi role map, window) | `tests/core/recording/test_live_analysis_post_processor.py` (`TestPostAnalysisWindow`) + `--module live_post_processor_v8`, `--module live_post_analysis_window` |
| `core/services/external_trigger_gate.py` (window rules) | `tests/core/services/test_external_trigger_gate.py::TestAnalysisWindowWaitingForArduino` + `--module external_trigger_gate` |
| `io/arduino_manager.py` (read-time stamp, event sink) | `tests/test_io_arduino_manager.py` + `--module arduino_event_stamp` |
| `core/main_view_model.py` (Arduino routing) | `tests/core/test_main_view_model_arduino_event.py`, `tests/test_live_batch_integration.py` + `--module arduino_event_routing` |
| `coordinators/live_camera_session_coordinator.py` (`owns_arduino_events`, manual mark, conflict) | `tests/test_live_batch_integration.py`, `tests/coordinators/test_live_camera_session_coordinator.py` + `--module arduino_trigger_session` |
| `ui/components/event_dispatcher.py` + `dialog_manager.py` (window state banner) | `tests/ui/components/test_event_dispatcher.py::TestAnalysisWindowStateChanged` (`-m gui`) |
| `ui/components/tab_builder.py` ("Mark start/stop") | `tests/ui/components/test_tab_builder.py::TestMarkWindowEventButton` (`-m gui`) |
| `ui/components/analysis_window_panel.py` | `tests/ui/components/test_analysis_window_panel.py` (pure line model + preview in the fast suite; Tk panel under `-m gui -n0`) + `--module analysis_window_panel` |
| `ui/wizard/templates.py` (v4 migration) | `tests/ui/wizard/test_wizard_templates.py` (`TestMigrateTemplate` is pure; `TestApplyTemplateData` is `gui`) + `--module wizard_templates` |
| `ui/components/class_roles_panel.py` | `tests/ui/components/test_class_roles_panel.py` (validation, pre-fill, stale sha, both scopes, event, context: fast suite; Tk panel and dialog: `-m gui -n0`) + `--module class_roles_panel` |
| `ui/components/canvas/overlay_roles.py` | `tests/ui/components/canvas/test_overlay_roles.py`; renderer/frame wiring in `test_canvas_renderer.py`, `test_canvas_manager.py` + `--module overlay_roles` |
| `coordinators/model_diagnostics_coordinator.py` (class roles) | `tests/coordinators/test_model_diagnostics_coordinator.py::TestReportClassRoles` |
| `ui/wizard/model_selection_step.py` (class roles) | `tests/ui/wizard/test_model_selection_step.py::TestModelSelectionClassRoles` |
| Barnes acceptance (ADR-011) | `tests/integration/test_barnes_window_e2e.py` |
| `src/zebtrack/locales/*` (any new `_()`) | `tests/i18n/test_pot_in_sync.py` (every source msgid is in the `.pot`), `tests/i18n/test_catalog_integrity.py` |

## Special markers

- `@pytest.mark.gui` — GUI tests, run with `-n0` (sequential), excluded by default
- `@pytest.mark.slow` — long-running, excluded by default
- `@pytest.mark.integration` — cross-component E2E
- `@pytest.mark.unit` — pure unit tests

Run cheatsheet:

```bash
poetry run pytest                            # fast (default, ~2778)
poetry run pytest -m gui -n0                 # GUI only (~949)
poetry run pytest -m slow                    # slow only (~35)
poetry run pytest -m "" -n0                  # everything (~3660+, 6-7 min)
poetry run pytest tests/coordinators/ -q     # by folder
poetry run pytest -k "multi_aquarium" -q     # by keyword
```

## Updating this map

When you add a **new module** in `src/zebtrack/`, append a row above. When you
add a **new test folder**, update the layer mapping table. Don't try to keep
exact file counts perfectly synced — patterns are what matter for routing.
