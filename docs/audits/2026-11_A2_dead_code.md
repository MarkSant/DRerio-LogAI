# A2 — Dead code audit (TASK-087)

- Date: 2026-11-14
- Base: branch `worktree-cov-plugins-utils` (b627f6f3), which already removed the dead code of
  `plugins/` and `utils/` (A2-01 to A2-03 in the loose-ends register).
- Scope: all 316 modules under `src/zebtrack`.
- Rule of this audit: it REPORTS. Nothing under `src/`, `tests/` or `scripts/` was changed, and
  nothing is deleted. The maintainer decides each deletion.
- Register entries this report expands: A2-04, A2-05, A2-06, A2-07, A2-08, A2-09, A2-10, and
  adds findings the register did not have (`CreateProjectDialog`, `DetectorContextManager`, the
  state-observer classes, `WizardData`, one unreachable `return`).

## Method

1. A throwaway AST script (outside the repository) built a module import graph and a name-reference
   index over `src/zebtrack`. A name counts as referenced when it appears as an `ast.Name`, an
   `ast.Attribute`, an `ImportFrom` alias, or inside a short string constant (so `getattr`, string
   dispatch, `@patch`-style paths and lazy `__getattr__` maps are not missed).
2. Every module candidate, class candidate and the large function clusters were then confirmed by
   reading the code and by a second `grep` over `src` and `tests`.
3. Tests are NOT callers. The "Tests that exist only for it" column lists test files that would go
   with the symbol.
4. The four flows (pre-recorded project, single video, live project, ad-hoc live) all start from the
   same composition root, `core/di_registrations.py`, and none constructs anything outside it, so a
   symbol with zero references in `src` is dead in all four. Where a flow could plausibly be the
   only user (live preview, wizard, multi-aquarium) it is named in the evidence.

## Summary

| Category | Confirmed / likely | Needs maintainer | Lines of code |
| --- | --- | --- | --- |
| 1. Modules imported by nothing | 3 | 1 (`exceptions.py`, shim) | 213 (+135) |
| 2. Modules only re-exported by an `__init__` | 8 | 0 | 2,047 |
| 3. Classes never instantiated | 11 | 4 (exception types) | 937 |
| 4. Functions and methods with no caller | 206 | 61 | about 5,800 |
| 5. Unreachable code | 5 sites | 0 | about 50 |
| 6. Duplicated implementations | 1 pair (2 functions) | 0 | about 80 |

Notes on the counts:

- Category 2 counts `ui/dialogs/create_project_dialog.py`, which was not in the register's list of
  seven. `coordinators/project_coordinator.py` is counted once, in category 3.
- Category 3 lines include the 681 lines of `ProjectCoordinator`. The "needs maintainer" four are
  exception subclasses that nothing raises or catches but that are part of a public hierarchy.
- Category 4 is the AST result of 337 zero-reference definitions, minus 29 Pydantic validators and
  `Dialog.apply`/`buttonbox` overrides, minus 21 definitions that live in the dead modules above,
  minus 17 refuted or reported elsewhere, minus 3 duck-typed names. The 61 "needs maintainer" rows have a string occurrence of
  their name somewhere in `src`, which may be dispatch.
- Lines are physical lines including docstrings. They overlap nowhere between categories.

## Findings: modules and classes

| ID | Location | Kind | Evidence | Tests that exist only for it | Confidence | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| A2-D-001 | `analysis/behavioral_analyzer.py:11` (42 lines) | module, class `BehavioralAnalyzer` | `grep -rn "analysis.behavioral_analyzer" src` returns nothing; `analysis/__init__.py` does not re-export it. Read: `analyze()` returns `random.uniform` values seeded by `hash(path)`. The `BehavioralAnalyzer` that `data_transformer.py:17` and `roi.py:21` import comes from `analysis/behavior.py` (the real one, about 860 lines), not from this module. | `tests/analysis/test_behavioral_analyzer.py`, `tests/analysis/test_behavioral_analyzer_extended.py`, `tests/test_analysis_behavioral_analyzer.py` | confirmed | delete the module and the three test files. Production never exercises it; it is a trap for anyone importing the wrong `BehavioralAnalyzer`. |
| A2-D-002 | `coordinators/_protocols.py:25,60` (80 lines) | module, 2 Protocols | `grep -rnw "UnifiedReportHost\|VideoSelectionHost" src` finds only the definitions and two docstring mentions in `_unified_report_mixin.py:41` and `_video_selection_mixin.py:45`. No annotation, no `cast`, no `TYPE_CHECKING` import uses them, so mypy gains nothing. | none | confirmed | delete, or wire it as `self: UnifiedReportHost` in the mixins if the typing intent is still wanted (rewire). Default: delete and drop the two docstring references. |
| A2-D-003 | `ui/components/validators/config_validator.py:13` (91 lines) | module, class `ConfigValidator` | `grep -rnw ConfigValidator src tests` returns only the definition. The package `ui/components/validators/` has no other member in use. | none | confirmed | delete (register A2-09). |
| A2-D-004 | `coordinators/project_coordinator.py:50` (681 lines) | class `ProjectCoordinator`, `ProjectCoordinatorError` | `grep -rn "ProjectCoordinator\b" src` returns the `coordinators/__init__.py` import and `__all__` plus a docstring in `core/recording/live_output_paths.py:31`. `core/di_registrations.py` never registers it and `grep -rni "project_coordinator\b" src` is empty. Project creation lives in `ProjectLifecycleCoordinator` and `ProjectWorkflowService`. Three of its `_publish_event` calls publish strings no one can subscribe to (register A1-01). | `tests/coordinators/test_project_coordinator.py` (41 tests) | confirmed | delete the module, the `__init__` re-export and the test file. Largest item of this audit. |
| A2-D-005 | `io/frame_source_factory.py:23` (234 lines) | module, class `FrameSourceFactory` | `grep -rnw FrameSourceFactory src` returns only the module itself and the `io/__init__.py` re-export. Live uses `io/camera.py` and `io/live_stream_source.py` directly; pre-recorded uses `io/video_source.py`. `CLAUDE.md` lists the file under "I/O & Processing", so the guide is stale too. | `tests/io/test_frame_source_factory.py` | confirmed | delete with its test and update `CLAUDE.md`. |
| A2-D-006 | `io/sources.py:15` (49 lines) | module, function `create_source` | `grep -rnw create_source src` returns the definition and the `io/__init__.py` re-export only. | `tests/test_io_sources.py` (17 tests) | confirmed | delete with its test. |
| A2-D-007 | `ui/components/analysis_controls.py:19` (249 lines) | module, class `AnalysisControlsWidget` | no `src` module imports it from `ui.components`; `grep -rnw AnalysisControlsWidget src` returns the module and the `__init__`. The analysis tab is built by `ui/builders/analysis_widgets.py`, which does not use this widget. | `tests/ui/components/test_analysis_controls_widget.py` | confirmed | delete with its test. |
| A2-D-008 | `ui/components/base_component.py:50` (327 lines) | module, `BaseUIComponent`, `UIComponentError` | nothing subclasses `BaseUIComponent`; its own docstring examples (`LayoutManager`, `MenuManager`) are not real subclasses (`MenuManager` does not inherit it). | `tests/ui/components/test_base_ui_component.py` | confirmed | delete with its test. |
| A2-D-009 | `ui/components/control_panel.py:15` (186 lines) | module, class `ControlPanelWidget` | `grep -rnw ControlPanelWidget src` returns the module and the `__init__`. | `tests/ui/components/test_control_panel_widget.py`; one assertion in `tests/test_event_bus_migration.py` | confirmed | delete; trim that assertion. |
| A2-D-010 | `ui/dialogs/live_config_dialog.py:46` (262 lines) | module, class `LiveConfigDialog` | no importer outside `ui/dialogs/__init__.py`. Live configuration is a wizard step (`WizardStepID.LIVE_CONFIG`, `ui/wizard/`), so the dialog is the pre-wizard path. | `tests/ui/dialogs/test_live_config_dialog.py`, `tests/ui/dialogs/test_live_config_dialog_new.py` | confirmed | delete with its two tests. |
| A2-D-011 | `ui/dialogs/multi_aquarium_confirm_dialog.py:20` (196 lines) | module, class `MultiAquariumConfirmDialog` | no importer outside `ui/dialogs/__init__.py`. No `src` module constructs it, so the aquarium-count confirmation either happens elsewhere or not at all (not traced). | `tests/ui/test_aquarium_dialogs.py` (shared with other dialogs: delete only the relevant class) | confirmed | delete the module; edit the shared test. |
| A2-D-012 | `ui/dialogs/create_project_dialog.py:31` (544 lines) | module, class `CreateProjectDialog` | NEW, not in the register. `grep -rnw CreateProjectDialog src` returns the module, the `__init__`, and one description string in `settings.py:1089` ("legacy CreateProjectDialog"). The wizard is the only creation path (CLAUDE.md, "Project Wizard"). | `tests/test_interval_frames_config.py` only reads the file's source text (`CREATE_PROJECT_DIALOG_SOURCE`) to assert a string | confirmed | delete, rewrite or drop the source-text assertion, and reword the `settings.py:1089` description. Second largest module item. |
| A2-D-013 | `core/recording/live_camera_service.py:50-99` | class `DetectorContextManager` | `grep -rnw DetectorContextManager src` returns only the definition and its own annotation. `detector.set_context` is the only thing it wraps; whether another site sets the context without it was not traced. | `tests/core/recording/test_detector_context_manager_extended.py` | confirmed | delete with its test. |
| A2-D-014 | `core/state_manager.py:319-343, 350-381, 384-439` | classes `StateObserverProtocol`, `BaseStateObserver`, `ObserverAdapter` (113 lines) | none of the three is referenced in `src` outside the definitions; none is constructed or subclassed in `src`. | `tests/test_state_manager_observer_pattern.py` | confirmed | delete with the file's tests for these three (its alias tests for `register_observer` go with A2-D-101-range rows). |
| A2-D-015 | `ui/wizard/models.py:688-731` | class `WizardData` (44 lines) | `grep -rnw WizardData src tests` returns only the definition. Its two `model_validator`s therefore never run. | none | confirmed | delete. |
| A2-D-016 | `core/project/schemas.py:63-72, 79-80` | `ProjectConfigSchema`, `InvalidProjectConfigError` | zero references in `src`. | `tests/core/test_schemas.py`, `tests/core/project/test_schemas_extended.py` | confirmed | delete both classes and the matching tests; keep `ROITemplateSchema` (live). |
| A2-D-017 | `ui/payloads.py:47, 52, 769` | `VideoPathsPayload`, `SelectionPayload`, `BatchAnalysisCompletedPayload` | referenced neither directly nor in the `event_bus_v2.py` payload registry (the other payload classes are, through `.payloads.X`). | `tests/ui/test_payloads_extended.py` (part) | likely | delete, after checking that no event is meant to carry them. |
| A2-D-018 | `coordinators/base_coordinator.py:381`, `live_calibration_coordinator.py:76`, `model_diagnostics_coordinator.py:75`, `processing_types.py:50` | `CoordinatorDependencyError`, `LiveCalibrationCoordinatorError`, `ModelDiagnosticsCoordinatorError`, `ProcessingCoordinatorError` (28 lines) | each is re-exported by `coordinators/__init__.py` and tested, but never raised or caught in `src`. | tests that only construct or subclass them | needs maintainer | The error-boundary contract says `*CoordinatorError` is the logging type. Keep until the maintainer decides whether the hierarchy is public API. |
| A2-D-019 | `exceptions.py` (135 lines) | module, shim | no importer in `src` (`grep -rn "zebtrack.exceptions" src` matches only its own docstring). Its docstring says it exists only to keep the import path working. | `tests/test_exceptions_public.py`, `tests/test_detector_parameter_error_boundary.py` | needs maintainer | keep: it is a deliberate public import path, not dead code. Delete only if the maintainer wants to drop that path. |

