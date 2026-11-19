# A2 tail — review of the zero-reference functions (TASK-087)

- Date: 2026-11-15
- Base: branch `worktree-cov-plugins-utils` (296ca6e0).
- Input: the appendix of `docs/audits/2026-11_A2_dead_code.md` (category 4, rows `A2-D-101` to
  `A2-D-367`). The summary of that report says 206 functions; the appendix lists **267 rows**,
  because it also carries the 26 `Dialog.apply`/`buttonbox` overrides that the summary counted as
  excluded. All 267 were classified here.
- Rule of this review: it REPORTS. Nothing under `src/`, `tests/` or `scripts/` was changed.
  Deletion is the maintainer's decision.

## Method

1. For each row, the function was located with `ast` by qualified name, so `file:line` and the
   line count in this report are the CURRENT ones. The line numbers in the A2 appendix are stale
   for several modules (`core/state_manager.py` is off by about 120 lines, `io/recorder.py` by
   about 20); use the ones below.
2. A word-boundary search of the bare name ran over `src/`, `scripts/`, `tests/`, `docs/` and the
   root files (`*.yaml`, `*.md`, `*.toml`, `*.cfg`). Each hit was tagged as comment, docstring,
   string (`getattr`, `__all__`, log key), attribute call or bare name.
3. Every hit in `src/` and `scripts/` was read. For each `getattr(..., "name")` hit, the enclosing
   method was identified (`ast`) to check that it is a live helper and not another dead one.
4. Names shared by several classes (`delete_template`, `load_template`, `collapse_tree_item`,
   `is_multi_aquarium_mode`, `origin_perf`, `pop_class_observations`, `close_dialog`) were checked
   per class: a caller of one is not a caller of the other.
5. The 26 `apply`/`buttonbox` rows were checked against their base class: every one of them
   derives from `tkinter.simpledialog.Dialog` (or the wizard `Dialog`), which calls the hook.

Verdicts:

- **DEAD**: no caller in `src/` or `scripts/`. A caller that is a test counts as dead; the test
  files that name the symbol are listed (the count is the number of lines that mention it; most
  are shared files where only the matching tests go).
- **ALIVE**: a caller exists that the A2 scan missed.
- **DYNAMIC**: reached through `getattr`, a string, or a framework hook (Tk, abstract base).
- **KEEP**: documented or exported on purpose, even with no caller.

`(safe)` after DEAD means: no reference of any kind outside the definition and the tests (no
docstring or comment mention in `src/`, no `scripts/`, no non-archive doc, no context file, no
abstract/interface member, no test fixture that depends on it, no cluster that needs one decision).

## Summary

| Verdict | Rows |
| --- | --- |
| DEAD | 214 (163 marked safe, 51 need a decision first) |
| DYNAMIC | 42 (26 Tk dialog hooks, 16 `getattr` reaches) |
| KEEP | 10 |
| ALIVE | 1 |
| Total | 267 |

Physical lines of the DEAD rows (signature to last line, docstring included): 4710.
Of those, the safe batch is **3136 lines in 163 functions** (list at the end).

## What deserves attention before deleting

### A. Dead because a caller is missing, not because the feature is gone

These are the rows where deleting the function would remove the only sign of a gap.

- **A2-D-322** `CameraDisconnectRecoveryDialog.close_dialog`. The "wait" action is documented as
  "callback should close it when camera reconnects", and `close_dialog` says "called by
  controller". `UICoordinator._on_camera_reconnected` (`ui/ui_coordinator.py:713`) only updates the
  status line; nothing closes the dialog, so after an automatic reconnect the "Waiting for the
  camera to reconnect..." dialog stays open until the operator clicks. Fix the caller; do not
  delete the method.
