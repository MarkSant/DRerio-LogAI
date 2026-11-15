# Loose-ends audit — November 2026

Register of the audit that runs alongside the `plugins/` and `utils/` coverage campaign
(TASK-087). One row per finding; a row is closed by a PR or by an explicit decision to accept it.

## How to read this file

- **Status** is one of `candidate` (a static scan flagged it; nobody has read the code yet),
  `confirmed` (the code was read and the defect is real), `fixed`, `removed`, `accepted` (real, and
  deliberately left) or `false positive`.
- **Deleting code is the maintainer's decision.** A row proposes; nothing is removed until its
  decision column says so.
- A confirmed defect gets a test that fails without the fix **before** it is fixed.
- Counts in the summaries come from AST and ripgrep scans of `src/zebtrack` at `b03e5546`
  (318 files). They size the work; they are not findings on their own.

## A1 — Event bus

`EventBusV2.publish` returns silently when an event has no subscriber, and
`BaseCoordinator._publish_event` is typed `event_type: Any`. Both make a dead event invisible to
mypy and to the user.

| ID | Finding | Evidence | Status | Decision |
| --- | --- | --- | --- | --- |
| A1-01 | Seven events are published as plain strings, not `UIEvents` members. `EventBusV2` keys its subscribers by enum member, so a string reaches nobody, and five of the seven names (`PROJECT_LOADED`, `ZONES_CONFIGURED`, `TRACKING_PARAMETERS_UPDATED`, `SINGLE_SUBJECT_MODE_CHANGED`, `DETECTOR_SETTINGS_RESTORED`) are not in the enum at all: nothing could ever have subscribed. `_publish_event(event_type: Any)` hides it from mypy, and a string with a non-dict payload would raise `AttributeError` inside `_coerce_payload` (`event_type.name`). Three sites are in `ProjectCoordinator`, which is never instantiated (A2-04); four are in `DetectorSetupCoordinator`, which runs in the live app. | `coordinators/project_coordinator.py:280,466,574`; `coordinators/detector_setup_coordinator.py:344,475,712,842`; `coordinators/base_coordinator.py:233`; `ui/event_bus_v2.py:572-592` | confirmed | proposed: type `_publish_event` as `UIEvents`, delete the four no-op publishes (no listener ever existed) and extend the orphan-event guard to this wrapper (A1-05) |
| A1-02 | 14 `UIEvents` members are published and never subscribed. Several are UI controls whose action goes nowhere: `PROCESSING_EXPORT_SUMMARIES`, `REPORTS_GENERATE_PARTIAL`, `CONFIG_ROI_RULE_CHANGED`, `BEHAVIORAL_CONFIG_*`, `CONTROL_PREVIEW_TOGGLED`, `CONTROL_INTERVAL_CHANGED`. | `ui/components/processing_reports.py:390,427,438`; `ui/components/behavioral_config_widget.py:414,424,441`; `ui/components/config_editor.py:887`; `ui/components/control_panel.py:150,159` | candidate | open |
| A1-03 | 22 members are subscribed and never published; six have handler code nothing can reach. | `core/viewmodels/main_view_model_runtime.py:54-84`; `ui/ui_coordinator.py:163-188`; `ui/components/event_dispatcher.py:297,321,382,729,1150,1154` | candidate | open |
| A1-04 | 38 members are never referenced outside `ui/event_bus_v2.py`. | scan | candidate | open |
| A1-05 | `tests/quality/test_no_orphan_ui_events.py` does not see `_publish_event` (106 sites), `_publish_model_event`, `_publish_arduino_ui`, `bind_callback` or the `_EVENTS_TO_HANDLE` tuple, and checks only "published but not subscribed". Four allowlist entries are stale as a result. | `tests/quality/test_no_orphan_ui_events.py` | candidate | open |
| A1-06 | `scripts/audit_events.py` reads `src/zebtrack/ui/events.py`, which no longer exists. | `scripts/audit_events.py` | candidate | open |
| A1-07 | `publish` runs every handler on the calling thread, so a publish from a worker thread reaches widget handlers directly. No publisher-to-thread map exists. | `ui/event_bus_v2.py:696` | candidate | open |

## A2 — Dead code