## Findings: unreachable code

| ID | Location | Kind | Evidence | Tests that exist only for it | Confidence | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| A2-D-020 | `coordinators/report_generation_coordinator.py:117-119` | `pandas` fallback under `pragma: no cover` | `_read_trajectory` falls back to `pd.read_parquet` when `_trajectory_data_service is None`. The only constructor call in `src` is `core/di_registrations.py:468`, which passes `trajectory_data_service=` (line 476). | none (uncovered by design) | confirmed | delete the fallback and make the parameter required, or keep as test convenience: maintainer's call. |
| A2-D-021 | `coordinators/report_generation_coordinator.py:1163-1171` | `cv2` fallback in `_probe_video_dimensions` | same constructor, same registration passes `video_metadata_service=` (line 475). `cap.release()` sits outside `try/finally`. | none | confirmed | delete the fallback. |
| A2-D-022 | `coordinators/report_generation_coordinator.py:1208-1227` | `cv2` fallback in `_extract_cropped_background_frame` | the registration passes `video_frame_extractor=` (line 477). Same unguarded `release()`. | none | confirmed | delete the fallback. |
| A2-D-023 | `coordinators/video_processing_coordinator.py:251-263` | `cv2` fallback in `_get_video_dimensions` | `VideoProcessingCoordinator(` is built only at `di_registrations.py:491`, with `video_metadata_service=` (line 507). The fallback also swallows `Exception`. | none | confirmed | delete the fallback. |
| A2-D-024 | `ui/components/roi_template_manager.py:152` | statement after `return` | `return False` at line 150 is followed by a bare `return True` in the same block. It is the only statement-after-terminator in `src` (AST scan of every block). | none | confirmed | delete the line. |

The four fallbacks are dead in all four flows because every flow obtains these coordinators from the
container. Tests construct the coordinators directly without the services, which is why the
`pragma: no cover` was added; those tests would need the stub services injected instead.

## Findings: duplicated implementations

| ID | Location | Kind | Evidence | Tests that exist only for it | Confidence | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| A2-D-025 | `utils/geometry.py:16` and `:44` versus `utils/__init__.py:81` and `:105` | `polygon_centroid`, `snap_point_to_axes` | The bodies are line-for-line identical (only the docstrings differ). PRODUCTION calls the copy in `utils/__init__.py`: `utils/geometry_service.py:6` does `from zebtrack.utils import Point, polygon_centroid, snap_point_to_axes` and calls them at lines 51 and 76. No `src` module imports them from `utils.geometry`; that module's live members are `simplify_polygon`, `resolve_polygon_epsilon_factor` and `DEFAULT_POLYGON_EPSILON_FACTOR`. | `tests/utils/test_geometry.py` (labelled "duplicated from utils.py tests"), part of `tests/test_property_based.py` | confirmed | delete the two copies in `utils/geometry.py` and the matching test classes, since the `utils/__init__.py` copy is the one in use and keeps its own tests in `tests/utils/test_utils_init.py` (register A2-10). Alternative: move the implementation to `geometry.py` and re-export from `__init__.py`; `__init__` must stay cheap to import (see `core/app_runner.py:124`), so prefer the first option. |

## Candidates refuted