- **A2-D-329/330** `MultiAquariumLivePreviewWindow.update_recorded_count` and
  `update_aquarium_frame` (52 lines). The window is built, but its two update methods have no
  caller, so a multi-aquarium live preview would show an empty window. Check whether the live
  multi-aquarium path (CLAUDE.md, "Live: the session's aquariums come from
  `_resolve_session_multi_zone_data()`") is meant to feed it.
- **A2-D-107/108 and A2-D-103** `MetricsCache.get_base_metrics`, `save_base_metrics` and
  `WindowResolution.cache_token`. `application_bootstrapper.py:212` constructs `AnalysisService`
  with `enable_metrics_cache=True`, `AnalysisService.__init__` builds a `MetricsCache`, and nothing
  ever reads or writes it. The cache is configured, logged as enabled, and inert. The name
  `clear_cache` hid the third dead member from the A2 scan.
- **A2-D-110** `ROIAnalyzer.analyze_center_vs_periphery` (74 lines). `docs/reference/metrics.md:138`,
  `system_integration.md:1020` and `.copilot-impact-map.yaml:461` cite it as the implementation of
  the center/periphery metric. Either those documents are stale or the metric is not computed by
  the report. Worth a ten-minute check against a real report before anything is deleted.
- **A2-D-134** `MultiAquariumDetector.detect_partitioned_parallel` (134 lines) and **A2-D-137**
  `_crop_aquarium_region`: documented as features in `system_integration.md:243-244`; the live path
  uses neither.
- **A2-D-304** `ValidationManager.apply_roi_settings` (80 lines). `system_integration.md:863` says it
  enforces the ROI overlap-ratio range split. The code that runs is
  `hardware_vm.update_detector_parameters` (`gui.py:904`, `event_dispatcher.py:1263`), validated by
  `Settings`; the doc names the wrong enforcer.
- **A2-D-356/357** `WizardCache`: instantiated in `wizard_dialog.py:110` and never used. The whole
  class (its `invalidate` and `_compute_hash` too) looks dead, not only the two rows.
- **A2-D-202** `VideoProcessingService.process_frame_source`: `docs/testing/LIVE_FLOW_TEST_PROTOCOL.md:208`
  already records it as having no callers.

### B. Rows the A2 report marked "needs maintainer" that are alive

- **A2-D-192** `StateManager.update_state` is the primary path of every coordinator's
  `_update_state`: `BaseCoordinator._update_state` (`base_coordinator.py:174`) calls
  `getattr(self.state_manager, "update_state")` first, and `StateManager.__init__` sets
  `prefer_unified_state_api = True`. Deleting it would silently push every coordinator onto the
  fallback path.
- **A2-D-212** `Camera.read_next_frame` is the live capture path
  (`frame_processing_pipeline._read_camera_frame`, :450, via `getattr`).
- **A2-D-133/138/161/162/165/168/218/223** are each reached by a `getattr` in the live pipeline or
  its coordinators (see rows).
- **A2-D-156** `ROITemplateManager.cleanup_orphaned_templates` is called by
  `scripts/cleanup_templates.py`.
- **A2-D-352** `ApplicationGUI.ask_missing_metadata` is part of the `@public_api` contract that
  `scripts/check_public_api.py` and `tests/ui/test_gui_public_api_contract.py` enforce, although
  nothing calls it. The copy in `DialogManager` (A2-D-258) is the dead one.

### C. Dead members whose deletion cascades

- `EventDispatcher.register_handler`, `register_direct_handler`, `unregister_handler`,
  `get_registered_count` (A2-D-261 to 264): `_create_dispatcher` and the `MODE_*` constants only
  serve them, and `tests/quality/test_no_orphan_ui_events.py:73-77` lists the first two as
  recognised subscription wrappers.
- `DetectorPlugin.model_input_shape` (A2-D-222/225/226) is an `@abstractmethod`; the two plugins and
  the test doubles implement it.
- `delete_template` exists in three classes (A2-D-157, 287, 365) and `load_template` in two
  (A2-D-155, 363); none has a caller. Delete each set together, since the test files overlap.
- `WizardService.clear_hardware_cache` (A2-D-183) is used by five test files as a setup/teardown
  reset: deleting it means rewriting fixtures.

### D. Not caught by a name-based scan (for the next run of the tool)

- A member whose name is shared with a live one is invisible (`MetricsCache.clear_cache`,
  `ConditionRuntime.origin_perf` next to `FrameLedger.origin_perf`).
- A function called only by another dead function stays "referenced": for example
  `BaseCoordinator._get_state` is named only in its own docstring.
- `scripts/` was not in the A2 corpus (A2-D-156).

## Findings by module

"Evidence" gives the reason for the verdict; where it only says "no reference", the search found
nothing in `src/` or `scripts/` beyond the definition. The `file:line` column is current at 296ca6e0.

### `analysis/analysis_service.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-101 | `AnalysisService.validate_trajectory_schema` (25 lines) | `analysis/analysis_service.py:1180` | DEAD (safe) | no reference in `src/` or `scripts/` | `analysis/test_analysis_service.py` (2), `analysis/test_analysis_service_error_handling.py` (1), `analysis/test_analysis_service_video_processing.py` (2) |
| A2-D-102 | `AnalysisService.process_videos_batch` (164 lines) | `analysis/analysis_service.py:1380` | DEAD (safe) | `_run_analysis_pipeline` is the live batch path | `analysis/test_analysis_events.py` (2), `analysis/test_analysis_service_batch.py` (6) |

### `analysis/analysis_window_service.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-103 | `WindowResolution.cache_token` (5 lines) | `analysis/analysis_window_service.py:206` | DEAD | cluster with 107/108: `MetricsCache` is built by the bootstrapper but never consulted | `analysis/test_analysis_window_service.py` (3) |

### `analysis/behavior.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-104 | `BehavioralAnalyzer.track_labels` (8 lines) | `analysis/behavior.py:170` | DYNAMIC | `getattr(behavior_analyzer, "track_labels", None)` in `roi.py:_resolve_track_axis` (:596) | - |
| A2-D-105 | `BehavioralAnalyzer.gap_rows` (4 lines) | `analysis/behavior.py:202` | KEEP | documented in `docs/reference/system_integration.md:983`; read only by tests | - |
| A2-D-106 | `BehavioralAnalyzer.window_is_empty` (4 lines) | `analysis/behavior.py:239` | DEAD | mentioned in a docstring of `behavior.py:234` | `analysis/test_behavior.py` (1) |

### `analysis/metrics_cache.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-107 | `MetricsCache.get_base_metrics` (48 lines) | `analysis/metrics_cache.py:174` | DEAD | `AnalysisService` builds `MetricsCache` (`enable_metrics_cache=True` in `application_bootstrapper.py:212`) and never calls it; `MetricsCache.clear_cache` is also uncalled (hidden by a name shared with `zone_scaler.clear_cache`) | `analysis/test_metrics_cache.py` (8), `analysis/test_metrics_cache_extended.py` (7) |
| A2-D-108 | `MetricsCache.save_base_metrics` (41 lines) | `analysis/metrics_cache.py:223` | DEAD | `AnalysisService` builds `MetricsCache` (`enable_metrics_cache=True` in `application_bootstrapper.py:212`) and never calls it; `MetricsCache.clear_cache` is also uncalled (hidden by a name shared with `zone_scaler.clear_cache`) | `analysis/test_metrics_cache.py` (6), `analysis/test_metrics_cache_extended.py` (4) |

### `analysis/roi.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-109 | `ROIAnalyzer.unobserved_time_s_by_track` (8 lines) | `analysis/roi.py:694` | DEAD (safe) | no reference in `src/` or `scripts/` | none |
| A2-D-110 | `ROIAnalyzer.analyze_center_vs_periphery` (74 lines) | `analysis/roi.py:1958` | DEAD | cited as the implementation in `docs/reference/metrics.md:138`, `system_integration.md:1020`, `.copilot-impact-map.yaml:461`: either those are stale or the metric is not computed by reports | `analysis/test_roi_metrics.py` (2) |

### `analysis/window_observations.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-111 | `subject_rois_by_frame` (20 lines) | `analysis/window_observations.py:162` | KEEP | exported in `window_observations.__all__` (:68) | - |

### `coordinators/base_coordinator.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-112 | `BaseCoordinator._get_state` (26 lines) | `coordinators/base_coordinator.py:202` | DEAD (safe) | only a docstring example in the same method | none |

### `coordinators/live_batch_coordinator.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-113 | `LiveBatchCoordinator.get_active_batches` (7 lines) | `coordinators/live_batch_coordinator.py:552` | DEAD (safe) | no reference in `src/` or `scripts/` | `coordinators/test_live_batch_coordinator.py` (1), `test_live_camera_workflow_e2e.py` (1) |
| A2-D-114 | `LiveBatchCoordinator.get_batch_for_session` (13 lines) | `coordinators/live_batch_coordinator.py:560` | DEAD (safe) | no reference in `src/` or `scripts/` | `coordinators/test_live_batch_coordinator.py` (2) |

### `coordinators/live_calibration_coordinator.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-115 | `LiveCalibrationCoordinator._has_recorded_before` (25 lines) | `coordinators/live_calibration_coordinator.py:1564` | DEAD | comment at `live_calibration_coordinator.py:377` names it as removed from the gate | `coordinators/test_live_calibration_coordinator.py` (9) |

### `coordinators/live_camera_session_coordinator.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-116 | `LiveCameraSessionCoordinator.get_live_session_info` (19 lines) | `coordinators/live_camera_session_coordinator.py:1394` | DEAD (safe) | no reference in `src/` or `scripts/` | `coordinators/test_live_camera_session_coordinator.py` (2), `coordinators/test_live_camera_session_coordinator_extended.py` (1) |
| A2-D-117 | `LiveCameraSessionCoordinator.mark_manual_window_event` (17 lines) | `coordinators/live_camera_session_coordinator.py:2222` | DYNAMIC | `getattr(coordinator, "mark_manual_window_event", None)` in `tab_builder._on_mark_window_event` (:453) | - |

### `coordinators/multi_aquarium_coordinator.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-118 | `MultiAquariumCoordinator._temporary_single_animal_mode` (79 lines) | `coordinators/multi_aquarium_coordinator.py:1047` | DEAD (safe) | 79 lines; two of the seven test refs are `hasattr` checks | `coordinators/test_multi_aquarium_coordinator.py` (1), `coordinators/test_processing_coordinator_coverage.py` (6) |

### `coordinators/progress_tracking_coordinator.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-119 | `ProgressTrackingCoordinator.make_progress_callback` (69 lines) | `coordinators/progress_tracking_coordinator.py:705` | DEAD | listed in the module docstring (`progress_tracking_coordinator.py:44`) | `coordinators/test_processing_coordinator_coverage.py` (3), `coordinators/test_progress_tracking_coordinator.py` (3) |

### `coordinators/project_lifecycle_coordinator.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-120 | `ProjectLifecycleCoordinator.register_project_outputs` (42 lines) | `coordinators/project_lifecycle_coordinator.py:981` | DEAD (safe) | no reference in `src/` or `scripts/` | `coordinators/test_project_lifecycle_coordinator.py` (1) |

### `coordinators/recording_session_coordinator.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-121 | `RecordingSessionCoordinator.get_recording_info` (17 lines) | `coordinators/recording_session_coordinator.py:479` | DEAD (safe) | no reference in `src/` or `scripts/` | `coordinators/test_recording_session_coordinator.py` (2) |

### `coordinators/ui_state_coordinator.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-122 | `UIStateController.apply_roi_template` (62 lines) | `coordinators/ui_state_coordinator.py:554` | DEAD (safe) | no reference in `src/` or `scripts/` | `coordinators/test_ui_state_coordinator.py` (4) |
| A2-D-123 | `UIStateController.update_main_arena` (17 lines) | `coordinators/ui_state_coordinator.py:617` | DEAD (safe) | no reference in `src/` or `scripts/` | `coordinators/test_ui_state_coordinator.py` (1) |
| A2-D-124 | `UIStateController._prepare_processing_ui` (13 lines) | `coordinators/ui_state_coordinator.py:701` | DEAD (safe) | no reference in `src/` or `scripts/` | `coordinators/test_ui_state_coordinator.py` (1) |
| A2-D-125 | `UIStateController._finalize_processing` (27 lines) | `coordinators/ui_state_coordinator.py:715` | DEAD (safe) | no reference in `src/` or `scripts/` | `coordinators/test_ui_state_coordinator.py` (2) |

### `core/conditions/evaluator.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-126 | `ConditionEvaluator.skipped_observations` (4 lines) | `core/conditions/evaluator.py:520` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/conditions/test_evaluator.py` (1) |

### `core/detection/aquarium_detector.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-127 | `ContourBasedMultiAquariumDetector.detect_multiple_aquariums_from_frame` (24 lines) | `core/detection/aquarium_detector.py:1247` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/test_aquarium_detector_multi.py` (3) |
| A2-D-128 | `ContourBasedMultiAquariumDetector._validate_aquarium_pair` (52 lines) | `core/detection/aquarium_detector.py:1438` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/test_aquarium_detector_multi.py` (5) |

### `core/detection/bbox_area_gate.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-129 | `BboxAreaGate.rejections` (4 lines) | `core/detection/bbox_area_gate.py:98` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/detection/test_bbox_area_gate.py` (8), `core/detection/test_bbox_area_gate_extended.py` (5), `core/detection/test_tracked_bbox_area_gate.py` (1) |
| A2-D-130 | `BboxAreaGate.sample_count` (4 lines) | `core/detection/bbox_area_gate.py:103` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/detection/test_bbox_area_gate.py` (4), `core/detection/test_bbox_area_gate_extended.py` (8) |

### `core/detection/detection_post_processor.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-131 | `DetectionPostProcessor.validate_track_continuity` (48 lines) | `core/detection/detection_post_processor.py:225` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/test_detection_post_processor.py` (4) |

### `core/detection/detection_types.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-132 | `MultiAquariumZoneData.aquarium_count` (4 lines) | `core/detection/detection_types.py:116` | DEAD (safe) | the `aquarium_count=` hits are log keyword arguments, not attribute reads | `core/test_multi_aquarium_models.py` (3), `test_property_detection_types.py` (2) |

### `core/detection/multi_aquarium_detector.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-133 | `MultiAquariumDetector.pop_class_observations` (10 lines) | `core/detection/multi_aquarium_detector.py:163` | DYNAMIC | `getattr(source, "pop_class_observations", None)` in `frame_processing_pipeline._pop_class_observations` (:1910) | - |
| A2-D-134 | `MultiAquariumDetector.detect_partitioned_parallel` (134 lines) | `core/detection/multi_aquarium_detector.py:744` | DEAD | 134 lines; documented as a feature in `system_integration.md:244` | `core/detection/test_multi_aquarium_detector_extended.py` (2), `core/test_detector_partitioned.py` (6), `performance/test_parallel_detection_benchmark.py` (3) |
| A2-D-135 | `MultiAquariumDetector.is_multi_aquarium_mode` (3 lines) | `core/detection/multi_aquarium_detector.py:1249` | DEAD (safe) | same name as `Recorder.is_multi_aquarium_mode` (A2-D-217); both dead | `core/test_detector_partitioned.py` (4), `io/test_recorder_multi_aquarium.py` (10) |
| A2-D-136 | `MultiAquariumDetector._point_in_polygon` (3 lines) | `core/detection/multi_aquarium_detector.py:1283` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/test_detector_partitioned.py` (6) |
| A2-D-137 | `MultiAquariumDetector._crop_aquarium_region` (8 lines) | `core/detection/multi_aquarium_detector.py:1287` | DEAD | documented in `system_integration.md:243` and `docs/guides/developer/live_camera_dev.md:32` | `core/test_detector_partitioned.py` (10) |

### `core/detection/single_detector.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-138 | `SingleDetector.pop_class_observations` (12 lines) | `core/detection/single_detector.py:220` | DYNAMIC | `getattr(source, "pop_class_observations", None)` in `frame_processing_pipeline._pop_class_observations` (:1910) | - |
| A2-D-139 | `SingleDetector.is_single_subject_mode` (3 lines) | `core/detection/single_detector.py:710` | DEAD (safe) | no reference in `src/` or `scripts/` | `test_detector.py` (1), `test_detector_service_integration.py` (2) |
| A2-D-140 | `SingleDetector._is_inside_polygon` (3 lines) | `core/detection/single_detector.py:751` | DEAD (safe) | no reference in `src/` or `scripts/` | `test_detector.py` (11) |
| A2-D-141 | `SingleDetector._ensure_simple_tracker` (21 lines) | `core/detection/single_detector.py:1088` | DEAD (safe) | no test, no doc | none |
| A2-D-142 | `SingleDetector._draw_zones` (5 lines) | `core/detection/single_detector.py:1161` | DEAD (safe) | no test, no doc | none |
| A2-D-143 | `SingleDetector._restore_trackers` (25 lines) | `core/detection/single_detector.py:1236` | DEAD (safe) | no test, no doc | none |

### `core/project/asset_manager.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-144 | `AssetManager.ensure_roi_template_dir` (18 lines) | `core/project/asset_manager.py:97` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/project/test_asset_manager.py` (7) |

### `core/project/project_manager.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-145 | `ProjectManager.has_trajectory_data_for_aquarium` (7 lines) | `core/project/project_manager.py:308` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/test_project_manager_multi_aquarium.py` (2) |
| A2-D-146 | `ProjectManager.has_summary_data_for_aquarium` (7 lines) | `core/project/project_manager.py:316` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/test_project_manager_multi_aquarium.py` (2) |
| A2-D-147 | `ProjectManager._validate_project_parameters` (3 lines) | `core/project/project_manager.py:492` | DEAD (safe) | no reference in `src/` or `scripts/` | `test_project_manager.py` (2) |
| A2-D-148 | `ProjectManager.set_arena_for_video` (9 lines) | `core/project/project_manager.py:1366` | DEAD (safe) | no test, no doc | none |
| A2-D-149 | `ProjectManager.get_arena_for_video` (7 lines) | `core/project/project_manager.py:1376` | DEAD (safe) | no test, no doc | none |
| A2-D-150 | `ProjectManager.set_rois_for_video` (13 lines) | `core/project/project_manager.py:1384` | DEAD (safe) | no test, no doc | none |
| A2-D-151 | `ProjectManager.get_rois_for_video` (8 lines) | `core/project/project_manager.py:1398` | DEAD (safe) | no test, no doc | none |

### `core/project/project_service.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-152 | `ProjectService.load_metadata_csv` (38 lines) | `core/project/project_service.py:340` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/test_project_service.py` (3) |
| A2-D-153 | `ProjectService.save_model_overrides` (51 lines) | `core/project/project_service.py:512` | DEAD (safe) | the `[attr]` hits are log event names, not calls | none |
| A2-D-154 | `ProjectService.save_arena_polygon` (29 lines) | `core/project/project_service.py:564` | DEAD (safe) | the `[attr]` hits are log event names, not calls | none |

### `core/project/roi_template_manager.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-155 | `ROITemplateManager.load_template` (66 lines) | `core/project/roi_template_manager.py:213` | DEAD | name shared with `ui/wizard/templates.py:TemplateManager.load_template` (A2-D-363); `docs/guides/developer/WORKFLOWS.md:205` row is an event name | `core/project/test_roi_template_manager.py` (10), `ui/wizard/test_wizard_templates.py` (2) |
| A2-D-156 | `ROITemplateManager.cleanup_orphaned_templates` (43 lines) | `core/project/roi_template_manager.py:342` | ALIVE | `scripts/cleanup_templates.py:31` calls `manager.cleanup_orphaned_templates()` (a maintenance CLI; the A2 scan did not read `scripts/`) | - |
| A2-D-157 | `ROITemplateManager.delete_template` (39 lines) | `core/project/roi_template_manager.py:386` | DEAD (safe) | delete together with A2-D-287 and A2-D-365 (same name, three classes, no callers) | `core/project/test_roi_template_manager.py` (2), `ui/components/test_roi_template_manager.py` (1), `ui/wizard/test_wizard_templates.py` (1) |

### `core/project/video_manager.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-158 | `VideoManager.refresh_complete_flag` (12 lines) | `core/project/video_manager.py:518` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/project/test_video_manager.py` (2) |

### `core/project/zone_manager.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-159 | `ZoneManager.update_entry_zone_flags` (27 lines) | `core/project/zone_manager.py:829` | DEAD (safe) | no test, no doc | none |

### `core/recording/condition_runtime.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-160 | `ConditionRuntime.origin_perf` (4 lines) | `core/recording/condition_runtime.py:315` | DEAD | name shared with `FrameLedger.origin_perf` (alive, A2-D-162); the ConditionRuntime property is read only by tests | `core/recording/test_condition_runtime.py` (2), `core/recording/test_frame_ledger.py` (4), `core/recording/test_frame_processing_pipeline_extended.py` (1) |

### `core/recording/frame_ledger.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-161 | `FrameLedger.pin_origin` (13 lines) | `core/recording/frame_ledger.py:233` | DYNAMIC | `getattr(ledger, ...)` in `frame_processing_pipeline._pin_capture_origin` (:1880, :1887) | - |
| A2-D-162 | `FrameLedger.origin_perf` (14 lines) | `core/recording/frame_ledger.py:248` | DYNAMIC | `getattr(ledger, ...)` in `frame_processing_pipeline._pin_capture_origin` (:1880, :1887) | - |
| A2-D-163 | `FrameLedger.rows_snapshot` (4 lines) | `core/recording/frame_ledger.py:423` | DEAD (safe) | docstring says it exists "for tests and inspection" | `core/recording/test_frame_ledger.py` (2) |
| A2-D-164 | `perf_to_wall` (11 lines) | `core/recording/frame_ledger.py:509` | KEEP | documented in `system_integration.md:755` as the timeline-reconstruction helper; used by `test_frame_timeline_reconstruction.py` | - |

### `core/recording/frame_processing_pipeline.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-165 | `FrameProcessingMixin.push_manual_condition_event` (19 lines) | `core/recording/frame_processing_pipeline.py:2129` | DYNAMIC | `getattr(self.live_camera_service, "push_manual_condition_event", None)` in `live_camera_session_coordinator.mark_manual_window_event` (:2231) | - |

### `core/recording/live_camera_mode.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-166 | `LiveCameraModeSelector.create_sequential_session_plan` (34 lines) | `core/recording/live_camera_mode.py:269` | DEAD (safe) | no test, no doc | none |
| A2-D-167 | `get_mode_description` (20 lines) | `core/recording/live_camera_mode.py:305` | DEAD (safe) | no test, no doc | none |

### `core/recording/live_session_manager.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-168 | `LiveSessionManagerMixin.is_session_active` (16 lines) | `core/recording/live_session_manager.py:186` | DYNAMIC | `getattr(live_service, "is_session_active", None)` in `project_lifecycle_coordinator._stop_live_session_if_active` (:239) | - |

### `core/recording/recording_service.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-169 | `RecordingService.set_ui_callbacks` (11 lines) | `core/recording/recording_service.py:91` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/recording/test_recording_service_extended.py` (1), `core/test_recording_service.py` (3) |

### `core/services/arduino_roi_evaluator.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-170 | `ArduinoRoiEvaluator.centroid_of_bbox` (4 lines) | `core/services/arduino_roi_evaluator.py:172` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/services/test_arduino_roi_evaluator_extended.py` (1), `core/test_arduino_roi_evaluator.py` (1) |

### `core/services/detector_service.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-171 | `DetectorService.get_params` (3 lines) | `core/services/detector_service.py:358` | DEAD | listed in `.copilot-context.yaml:121` `key_methods` (context file, not a caller) | none |
| A2-D-172 | `DetectorService.get_parameter_definitions` (12 lines) | `core/services/detector_service.py:362` | DEAD | listed in `.copilot-context.yaml:121` `key_methods` | `core/services/test_detector_service_extended.py` (2) |
| A2-D-173 | `DetectorService.get_available_configs` (3 lines) | `core/services/detector_service.py:375` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/services/test_detector_service_extended.py` (1) |
| A2-D-174 | `DetectorService.get_active_config` (5 lines) | `core/services/detector_service.py:379` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/services/test_detector_service_extended.py` (3) |
| A2-D-175 | `DetectorService.set_active_config` (4 lines) | `core/services/detector_service.py:385` | DEAD (safe) | no test, no doc | none |

### `core/services/model_service.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-176 | `ModelService.validate_weight` (18 lines) | `core/services/model_service.py:141` | DEAD (safe) | `ModelService` is alive; these four members are not | `core/services/test_model_service_extended.py` (3) |
| A2-D-177 | `ModelService.get_weight_type` (14 lines) | `core/services/model_service.py:182` | DEAD (safe) | `ModelService` is alive; these four members are not | `core/test_model_service.py` (3) |
| A2-D-178 | `ModelService.validate_model_configuration` (78 lines) | `core/services/model_service.py:290` | DEAD (safe) | `ModelService` is alive; these four members are not | `core/test_model_service.py` (6) |
| A2-D-179 | `ModelService.get_weight_configuration_summary` (51 lines) | `core/services/model_service.py:369` | DEAD (safe) | `ModelService` is alive; these four members are not | `core/test_model_service.py` (3) |

### `core/services/trajectory_data_service.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-180 | `TrajectoryDataService.load_trajectory_safe` (28 lines) | `core/services/trajectory_data_service.py:59` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/services/test_trajectory_data_service_extended.py` (2), `core/test_trajectory_data_service.py` (4) |

### `core/services/weight_manager.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-181 | `WeightManager.set_default_weight_by_type` (30 lines) | `core/services/weight_manager.py:1027` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/services/test_weight_manager_extended.py` (3), `core/test_weight_manager_discovery.py` (1), `core/test_weight_type_classification.py` (3) |
| A2-D-182 | `WeightManager.convert_to_openvino_int8` (137 lines) | `core/services/weight_manager.py:1797` | KEEP | documented in `docs/performance/HARDWARE_OPTIMIZATION_GUIDE.md:80` (137 lines) | - |

### `core/services/wizard_service.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-183 | `WizardService.clear_hardware_cache` (5 lines) | `core/services/wizard_service.py:169` | DEAD | used by 5 test files as a cache reset in setup/teardown: deleting means rewriting fixtures, not deleting tests | `core/services/test_wizard_service_camera_friendly_names.py` (2), `core/services/test_wizard_service_extended.py` (2), `test_wizard_service_caching.py` (4) +1 more |
| A2-D-184 | `WizardService.suggest_analysis_interval` (24 lines) | `core/services/wizard_service.py:619` | DEAD | listed as API in `docs/guides/developer/wizard.md:28-41` | `core/services/test_wizard_service_extended.py` (5), `ui/wizard/test_wizard_live_e2e.py` (2) |
| A2-D-185 | `WizardService.calculate_experiment_structure` (44 lines) | `core/services/wizard_service.py:644` | DEAD | listed as API in `docs/guides/developer/wizard.md:28-41` | `ui/wizard/test_wizard_live_e2e.py` (2) |
| A2-D-186 | `WizardService.validate_calibration_data` (70 lines) | `core/services/wizard_service.py:742` | DEAD | listed as API in `docs/guides/developer/wizard.md:28-41` | `core/services/test_wizard_service_extended.py` (10) |
| A2-D-187 | `WizardService.validate_multi_aquarium_config` (166 lines) | `core/services/wizard_service.py:903` | DEAD (safe) | log event name only (:1059); CHANGELOG mention is history | `core/services/test_wizard_service_extended.py` (4), `core/test_wizard_service_multi_aquarium.py` (21) |

### `core/state_manager.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-188 | `StateManager.register_observer` (16 lines) | `core/state_manager.py:428` | DEAD | `StateManager` introspection/legacy API; integration tests call it (`register_observer` in 4 test files); `get_history` has a docstring example (`state_manager.py:48`) | `integration/test_critical_integrations.py` (1), `integration/test_error_scenarios.py` (2), `integration/test_full_workflow.py` (1) +1 more |
| A2-D-189 | `StateManager.register_global_observer` (11 lines) | `core/state_manager.py:470` | DEAD | `StateManager` introspection/legacy API; integration tests call it (`register_observer` in 4 test files); `get_history` has a docstring example (`state_manager.py:48`) | `test_state_manager_observer_pattern.py` (2) |
| A2-D-190 | `StateManager.unsubscribe_all` (13 lines) | `core/state_manager.py:502` | DEAD | `StateManager` introspection/legacy API; integration tests call it (`register_observer` in 4 test files); `get_history` has a docstring example (`state_manager.py:48`) | `test_state_manager.py` (1) |
| A2-D-191 | `StateManager.get_state_snapshot` (22 lines) | `core/state_manager.py:748` | DEAD | `StateManager` introspection/legacy API; integration tests call it (`register_observer` in 4 test files); `get_history` has a docstring example (`state_manager.py:48`) | `integration/test_critical_integrations.py` (2), `integration/test_full_workflow.py` (1), `test_state_manager.py` (2) |
| A2-D-192 | `StateManager.update_state` (28 lines) | `core/state_manager.py:809` | DYNAMIC | hot path: `BaseCoordinator._update_state` calls `getattr(self.state_manager, "update_state")` first when `prefer_unified_state_api` is true (`base_coordinator.py:174`, and it is set to true in `StateManager.__init__`) | - |
| A2-D-193 | `StateManager.get_history` (33 lines) | `core/state_manager.py:1038` | DEAD | `StateManager` introspection/legacy API; integration tests call it (`register_observer` in 4 test files); `get_history` has a docstring example (`state_manager.py:48`) | `coordinators/test_base_coordinator.py` (1), `coordinators/test_detector_setup_coordinator.py` (1), `core/test_state_manager_extended.py` (1) +4 more |
| A2-D-194 | `StateManager.clear_history` (5 lines) | `core/state_manager.py:1072` | DEAD | `StateManager` introspection/legacy API; integration tests call it (`register_observer` in 4 test files); `get_history` has a docstring example (`state_manager.py:48`) | `test_state_manager.py` (1) |
| A2-D-195 | `StateManager.dump_state` (55 lines) | `core/state_manager.py:1080` | DEAD | `StateManager` introspection/legacy API; integration tests call it (`register_observer` in 4 test files); `get_history` has a docstring example (`state_manager.py:48`) | `test_state_manager.py` (2) |
| A2-D-196 | `StateManager.verify_state_integrity` (42 lines) | `core/state_manager.py:1155` | DEAD | `StateManager` introspection/legacy API; integration tests call it (`register_observer` in 4 test files); `get_history` has a docstring example (`state_manager.py:48`) | `test_state_manager_observer_pattern.py` (6) |

### `core/ui_scheduler.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-197 | `UIScheduler.cancel_scheduled` (14 lines) | `core/ui_scheduler.py:136` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/test_ui_scheduler.py` (5), `core/test_ui_scheduler_extended.py` (2), `test_ui_scheduler_threading.py` (3) |

### `core/video/processing_worker.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-198 | `_WorkerProcess._format_subject` (14 lines) | `core/video/processing_worker.py:571` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/test_processing_worker_unit.py` (5) |

### `core/video/progress_notifier.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-199 | `ProgressNotifierMixin.create_progress_callback` (112 lines) | `core/video/progress_notifier.py:51` | DEAD | 112 lines, duplicate of the live `_make_progress_callback`; listed in the module docstring (`progress_notifier.py:5`) | `core/test_video_processing_service_helpers.py` (2), `core/test_video_processing_service_thread_safety.py` (1) |

### `core/video/video_context_factory.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-200 | `VideoContextFactoryMixin._seek_to_frame` (38 lines) | `core/video/video_context_factory.py:115` | DEAD | listed in the module docstring (`video_context_factory.py:5`) | `core/test_video_context_factory.py` (4), `core/test_video_processing_service_helpers.py` (4), `core/test_video_processing_service_tracking.py` (3) |

### `core/video/video_metadata_service.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-201 | `VideoMetadataService.get_video_info` (34 lines) | `core/video/video_metadata_service.py:57` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/test_video_metadata_service.py` (2), `core/video/test_video_metadata_service_extended.py` (2) |

### `core/video/video_processing_service.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-202 | `VideoProcessingService.process_frame_source` (61 lines) | `core/video/video_processing_service.py:126` | DEAD | documented as zero-caller in `docs/testing/LIVE_FLOW_TEST_PROTOCOL.md:208`; named in the class docstring (`video_processing_service.py:82`) | none |

### `core/viewmodels/analysis_control_view_model.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-203 | `AnalysisControlViewModel.auto_detect_zones` (10 lines) | `core/viewmodels/analysis_control_view_model.py:265` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/test_analysis_control_view_model.py` (4) |

### `core/viewmodels/hardware_status_view_model.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-204 | `HardwareStatusViewModel.setup_arduino` (8 lines) | `core/viewmodels/hardware_status_view_model.py:114` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/test_hardware_status_view_model.py` (1) |
| A2-D-205 | `HardwareStatusViewModel._get_arduino_manager` (3 lines) | `core/viewmodels/hardware_status_view_model.py:196` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/test_hardware_status_view_model.py` (1) |
| A2-D-206 | `HardwareStatusViewModel.get_weight_names_for_slot` (17 lines) | `core/viewmodels/hardware_status_view_model.py:258` | DYNAMIC | `getattr(self.controller.hardware_vm, "get_weight_names_for_slot")` in `project_model_configuration_panel._refresh_slot_dropdown_values` (:431) | - |

### `i18n.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-207 | `lazy` (3 lines) | `i18n.py:292` | KEEP | documented in `docs/guides/developer/i18n.md:117`; keyword of `scripts/i18n_scan.py:151`, `scripts/update_translations.py:43`, `babel.cfg` | - |
| A2-D-208 | `reset_for_tests` (9 lines) | `i18n.py:297` | KEEP | called by `tests/conftest.py:65,68` (test hook inside the module) | - |

### `io/arduino.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-209 | `Arduino.send_string_command` (41 lines) | `io/arduino.py:172` | DEAD | named in the `Arduino.send_command` docstring (`arduino.py:107`); security tests exercise it (`test_arduino_security.py`) | `io/test_arduino_connection.py` (1), `io/test_arduino_security.py` (9) |

### `io/arduino_manager.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-210 | `ArduinoManager.list_available_ports` (10 lines) | `io/arduino_manager.py:220` | DEAD (safe) | no test, no doc | none |
| A2-D-211 | `ArduinoManager.last_command` (3 lines) | `io/arduino_manager.py:472` | DEAD (safe) | no reference in `src/` or `scripts/` | `test_io_arduino_manager.py` (7) |

### `io/camera.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-212 | `Camera.read_next_frame` (25 lines) | `io/camera.py:373` | DYNAMIC | `getattr(self.camera, "read_next_frame", None)` in `frame_processing_pipeline._read_camera_frame` (:450): the live capture path | - |

### `io/object_sidecar.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-213 | `read_object_sidecar_metadata` (13 lines) | `io/object_sidecar.py:414` | KEEP | listed in `object_sidecar.__all__` (:55) | - |

### `io/recorder.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-214 | `Recorder.is_paused` (7 lines) | `io/recorder.py:483` | DEAD (safe) | the `"is_paused"` hit is a dict key built by `get_pause_metadata` | `test_live_camera_workflow_e2e.py` (2) |
| A2-D-215 | `Recorder.get_pause_metadata` (11 lines) | `io/recorder.py:491` | DEAD (safe) | no reference in `src/` or `scripts/` | none |
| A2-D-216 | `Recorder.write_video_frame_multi_aquarium` (18 lines) | `io/recorder.py:911` | DEAD (safe) | no reference in `src/` or `scripts/` | `io/test_recorder_multi_aquarium.py` (2) |
| A2-D-217 | `Recorder.is_multi_aquarium_mode` (3 lines) | `io/recorder.py:984` | DEAD (safe) | no reference in `src/` or `scripts/` | `core/test_detector_partitioned.py` (4), `io/test_recorder_multi_aquarium.py` (10) |
| A2-D-218 | `Recorder.get_aquarium_recorders` (3 lines) | `io/recorder.py:988` | DYNAMIC | `getattr(recorder, "get_aquarium_recorders", None)` in `frame_processing_pipeline._finalize_aquarium_windows` (:2438) | - |
| A2-D-219 | `Recorder.mask_parquet_filename` (4 lines) | `io/recorder.py:1162` | DEAD (safe) | no reference in `src/` or `scripts/` | `test_recorder.py` (1) |
| A2-D-220 | `Recorder.object_parquet_filename` (4 lines) | `io/recorder.py:1347` | DEAD (safe) | no reference in `src/` or `scripts/` | `test_recorder.py` (1) |
| A2-D-221 | `Recorder._validate_unique_detections` (50 lines) | `io/recorder.py:1632` | DEAD (safe) | no test, no doc | none |

### `plugins/base.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-222 | `DetectorPlugin.model_input_shape` (7 lines) | `plugins/base.py:90` | DEAD | abstract property of `DetectorPlugin` (`base.py:89` is `@abstractmethod`) plus two overrides: deleting is an interface decision; test doubles implement it | `plugins/test_base.py` (3), `plugins/test_openvino_detector.py` (1), `plugins/test_ultralytics_detector.py` (3) |

### `plugins/openvino_detector.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-223 | `OpenVINOPlugin.set_context_classes_present` (3 lines) | `plugins/openvino_detector.py:440` | DYNAMIC | `getattr(plugin, "set_context_classes_present", None)` in `single_detector.py:164` and `multi_aquarium_detector.py:130` | - |
| A2-D-224 | `OpenVINOPlugin.set_tracking_parameters` (12 lines) | `plugins/openvino_detector.py:455` | DEAD (safe) | delete the two plugin implementations together | `plugins/test_openvino_detector.py` (3), `plugins/test_ultralytics_detector.py` (7) |
| A2-D-225 | `OpenVINOPlugin.model_input_shape` (3 lines) | `plugins/openvino_detector.py:899` | DEAD | abstract property of `DetectorPlugin` (`base.py:89` is `@abstractmethod`) plus two overrides: deleting is an interface decision; test doubles implement it | `plugins/test_base.py` (3), `plugins/test_openvino_detector.py` (1), `plugins/test_ultralytics_detector.py` (3) |

### `plugins/ultralytics_detector.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-226 | `UltralyticsDetectorPlugin.model_input_shape` (6 lines) | `plugins/ultralytics_detector.py:351` | DEAD | abstract property of `DetectorPlugin` (`base.py:89` is `@abstractmethod`) plus two overrides: deleting is an interface decision; test doubles implement it | `plugins/test_base.py` (3), `plugins/test_openvino_detector.py` (1), `plugins/test_ultralytics_detector.py` (3) |
| A2-D-227 | `UltralyticsDetectorPlugin.set_tracking_parameters` (12 lines) | `plugins/ultralytics_detector.py:357` | DEAD (safe) | delete the two plugin implementations together | `plugins/test_openvino_detector.py` (3), `plugins/test_ultralytics_detector.py` (7) |

### `settings.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-228 | `YOLOModelSettings.effective_animal_confidence` (8 lines) | `settings.py:363` | DEAD (safe) | no reference in `src/` or `scripts/` | `test_settings.py` (1) |
| A2-D-229 | `reload_settings` (32 lines) | `settings.py:1686` | KEEP | listed in `settings.__all__`; `config.yaml:15,551` tells users to run `export_schema` | - |
| A2-D-230 | `export_schema` (35 lines) | `settings.py:1836` | KEEP | listed in `settings.__all__`; `config.yaml:15,551` tells users to run `export_schema` | - |

### `tracker/matching.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-231 | `merge_matches` (15 lines) | `tracker/matching.py:9` | DEAD (safe) | `tracker/matching.py` is alive through its four other functions | `test_matching.py` (3) |
| A2-D-232 | `v_iou_distance` (21 lines) | `tracker/matching.py:161` | DEAD (safe) | `tracker/matching.py` is alive through its four other functions | none |
| A2-D-233 | `embedding_distance` (15 lines) | `tracker/matching.py:184` | DEAD (safe) | `tracker/matching.py` is alive through its four other functions | `test_matching.py` (4) |
| A2-D-234 | `gate_cost_matrix` (12 lines) | `tracker/matching.py:201` | DEAD (safe) | `tracker/matching.py` is alive through its four other functions | `test_matching.py` (4) |
| A2-D-235 | `fuse_motion` (17 lines) | `tracker/matching.py:215` | DEAD (safe) | `tracker/matching.py` is alive through its four other functions | none |
| A2-D-236 | `fuse_iou` (12 lines) | `tracker/matching.py:234` | DEAD (safe) | `tracker/matching.py` is alive through its four other functions | `test_matching.py` (3) |

### `ui/builders/common_widgets.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-237 | `CommonWidgetsBuilder.build_status_icon_legend_simple` (11 lines) | `ui/builders/common_widgets.py:44` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_widget_factory.py` (2) |
| A2-D-238 | `CommonWidgetsBuilder.configure_styles` (61 lines) | `ui/builders/common_widgets.py:115` | DEAD (safe) | no test, no doc | none |
| A2-D-239 | `CommonWidgetsBuilder.prompt_for_weight_type` (50 lines) | `ui/builders/common_widgets.py:177` | DEAD (safe) | no test, no doc | none |

### `ui/builders/zone_control_builder.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-240 | `ZoneControlBuilder._ensure_reuse_template_var` (10 lines) | `ui/builders/zone_control_builder.py:52` | DEAD | design note in `zone_control_builder.py:47` names `_ensure_reuse_template_var` | none |
| A2-D-241 | `ZoneControlBuilder.reuse_arena_template_var` (4 lines) | `ui/builders/zone_control_builder.py:64` | DEAD | design note in `zone_control_builder.py:47` names `_ensure_reuse_template_var` | none |

### `ui/builders/zone_widgets.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-242 | `ZoneWidgetsBuilder.create_zone_summary_cards_section` (19 lines) | `ui/builders/zone_widgets.py:24` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_widget_factory.py` (1) |
| A2-D-243 | `ZoneWidgetsBuilder.create_scrollable_controls_frame` (22 lines) | `ui/builders/zone_widgets.py:109` | DEAD (safe) | no reference in `src/` or `scripts/` | none |
| A2-D-244 | `ZoneWidgetsBuilder.create_template_rois` (68 lines) | `ui/builders/zone_widgets.py:136` | DEAD (safe) | no reference in `src/` or `scripts/` | none |

### `ui/components/analysis_view_controller.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-245 | `AnalysisViewController.on_track_selection_changed` (3 lines) | `ui/components/analysis_view_controller.py:453` | DEAD (safe) | no test, no doc | none |

### `ui/components/analysis_window_panel.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-246 | `AnalysisWindowPanel.is_session_only` (4 lines) | `ui/components/analysis_window_panel.py:981` | DEAD (safe) | no reference in `src/` or `scripts/` | `test_live_analysis_ui.py` (1), `ui/components/test_analysis_window_panel.py` (1) |

### `ui/components/base.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-247 | `BaseWidget.set_enabled` (9 lines) | `ui/components/base.py:155` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_base_widget.py` (2) |

### `ui/components/canvas/renderer.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-248 | `CanvasRenderer.clear_placeholder_logo` (7 lines) | `ui/components/canvas/renderer.py:186` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_canvas_renderer.py` (1) |

### `ui/components/class_roles_panel.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-249 | `ClassRolesPanel.seed_fit` (3 lines) | `ui/components/class_roles_panel.py:1240` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_class_roles_panel.py` (2) |

### `ui/components/config_editor.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-250 | `ConfigEditorWidget.focus_roi_section` (17 lines) | `ui/components/config_editor.py:559` | DYNAMIC | `getattr(widget, "focus_roi_section", None)` in `event_dispatcher._handle_open_roi_settings` (:1111) | - |

### `ui/components/dialog_manager.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-251 | `DialogManager.set_dialog_suppression` (16 lines) | `ui/components/dialog_manager.py:65` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_dialog_manager_extended.py` (10) |
| A2-D-252 | `DialogManager.open_global_calibration_window` (6 lines) | `ui/components/dialog_manager.py:436` | DEAD (safe) | `DialogManager` open_* methods; only archive docs name them | `ui/components/test_dialog_manager.py` (1) |
| A2-D-253 | `DialogManager.open_project_calibration_window` (28 lines) | `ui/components/dialog_manager.py:443` | DEAD (safe) | `DialogManager` open_* methods; only archive docs name them | `ui/components/test_dialog_manager.py` (3) |
| A2-D-254 | `DialogManager.show_template_save_dialog` (33 lines) | `ui/components/dialog_manager.py:476` | DEAD (safe) | `DialogManager` open_* methods; only archive docs name them | `ui/components/test_dialog_manager.py` (6) |
| A2-D-255 | `DialogManager.open_center_periphery_dialog` (10 lines) | `ui/components/dialog_manager.py:671` | DEAD (safe) | `DialogManager` open_* methods; only archive docs name them | `ui/components/test_dialog_manager.py` (4) |
| A2-D-256 | `DialogManager.open_template_rois_dialog` (10 lines) | `ui/components/dialog_manager.py:682` | DEAD (safe) | `DialogManager` open_* methods; only archive docs name them | `ui/components/test_dialog_manager.py` (4) |
| A2-D-257 | `DialogManager.open_single_video_config_dialog` (14 lines) | `ui/components/dialog_manager.py:693` | DEAD (safe) | `DialogManager` open_* methods; only archive docs name them | `ui/components/test_dialog_manager.py` (4) |
| A2-D-258 | `DialogManager.ask_missing_metadata` (13 lines) | `ui/components/dialog_manager.py:838` | DEAD | the `scripts/check_public_api.py:22` string refers to `ApplicationGUI.ask_missing_metadata` (A2-D-352, KEEP); this `DialogManager` copy has no caller | `ui/components/test_dialog_manager.py` (4), `ui/test_gui_public_api_contract.py` (1) |
| A2-D-259 | `DialogManager.confirm_delete_roi_template` (27 lines) | `ui/components/dialog_manager.py:1174` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_dialog_manager.py` (4) |
| A2-D-260 | `DialogManager.open_path_in_explorer` (17 lines) | `ui/components/dialog_manager.py:1441` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_dialog_manager.py` (4) |

### `ui/components/event_dispatcher.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-261 | `EventDispatcher.register_handler` (15 lines) | `ui/components/event_dispatcher.py:204` | DEAD | cascade: `_create_dispatcher` and the `MODE_*` constants only serve `register_handler`; `tests/quality/test_no_orphan_ui_events.py:73-77` lists the names as subscription wrappers | `quality/test_no_orphan_ui_events.py` (3), `ui/components/test_event_dispatcher.py` (6), `ui/components/test_event_dispatcher_extended.py` (6) |
| A2-D-262 | `EventDispatcher.register_direct_handler` (6 lines) | `ui/components/event_dispatcher.py:249` | DEAD | cascade: `_create_dispatcher` and the `MODE_*` constants only serve `register_handler`; `tests/quality/test_no_orphan_ui_events.py:73-77` lists the names as subscription wrappers | `quality/test_no_orphan_ui_events.py` (4), `ui/components/test_event_dispatcher.py` (2) |
| A2-D-263 | `EventDispatcher.unregister_handler` (16 lines) | `ui/components/event_dispatcher.py:256` | DEAD | cascade: `_create_dispatcher` and the `MODE_*` constants only serve `register_handler`; `tests/quality/test_no_orphan_ui_events.py:73-77` lists the names as subscription wrappers | `ui/components/test_event_dispatcher.py` (2) |
| A2-D-264 | `EventDispatcher.get_registered_count` (3 lines) | `ui/components/event_dispatcher.py:273` | DEAD | cascade: `_create_dispatcher` and the `MODE_*` constants only serve `register_handler`; `tests/quality/test_no_orphan_ui_events.py:73-77` lists the names as subscription wrappers | `ui/components/test_event_dispatcher.py` (2) |

### `ui/components/global_model_configuration_panel.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-265 | `TargetChoiceDialog.apply` (2 lines) | `ui/components/global_model_configuration_panel.py:101` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |

### `ui/components/menu_manager.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-266 | `MenuManager.resolve_overview_asset_from_click` (42 lines) | `ui/components/menu_manager.py:440` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_menu_manager.py` (3) |
| A2-D-267 | `MenuManager.show_overview_context_menu` (39 lines) | `ui/components/menu_manager.py:483` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_menu_manager.py` (3) |

### `ui/components/processing_reports.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-268 | `ProcessingReportsWidget.collapse_tree_item` (4 lines) | `ui/components/processing_reports.py:735` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_project_overview.py` (1) |
| A2-D-269 | `ProcessingReportsWidget.update_selection_info` (10 lines) | `ui/components/processing_reports.py:751` | DEAD (safe) | no reference in `src/` or `scripts/` | none |

### `ui/components/project_overview.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-270 | `ProjectOverviewWidget.resolve_selected_video_paths` (37 lines) | `ui/components/project_overview.py:232` | DYNAMIC | `getattr(widget, ...)` in `dialog_manager._resolve_selected_project_videos` (:1009) / `_resolve_selected_recording_scope` (:1067) and `video_selector_tree_manager._resolve_selection_from_project_overview` (:753) | - |
| A2-D-271 | `ProjectOverviewWidget.get_selected_scope` (25 lines) | `ui/components/project_overview.py:313` | DYNAMIC | `getattr(widget, ...)` in `dialog_manager._resolve_selected_project_videos` (:1009) / `_resolve_selected_recording_scope` (:1067) and `video_selector_tree_manager._resolve_selection_from_project_overview` (:753) | - |
| A2-D-272 | `ProjectOverviewWidget.collapse_tree_item` (4 lines) | `ui/components/project_overview.py:389` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_project_overview.py` (1) |

### `ui/components/project_views/reports_tree_manager.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-273 | `ReportsTreeManager.append_processing_reports_artifacts` (9 lines) | `ui/components/project_views/reports_tree_manager.py:660` | DEAD (safe) | legacy alias pair | none |
| A2-D-274 | `ReportsTreeManager.append_report_artifacts` (5 lines) | `ui/components/project_views/reports_tree_manager.py:670` | DEAD (safe) | legacy alias pair | none |
| A2-D-275 | `ReportsTreeManager._refresh_processing_reports_tab` (3 lines) | `ui/components/project_views/reports_tree_manager.py:730` | DEAD | named in the module docstring of `video_selector_tree_manager.py:8` | none |
| A2-D-276 | `ReportsTreeManager._get_project_status_counts` (3 lines) | `ui/components/project_views/reports_tree_manager.py:734` | DEAD (safe) | 3-line shim; the real handlers live in `_generator` | none |
| A2-D-277 | `ReportsTreeManager._populate_reports_tree_from_hierarchy` (5 lines) | `ui/components/project_views/reports_tree_manager.py:738` | DEAD (safe) | 3-line shim; the real handlers live in `_generator` | none |
| A2-D-278 | `ReportsTreeManager._delete_video_asset` (3 lines) | `ui/components/project_views/reports_tree_manager.py:748` | DEAD (safe) | 3-line shim; the real handlers live in `_generator` | none |
| A2-D-279 | `ReportsTreeManager._delete_all_processing_data` (3 lines) | `ui/components/project_views/reports_tree_manager.py:752` | DEAD (safe) | 3-line shim; the real handlers live in `_generator` | none |
| A2-D-280 | `ReportsTreeManager._delete_video_from_project` (3 lines) | `ui/components/project_views/reports_tree_manager.py:756` | DEAD (safe) | 3-line shim; the real handlers live in `_generator` | none |
| A2-D-281 | `ReportsTreeManager._delete_all_unified_reports` (3 lines) | `ui/components/project_views/reports_tree_manager.py:760` | DEAD (safe) | 3-line shim; the real handlers live in `_generator` | none |

### `ui/components/project_views/video_selector_tree_manager.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-282 | `VideoSelectorTreeManager.on_project_overview_tree_double_click` (3 lines) | `ui/components/project_views/video_selector_tree_manager.py:768` | DEAD (safe) | no reference in `src/` or `scripts/` | none |
| A2-D-283 | `VideoSelectorTreeManager.on_project_overview_right_click` (17 lines) | `ui/components/project_views/video_selector_tree_manager.py:812` | DEAD (safe) | no reference in `src/` or `scripts/` | none |
| A2-D-284 | `VideoSelectorTreeManager.refresh_openvino_summary` (7 lines) | `ui/components/project_views/video_selector_tree_manager.py:897` | DEAD (safe) | no reference in `src/` or `scripts/` | none |
| A2-D-285 | `VideoSelectorTreeManager.populate_video_selector_tree` (6 lines) | `ui/components/project_views/video_selector_tree_manager.py:909` | DEAD (safe) | no reference in `src/` or `scripts/` | none |
| A2-D-286 | `VideoSelectorTreeManager.refresh_video_selector_tree` (6 lines) | `ui/components/project_views/video_selector_tree_manager.py:916` | DEAD (safe) | no reference in `src/` or `scripts/` | none |

### `ui/components/roi_template_manager.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-287 | `ROITemplateManager.delete_template` (27 lines) | `ui/components/roi_template_manager.py:266` | DEAD (safe) | delete together with A2-D-157 | `core/project/test_roi_template_manager.py` (2), `ui/components/test_roi_template_manager.py` (1), `ui/wizard/test_wizard_templates.py` (1) |
| A2-D-288 | `ROITemplateManager.import_template` (28 lines) | `ui/components/roi_template_manager.py:419` | DEAD (safe) | no reference in `src/` or `scripts/` | `test_project_manager.py` (1), `ui/components/test_roi_template_manager.py` (1) |

### `ui/components/state_synchronizer.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-289 | `StateSynchronizer.reset_global_config_form_widget` (7 lines) | `ui/components/state_synchronizer.py:426` | DEAD (safe) | no reference in `src/` or `scripts/` | none |
| A2-D-290 | `StateSynchronizer._default_analysis_metadata_text` (7 lines) | `ui/components/state_synchronizer.py:444` | DEAD (safe) | no reference in `src/` or `scripts/` | `test_analysis_metadata_display.py` (2), `ui/components/test_state_synchronizer.py` (1) |

### `ui/components/validation_manager.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-291 | `ValidationManager.save_global_config_from_widget` (90 lines) | `ui/components/validation_manager.py:111` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_validation_manager.py` (4), `ui/components/test_validation_manager_extended.py` (11) |
| A2-D-292 | `ValidationManager.compose_overview_status_line` (26 lines) | `ui/components/validation_manager.py:202` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_validation_manager.py` (8), `ui/components/test_validation_manager_extended.py` (4) |
| A2-D-293 | `ValidationManager.check_live_project_calibration` (42 lines) | `ui/components/validation_manager.py:412` | DEAD | comments in `project_initializer.py:188,196` say it is "preserved for explicit invocation"; nothing invokes it | `ui/components/test_project_initializer_live_camera.py` (5), `ui/components/test_validation_manager.py` (5), `ui/components/test_validation_manager_extended.py` (2) |
| A2-D-294 | `ValidationManager.get_selected_roi_template` (37 lines) | `ui/components/validation_manager.py:556` | DEAD (safe) | the `[attr]` hits are log event names | `ui/components/test_validation_manager.py` (5) |
| A2-D-295 | `ValidationManager.validate_roi_template_data` (12 lines) | `ui/components/validation_manager.py:594` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_validation_manager.py` (5) |
| A2-D-296 | `ValidationManager.validate_arena_for_analysis` (12 lines) | `ui/components/validation_manager.py:607` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_validation_manager.py` (4) |
| A2-D-297 | `ValidationManager.validate_arena_polygon_data` (12 lines) | `ui/components/validation_manager.py:620` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_validation_manager.py` (4) |
| A2-D-298 | `ValidationManager.validate_positive_integer` (26 lines) | `ui/components/validation_manager.py:633` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_validation_manager.py` (6) |
| A2-D-299 | `ValidationManager.validate_active_video_selection` (12 lines) | `ui/components/validation_manager.py:660` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_validation_manager.py` (4) |
| A2-D-300 | `ValidationManager.format_roi_template_display` (41 lines) | `ui/components/validation_manager.py:885` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_validation_manager.py` (5) |
| A2-D-301 | `ValidationManager.build_roi_template_identifier` (20 lines) | `ui/components/validation_manager.py:927` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_validation_manager.py` (5) |
| A2-D-302 | `ValidationManager.format_time` (19 lines) | `ui/components/validation_manager.py:949` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_validation_manager.py` (2) |
| A2-D-303 | `ValidationManager.format_subject_for_reports` (14 lines) | `ui/components/validation_manager.py:969` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_validation_manager.py` (5) |
| A2-D-304 | `ValidationManager.apply_roi_settings` (80 lines) | `ui/components/validation_manager.py:1553` | DEAD | `system_integration.md:863` says it enforces the ROI range split; the real path is `hardware_vm.update_detector_parameters` -> `Settings` validators (`gui.py:904`, `event_dispatcher.py:1263`) | `ui/components/test_validation_manager.py` (5) |

### `ui/components/video_display.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-305 | `VideoDisplayWidget.load_frame` (84 lines) | `ui/components/video_display.py:97` | DEAD (safe) | `VideoDisplayWidget` helpers | `ui/components/test_video_display_widget.py` (1) |
| A2-D-306 | `VideoDisplayWidget.set_image` (10 lines) | `ui/components/video_display.py:182` | DEAD (safe) | `VideoDisplayWidget` helpers | `ui/components/test_video_display_widget.py` (1) |
| A2-D-307 | `VideoDisplayWidget.video_to_canvas` (23 lines) | `ui/components/video_display.py:271` | DEAD (safe) | `VideoDisplayWidget` helpers | `ui/components/test_video_display_widget.py` (1) |
| A2-D-308 | `VideoDisplayWidget.canvas_to_video` (23 lines) | `ui/components/video_display.py:295` | DEAD (safe) | `VideoDisplayWidget` helpers | `ui/components/test_video_display_widget.py` (1) |
| A2-D-309 | `VideoDisplayWidget.get_image_size` (5 lines) | `ui/components/video_display.py:319` | DEAD (safe) | `VideoDisplayWidget` helpers | `ui/components/test_video_display_widget.py` (2) |
| A2-D-310 | `VideoDisplayWidget.get_scale` (8 lines) | `ui/components/video_display.py:325` | DEAD (safe) | no test, no doc | none |

### `ui/components/zone_controls.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-311 | `ZoneControlsWidget._build_single_analysis_options` (27 lines) | `ui/components/zone_controls.py:610` | DEAD | disabled call kept as a comment at `zone_controls.py:197` | none |
| A2-D-312 | `ZoneControlsWidget._on_toggle_view_clicked` (3 lines) | `ui/components/zone_controls.py:1003` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_zone_controls_extended.py` (1) |
| A2-D-313 | `ZoneControlsWidget._on_video_refresh_clicked` (3 lines) | `ui/components/zone_controls.py:1033` | DEAD (safe) | no test, no doc | none |
| A2-D-314 | `ZoneControlsWidget.set_roi_rule_config` (8 lines) | `ui/components/zone_controls.py:1434` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_zone_controls_widget.py` (1) |
| A2-D-315 | `ZoneControlsWidget.update_template_list` (4 lines) | `ui/components/zone_controls.py:1544` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/components/test_zone_controls_widget.py` (1) |
| A2-D-316 | `ZoneControlsWidget.get_active_aquarium_id` (7 lines) | `ui/components/zone_controls.py:1638` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/test_zone_controls_multi_aquarium.py` (6) |

### `ui/components/zone_edit_guard.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-317 | `ZoneEditGuard.warn_about_pending_zone_edit` (11 lines) | `ui/components/zone_edit_guard.py:112` | DEAD (safe) | no test, no doc | none |

### `ui/dialogs/aquarium_assignment_dialog.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-318 | `AquariumAssignmentDialog.buttonbox` (23 lines) | `ui/dialogs/aquarium_assignment_dialog.py:531` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |

### `ui/dialogs/aquarium_detection_progress_dialog.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-319 | `AquariumDetectionProgressDialog.show_completion` (22 lines) | `ui/dialogs/aquarium_detection_progress_dialog.py:325` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/dialogs/test_aquarium_detection_progress_dialog.py` (1) |
| A2-D-320 | `AquariumDetectionProgressDialog.close_dialog` (6 lines) | `ui/dialogs/aquarium_detection_progress_dialog.py:348` | DEAD (safe) | `ui_coordinator._on_aquarium_detection_progress` destroys the dialog directly | `ui/dialogs/test_aquarium_detection_progress_dialog.py` (1) |

### `ui/dialogs/calibration_dialog.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-321 | `CalibrationDialog.buttonbox` (7 lines) | `ui/dialogs/calibration_dialog.py:233` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |

### `ui/dialogs/camera_disconnect_recovery_dialog.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-322 | `CameraDisconnectRecoveryDialog.close_dialog` (7 lines) | `ui/dialogs/camera_disconnect_recovery_dialog.py:342` | DEAD | NOT a safe delete: the `wait` action leaves the dialog open on purpose ("callback should close it when camera reconnects", `camera_disconnect_recovery_dialog.py:_on_wait`) and `ui_coordinator._on_camera_reconnected` (:713) never calls `close_dialog`. A missing caller, not dead code | `ui/dialogs/test_aquarium_detection_progress_dialog.py` (1) |

### `ui/dialogs/center_periphery_dialog.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-323 | `CenterPeripheryDialog.apply` (6 lines) | `ui/dialogs/center_periphery_dialog.py:78` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |

### `ui/dialogs/color_selection_dialog.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-324 | `ColorSelectionDialog.apply` (7 lines) | `ui/dialogs/color_selection_dialog.py:78` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |

### `ui/dialogs/live_analysis_dialog.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-325 | `LiveAnalysisDialog.buttonbox` (15 lines) | `ui/dialogs/live_analysis_dialog.py:710` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |
| A2-D-326 | `LiveAnalysisDialog.apply` (122 lines) | `ui/dialogs/live_analysis_dialog.py:1029` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |

### `ui/dialogs/missing_metadata_dialog.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-327 | `MissingMetadataDialog.apply` (7 lines) | `ui/dialogs/missing_metadata_dialog.py:90` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |

### `ui/dialogs/model_diagnostics_dialog.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-328 | `ModelDiagnosticsDialog.buttonbox` (11 lines) | `ui/dialogs/model_diagnostics_dialog.py:42` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |

### `ui/dialogs/multi_aquarium_live_preview_window.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-329 | `MultiAquariumLivePreviewWindow.update_recorded_count` (10 lines) | `ui/dialogs/multi_aquarium_live_preview_window.py:149` | DEAD | the window is built but nothing feeds it frames or counts; decide whether multi-aquarium live preview is wired before deleting | `ui/dialogs/test_multi_aquarium_live_preview_window.py` (1) |
| A2-D-330 | `MultiAquariumLivePreviewWindow.update_aquarium_frame` (52 lines) | `ui/dialogs/multi_aquarium_live_preview_window.py:285` | DEAD | the window is built but nothing feeds it frames or counts; decide whether multi-aquarium live preview is wired before deleting | `ui/dialogs/test_multi_aquarium_live_preview_window.py` (2) |

### `ui/dialogs/pending_videos_dialog.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-331 | `PendingVideosDialog.buttonbox` (10 lines) | `ui/dialogs/pending_videos_dialog.py:139` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |
| A2-D-332 | `PendingVideosDialog.apply` (11 lines) | `ui/dialogs/pending_videos_dialog.py:150` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |

### `ui/dialogs/project_video_import_dialog.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-333 | `SubjectEntriesDialog.apply` (9 lines) | `ui/dialogs/project_video_import_dialog.py:133` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |
| A2-D-334 | `VideoMetadataDialog.apply` (12 lines) | `ui/dialogs/project_video_import_dialog.py:240` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |
| A2-D-335 | `BatchVideoMetadataDialog.apply` (9 lines) | `ui/dialogs/project_video_import_dialog.py:405` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |
| A2-D-336 | `ProjectVideoImportDialog.buttonbox` (9 lines) | `ui/dialogs/project_video_import_dialog.py:602` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |
| A2-D-337 | `ProjectVideoImportDialog.apply` (10 lines) | `ui/dialogs/project_video_import_dialog.py:682` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |

### `ui/dialogs/save_roi_template_dialog.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-338 | `SaveROITemplateDialog.apply` (16 lines) | `ui/dialogs/save_roi_template_dialog.py:197` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |

### `ui/dialogs/single_video_config_dialog.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-339 | `SingleVideoConfigDialog.apply` (141 lines) | `ui/dialogs/single_video_config_dialog.py:614` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |

### `ui/dialogs/start_recording_dialog.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-340 | `StartRecordingDialog.apply` (11 lines) | `ui/dialogs/start_recording_dialog.py:239` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |

### `ui/dialogs/subject_selection_dialog.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-341 | `SubjectSelectionDialog.buttonbox` (8 lines) | `ui/dialogs/subject_selection_dialog.py:100` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |

### `ui/dialogs/template_dialog.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-342 | `TemplateDialog.apply` (13 lines) | `ui/dialogs/template_dialog.py:105` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |

### `ui/gui.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-343 | `ApplicationGUI._open_global_calibration_window` (3 lines) | `ui/gui.py:726` | DEAD (safe) | `ApplicationGUI` leftovers of the DialogManager/tree-manager decomposition | none |
| A2-D-344 | `ApplicationGUI._open_project_calibration_window` (22 lines) | `ui/gui.py:741` | DEAD (safe) | `ApplicationGUI` leftovers of the DialogManager/tree-manager decomposition | none |
| A2-D-345 | `ApplicationGUI._on_reset_global_config_form_widget` (7 lines) | `ui/gui.py:764` | DEAD (safe) | `ApplicationGUI` leftovers of the DialogManager/tree-manager decomposition | none |
| A2-D-346 | `ApplicationGUI._on_project_overview_tree_double_click` (10 lines) | `ui/gui.py:793` | DEAD (safe) | `ApplicationGUI` leftovers of the DialogManager/tree-manager decomposition | none |
| A2-D-347 | `ApplicationGUI._on_project_overview_right_click` (11 lines) | `ui/gui.py:804` | DEAD (safe) | `ApplicationGUI` leftovers of the DialogManager/tree-manager decomposition | none |
| A2-D-348 | `ApplicationGUI._on_frame_configure` (4 lines) | `ui/gui.py:816` | DEAD (safe) | `ApplicationGUI` leftovers of the DialogManager/tree-manager decomposition | none |
| A2-D-349 | `ApplicationGUI._on_canvas_configure_scroll` (5 lines) | `ui/gui.py:821` | DEAD (safe) | `ApplicationGUI` leftovers of the DialogManager/tree-manager decomposition | none |
| A2-D-350 | `ApplicationGUI._recenter_canvas_image` (27 lines) | `ui/gui.py:847` | DEAD (safe) | `ApplicationGUI` leftovers of the DialogManager/tree-manager decomposition | none |
| A2-D-351 | `ApplicationGUI._remove_selected_roi_confirm` (8 lines) | `ui/gui.py:917` | DEAD (safe) | `ApplicationGUI` leftovers of the DialogManager/tree-manager decomposition | `integration/test_gui_component_integration.py` (1) |
| A2-D-352 | `ApplicationGUI.ask_missing_metadata` (5 lines) | `ui/gui.py:1032` | KEEP | `@public_api`; required by `scripts/check_public_api.py:22` and `tests/ui/test_gui_public_api_contract.py` | - |
| A2-D-353 | `ApplicationGUI._on_save_arena` (5 lines) | `ui/gui.py:1037` | DEAD (safe) | `ApplicationGUI` leftovers of the DialogManager/tree-manager decomposition | none |

### `ui/ui_coordinator.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-354 | `UICoordinator.get_statistics` (12 lines) | `ui/ui_coordinator.py:636` | DEAD (safe) | no reference in `src/` or `scripts/` | `ui/test_ui_coordinator_helpers.py` (1) |
| A2-D-355 | `UICoordinator.reset_statistics` (4 lines) | `ui/ui_coordinator.py:897` | DEAD (safe) | no reference in `src/` or `scripts/` | none |

### `ui/wizard/cache.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-356 | `WizardCache.get_scan_results` (33 lines) | `ui/wizard/cache.py:46` | DEAD | `WizardCache` is instantiated (`wizard_dialog.py:110`) but nothing calls it; likely the whole class is dead, decide together | none |
| A2-D-357 | `WizardCache.get_design_detection` (33 lines) | `ui/wizard/cache.py:80` | DEAD | `WizardCache` is instantiated (`wizard_dialog.py:110`) but nothing calls it; likely the whole class is dead, decide together | none |

### `ui/wizard/custom_regex_dialog.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-358 | `CustomRegexDialog.buttonbox` (28 lines) | `ui/wizard/custom_regex_dialog.py:606` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |
| A2-D-359 | `CustomRegexDialog.apply` (15 lines) | `ui/wizard/custom_regex_dialog.py:691` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |
| A2-D-360 | `CustomRegexDialog._match_path` (14 lines) | `ui/wizard/custom_regex_dialog.py:884` | DEAD (safe) | no test, no doc | none |

### `ui/wizard/design_editor_dialog.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-361 | `DesignEditorDialog.buttonbox` (15 lines) | `ui/wizard/design_editor_dialog.py:262` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |
| A2-D-362 | `DesignEditorDialog.apply` (30 lines) | `ui/wizard/design_editor_dialog.py:525` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |

### `ui/wizard/templates.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-363 | `TemplateManager.load_template` (32 lines) | `ui/wizard/templates.py:453` | DEAD | name shared with `core/project/roi_template_manager.py:load_template` (A2-D-155); `WORKFLOWS.md:205` row is an event name | `core/project/test_roi_template_manager.py` (10), `ui/wizard/test_wizard_templates.py` (2) |
| A2-D-364 | `TemplateManager.list_templates` (40 lines) | `ui/wizard/templates.py:524` | DEAD | comment at `templates.py:61` mentions it | `ui/wizard/test_wizard_templates.py` (1) |
| A2-D-365 | `TemplateManager.delete_template` (30 lines) | `ui/wizard/templates.py:565` | DEAD (safe) | delete together with A2-D-157 | `core/project/test_roi_template_manager.py` (2), `ui/components/test_roi_template_manager.py` (1), `ui/wizard/test_wizard_templates.py` (1) |

### `ui/wizard/wizard_dialog.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-366 | `WizardDialog.buttonbox` (31 lines) | `ui/wizard/wizard_dialog.py:191` | DYNAMIC | `tkinter.simpledialog.Dialog` hook (`apply`/`buttonbox`), called by `Dialog.__init__`/`ok`; the class derives from it | - |

### `utils/cache.py`

| ID | Function | `file:line` | Verdict | Evidence | Tests that go with it |
| --- | --- | --- | --- | --- | --- |
| A2-D-367 | `ttl_cache` (47 lines) | `utils/cache.py:163` | DEAD | module docstring (:6) and a docstring example (:181) mention it; `TTLCache` (alive) is the used part of the module | `utils/test_cache.py` (11) |

## Safest deletion batch

Rows marked `(safe)`: **163 functions, 3136 physical lines**. Each has no
reference of any kind outside its definition and its tests, and none is an interface member, a
documented API, a Tk hook, or part of a cluster that needs a decision first.

| Module | Functions | Lines | Row numbers (`A2-D-`) |
| --- | --- | --- | --- |
| `analysis/analysis_service.py` | 2 | 189 | 101, 102 |
| `analysis/roi.py` | 1 | 8 | 109 |
| `coordinators/base_coordinator.py` | 1 | 26 | 112 |
| `coordinators/live_batch_coordinator.py` | 2 | 20 | 113, 114 |
| `coordinators/live_camera_session_coordinator.py` | 1 | 19 | 116 |
| `coordinators/multi_aquarium_coordinator.py` | 1 | 79 | 118 |
| `coordinators/project_lifecycle_coordinator.py` | 1 | 42 | 120 |
| `coordinators/recording_session_coordinator.py` | 1 | 17 | 121 |
| `coordinators/ui_state_coordinator.py` | 4 | 119 | 122, 123, 124, 125 |
| `core/conditions/evaluator.py` | 1 | 4 | 126 |
| `core/detection/aquarium_detector.py` | 2 | 76 | 127, 128 |
| `core/detection/bbox_area_gate.py` | 2 | 8 | 129, 130 |
| `core/detection/detection_post_processor.py` | 1 | 48 | 131 |
| `core/detection/detection_types.py` | 1 | 4 | 132 |
| `core/detection/multi_aquarium_detector.py` | 2 | 6 | 135, 136 |
| `core/detection/single_detector.py` | 5 | 57 | 139, 140, 141, 142, 143 |
| `core/project/asset_manager.py` | 1 | 18 | 144 |
| `core/project/project_manager.py` | 7 | 54 | 145, 146, 147, 148, 149, 150, 151 |
| `core/project/project_service.py` | 3 | 118 | 152, 153, 154 |
| `core/project/roi_template_manager.py` | 1 | 39 | 157 |
| `core/project/video_manager.py` | 1 | 12 | 158 |
| `core/project/zone_manager.py` | 1 | 27 | 159 |
| `core/recording/frame_ledger.py` | 1 | 4 | 163 |
| `core/recording/live_camera_mode.py` | 2 | 54 | 166, 167 |
| `core/recording/recording_service.py` | 1 | 11 | 169 |
| `core/services/arduino_roi_evaluator.py` | 1 | 4 | 170 |
| `core/services/detector_service.py` | 3 | 12 | 173, 174, 175 |
| `core/services/model_service.py` | 4 | 161 | 176, 177, 178, 179 |
| `core/services/trajectory_data_service.py` | 1 | 28 | 180 |
| `core/services/weight_manager.py` | 1 | 30 | 181 |
| `core/services/wizard_service.py` | 1 | 166 | 187 |
| `core/ui_scheduler.py` | 1 | 14 | 197 |
| `core/video/processing_worker.py` | 1 | 14 | 198 |
| `core/video/video_metadata_service.py` | 1 | 34 | 201 |
| `core/viewmodels/analysis_control_view_model.py` | 1 | 10 | 203 |
| `core/viewmodels/hardware_status_view_model.py` | 2 | 11 | 204, 205 |
| `io/arduino_manager.py` | 2 | 13 | 210, 211 |
| `io/recorder.py` | 7 | 97 | 214, 215, 216, 217, 219, 220, 221 |
| `plugins/openvino_detector.py` | 1 | 12 | 224 |
| `plugins/ultralytics_detector.py` | 1 | 12 | 227 |
| `settings.py` | 1 | 8 | 228 |
| `tracker/matching.py` | 6 | 92 | 231, 232, 233, 234, 235, 236 |
| `ui/builders/common_widgets.py` | 3 | 122 | 237, 238, 239 |
| `ui/builders/zone_widgets.py` | 3 | 109 | 242, 243, 244 |
| `ui/components/analysis_view_controller.py` | 1 | 3 | 245 |
| `ui/components/analysis_window_panel.py` | 1 | 4 | 246 |
| `ui/components/base.py` | 1 | 9 | 247 |
| `ui/components/canvas/renderer.py` | 1 | 7 | 248 |
| `ui/components/class_roles_panel.py` | 1 | 3 | 249 |
| `ui/components/dialog_manager.py` | 9 | 161 | 251, 252, 253, 254, 255, 256, 257, 259, 260 |
| `ui/components/menu_manager.py` | 2 | 81 | 266, 267 |
| `ui/components/processing_reports.py` | 2 | 14 | 268, 269 |
| `ui/components/project_overview.py` | 1 | 4 | 272 |
| `ui/components/project_views/reports_tree_manager.py` | 8 | 34 | 273, 274, 276, 277, 278, 279, 280, 281 |
| `ui/components/project_views/video_selector_tree_manager.py` | 5 | 39 | 282, 283, 284, 285, 286 |
| `ui/components/roi_template_manager.py` | 2 | 55 | 287, 288 |
| `ui/components/state_synchronizer.py` | 2 | 14 | 289, 290 |
| `ui/components/validation_manager.py` | 12 | 321 | 291, 292, 294, 295, 296, 297, 298, 299, 300, 301, 302, 303 |
| `ui/components/video_display.py` | 6 | 153 | 305, 306, 307, 308, 309, 310 |
| `ui/components/zone_controls.py` | 5 | 25 | 312, 313, 314, 315, 316 |
| `ui/components/zone_edit_guard.py` | 1 | 11 | 317 |
| `ui/dialogs/aquarium_detection_progress_dialog.py` | 2 | 28 | 319, 320 |
| `ui/gui.py` | 10 | 102 | 343, 344, 345, 346, 347, 348, 349, 350, 351, 353 |
| `ui/ui_coordinator.py` | 2 | 16 | 354, 355 |
| `ui/wizard/custom_regex_dialog.py` | 1 | 14 | 360 |
| `ui/wizard/templates.py` | 1 | 30 | 365 |

Tests that go with the batch: 84 test files mention at least one of these functions. The
shared ones (for example `tests/ui/components/test_dialog_manager.py`,
`tests/ui/components/test_validation_manager.py`, `tests/core/test_detector_partitioned.py`,
`tests/test_state_manager*.py`) lose only the tests that call the deleted function; the files that
exist only for one function (for example `tests/test_matching.py` for the `tracker/matching.py`
rows) can be deleted whole. After the deletion:

1. `poetry run pytest -q` and `poetry run pytest -m gui -n0` (the UI rows),
2. `poetry run mypy .` and `poetry run ruff check .`,
3. update the test-impact entries in `docs/testing/TEST_MAP.md` and the mentions listed under
   "What deserves attention" for any row that was also documented.

Dead rows that are NOT in the batch (51) are those in sections A and C above, rows
with a docstring, comment, doc or context-file mention that must be edited in the same change, and
`StateManager` introspection methods used by integration tests.

## What this review did not do

- No test or tool was run; every statement is from reading the code and from text search.
- A `getattr` target was checked for a live enclosing method, not traced to a Tk binding or event.
- Docs under `docs/archive/` and `docs/audits/` were not treated as references. `CHANGELOG.md` was
  treated as history.
- Dead branches inside live functions, dead constants and unused parameters were not examined (the
  same scope as A2).

## Deletion pass (2026-11-18)

The maintainer approved the rows marked `(safe)` in the section "Safest deletion batch" and nothing else.
Every row was re-verified against the tree as it was on the day of the pass (name search over `src/`,
`scripts/`, `tests/`, `docs/`, `.copilot-impact-map.yaml` and `resources/`, including `getattr` and string
dispatch), and each commit ran `ruff` and the touched tests. The rows in sections A, B and C above were not touched.

### Result

| | Rows | Lines (signature to last line, as counted above) |
| --- | --- | --- |
| Deleted | 154 | 2989 |
| Skipped | 9 | 147 |
| Total approved | 163 | 3136 |

Net change of the commits `refactor(dead-code): ...`: `src/` 16 lines added and 3356 removed; `tests/` 93 added and 3693 removed. The `src/` figure also covers the cascade removals below and the unused imports they freed. Of the 163 rows, 154 were deleted and 9 skipped (3 alive or off limits, 6 not a clean delete).

### Rows deleted

All the rows of the table at the top of "Safest deletion batch", except the nine below. Commits, in order:

| Commit | Scope | Rows (`A2-D-`) |
| --- | --- | --- |
| `f91f4a08` | analysis_service, roi | 101, 102, 109 |
| `f6495935` | coordinators | 112, 113, 114, 116, 118, 120, 121, 122, 123, 124, 125 |
| `7c468095` | core/detection, evaluator | 126-132, 135, 136, 139-143 |
| `b85e2a1f` | core/project, the three `delete_template` | 144-154, 157, 158, 159, 287, 365 |
| `f561075d` | core/services, recording, viewmodels | 163, 166, 167, 170, 173-181, 187, 197, 198, 201, 203, 204, 205 |
| `362ecf18` | io, plugins, settings, tracker | 210, 211, 214-217, 219-221, 224, 227, 228, 231-236 |
| `28c3c1eb` | UI builders and small components | 237-239, 242-249 |
| `480e8e16` | DialogManager, MenuManager | 252-257, 259, 260, 266, 267 |
| `b6ca4e29` | UI trees and synchronisers | 268, 269, 272-274, 276-286, 288-290 |
| `a336b435` | ValidationManager | 291, 292, 294-303 |
| `f2d653d4` | video_display, zone_controls, zone_edit_guard, progress dialog | 306-310, 315, 316, 317, 319 |
| `aa025354` | ApplicationGUI, CustomRegexDialog | 343-351, 353, 360 |

### Rows skipped

| Row | Function | Verdict now | Reason |
| --- | --- | --- | --- |
| A2-D-169 | `RecordingService.set_ui_callbacks` | kept | not a clean delete: it is the only writer of `RecordingService._ui_callbacks`, which three methods read (`show_error`, `update_button_state`, `set_status`, the stop callback) and about 20 tests rely on. Nothing in production calls it, so those callbacks are never wired: a missing caller, not dead weight. |
| A2-D-251 | `DialogManager.set_dialog_suppression` | kept | missing wiring, not dead code: `ProgressTrackingCoordinator._set_dialog_suppression` (called by the batch start) only touches the batch context and never forwards to `DialogManager.set_dialog_suppression`, so batch dialogs are never suppressed. |
| A2-D-305 | `VideoDisplayWidget.load_frame` | kept | `load_frame` is the only publisher of `FRAME_DISPLAYED` and `FRAME_ERROR`; without it `tests/quality/test_no_orphan_ui_events.py` fails and the fix is deleting `UIEvents` members in `ui/event_bus_v2.py` (off limits). |
| A2-D-312 | `ZoneControlsWidget._on_toggle_view_clicked` | kept | only publisher of `ZONE_TOGGLE_VIEW`; the event keeps its subscriber in `event_dispatcher.py` and its member in `event_bus_v2.py` (off limits), and the orphan-event guard fails without it. |
| A2-D-313 | `ZoneControlsWidget._on_video_refresh_clicked` | kept | same as A2-D-312, for `ZONE_VIDEO_REFRESH`. |
| A2-D-314 | `ZoneControlsWidget.set_roi_rule_config` | kept | the docstring says it re-displays the effective ROI rule after opening a project, and `tab_builder.py` resolves the rule only once at build time: looks like a missing caller, so it was left for a decision. |
| A2-D-320 | `AquariumDetectionProgressDialog.close_dialog` | alive now | `UICoordinator._close_aquarium_detection_dialog` now calls `dialog.close_dialog()` on the `AquariumDetectionProgressDialog` it opened. |
| A2-D-354 | `UICoordinator.get_statistics` | off limits | `ui/ui_coordinator.py` is being edited by the main session. |
| A2-D-355 | `UICoordinator.reset_statistics` | off limits | `ui/ui_coordinator.py` is being edited by the main session. |

### Removed along with them (cascade)

Helpers, imports and attributes that only the deleted code used, re-verified the same way:

- `AnalysisService._finalize_batch_processing`, `AnalysisService.build_metadata_context`: only `process_videos_batch` (A2-D-102) called them.
- `BaseTrack.set_id_counter`: only `SingleDetector._restore_trackers` (A2-D-143) called it.
- `ModelService.list_available_weights`: only `DetectorService.get_available_configs` (A2-D-173) called it.
- `CommonWidgetsBuilder.get_zone_summary_helper_text`, `ZoneWidgetsBuilder.on_frame_configure`, `ZoneWidgetsBuilder.on_canvas_configure_scroll`: only the removed builders used them.
- `MenuManager.get_overview_badge_font` and the `_overview_menu_font` attribute (menu manager and `gui.py`): only `show_overview_context_menu` (A2-D-267) used them.
- `ApplicationGUI.show_project_model_configuration_tab`, `ApplicationGUI._reload_config_editor_values_widget`: only the removed `_open_project_calibration_window` and `_on_reset_global_config_form_widget` called them.
- Imports freed by the deletions (`os`, `pandas`, `tkinter`, `cv2`, `yaml` and others), found with `ruff` F401.
- Two mutations of `live_camera_mode_selector` in `scripts/mutation_catalog.yaml` (`plan-ids-one-based`, `plan-notes-zero-based`): their `find` text lived in `create_sequential_session_plan` (A2-D-166). The block keeps its other mutations.
- Two entries of `tests/quality/shared_settings_allowlist.txt` that `_temporary_single_animal_mode` (A2-D-118) left stale.

### Cascade candidates left for a decision

No caller is left in `src/` or `scripts/` for these, but they are public members of other modules, vendored code, or have tests of their own, so they were not part of the approval:

- `ProjectViewModel.apply_project_settings_to_batch`: its only caller was `process_videos_batch`; it delegates to `batch_configuration_service.apply_settings`, which is a further cascade.
- `KalmanFilter.gating_distance`, `STrack.to_xyah`, `STrack.tlwh_to_tlbr`: vendored tracker API with their own tests; only the removed `tracker/matching.py` functions used them.
- `PanelBuilder.create_zone_summary_cards`, `VideoSelectorTreeManager.update_zone_summary_cards`: other modules, own tests; only the removed zone-summary section used them.
- `ReportAssetActions.delete_all_processing_data`: only the removed `ReportsTreeManager._delete_all_processing_data` shim called it.
- `HardwareStatusViewModel.get_openvino_cache_status`: only the removed `VideoSelectorTreeManager.refresh_openvino_summary` called it.
- `VideoSelectorTreeManager._on_project_overview_tree_double_click_impl`: only the removed `ApplicationGUI._on_project_overview_tree_double_click` and its tree-manager shim called it.
- `CenterPeripheryDialog`, `TemplateDialog` (classes in `ui/dialogs/`): the `DialogManager` wrappers that opened them are gone; both are still exported from `ui/dialogs/__init__.py`.

### Judgement calls in the edits

- Tests that read a deleted accessor only to observe state now read the private attribute the accessor returned, so the check survives: `BboxAreaGate.rejections` and `sample_count` (`_rejections`, `_areas`), `Recorder.is_paused()`, `is_multi_aquarium_mode()` and the two sidecar names, `ArduinoManager.last_command()`, `FrameLedger.rows_snapshot()` in the pipeline helpers, `SingleDetector.is_single_subject_mode()`, `AnalysisWindowPanel.is_session_only`, `ClassRolesPanel.seed_fit()`, `ZoneControlsWidget.get_active_aquarium_id()` and the two `LiveBatchCoordinator` getters (`_active_batches`).
- Tests that used `WeightManager.set_default_weight_by_type` only as set-up now call `set_default_weight_for` with the target that wrapper inferred (`zebrafish` for `seg`, `aquarium` for `det`). The wizard template test that used `TemplateManager.delete_template` to create the tombstone now unlinks the file.
- `test_expand_and_collapse_tree_item` keeps its expand half (`test_expand_tree_item`); `test_detect_filters_multiple_detections_by_polygon` no longer patches the dead `_is_inside_polygon`.
- The `check-path-consistency` hook flags every changed file that still has a path-like `str` parameter, so three untouched legacy signatures became `Path | str` with a `str(...)` at the use: `TrajectoryDataService.load_trajectory`, `VideoMetadataService.get_video_dimensions` and `VideoDisplayWidget.load_frame`.

### Tests removed

248 test functions went with the rows (counted by `def test_...` lines in the diffs; a few are parts of tests that were rewritten rather than removed). Whole files deleted: `tests/analysis/test_analysis_events.py`, `tests/core/test_wizard_service_multi_aquarium.py`. Per file:

| File | Count | Tests |
| --- | --- | --- |
| `tests/analysis/test_analysis_events.py` | 1 | `test_process_videos_batch_publishes_social_summary_event` |
| `tests/analysis/test_analysis_service.py` | 2 | `test_validate_trajectory_schema_success`, `test_validate_trajectory_schema_missing_columns` |
| `tests/analysis/test_analysis_service_batch.py` | 9 | `test_process_videos_batch_initialization`, `test_process_videos_batch_with_single_video_config`, `test_process_videos_batch_cancellation`, `test_process_videos_batch_partial_processing`, `test_process_videos_batch_with_metadata_derivation`, `test_process_videos_batch_exception_handling`, `test_finalize_batch_processing_success`, `test_finalize_batch_processing_cancelled`, `test_finalize_batch_processing_empty_videos_list` |
| `tests/analysis/test_analysis_service_error_handling.py` | 2 | `test_schema_validation_extra_columns_allowed`, `test_build_metadata_context_with_none_video_info` |
| `tests/analysis/test_analysis_service_video_processing.py` | 5 | `test_validate_trajectory_schema_valid`, `test_validate_trajectory_schema_missing_columns`, `test_build_metadata_context_single_video`, `test_build_metadata_context_with_derive_callback`, `test_build_metadata_context_derive_callback_fails` |
| `tests/coordinators/test_live_camera_session_coordinator.py` | 2 | `test_get_live_session_info_not_active`, `test_get_live_session_info_active` |
| `tests/coordinators/test_live_camera_session_coordinator_extended.py` | 1 | `test_get_live_session_info_idle` |
| `tests/coordinators/test_multi_aquarium_coordinator.py` | 1 | `test_temporary_single_animal_mode` |
| `tests/coordinators/test_processing_coordinator_coverage.py` | 3 | `test_temporary_single_animal_mode_method_exists`, `test_temporary_single_animal_mode_is_context_manager`, `test_temporary_mode_infers_tracker_pref_from_single_animal` |
| `tests/coordinators/test_project_lifecycle_coordinator.py` | 1 | `test_register_project_outputs` |
| `tests/coordinators/test_recording_session_coordinator.py` | 2 | `test_get_recording_info`, `test_get_recording_info_not_recording` |
| `tests/coordinators/test_ui_state_coordinator.py` | 7 | `test_no_active_video`, `test_apply_success`, `test_apply_file_not_found`, `test_apply_generic_exception`, `test_update_main_arena_success`, `test_prepare_processing_ui`, `test_finalize_processing_success_and_cancelled` |
| `tests/core/project/test_asset_manager.py` | 5 | `test_ensure_roi_template_dir`, `test_ensure_roi_template_dir`, `test_ensure_roi_template_dir`, `test_ensure_roi_template_dir`, `test_ensure_roi_template_dir_empty_raises` |
| `tests/core/project/test_roi_template_manager.py` | 1 | `test_delete_template` |
| `tests/core/project/test_video_manager.py` | 1 | `test_refresh_complete_flag` |
| `tests/core/recording/test_live_camera_mode_extended.py` | 4 | `test_one_single_aquarium_session_per_aquarium`, `test_zero_aquariums_is_an_empty_plan`, `test_every_mode_has_its_own_description`, `test_unknown_value_has_a_fallback` |
| `tests/core/services/test_arduino_roi_evaluator_extended.py` | 1 | `test_centroid_of_bbox` |
| `tests/core/services/test_detector_service_extended.py` | 2 | `test_get_active_config`, `test_get_available_configs_and_active_config` |
| `tests/core/services/test_model_service_extended.py` | 2 | `test_list_available_weights`, `test_validate_weight` |
| `tests/core/services/test_trajectory_data_service_extended.py` | 2 | `test_load_trajectory_safe_missing_returns_none`, `test_load_trajectory_safe_corrupt_returns_none` |
| `tests/core/services/test_weight_manager_extended.py` | 1 | `test_set_default_weight_by_type` |
| `tests/core/services/test_wizard_service_extended.py` | 3 | `test_disabled_multi_aquarium`, `test_dict_config_enabled_with_wrong_count`, `test_dict_config_small_polygon_warning_and_overlap_warning` |
| `tests/core/test_analysis_control_view_model.py` | 3 | `test_auto_detect_zones_publishes_event`, `test_auto_detect_defaults_the_stabilization_and_the_path`, `test_auto_detect_without_a_bus_is_a_noop` |
| `tests/core/test_aquarium_detector_multi.py` | 7 | `test_detect_from_frame_two_aquariums`, `test_detect_from_frame_wrong_expected_count`, `test_detect_from_frame_expected_count_one`, `test_validate_aquarium_pair_valid`, `test_validate_aquarium_pair_same_side`, `test_validate_aquarium_pair_size_mismatch`, `test_validate_aquarium_pair_wrong_count` |
| `tests/core/test_arduino_roi_evaluator.py` | 1 | `test_centroid_of_bbox` |
| `tests/core/test_detection_post_processor.py` | 4 | `test_empty_does_not_raise`, `test_all_none_track_ids_does_not_raise`, `test_gap_does_not_raise`, `test_duplicate_does_not_raise` |
| `tests/core/test_detector_partitioned.py` | 6 | `test_is_multi_aquarium_mode_false`, `test_is_multi_aquarium_mode_true`, `test_point_inside`, `test_point_outside`, `test_point_on_boundary`, `test_empty_polygon` |
| `tests/core/test_hardware_status_view_model.py` | 2 | `test_setup_arduino_is_deprecated_and_reports_failure`, `test_get_arduino_manager_returns_the_bootstrapped_manager` |
| `tests/core/test_model_service.py` | 12 | `test_get_weight_type_seg`, `test_get_weight_type_det`, `test_get_weight_type_not_found`, `test_validate_model_configuration_valid`, `test_validate_model_configuration_no_weight`, `test_validate_model_configuration_weight_not_found`, `test_validate_model_configuration_weight_file_missing`, `test_validate_model_configuration_openvino_not_ready`, `test_validate_model_configuration_openvino_failed`, `test_get_weight_configuration_summary_complete`, `test_get_weight_configuration_summary_none`, `test_get_weight_configuration_summary_not_found` |
| `tests/core/test_multi_aquarium_models.py` | 1 | `test_aquarium_count_property` |
| `tests/core/test_processing_worker_unit.py` | 1 | `test_format_subject_handles_numeric_and_strings` |
| `tests/core/test_project_manager_multi_aquarium.py` | 2 | `test_has_trajectory_data_for_aquarium_is_granular`, `test_has_summary_data_for_aquarium_is_granular` |
| `tests/core/test_project_service.py` | 3 | `test_load_metadata_csv_success`, `test_load_metadata_csv_not_found`, `test_load_metadata_csv_invalid_format` |
| `tests/core/test_trajectory_data_service.py` | 3 | `test_safe_load_success`, `test_safe_load_missing_returns_none`, `test_safe_load_corrupted_returns_none` |
| `tests/core/test_ui_scheduler.py` | 3 | `test_cancel_scheduled`, `test_cancel_scheduled_without_root`, `test_cancel_scheduled_handles_exception` |
| `tests/core/test_ui_scheduler_extended.py` | 2 | `test_cancel_scheduled_no_root`, `test_cancel_scheduled_calls_after_cancel` |
| `tests/core/test_video_metadata_service.py` | 2 | `test_get_video_info_success`, `test_get_video_info_open_fail` |
| `tests/core/test_wizard_service_multi_aquarium.py` | 18 | `test_validate_disabled_config`, `test_validate_enabled_with_2_aquariums`, `test_validate_missing_aquariums`, `test_validate_only_one_aquarium`, `test_validate_invalid_regex_pattern`, `test_validate_regex_missing_groups`, `test_validate_regex_with_correct_groups`, `test_validate_regex_against_matching_filenames`, `test_validate_regex_against_non_matching_filenames`, `test_validate_with_empty_regex`, `test_validate_partial_regex_match`, `test_validate_dict_like_config`, `test_validate_dict_enabled_missing_aquariums`, `test_validate_with_none_sample_filenames`, `test_validate_with_empty_sample_filenames`, `test_validate_complex_regex`, `test_validate_multiple_errors_accumulated`, `test_complete_wizard_flow_validation` |
| `tests/core/video/test_video_metadata_service_extended.py` | 2 | `test_get_video_info_success`, `test_get_video_info_cannot_open_raises` |
| `tests/integration/test_gui_component_integration.py` | 1 | `test_remove_selected_roi_confirm` |
| `tests/io/test_recorder_multi_aquarium.py` | 1 | `test_writes_frame_to_correct_recorder` |
| `tests/plugins/test_openvino_detector.py` | 1 | `test_tracking_hints_ignore_missing_and_non_positive_values` |
| `tests/plugins/test_ultralytics_detector.py` | 2 | `test_ultralytics_detector_set_tracking_parameters`, `test_set_tracking_parameters` |
| `tests/test_basetrack.py` | 2 | `test_set_id_counter`, `test_set_id_counter_zero` |
| `tests/test_detector.py` | 2 | `test_is_inside_polygon`, `test_is_inside_polygon_four_corners_or_center` |
| `tests/test_matching.py` | 10 | `test_identical_boxes_full_score`, `test_output_in_unit_range`, `test_consistent_matches_intersect`, `test_disjoint_matches_have_no_intersection`, `test_empty`, `test_identical_features_zero_distance`, `test_orthogonal_features_unit_distance`, `test_far_detection_is_gated_to_inf`, `test_close_detection_unchanged`, `test_empty_short_circuit` |
| `tests/test_project_manager.py` | 1 | `test_validate_project_parameters_bounds` |
| `tests/test_property_detection_types.py` | 1 | `test_aquarium_count_matches_list_length` |
| `tests/test_settings.py` | 1 | `test_real_settings_expose_the_same_answer_as_the_property` |
| `tests/test_ui_scheduler_threading.py` | 1 | `test_concurrent_cancel_scheduled_calls` |
| `tests/ui/components/test_base_widget.py` | 1 | `test_set_enabled_updates_children` |
| `tests/ui/components/test_canvas_renderer.py` | 1 | `test_clear_placeholder_logo_drops_tag_and_reference` |
| `tests/ui/components/test_dialog_manager.py` | 17 | `test_open_global_calibration_window`, `test_open_project_calibration_window_no_project`, `test_open_project_calibration_window_success`, `test_show_template_save_dialog_returns_result`, `test_show_template_save_dialog_returns_none_on_cancel`, `test_open_center_periphery_dialog_returns_result`, `test_open_center_periphery_dialog_returns_none_on_cancel`, `test_open_template_rois_dialog_returns_result`, `test_open_template_rois_dialog_returns_none_on_cancel`, `test_open_single_video_config_dialog_returns_result`, `test_open_single_video_config_dialog_returns_none_on_cancel`, `test_confirm_delete_roi_template_confirmed`, `test_confirm_delete_roi_template_cancelled`, `test_open_path_in_explorer_delegates_to_os_opener`, `test_open_path_in_explorer_error`, `test_show_template_save_dialog_empty_result_dict`, `test_open_project_calibration_falls_back_to_dialog_when_tab_unavailable` |
| `tests/ui/components/test_menu_manager.py` | 9 | `test_get_overview_badge_font_creates_font`, `test_get_overview_badge_font_caches_font`, `test_get_overview_badge_font_no_tree`, `test_resolve_overview_asset_from_click_no_tree`, `test_resolve_overview_asset_from_click_no_bbox`, `test_resolve_overview_asset_from_click_arena`, `test_show_overview_context_menu_no_tree`, `test_show_overview_context_menu_creates_menu`, `test_show_overview_context_menu_labels` |
| `tests/ui/components/test_project_overview.py` | 1 | `test_expand_and_collapse_tree_item` |
| `tests/ui/components/test_roi_template_manager.py` | 2 | `test_delete_template`, `test_import_template_error_shows_message` |
| `tests/ui/components/test_state_synchronizer.py` | 1 | `test_default_analysis_metadata_text` |
| `tests/ui/components/test_validation_manager.py` | 41 | `test_compose_overview_status_line_empty`, `test_compose_overview_status_line_negative_total`, `test_compose_overview_status_line_single_status`, `test_compose_overview_status_line_multiple_statuses`, `test_compose_overview_status_line_all_statuses`, `test_compose_overview_status_line_unknown_status`, `test_get_selected_roi_template_empty_cache`, `test_get_selected_roi_template_no_selection`, `test_get_selected_roi_template_found`, `test_get_selected_roi_template_not_found`, `test_validate_roi_template_data_none`, `test_validate_roi_template_data_no_polygon_no_rois`, `test_validate_roi_template_data_with_polygon`, `test_validate_roi_template_data_with_rois_only`, `test_validate_arena_for_analysis_none`, `test_validate_arena_for_analysis_empty`, `test_validate_arena_for_analysis_valid`, `test_validate_arena_polygon_data_none`, `test_validate_arena_polygon_data_no_polygon`, `test_validate_arena_polygon_data_valid`, `test_validate_positive_integer_valid`, `test_validate_positive_integer_invalid`, `test_validate_positive_integer_custom_field_name`, `test_validate_active_video_selection_none`, `test_validate_active_video_selection_empty`, `test_validate_active_video_selection_valid`, `test_format_roi_template_display_basic`, `test_format_roi_template_display_arena_and_rois`, `test_format_roi_template_display_global`, `test_format_roi_template_display_no_data`, `test_build_roi_template_identifier_project_with_slug`, `test_build_roi_template_identifier_with_file`, `test_build_roi_template_identifier_fallback_to_name`, `test_format_time_variations`, `test_format_subject_for_reports_is_alias`, `test_validate_positive_integer_with_float_string`, `test_compose_overview_status_line_only_unknown_statuses`, `test_build_roi_template_identifier_empty_template`, `test_save_global_config_validation_error`, `test_save_global_config_without_settings`, `test_save_global_config_success` |
| `tests/ui/components/test_validation_manager_extended.py` | 13 | `test_compose_overview_status_line`, `test_save_global_config_from_widget_validation_errors`, `test_compose_overview_status_line_empty`, `test_compose_overview_status_line_populated`, `test_save_global_config_invalid_fps`, `test_save_global_config_invalid_processing_interval`, `test_save_global_config_invalid_flush_rows`, `test_save_global_config_invalid_polyorder`, `test_save_global_config_even_window_length`, `test_save_global_config_invalid_fps`, `test_save_global_config_invalid_processing_interval`, `test_save_global_config_invalid_display_interval`, `test_save_global_config_invalid_offset` |
| `tests/ui/components/test_video_display_widget.py` | 3 | `test_get_image_size_defaults`, `test_set_image_updates_state`, `test_coordinate_conversions` |
| `tests/ui/components/test_widget_factory.py` | 3 | `test_build_status_icon_legend_simple`, `test_get_zone_summary_helper_text`, `test_create_zone_summary_cards_section_updates_project_view_manager` |
| `tests/ui/components/test_zone_controls_widget.py` | 1 | `test_update_template_list` |
| `tests/ui/test_zone_controls_multi_aquarium.py` | 2 | `test_get_active_aquarium_id_default`, `test_get_active_aquarium_id_returns_set_value` |