| ID | Finding | Evidence | Status | Decision |
| --- | --- | --- | --- | --- |
| A2-01 | `src/zebtrack/utils.py` sits beside the `utils/` package, which shadows it. Reachable only through `spec_from_file_location` in one test. | `src/zebtrack/utils.py`; `tests/test_utils_module.py` | removed | deleted with `tests/test_utils_module.py` (maintainer's decision, 2026-11-14) |
| A2-02 | `utils.video.get_video_dimensions` has no caller in `src`; every caller uses `VideoMetadataService.get_video_dimensions`. Only its own tests import it. | `utils/video.py`; `tests/utils/test_video.py` | removed | deleted with `tests/utils/test_video.py` (maintainer's decision, 2026-11-14) |
| A2-03 | Three public functions in the campaign's own packages have no caller. | `plugins/openvino_detector.py:412 get_context_info`; `utils/hardware_benchmark.py:1097 get_optimal_settings`; `utils/hardware_capability.py:461 assess_hardware_for_live_multi_aquarium` | removed (no caller in `src`; the first is only defined again by test fakes, the other two are called only by tests) | removed (2026-11-14), with their tests |
| A2-04 | `ProjectCoordinator` (681 lines) is exported and tested but never instantiated. | `coordinators/project_coordinator.py:50` | candidate | open |
| A2-05 | A random-data mock `BehavioralAnalyzer` lives in production source; the real one is in `analysis/behavior.py`. | `analysis/behavioral_analyzer.py` | candidate | open |
| A2-06 | Seven modules are re-exported by a package `__init__` and used nowhere. | `io/frame_source_factory.py`, `io/sources.py`, `ui/components/{analysis_controls,base_component,control_panel}.py`, `ui/dialogs/{live_config_dialog,multi_aquarium_confirm_dialog}.py` | candidate | open |
| A2-07 | `cv2` fallbacks under `# pragma: no cover` cannot run in production: DI always injects the service they guard against. They also call `cap.release()` outside `try/finally`. | `coordinators/report_generation_coordinator.py:117-119,1163-1171,1208-1227`; `coordinators/video_processing_coordinator.py:251-263` | candidate | open |
| A2-08 | 218 of 5093 definitions are named only once in `src`. | scan | candidate | open |
| A2-10 | `polygon_centroid` and `snap_point_to_axes` existed three times, now twice: in `utils/__init__.py`, in `utils/geometry.py` (the third copy went with the stray `utils.py`, A2-01). The copies are separate functions (`zebtrack.utils.polygon_centroid is not zebtrack.utils.geometry.polygon_centroid`), so a fix to one does not reach the others. | `utils/__init__.py:81,105`; `utils/geometry.py` | confirmed | proposed: keep `geometry.py`, re-export from `__init__` |
| A2-11 | `BenchmarkRecommendation.recommended_batch_size` and `.decode_backend` are computed and never read by the application. On a machine without GPU the batch size comes out as `0` (`min(4, int(0.0))`). | `utils/hardware_benchmark.py` (`_generate_recommendation`); readers: `core/app_runner.py:538-566` use only inference size, memory mode and FPS | confirmed | open |
| A2-12 | A `try/except` around a plain dict assignment can never fire. | `plugins/openvino_detector.py` (`config["NPU_TURBO"] = True`) | confirmed | open |
| A2-09 | `ui/components/validators/config_validator.py` has no user in `src` or `tests`. | scan | candidate | open |

## A3 — Dependency injection

| ID | Finding | Evidence | Status | Decision |
| --- | --- | --- | --- | --- |
| A3-01 | Three `ProjectService` instances exist: the container's, the bootstrapper's and `ProjectManager`'s. | `core/di_registrations.py:198`; `core/application_bootstrapper.py:208`; `core/project/project_manager.py:71` | candidate | open |
| A3-02 | Twelve container registrations are never resolved; the same objects are wired by hand. | `core/di_registrations.py:437-442,524-527` | candidate | open |
| A3-03 | `MainViewModelDependencies` carries fields nothing reads, and `test_sync_event` is a test-only field in a production dataclass. | `core/dependency_container.py:207` | candidate | open |

## A4 — Single source of truth and scientific correctness

| ID | Finding | Evidence | Status | Decision |
| --- | --- | --- | --- | --- |
| A4-01 | `get_zone_data()` (aquarium 0 only) is called in report and post-analysis contexts. Read one by one (2026-11-15): the single-aquarium report paths (`report_generation_coordinator.py`, `_process_single` and the session-folder fallback) pass `video_path` and run only when the video is not multi-aquarium, so aquarium 0 is the right answer there; the multi path asks `get_multi_aquarium_zone_data` first. Two real gaps remain, both in the UNIFIED report: `_find_project_roi_names` and `_collect_roi_colors_into` read ROI names and colours from aquarium 0 only, so a ROI that exists only in another aquarium is missing from the name list and gets no colour. | `coordinators/report_generation_coordinator.py` (`_find_project_roi_names`); `coordinators/_unified_report_mixin.py` (`_collect_roi_colors_into`) | confirmed (narrowed to the two unified-report helpers) | open |
| A4-02 | Animals are counted with `nunique` outside `track_significance`. Read (2026-11-15): both sites feed only the "tracks" figure of the completion dialog shown after a live session. No metric uses them, but the figure counts raw track ids, so a one-row spurious track shows as an extra animal. | `core/recording/live_analysis_post_processor.py` (two `df["track_id"].nunique()` sites) | confirmed, display only | open: use `count_subjects()` or label the figure "track ids" |
| A4-03 | `settings.video_processing.fps` is read in report code. | `coordinators/report_generation_coordinator.py:304` | false positive | the value is passed down as `fallback_fps` to `_resolve_report_time_base`, which is the documented last resort of the time base |
| A4-04 | Whole-row `drop_duplicates()` on ROI events. Read (2026-11-15): the rows are `(timestamp, event, roi_name)` of one trajectory, so a duplicate is the same event logged twice, not two animals with equal metrics (the case the project rule is about). | `analysis/roi.py` (`event_df = pd.DataFrame(events).drop_duplicates()`) | accepted | none |
| A4-05 | The deprecated `ReporterContext(trajectory_df=...)` path still has three production callers. | `coordinators/report_generation_coordinator.py:834,925`; `core/video/analysis_pipeline_runner.py:412` | candidate | open |
| A4-06 | Follow-ups left by `docs/tasks/v8/AUDIT.md`: wrong keyword arguments (`live_analysis_post_processor.py:1189`), distance summed across tracking gaps, `fillna(0)` in freezing. | `docs/tasks/v8/AUDIT.md` | candidate | open |
| A4-07 | An unpacking bug in hardware capability detection was left open by the 2026-01 live-camera audit. | `utils/hardware_capability.py:129` | false positive | `_detect_gpu` returns four values and the call site unpacks four; already fixed. Now pinned by `tests/utils/test_hardware_capability.py`. |
| A4-08 | OpenVINO segmentation masks were stretched onto the frame together with the letterbox padding. On a 640x480 frame every contour was squeezed towards the centre, up to 20 px away from its own bounding box. This is the geometry the `seg_overlap` ROI rule measures against; the Ultralytics backend was not affected. | `plugins/openvino_detector.py` (`_scale_image`) | fixed | red test first: `TestMasks::test_captured_contours_align_with_their_detection_in_frame_pixels`, `TestScaleImage`; mutation `mask-padding-not-cropped` |
| A4-09 | Height and width were swapped on the way to the letterbox. Invisible while every exported model is square; a 384x640 model received a 640x384 tensor. | `plugins/openvino_detector.py` (`_preprocess`) | fixed | red test first: `TestInputShape::test_a_rectangular_model_gets_a_tensor_of_its_own_shape`; mutation `letterbox-shape-swapped` |
| A4-10 | The hardware benchmark compiled GPU/NPU models into `openvino_model_cache/compiled_cache` relative to the WORKING DIRECTORY, while the detector resolves the same setting against the repository root. Started from anywhere else, the benchmark left a stray cache folder behind and the application never reused the blobs. | `utils/hardware_benchmark.py` (`_compiled_cache_dir`) | fixed | red test first; mutation `compiled-cache-follows-cwd` |
| A4-11 | For an NVIDIA+CUDA machine `_generate_recommendation` returns early, before the decode backend is chosen and before `_apply_hardware_sizing` runs: such a machine never gets the low-memory mode, however little RAM it has. | `utils/hardware_benchmark.py` (`_generate_recommendation`) | confirmed | open: is skipping the sizing intended? |
| A4-12 | The capability tiers compare `total_memory_gb` against nominal sizes (`< 8`, `< 16`), but a nominal 16 GB machine reports about 15.8 GiB and a nominal 8 GB one about 7.8, so each lands one tier below the one its documentation promises. | `utils/hardware_capability.py` (`_calculate_capability_tier`) | candidate | open: needs a reading from real machines |
| A4-13 | `_run_analysis_pipeline` receives `video_path` and still calls `project_manager.get_zone_data()` with no video, i.e. the GLOBAL zones, to build the ROIs of the analysis that follows tracking. For a single video that is the only zone set there is. For a pre-recorded PROJECT, whose per-video saves no longer mirror into the global default, it would analyse against empty or another video's ROIs. Not established: whether a project batch reaches this method at all. Its batch caller `AnalysisService.process_videos_batch` has no caller in `src`. | `core/video/analysis_pipeline_runner.py` (`_run_analysis_pipeline`); `core/video/video_processing_service.py` (`process_single_video`); `analysis/analysis_service.py` (`process_videos_batch`) | candidate | open: trace the project batch flow before changing anything |

## A5 — Silent failures

| ID | Finding | Evidence | Status | Decision |
| --- | --- | --- | --- | --- |
| A5-01 | 40 of 532 broad handlers neither log nor re-raise; 30 are in `ui/`. | scan | candidate | open |
| A5-02 | The `MODEL_FORCE_BENCHMARK` and `MODEL_CONVERT_OPENVINO` worker threads discard their result; the user gets no answer. | `core/viewmodels/main_view_model_runtime.py:246,256` | candidate | open |

## A6 — Threads, Tk and resources

| ID | Finding | Evidence | Status | Decision |
| --- | --- | --- | --- | --- |
| A6-01 | `time.sleep` likely on the Tk thread. | `ui/components/project_views/report_generator_actions.py:302`; `coordinators/live_calibration_coordinator.py:992-1527` | candidate | open |
| A6-02 | The pipeline benchmark left its video open when a run failed midway. | `utils/hardware_benchmark.py` (`_benchmark_pipeline_complete`) | fixed | red test first: `TestPipelineBenchmark::test_the_video_is_released_when_the_run_fails_midway` |
| A6-03 | `HardwareCapabilityDetector.assess_capability` samples the CPU with `psutil.cpu_percent(interval=0.5)`, a half-second block, and is called from the live wizard step. | `utils/hardware_capability.py`; `ui/wizard/live_config_step.py:543` | candidate | open: confirm the calling thread |

## A7 — Configuration and stale documentation

| ID | Finding | Evidence | Status | Decision |
| --- | --- | --- | --- | --- |
| A7-01 | Five `Settings` fields have no reader (`yolo_model.animal_confidence_threshold` was flagged too and is a false positive: `settings.resolve_animal_confidence` reads it through `getattr`). | `yolo_model.animal_confidence_threshold`, `live_analysis.auto_stop_on_limit`, `live_analysis.show_countdown`, `detection_zones.max_aquarium_area_ratio`, `ui_features.use_wizard_for_project_creation`, `performance.max_parallel_videos` | candidate | open |
| A7-02 | `load_settings()` is called outside the composition root, bypassing the injected settings. | `ui/wizard/calibration_step.py:294` | candidate | open |
| A7-03 | `KNOWN_ISSUES.md` describes a 519-test suite and a test file that no longer exists. | `docs/reference/KNOWN_ISSUES.md` | candidate | open |
| A7-04 | `.copilot-impact-map.yaml` names paths that do not exist. | `.copilot-impact-map.yaml:193,197,247` | candidate | open |
| A7-06 | `scripts/impact_analyzer.py`, mandatory before every change, crashes on a Windows console: it prints emoji and `cp1252` cannot encode them. It only works with `PYTHONIOENCODING=utf-8`. | `scripts/impact_analyzer.py:692` | confirmed | open |
| A7-07 | Tests wrote into the repository: the cache-directory tests created `scratch_ov_cache_test/` and `openvino_model_cache/` under the repository root. | former `tests/plugins/test_openvino_detector_extended.py` | fixed | rewritten against a temporary root in `tests/plugins/test_openvino_detector.py::TestCacheDir` |
| A7-08 | A test helper installs `sys.modules["openvino"] = MagicMock()` and never removes it, so on a machine without OpenVINO every later test sees a fake runtime. | `tests/test_openvino_batch_inference.py:46` | confirmed | open: the file's behaviours are now also covered, without mocks, by `TestDetectBatch` |
| A7-05 | A comment in `pytest.ini` says the default run is parallel; `addopts` passes `-n0`. | `pytest.ini` | candidate | open |

## A8 — End-to-end flows

No finding yet. The deliverable is one golden test per flow (pre-recorded project, single video,
live project, ad-hoc live), built on `tests/helpers/prerecorded_pipeline.py` and
[`LIVE_FLOW_TEST_PROTOCOL.md`](../testing/LIVE_FLOW_TEST_PROTOCOL.md).