| Candidate | Why it is alive |
| --- | --- |
| `core/detection/single_detector.py` (`SingleDetector`) | imported by `core/detection/__init__.py:18` and aliased as `Detector` (line 23); `DetectorService` and the live pipeline use `Detector`. A name search for `SingleDetector` alone misses it. |
| `analysis/reporters/parquet_reporter.py`, `analysis/reporters/project_reporter.py` | used by `report_generation_coordinator`, `analysis_pipeline_runner` and `_unified_report_mixin` through the package, not by module path. |
| `core/conditions/artifact.py` | used by `analysis_window_service` and `condition_runtime` (`write_artifact`, `read_artifact`, `OnlineWindow`). |
| `ui/builders/zone_control_builder.py`, `ui/components/{config_editor,drawing_state_manager,menu_manager,polygon_drawing_service,project_overview,roi_template_manager,tab_builder}.py` | the module graph sees them only through `ui/components/__init__.py`, but `ui/gui.py` and the builders import the classes from the package. |
| `ui/dialogs/{diagnostic_progress_dialog,live_preview_window}.py` | used by `model_diagnostics_coordinator` and five `core/recording` modules. |
| `exceptions.py` as dead code | a deliberate shim; see A2-D-019. |
| `fetch_weights.py`, `__main__.py` | entry points (excluded by the brief). |
| `on_project_manager_replaced` on six panels (`analysis_window_panel`, `arduino_bindings_panel`, `class_roles_panel`, `model_diagnostics_panel`, `project_model_configuration_panel`, `zone_context_panel`) | called through `getattr(panel, "on_project_manager_replaced", None)` in `ui/gui.py:541`. |
| `hide`, `cleanup`, `build`, `display_frame` | duck-typed names shared across widgets; their string/attribute references are real. |
| Pydantic `field_validator`/`model_validator` methods in `settings.py`, `ui/wizard/models.py`, `core/conditions/model.py`, `core/services/arduino_bindings.py` | run by Pydantic, not by a call site (29 excluded). |
| `Dialog.apply` and `buttonbox` overrides | called by `tkinter.simpledialog.Dialog`. |
| the other `ui/payloads.py` classes | referenced by the registry in `ui/event_bus_v2.py` as `payloads.X`. |
| `ClassRoleSource`, `ClassRolesScope`, `ArtifactExternalEvent`, `AnalysisConfigSettings` | referenced as annotations, enum members or by string. |
| `tracker/matching.py` as a module | alive (`byte_tracker.py` uses `iou_distance`, `fuse_score`, `linear_assignment`, `hybrid_iou_center_distance`); only six of its functions are dead (see appendix). |

## Verified clusters in the function tail

These were read or `grep`-checked individually and are all `confirmed` as having no caller in `src`;
the appendix rows carry the same ids as the symbols.

- `tracker/matching.py`: `merge_matches`, `v_iou_distance`, `embedding_distance`, `gate_cost_matrix`,
  `fuse_motion`, `fuse_iou`. The module's four live functions (`iou_distance`, `fuse_score`, `linear_assignment`, `hybrid_iou_center_distance`) are used by `byte_tracker.py`. These
  are leftovers of the ByteTrack port; `fuse_motion` and `v_iou_distance` have no test either.
- `ui/gui.py:726-1037`: `_open_global_calibration_window`, `_open_project_calibration_window`,
  `_on_reset_global_config_form_widget`, `_on_project_overview_tree_double_click`,
  `_on_project_overview_right_click`, `_on_frame_configure`, `_on_canvas_configure_scroll`,
  `_recenter_canvas_image`, `_remove_selected_roi_confirm`, `ask_missing_metadata`, `_on_save_arena`.
  Each name occurs once in `src` (its `def`), so no `bind`, `command=` or `subscribe` reaches it. `DialogManager` and
  `VideoSelectorTreeManager` have same-named counterparts (`open_global_calibration_window`,
  `on_project_overview_tree_double_click`, ...), and those are unreferenced too.
- `ui/components/validation_manager.py`: eleven methods from `validate_roi_template_data` (594)
  through `format_subject_for_reports` (969) have no caller.
- `core/project/project_manager.py:1366-1398`: `set_arena_for_video`, `get_arena_for_video`,
  `set_rois_for_video`, `get_rois_for_video` have no caller and no test. Zones go through
  `save_zone_data`/`get_zone_data` (see the mirroring rules in CLAUDE.md).
- `io/recorder.py:911`: `write_video_frame_multi_aquarium` has no caller; `Recorder.is_multi_aquarium_mode`
  (965) and `get_pause_metadata` (491) are also unreferenced.
- `ui/components/project_views/reports_tree_manager.py:660-760` and
  `video_selector_tree_manager.py:768-916`: methods with no caller; most have no test.
- `ui/components/event_dispatcher.py`: `register_handler`, `register_direct_handler`,
  `unregister_handler`, `get_registered_count` have no caller in `src`.

## What this audit did not cover

- The function tail (category 4) was classified by the AST scan; only the clusters listed above were
  read and `grep`-checked one by one. The remaining rows are `likely` for that reason, and the 61
  `needs maintainer` rows have a name that also appears in a string.
- Not detected by this method, so the real count is higher:
  - a method whose name is shared with a live method elsewhere (the scan is by name, so a dead
    `delete_template` next to a live one counts as referenced);
  - a function called only by another dead function (transitive deadness);
  - a function whose only caller is a test (it is listed when the name occurs nowhere in `src`,
    which includes this case).
