# Test Map: source → tests

Quick lookup for which tests cover which source area. Use this **before** modifying
production code to know which tests to run / extend.

> Last refreshed: 2026-05-09. Counts may drift; pattern column stays accurate.

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
- `tests/i18n/` (6) — catalogue integrity and the untranslated-literal ratchet
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