- Not examined: dead branches inside live functions, unused imports (Ruff's job), unused
  parameters, dead constants and settings keys, `config.yaml` keys without readers.
- `locales/` and `templates/` data files were not examined.
- Test impact is counted in test files that name the symbol, from a text search; a file that only
  mentions the name in a comment is included.

## Appendix: remaining zero-reference definitions (category 4)

Definitions whose name is never referenced in `src`, outside the dead modules above. `Test files`
counts files under `tests/` that mention the name. Rows marked `needs maintainer` have at least one
string occurrence of the name in `src`.

| ID | Location | Kind | Symbol | Test files naming it | Confidence |
| --- | --- | --- | --- | --- | --- |
| A2-D-101 | `analysis/analysis_service.py:1158` | method | `AnalysisService.validate_trajectory_schema` | 3 | likely |
| A2-D-102 | `analysis/analysis_service.py:1358` | method | `AnalysisService.process_videos_batch` | 2 | likely |
| A2-D-103 | `analysis/analysis_window_service.py:206` | method | `WindowResolution.cache_token` | 1 | likely |
| A2-D-104 | `analysis/behavior.py:170` | method (property) | `BehavioralAnalyzer.track_labels` | 3 | needs maintainer |
| A2-D-105 | `analysis/behavior.py:202` | method (property) | `BehavioralAnalyzer.gap_rows` | 1 | likely |
| A2-D-106 | `analysis/behavior.py:239` | method (property) | `BehavioralAnalyzer.window_is_empty` | 1 | needs maintainer |
| A2-D-107 | `analysis/metrics_cache.py:174` | method | `MetricsCache.get_base_metrics` | 2 | likely |
| A2-D-108 | `analysis/metrics_cache.py:223` | method | `MetricsCache.save_base_metrics` | 2 | likely |
| A2-D-109 | `analysis/roi.py:694` | method (property) | `ROIAnalyzer.unobserved_time_s_by_track` | 0 | likely |
| A2-D-110 | `analysis/roi.py:1958` | method | `ROIAnalyzer.analyze_center_vs_periphery` | 1 | likely |
| A2-D-111 | `analysis/window_observations.py:162` | function | `subject_rois_by_frame` | 1 | needs maintainer |
| A2-D-112 | `coordinators/base_coordinator.py:202` | method | `BaseCoordinator._get_state` | 0 | likely |
| A2-D-113 | `coordinators/live_batch_coordinator.py:551` | method | `LiveBatchCoordinator.get_active_batches` | 2 | likely |
| A2-D-114 | `coordinators/live_batch_coordinator.py:559` | method | `LiveBatchCoordinator.get_batch_for_session` | 1 | likely |
| A2-D-115 | `coordinators/live_calibration_coordinator.py:1564` | method | `LiveCalibrationCoordinator._has_recorded_before` | 1 | likely |
| A2-D-116 | `coordinators/live_camera_session_coordinator.py:1394` | method | `LiveCameraSessionCoordinator.get_live_session_info` | 2 | likely |
| A2-D-117 | `coordinators/live_camera_session_coordinator.py:2222` | method | `LiveCameraSessionCoordinator.mark_manual_window_event` | 2 | needs maintainer |
| A2-D-118 | `coordinators/multi_aquarium_coordinator.py:1047` | method | `MultiAquariumCoordinator._temporary_single_animal_mode` | 2 | likely |
| A2-D-119 | `coordinators/progress_tracking_coordinator.py:705` | method | `ProgressTrackingCoordinator.make_progress_callback` | 2 | likely |
| A2-D-120 | `coordinators/project_lifecycle_coordinator.py:981` | method | `ProjectLifecycleCoordinator.register_project_outputs` | 1 | likely |
| A2-D-121 | `coordinators/recording_session_coordinator.py:479` | method | `RecordingSessionCoordinator.get_recording_info` | 1 | likely |
| A2-D-122 | `coordinators/ui_state_coordinator.py:554` | method | `UIStateController.apply_roi_template` | 1 | likely |
| A2-D-123 | `coordinators/ui_state_coordinator.py:617` | method | `UIStateController.update_main_arena` | 1 | likely |
| A2-D-124 | `coordinators/ui_state_coordinator.py:701` | method | `UIStateController._prepare_processing_ui` | 1 | likely |
| A2-D-125 | `coordinators/ui_state_coordinator.py:715` | method | `UIStateController._finalize_processing` | 1 | likely |
| A2-D-126 | `core/conditions/evaluator.py:520` | method (property) | `ConditionEvaluator.skipped_observations` | 1 | likely |
| A2-D-127 | `core/detection/aquarium_detector.py:1247` | method | `ContourBasedMultiAquariumDetector.detect_multiple_aquariums_from_frame` | 1 | likely |
| A2-D-128 | `core/detection/aquarium_detector.py:1438` | method | `ContourBasedMultiAquariumDetector._validate_aquarium_pair` | 1 | likely |
| A2-D-129 | `core/detection/bbox_area_gate.py:98` | method (property) | `BboxAreaGate.rejections` | 3 | likely |
| A2-D-130 | `core/detection/bbox_area_gate.py:103` | method (property) | `BboxAreaGate.sample_count` | 2 | likely |
| A2-D-131 | `core/detection/detection_post_processor.py:225` | method (static) | `DetectionPostProcessor.validate_track_continuity` | 1 | likely |
| A2-D-132 | `core/detection/detection_types.py:116` | method (property) | `MultiAquariumZoneData.aquarium_count` | 2 | needs maintainer |
| A2-D-133 | `core/detection/multi_aquarium_detector.py:163` | method | `MultiAquariumDetector.pop_class_observations` | 3 | needs maintainer |
| A2-D-134 | `core/detection/multi_aquarium_detector.py:744` | method | `MultiAquariumDetector.detect_partitioned_parallel` | 3 | likely |
| A2-D-135 | `core/detection/multi_aquarium_detector.py:1249` | method | `MultiAquariumDetector.is_multi_aquarium_mode` | 2 | likely |
| A2-D-136 | `core/detection/multi_aquarium_detector.py:1283` | method | `MultiAquariumDetector._point_in_polygon` | 1 | likely |
| A2-D-137 | `core/detection/multi_aquarium_detector.py:1287` | method | `MultiAquariumDetector._crop_aquarium_region` | 1 | likely |
| A2-D-138 | `core/detection/single_detector.py:220` | method | `SingleDetector.pop_class_observations` | 3 | needs maintainer |
| A2-D-139 | `core/detection/single_detector.py:710` | method | `SingleDetector.is_single_subject_mode` | 2 | likely |
| A2-D-140 | `core/detection/single_detector.py:751` | method | `SingleDetector._is_inside_polygon` | 1 | likely |
| A2-D-141 | `core/detection/single_detector.py:1088` | method | `SingleDetector._ensure_simple_tracker` | 0 | likely |
| A2-D-142 | `core/detection/single_detector.py:1161` | method | `SingleDetector._draw_zones` | 0 | likely |
| A2-D-143 | `core/detection/single_detector.py:1236` | method | `SingleDetector._restore_trackers` | 0 | likely |
| A2-D-144 | `core/project/asset_manager.py:94` | method (static) | `AssetManager.ensure_roi_template_dir` | 2 | likely |
| A2-D-145 | `core/project/project_manager.py:308` | method | `ProjectManager.has_trajectory_data_for_aquarium` | 1 | likely |
| A2-D-146 | `core/project/project_manager.py:316` | method | `ProjectManager.has_summary_data_for_aquarium` | 1 | likely |
| A2-D-147 | `core/project/project_manager.py:492` | method | `ProjectManager._validate_project_parameters` | 1 | likely |
| A2-D-148 | `core/project/project_manager.py:1366` | method | `ProjectManager.set_arena_for_video` | 0 | likely |
| A2-D-149 | `core/project/project_manager.py:1376` | method | `ProjectManager.get_arena_for_video` | 0 | likely |
| A2-D-150 | `core/project/project_manager.py:1384` | method | `ProjectManager.set_rois_for_video` | 0 | likely |
| A2-D-151 | `core/project/project_manager.py:1398` | method | `ProjectManager.get_rois_for_video` | 0 | likely |
| A2-D-152 | `core/project/project_service.py:334` | method | `ProjectService.load_metadata_csv` | 1 | likely |
| A2-D-153 | `core/project/project_service.py:506` | method | `ProjectService.save_model_overrides` | 0 | needs maintainer |
| A2-D-154 | `core/project/project_service.py:558` | method | `ProjectService.save_arena_polygon` | 0 | needs maintainer |
| A2-D-155 | `core/project/roi_template_manager.py:213` | method | `ROITemplateManager.load_template` | 4 | likely |
| A2-D-156 | `core/project/roi_template_manager.py:342` | method | `ROITemplateManager.cleanup_orphaned_templates` | 1 | likely |
| A2-D-157 | `core/project/roi_template_manager.py:386` | method | `ROITemplateManager.delete_template` | 3 | likely |
| A2-D-158 | `core/project/video_manager.py:518` | method (static) | `VideoManager.refresh_complete_flag` | 1 | likely |
| A2-D-159 | `core/project/zone_manager.py:829` | method (static) | `ZoneManager.update_entry_zone_flags` | 0 | likely |
| A2-D-160 | `core/recording/condition_runtime.py:315` | method (property) | `ConditionRuntime.origin_perf` | 3 | needs maintainer |
| A2-D-161 | `core/recording/frame_ledger.py:233` | method | `FrameLedger.pin_origin` | 3 | needs maintainer |
| A2-D-162 | `core/recording/frame_ledger.py:248` | method (property) | `FrameLedger.origin_perf` | 3 | needs maintainer |
| A2-D-163 | `core/recording/frame_ledger.py:423` | method | `FrameLedger.rows_snapshot` | 1 | likely |
| A2-D-164 | `core/recording/frame_ledger.py:509` | function | `perf_to_wall` | 2 | likely |
| A2-D-165 | `core/recording/frame_processing_pipeline.py:2129` | method | `FrameProcessingMixin.push_manual_condition_event` | 2 | needs maintainer |
| A2-D-166 | `core/recording/live_camera_mode.py:269` | method | `LiveCameraModeSelector.create_sequential_session_plan` | 0 | likely |
| A2-D-167 | `core/recording/live_camera_mode.py:305` | function | `get_mode_description` | 0 | likely |
| A2-D-168 | `core/recording/live_session_manager.py:186` | method | `LiveSessionManagerMixin.is_session_active` | 4 | needs maintainer |
| A2-D-169 | `core/recording/recording_service.py:91` | method | `RecordingService.set_ui_callbacks` | 2 | likely |
| A2-D-170 | `core/services/arduino_roi_evaluator.py:172` | method (static) | `ArduinoRoiEvaluator.centroid_of_bbox` | 2 | likely |
| A2-D-171 | `core/services/detector_service.py:358` | method | `DetectorService.get_params` | 0 | needs maintainer |
| A2-D-172 | `core/services/detector_service.py:362` | method | `DetectorService.get_parameter_definitions` | 1 | likely |
| A2-D-173 | `core/services/detector_service.py:375` | method | `DetectorService.get_available_configs` | 1 | likely |
| A2-D-174 | `core/services/detector_service.py:379` | method | `DetectorService.get_active_config` | 1 | likely |
| A2-D-175 | `core/services/detector_service.py:385` | method | `DetectorService.set_active_config` | 0 | likely |
| A2-D-176 | `core/services/model_service.py:141` | method | `ModelService.validate_weight` | 1 | likely |
| A2-D-177 | `core/services/model_service.py:182` | method | `ModelService.get_weight_type` | 1 | likely |
| A2-D-178 | `core/services/model_service.py:290` | method | `ModelService.validate_model_configuration` | 1 | likely |
| A2-D-179 | `core/services/model_service.py:369` | method | `ModelService.get_weight_configuration_summary` | 1 | likely |
| A2-D-180 | `core/services/trajectory_data_service.py:59` | method (static) | `TrajectoryDataService.load_trajectory_safe` | 2 | likely |
| A2-D-181 | `core/services/weight_manager.py:1027` | method | `WeightManager.set_default_weight_by_type` | 3 | likely |
| A2-D-182 | `core/services/weight_manager.py:1797` | method | `WeightManager.convert_to_openvino_int8` | 1 | likely |
| A2-D-183 | `core/services/wizard_service.py:169` | method | `WizardService.clear_hardware_cache` | 4 | likely |
| A2-D-184 | `core/services/wizard_service.py:619` | method (static) | `WizardService.suggest_analysis_interval` | 2 | likely |
| A2-D-185 | `core/services/wizard_service.py:644` | method (static) | `WizardService.calculate_experiment_structure` | 1 | likely |
| A2-D-186 | `core/services/wizard_service.py:742` | method (static) | `WizardService.validate_calibration_data` | 1 | likely |
| A2-D-187 | `core/services/wizard_service.py:903` | method (static) | `WizardService.validate_multi_aquarium_config` | 2 | needs maintainer |
| A2-D-188 | `core/state_manager.py:551` | method | `StateManager.register_observer` | 4 | likely |
| A2-D-189 | `core/state_manager.py:593` | method | `StateManager.register_global_observer` | 1 | likely |
| A2-D-190 | `core/state_manager.py:625` | method | `StateManager.unsubscribe_all` | 1 | needs maintainer |
| A2-D-191 | `core/state_manager.py:871` | method | `StateManager.get_state_snapshot` | 3 | likely |
| A2-D-192 | `core/state_manager.py:932` | method | `StateManager.update_state` | 6 | needs maintainer |
| A2-D-193 | `core/state_manager.py:1161` | method | `StateManager.get_history` | 8 | likely |
| A2-D-194 | `core/state_manager.py:1195` | method | `StateManager.clear_history` | 1 | likely |
| A2-D-195 | `core/state_manager.py:1203` | method | `StateManager.dump_state` | 1 | likely |
| A2-D-196 | `core/state_manager.py:1278` | method | `StateManager.verify_state_integrity` | 1 | likely |
| A2-D-197 | `core/ui_scheduler.py:136` | method | `UIScheduler.cancel_scheduled` | 3 | likely |
| A2-D-198 | `core/video/processing_worker.py:571` | function (static) | `_WorkerProcess._format_subject` | 1 | likely |
| A2-D-199 | `core/video/progress_notifier.py:51` | method | `ProgressNotifierMixin.create_progress_callback` | 2 | likely |
| A2-D-200 | `core/video/video_context_factory.py:115` | method | `VideoContextFactoryMixin._seek_to_frame` | 3 | likely |
| A2-D-201 | `core/video/video_metadata_service.py:57` | method (static) | `VideoMetadataService.get_video_info` | 2 | likely |
| A2-D-202 | `core/video/video_processing_service.py:126` | method | `VideoProcessingService.process_frame_source` | 0 | needs maintainer |
| A2-D-203 | `core/viewmodels/analysis_control_view_model.py:265` | method | `AnalysisControlViewModel.auto_detect_zones` | 1 | likely |
| A2-D-204 | `core/viewmodels/hardware_status_view_model.py:113` | method | `HardwareStatusViewModel.setup_arduino` | 0 | likely |
| A2-D-205 | `core/viewmodels/hardware_status_view_model.py:195` | method | `HardwareStatusViewModel._get_arduino_manager` | 0 | likely |
| A2-D-206 | `core/viewmodels/hardware_status_view_model.py:257` | method | `HardwareStatusViewModel.get_weight_names_for_slot` | 1 | needs maintainer |
| A2-D-207 | `i18n.py:292` | function | `lazy` | 11 | needs maintainer |
| A2-D-208 | `i18n.py:297` | function | `reset_for_tests` | 2 | likely |
| A2-D-209 | `io/arduino.py:172` | method | `Arduino.send_string_command` | 2 | likely |
| A2-D-210 | `io/arduino_manager.py:220` | method | `ArduinoManager.list_available_ports` | 0 | likely |
| A2-D-211 | `io/arduino_manager.py:472` | method | `ArduinoManager.last_command` | 1 | likely |
| A2-D-212 | `io/camera.py:373` | method | `Camera.read_next_frame` | 2 | needs maintainer |
| A2-D-213 | `io/object_sidecar.py:414` | function | `read_object_sidecar_metadata` | 2 | needs maintainer |
| A2-D-214 | `io/recorder.py:483` | method | `Recorder.is_paused` | 1 | needs maintainer |
| A2-D-215 | `io/recorder.py:491` | method | `Recorder.get_pause_metadata` | 0 | likely |
| A2-D-216 | `io/recorder.py:911` | method | `Recorder.write_video_frame_multi_aquarium` | 1 | likely |
| A2-D-217 | `io/recorder.py:965` | method | `Recorder.is_multi_aquarium_mode` | 2 | likely |
| A2-D-218 | `io/recorder.py:969` | method | `Recorder.get_aquarium_recorders` | 2 | needs maintainer |
| A2-D-219 | `io/recorder.py:1143` | method (property) | `Recorder.mask_parquet_filename` | 1 | likely |
| A2-D-220 | `io/recorder.py:1328` | method (property) | `Recorder.object_parquet_filename` | 1 | likely |
| A2-D-221 | `io/recorder.py:1613` | method | `Recorder._validate_unique_detections` | 0 | likely |
| A2-D-222 | `plugins/base.py:90` | method (property) | `DetectorPlugin.model_input_shape` | 11 | likely |
| A2-D-223 | `plugins/openvino_detector.py:440` | method | `OpenVINOPlugin.set_context_classes_present` | 1 | needs maintainer |
| A2-D-224 | `plugins/openvino_detector.py:455` | method | `OpenVINOPlugin.set_tracking_parameters` | 4 | likely |
| A2-D-225 | `plugins/openvino_detector.py:899` | method (property) | `OpenVINOPlugin.model_input_shape` | 11 | likely |
| A2-D-226 | `plugins/ultralytics_detector.py:351` | method (property) | `UltralyticsDetectorPlugin.model_input_shape` | 11 | likely |
| A2-D-227 | `plugins/ultralytics_detector.py:357` | method | `UltralyticsDetectorPlugin.set_tracking_parameters` | 4 | likely |
| A2-D-228 | `settings.py:363` | method (property) | `YOLOModelSettings.effective_animal_confidence` | 1 | likely |
| A2-D-229 | `settings.py:1686` | function | `reload_settings` | 1 | needs maintainer |
| A2-D-230 | `settings.py:1836` | function | `export_schema` | 1 | needs maintainer |
| A2-D-231 | `tracker/matching.py:9` | function | `merge_matches` | 1 | likely |
| A2-D-232 | `tracker/matching.py:161` | function | `v_iou_distance` | 0 | likely |
| A2-D-233 | `tracker/matching.py:184` | function | `embedding_distance` | 1 | likely |
| A2-D-234 | `tracker/matching.py:201` | function | `gate_cost_matrix` | 1 | likely |
| A2-D-235 | `tracker/matching.py:215` | function | `fuse_motion` | 0 | likely |
| A2-D-236 | `tracker/matching.py:234` | function | `fuse_iou` | 1 | likely |
| A2-D-237 | `ui/builders/common_widgets.py:44` | method | `CommonWidgetsBuilder.build_status_icon_legend_simple` | 1 | likely |
| A2-D-238 | `ui/builders/common_widgets.py:115` | method | `CommonWidgetsBuilder.configure_styles` | 0 | likely |
| A2-D-239 | `ui/builders/common_widgets.py:177` | method | `CommonWidgetsBuilder.prompt_for_weight_type` | 0 | likely |
| A2-D-240 | `ui/builders/zone_control_builder.py:52` | method | `ZoneControlBuilder._ensure_reuse_template_var` | 0 | likely |
| A2-D-241 | `ui/builders/zone_control_builder.py:64` | method (property) | `ZoneControlBuilder.reuse_arena_template_var` | 0 | likely |
| A2-D-242 | `ui/builders/zone_widgets.py:24` | method | `ZoneWidgetsBuilder.create_zone_summary_cards_section` | 1 | likely |
| A2-D-243 | `ui/builders/zone_widgets.py:109` | method | `ZoneWidgetsBuilder.create_scrollable_controls_frame` | 0 | likely |
| A2-D-244 | `ui/builders/zone_widgets.py:136` | method | `ZoneWidgetsBuilder.create_template_rois` | 0 | likely |
| A2-D-245 | `ui/components/analysis_view_controller.py:453` | method | `AnalysisViewController.on_track_selection_changed` | 0 | likely |
| A2-D-246 | `ui/components/analysis_window_panel.py:981` | method (property) | `AnalysisWindowPanel.is_session_only` | 2 | likely |
| A2-D-247 | `ui/components/base.py:155` | method | `BaseWidget.set_enabled` | 1 | likely |
| A2-D-248 | `ui/components/canvas/renderer.py:186` | method | `CanvasRenderer.clear_placeholder_logo` | 1 | likely |
| A2-D-249 | `ui/components/class_roles_panel.py:1240` | method | `ClassRolesPanel.seed_fit` | 1 | likely |
| A2-D-250 | `ui/components/config_editor.py:559` | method | `ConfigEditorWidget.focus_roi_section` | 1 | needs maintainer |
| A2-D-251 | `ui/components/dialog_manager.py:65` | method | `DialogManager.set_dialog_suppression` | 1 | likely |
| A2-D-252 | `ui/components/dialog_manager.py:436` | method | `DialogManager.open_global_calibration_window` | 1 | likely |
| A2-D-253 | `ui/components/dialog_manager.py:443` | method | `DialogManager.open_project_calibration_window` | 1 | likely |
| A2-D-254 | `ui/components/dialog_manager.py:476` | method | `DialogManager.show_template_save_dialog` | 1 | likely |
| A2-D-255 | `ui/components/dialog_manager.py:671` | method | `DialogManager.open_center_periphery_dialog` | 1 | likely |
| A2-D-256 | `ui/components/dialog_manager.py:682` | method | `DialogManager.open_template_rois_dialog` | 1 | likely |
| A2-D-257 | `ui/components/dialog_manager.py:693` | method | `DialogManager.open_single_video_config_dialog` | 1 | likely |
| A2-D-258 | `ui/components/dialog_manager.py:838` | method | `DialogManager.ask_missing_metadata` | 2 | likely |
| A2-D-259 | `ui/components/dialog_manager.py:1174` | method | `DialogManager.confirm_delete_roi_template` | 1 | likely |
| A2-D-260 | `ui/components/dialog_manager.py:1441` | method | `DialogManager.open_path_in_explorer` | 1 | likely |
| A2-D-261 | `ui/components/event_dispatcher.py:204` | method | `EventDispatcher.register_handler` | 3 | likely |
| A2-D-262 | `ui/components/event_dispatcher.py:249` | method | `EventDispatcher.register_direct_handler` | 2 | likely |
| A2-D-263 | `ui/components/event_dispatcher.py:256` | method | `EventDispatcher.unregister_handler` | 1 | likely |
| A2-D-264 | `ui/components/event_dispatcher.py:273` | method | `EventDispatcher.get_registered_count` | 1 | likely |
| A2-D-265 | `ui/components/global_model_configuration_panel.py:101` | method | `TargetChoiceDialog.apply` | 21 | needs maintainer |
| A2-D-266 | `ui/components/menu_manager.py:440` | method | `MenuManager.resolve_overview_asset_from_click` | 1 | likely |
| A2-D-267 | `ui/components/menu_manager.py:483` | method | `MenuManager.show_overview_context_menu` | 1 | likely |
| A2-D-268 | `ui/components/processing_reports.py:735` | method | `ProcessingReportsWidget.collapse_tree_item` | 1 | likely |
| A2-D-269 | `ui/components/processing_reports.py:751` | method | `ProcessingReportsWidget.update_selection_info` | 0 | likely |
| A2-D-270 | `ui/components/project_overview.py:232` | method | `ProjectOverviewWidget.resolve_selected_video_paths` | 2 | needs maintainer |
| A2-D-271 | `ui/components/project_overview.py:313` | method | `ProjectOverviewWidget.get_selected_scope` | 2 | needs maintainer |
| A2-D-272 | `ui/components/project_overview.py:389` | method | `ProjectOverviewWidget.collapse_tree_item` | 1 | likely |
| A2-D-273 | `ui/components/project_views/reports_tree_manager.py:660` | method | `ReportsTreeManager.append_processing_reports_artifacts` | 0 | needs maintainer |
| A2-D-274 | `ui/components/project_views/reports_tree_manager.py:670` | method | `ReportsTreeManager.append_report_artifacts` | 0 | likely |
| A2-D-275 | `ui/components/project_views/reports_tree_manager.py:730` | method | `ReportsTreeManager._refresh_processing_reports_tab` | 0 | likely |
| A2-D-276 | `ui/components/project_views/reports_tree_manager.py:734` | method | `ReportsTreeManager._get_project_status_counts` | 0 | likely |
| A2-D-277 | `ui/components/project_views/reports_tree_manager.py:738` | method | `ReportsTreeManager._populate_reports_tree_from_hierarchy` | 0 | likely |
| A2-D-278 | `ui/components/project_views/reports_tree_manager.py:748` | method | `ReportsTreeManager._delete_video_asset` | 0 | likely |
| A2-D-279 | `ui/components/project_views/reports_tree_manager.py:752` | method | `ReportsTreeManager._delete_all_processing_data` | 0 | likely |
| A2-D-280 | `ui/components/project_views/reports_tree_manager.py:756` | method | `ReportsTreeManager._delete_video_from_project` | 0 | likely |
| A2-D-281 | `ui/components/project_views/reports_tree_manager.py:760` | method | `ReportsTreeManager._delete_all_unified_reports` | 0 | likely |
| A2-D-282 | `ui/components/project_views/video_selector_tree_manager.py:768` | method | `VideoSelectorTreeManager.on_project_overview_tree_double_click` | 0 | likely |
| A2-D-283 | `ui/components/project_views/video_selector_tree_manager.py:812` | method | `VideoSelectorTreeManager.on_project_overview_right_click` | 0 | likely |
| A2-D-284 | `ui/components/project_views/video_selector_tree_manager.py:897` | method | `VideoSelectorTreeManager.refresh_openvino_summary` | 0 | likely |
| A2-D-285 | `ui/components/project_views/video_selector_tree_manager.py:909` | method | `VideoSelectorTreeManager.populate_video_selector_tree` | 0 | likely |
| A2-D-286 | `ui/components/project_views/video_selector_tree_manager.py:916` | method | `VideoSelectorTreeManager.refresh_video_selector_tree` | 0 | likely |
| A2-D-287 | `ui/components/roi_template_manager.py:266` | method | `ROITemplateManager.delete_template` | 3 | likely |
| A2-D-288 | `ui/components/roi_template_manager.py:419` | method | `ROITemplateManager.import_template` | 2 | likely |
| A2-D-289 | `ui/components/state_synchronizer.py:426` | method | `StateSynchronizer.reset_global_config_form_widget` | 0 | likely |
| A2-D-290 | `ui/components/state_synchronizer.py:444` | method | `StateSynchronizer._default_analysis_metadata_text` | 2 | likely |
| A2-D-291 | `ui/components/validation_manager.py:111` | method | `ValidationManager.save_global_config_from_widget` | 2 | likely |
| A2-D-292 | `ui/components/validation_manager.py:202` | method | `ValidationManager.compose_overview_status_line` | 2 | likely |
| A2-D-293 | `ui/components/validation_manager.py:412` | method | `ValidationManager.check_live_project_calibration` | 3 | likely |
| A2-D-294 | `ui/components/validation_manager.py:556` | method | `ValidationManager.get_selected_roi_template` | 1 | needs maintainer |
| A2-D-295 | `ui/components/validation_manager.py:594` | method | `ValidationManager.validate_roi_template_data` | 1 | likely |
| A2-D-296 | `ui/components/validation_manager.py:607` | method | `ValidationManager.validate_arena_for_analysis` | 1 | likely |
| A2-D-297 | `ui/components/validation_manager.py:620` | method | `ValidationManager.validate_arena_polygon_data` | 1 | likely |
| A2-D-298 | `ui/components/validation_manager.py:633` | method | `ValidationManager.validate_positive_integer` | 1 | likely |
| A2-D-299 | `ui/components/validation_manager.py:660` | method | `ValidationManager.validate_active_video_selection` | 1 | likely |
| A2-D-300 | `ui/components/validation_manager.py:885` | method | `ValidationManager.format_roi_template_display` | 1 | likely |
| A2-D-301 | `ui/components/validation_manager.py:927` | method | `ValidationManager.build_roi_template_identifier` | 1 | likely |
| A2-D-302 | `ui/components/validation_manager.py:949` | method (static) | `ValidationManager.format_time` | 1 | likely |
| A2-D-303 | `ui/components/validation_manager.py:969` | method (static) | `ValidationManager.format_subject_for_reports` | 1 | likely |
| A2-D-304 | `ui/components/validation_manager.py:1553` | method | `ValidationManager.apply_roi_settings` | 1 | needs maintainer |
| A2-D-305 | `ui/components/video_display.py:97` | method | `VideoDisplayWidget.load_frame` | 1 | needs maintainer |
| A2-D-306 | `ui/components/video_display.py:182` | method | `VideoDisplayWidget.set_image` | 1 | likely |
| A2-D-307 | `ui/components/video_display.py:271` | method | `VideoDisplayWidget.video_to_canvas` | 1 | likely |
| A2-D-308 | `ui/components/video_display.py:295` | method | `VideoDisplayWidget.canvas_to_video` | 1 | likely |
| A2-D-309 | `ui/components/video_display.py:319` | method | `VideoDisplayWidget.get_image_size` | 1 | likely |
| A2-D-310 | `ui/components/video_display.py:325` | method | `VideoDisplayWidget.get_scale` | 0 | likely |
| A2-D-311 | `ui/components/zone_controls.py:610` | method | `ZoneControlsWidget._build_single_analysis_options` | 0 | likely |
| A2-D-312 | `ui/components/zone_controls.py:1003` | method | `ZoneControlsWidget._on_toggle_view_clicked` | 1 | likely |
| A2-D-313 | `ui/components/zone_controls.py:1033` | method | `ZoneControlsWidget._on_video_refresh_clicked` | 0 | likely |
| A2-D-314 | `ui/components/zone_controls.py:1434` | method | `ZoneControlsWidget.set_roi_rule_config` | 1 | likely |
| A2-D-315 | `ui/components/zone_controls.py:1544` | method | `ZoneControlsWidget.update_template_list` | 1 | likely |
| A2-D-316 | `ui/components/zone_controls.py:1638` | method | `ZoneControlsWidget.get_active_aquarium_id` | 1 | likely |
| A2-D-317 | `ui/components/zone_edit_guard.py:112` | method | `ZoneEditGuard.warn_about_pending_zone_edit` | 0 | likely |
| A2-D-318 | `ui/dialogs/aquarium_assignment_dialog.py:531` | method | `AquariumAssignmentDialog.buttonbox` | 0 | needs maintainer |
| A2-D-319 | `ui/dialogs/aquarium_detection_progress_dialog.py:307` | method | `AquariumDetectionProgressDialog.show_completion` | 0 | likely |
| A2-D-320 | `ui/dialogs/aquarium_detection_progress_dialog.py:330` | method | `AquariumDetectionProgressDialog.close_dialog` | 0 | likely |
| A2-D-321 | `ui/dialogs/calibration_dialog.py:233` | method | `CalibrationDialog.buttonbox` | 0 | needs maintainer |
| A2-D-322 | `ui/dialogs/camera_disconnect_recovery_dialog.py:285` | method | `CameraDisconnectRecoveryDialog.close_dialog` | 0 | likely |
| A2-D-323 | `ui/dialogs/center_periphery_dialog.py:78` | method | `CenterPeripheryDialog.apply` | 21 | needs maintainer |
| A2-D-324 | `ui/dialogs/color_selection_dialog.py:78` | method | `ColorSelectionDialog.apply` | 21 | needs maintainer |
| A2-D-325 | `ui/dialogs/live_analysis_dialog.py:710` | method | `LiveAnalysisDialog.buttonbox` | 0 | needs maintainer |
| A2-D-326 | `ui/dialogs/live_analysis_dialog.py:1029` | method | `LiveAnalysisDialog.apply` | 21 | needs maintainer |
| A2-D-327 | `ui/dialogs/missing_metadata_dialog.py:90` | method | `MissingMetadataDialog.apply` | 21 | needs maintainer |
| A2-D-328 | `ui/dialogs/model_diagnostics_dialog.py:42` | method | `ModelDiagnosticsDialog.buttonbox` | 0 | needs maintainer |
| A2-D-329 | `ui/dialogs/multi_aquarium_live_preview_window.py:128` | method | `MultiAquariumLivePreviewWindow.update_recorded_count` | 0 | likely |
| A2-D-330 | `ui/dialogs/multi_aquarium_live_preview_window.py:258` | method | `MultiAquariumLivePreviewWindow.update_aquarium_frame` | 0 | likely |
| A2-D-331 | `ui/dialogs/pending_videos_dialog.py:139` | method | `PendingVideosDialog.buttonbox` | 0 | needs maintainer |
| A2-D-332 | `ui/dialogs/pending_videos_dialog.py:150` | method | `PendingVideosDialog.apply` | 21 | needs maintainer |
| A2-D-333 | `ui/dialogs/project_video_import_dialog.py:133` | method | `SubjectEntriesDialog.apply` | 21 | needs maintainer |
| A2-D-334 | `ui/dialogs/project_video_import_dialog.py:240` | method | `VideoMetadataDialog.apply` | 21 | needs maintainer |
| A2-D-335 | `ui/dialogs/project_video_import_dialog.py:405` | method | `BatchVideoMetadataDialog.apply` | 21 | needs maintainer |
| A2-D-336 | `ui/dialogs/project_video_import_dialog.py:602` | method | `ProjectVideoImportDialog.buttonbox` | 0 | needs maintainer |
| A2-D-337 | `ui/dialogs/project_video_import_dialog.py:682` | method | `ProjectVideoImportDialog.apply` | 21 | needs maintainer |
| A2-D-338 | `ui/dialogs/save_roi_template_dialog.py:197` | method | `SaveROITemplateDialog.apply` | 21 | needs maintainer |
| A2-D-339 | `ui/dialogs/single_video_config_dialog.py:614` | method | `SingleVideoConfigDialog.apply` | 21 | needs maintainer |
| A2-D-340 | `ui/dialogs/start_recording_dialog.py:239` | method | `StartRecordingDialog.apply` | 21 | needs maintainer |
| A2-D-341 | `ui/dialogs/subject_selection_dialog.py:100` | method | `SubjectSelectionDialog.buttonbox` | 0 | needs maintainer |
| A2-D-342 | `ui/dialogs/template_dialog.py:105` | method | `TemplateDialog.apply` | 21 | needs maintainer |
| A2-D-343 | `ui/gui.py:726` | method | `ApplicationGUI._open_global_calibration_window` | 0 | likely |
| A2-D-344 | `ui/gui.py:741` | method | `ApplicationGUI._open_project_calibration_window` | 0 | likely |
| A2-D-345 | `ui/gui.py:764` | method | `ApplicationGUI._on_reset_global_config_form_widget` | 0 | likely |
| A2-D-346 | `ui/gui.py:793` | method | `ApplicationGUI._on_project_overview_tree_double_click` | 0 | likely |
| A2-D-347 | `ui/gui.py:804` | method | `ApplicationGUI._on_project_overview_right_click` | 0 | likely |
| A2-D-348 | `ui/gui.py:816` | method | `ApplicationGUI._on_frame_configure` | 0 | likely |
| A2-D-349 | `ui/gui.py:821` | method | `ApplicationGUI._on_canvas_configure_scroll` | 0 | likely |
| A2-D-350 | `ui/gui.py:847` | method | `ApplicationGUI._recenter_canvas_image` | 0 | likely |
| A2-D-351 | `ui/gui.py:917` | method | `ApplicationGUI._remove_selected_roi_confirm` | 1 | likely |
| A2-D-352 | `ui/gui.py:1032` | method | `ApplicationGUI.ask_missing_metadata` | 2 | likely |
| A2-D-353 | `ui/gui.py:1037` | method | `ApplicationGUI._on_save_arena` | 0 | likely |
| A2-D-354 | `ui/ui_coordinator.py:636` | method | `UICoordinator.get_statistics` | 1 | likely |
| A2-D-355 | `ui/ui_coordinator.py:897` | method | `UICoordinator.reset_statistics` | 0 | likely |
| A2-D-356 | `ui/wizard/cache.py:46` | method | `WizardCache.get_scan_results` | 0 | likely |
| A2-D-357 | `ui/wizard/cache.py:80` | method | `WizardCache.get_design_detection` | 0 | likely |
| A2-D-358 | `ui/wizard/custom_regex_dialog.py:460` | method | `CustomRegexDialog.buttonbox` | 0 | needs maintainer |
| A2-D-359 | `ui/wizard/custom_regex_dialog.py:545` | method | `CustomRegexDialog.apply` | 21 | needs maintainer |
| A2-D-360 | `ui/wizard/custom_regex_dialog.py:860` | method | `CustomRegexDialog._match_path` | 0 | likely |
| A2-D-361 | `ui/wizard/design_editor_dialog.py:262` | method | `DesignEditorDialog.buttonbox` | 0 | needs maintainer |
| A2-D-362 | `ui/wizard/design_editor_dialog.py:525` | method | `DesignEditorDialog.apply` | 21 | needs maintainer |
| A2-D-363 | `ui/wizard/templates.py:453` | method | `TemplateManager.load_template` | 4 | likely |
| A2-D-364 | `ui/wizard/templates.py:524` | method | `TemplateManager.list_templates` | 1 | likely |
| A2-D-365 | `ui/wizard/templates.py:565` | method | `TemplateManager.delete_template` | 3 | likely |
| A2-D-366 | `ui/wizard/wizard_dialog.py:191` | method | `WizardDialog.buttonbox` | 0 | needs maintainer |
| A2-D-367 | `utils/cache.py:163` | function | `ttl_cache` | 1 | likely |

## Guard that stays (2026-11-19)

`tests/quality/test_no_dead_code.py` runs `vulture` (dev dependency, `^2.14`, locked at 2.16)
over `src/zebtrack` and compares the findings with `tests/quality/vulture_whitelist.txt`.
Tests are not scanned, so a name only a test uses counts as dead in production.

- A finding that is not on the list fails: a new unused function, method, class, attribute,
  variable or unreachable block.
- An entry vulture no longer reports fails too (stale), so the list only shrinks.
- Keys are `<path>::<kind>::<qualified name>` with no line number; a method that shares its
  name with a live one elsewhere is still its own entry.
- Every entry sits under a `[tag] reason` section. The baseline of 423 keys (465 vulture
  lines; write-only attributes assigned in several places collapse to one key):

| Section | Entries | Why it stays |
|---|---|---|
| `pydantic` | 61 | `model_config` and validators, run by Pydantic |
| `tk-hook` | 26 | `apply`/`buttonbox`/`body`, called by `simpledialog.Dialog` |
| `public-api` | 1 | `ApplicationGUI.ask_missing_metadata` (A2-D-352) |
| `enum-member` | 5 | reached by value or iteration, persisted by name |
| `schema-field` | 55 | Pydantic/dataclass/TypedDict fields read by serialization |
| `signature` | 1 | `exc_info` imposed by `shutil.rmtree(onerror=...)` |
| `certain` | 4 | 100% confidence and real: three ignored parameters and an unreachable `return True` in `ROITemplateManager._validate_template_file` |
| `baseline` | 270 | not reviewed one by one; candidate dead code (write-only attributes, 50 unused classes, all of them `ui/payloads.py` payloads with no entry in the `event_bus_v2` registry, and methods nobody names) |

The `getattr` reaches listed in the tail review (A2-D-133/138/161/162/165/168/218/223) do not
appear: they were deleted in the deletion pass or share their name with a live member, which
vulture, like the original scan, cannot tell apart (tail review, section D).

### Proof that the guard sees

1. Planted `def _planted_dead_helper(): return 42` at the end of
   `src/zebtrack/analysis/track_significance.py`. The guard failed with
   `src/zebtrack/analysis/track_significance.py::function::_planted_dead_helper (line 259, 60% confidence)`.
   Restored by copy; SHA-256 prefix `c96417b230549832` before and after.
2. Appended `src/zebtrack/analysis/track_significance.py::function::gone_long_ago` to the
   whitelist. The stale-entry test failed naming that key. Restored; SHA-256 prefix
   `3661bae0b01338e5` before and after.

The exploratory `ruff --select ERA,ARG` pass the plan asked for is in
[`2026-11_A2_ruff_era_arg.md`](2026-11_A2_ruff_era_arg.md): 196 hits, 34 real, nothing fixed.
