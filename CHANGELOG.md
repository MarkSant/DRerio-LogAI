# Changelog

All notable changes to DRerio LogAI (zebtrack) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- markdownlint-disable MD024 --><!-- justification: repeated standard headings per release section -->

## [Unreleased]

### 📚 Documentation & Standardization

#### Phase 8 — Documentation & Standardization (February 2026)

- **8.1 English translation**: Translated Portuguese docstrings and inline
  comments to English across 12 source files (gui.py, drawing_state_manager,
  roi_template_manager, polygon_drawing_service, event_dispatcher,
  batch_configuration_service, video_metadata_service, thread_coordinator,
  orchestrator_registry, detection_types, dialog_coordinator,
  visualization_generator); kept PT-BR user-facing strings intentionally
- **8.2 Coverage gates**: Researched JOSS, pyOpenSci, OpenSSF standards;
  measured baseline at 46.1%; raised CI gates (Linux core 45→50%, GUI
  30→32%, Windows 25→28%, local 40→45%); fixed 5 test regressions from
  Phase 7 API changes; created `docs/testing/COVERAGE_STANDARDS_ANALYSIS.md`
  with evidence-based roadmap to OpenSSF Silver (80%)
- **8.3 Property-based testing**: Added Hypothesis ^6.100.0 dependency; 83
  property tests across 6 files covering settings round-trips, detection
  type conversions, recorder IOU/dedup/normalize, zone scaler identity and
  proportional scaling, behavioral analysis invariants, and calibration
  point ordering
- **8.4 ADR documentation**: Created ADR-001 (Multi-Aquarium Support) and
  ADR-004 (Live Camera Architecture Divergence); updated ADR-009 with Phase
  4 coordinator decomposition status
- **8.5 System integration map**: Updated from v3.2 to v4.0 — documented
  Phase 4 coordinator decomposition (4 super → 16 specialized), added
  ADR-009 deprecation notice, performance architecture (Phase 7),
  documentation standards section, document changelog

### ⚡ Performance

#### Phase 7 — Performance Optimizations (February 2026)

**Measured speedups** (pytest-benchmark, -n0):

| Optimization | Before | After | Speedup |
|---|---|---|---|
| Angular velocity (5 000 pts) | 13.5 ms (loop) | 1.4 ms (NumPy) | ~9× |
| Recorder flush (500 rows) | 3.6 ms (pd.DataFrame) | 0.4 ms (pa.table) | ~8× |
| Polygon containment (1 000 pts) | 3.2 ms (pointPolygonTest) | 1.9 ms (mask) | ~1.7× |
| Preview IPC write (720p) | 2.8 ms (pickle) | 0.9 ms (SharedMemory) | ~3× |

- **7.2 Batch inference**: Added `detect_batch()` default to
  `DetectorPlugin` ABC (sequential fallback); `UltralyticsPlugin` overrides
  with native `model.predict(frames)` for GPU-efficient stacked inference;
  OpenVINO uses base fallback (model compiled for batch=1);
  `SingleDetector.detect_batch()` delegates directly
- **7.3 SharedMemory preview frames**: Created `SharedFrameBuffer` utility
  (`core/video/shared_frame_buffer.py`) — single-slot shared memory block
  with sequence-numbered header for zero-copy IPC; `ProcessingWorker`
  creates the buffer, `_WorkerProcess` attaches and writes preview frames,
  `_monitor_loop` reads via sequence metadata; graceful pickle fallback on
  failure; eliminated ~2–6 MB per-frame serialisation overhead
- **7.4 Vectorized angular velocity**: Replaced Python `for`-loop in
  `behavior.py:get_angular_velocity()` with NumPy vectorised operations
  (`np.diff`, `np.hypot`, `np.arctan2`, boolean masking) — ~9× faster for
  typical 5 000-point trajectories
- **7.5 Columnar buffers recorder**: Replaced `pd.DataFrame(snapshot)` →
  `pa.Table.from_pandas(df)` path in `recorder.py` with direct `pa.table()`
  construction from column arrays — bypasses pandas allocation entirely;
  added `_snapshot_to_pa_table()` and `_dedup_snapshot()` methods
- **7.6 ROI polygon mask cache**: Pre-computes binary polygon masks via
  `cv2.fillPoly()` at zone-scaling time in `zone_scaler.py`; both
  `is_inside_polygon()` and `bbox_hits_roi_polygon()` use O(1) pixel
  lookups with automatic fallback to `cv2.pointPolygonTest`
- **7.7 TTL cache utility**: Created reusable `TTLCache` and `ttl_cache`
  decorator in `utils/cache.py` (thread-safe, per-entry expiry, maxsize
  eviction, hit/miss counters); refactored `WizardService` (replaced 6
  class-level cache attrs) and `VideoManager` (replaced `_scan_cache` dict)
- **7.8 Model warm-up**: Added `_warm_up()` to `UltralyticsPlugin` and
  `OpenVINODetectorPlugin` — runs a single dummy inference at load time to
  pre-allocate device memory and JIT-compile CUDA/OpenVINO kernels
- **Benchmarks**: 11 pytest-benchmark tests in
  `tests/benchmarks/test_phase7_benchmarks.py` covering all optimisations
  with before/after baselines

### 🏷️ Type System & Static Quality

#### Phase 6 — Type System & Static Quality (February 2026)

**Metrics**: `# type: ignore` 166 → 40 (−76%); mypy errors 24 (all pre-existing)

- **Enabled** `pydantic.mypy` plugin (`init_forbid_extra`, `init_typed`,
  `warn_required_dynamic_aliases`) — removed 15 unnecessary `# type:
  ignore[call-arg]` from `settings.py` Pydantic model instantiations
- **Created** `coordinators/_protocols.py` with `@runtime_checkable`
  Protocol classes (`UnifiedReportHost`, `VideoSelectionHost`) documenting
  host contracts for coordinator mixins — then replaced `self: Protocol`
  annotation pattern with class-level attribute declarations on mixin
  classes to avoid mypy "Invalid self argument" errors (net −46 ignores)
- **Fixed** `UICoordinator` → `UIScheduler` type mismatch in `__main__.py`
  Composition Root — removed 7 `# type: ignore[arg-type]` from coordinator
  constructor calls
- **Added** convenience methods `has_main_arena()`, `has_roi_polygons()`,
  `get_arena_polygon()` to `ProjectManager` — replaced unsafe
  `zone_data.polygon` access patterns, removed 9 ignores from
  `zone_management_facade.py`
- **Retyped** `decorators.py` with `ParamSpec`/`TypeVar` for
  `@public_api` and `@deprecated` — removed 8 `# type: ignore`
- **Added** mypy `ignore_missing_imports` overrides for `serial.*` and
  `torch.*` third-party modules — removed 15 conditional-import ignores
  from `plugins/`, `arduino_manager.py`, `arduino.py`
- **Narrowed** `view` and OpenVINO types in `__main__.py` with `isinstance`
  checks and `cast()` — removed 14 ignores (`attr-defined`, `arg-type`)
- **Made** `RecordingService.controller` properly `Optional` — removed 1
  ignore from `controller.state_manager` access
- **Swept** remaining fixable ignores: widened `base_coordinator.py` param
  types, added `isinstance` guards in `single_detector.py` and
  `zone_scaler.py`, added `assert` narrows in `processing_reports.py`,
  narrowed 3 bare `# type: ignore` to specific error codes — total −11
  ignores in sweep batch
- **Added** `UP047` to ruff ignore list — defers PEP 695 type-param syntax
  migration until ecosystem support matures

**Remaining 40 ignores** (unfixable without upstream changes): Pillow
`LANCZOS`/`BICUBIC` compat (5), Tkinter `label.image` trick (5), Tkinter
overloads/arg-type (7), `cv2.VideoWriter_fourcc` (2), conditional imports
(4), `ttkbootstrap` (1), `os.startfile` Windows-only (1), structlog
`list-item` (1), ByteTracker private attr (1), and miscellaneous
narrowing/assignment (13).

### 🛡️ Security & Thread Safety

#### Phase 5 — Security and Thread Safety Hardening (February 2026)

- **Replaced** `pickle` with JSON serialization in `analysis/metrics_cache.py`
  — eliminates arbitrary code execution risk from cache deserialization; added
  `_NumpyJSONEncoder` and `_sanitize_for_json()` for NumPy type handling
- **Added** `threading.Lock` to `io/recorder.py` — protects
  `detection_data` list from concurrent access in multi-threaded processing;
  uses snapshot-buffer pattern in `_flush_detection_data()` so I/O happens
  outside the lock; best-effort recovery re-injects data on flush failure
- **Implemented** atomic Parquet writes via temp-file + `os.replace()` in
  `io/recorder.py` — prevents partial/corrupt files on crash; added
  `_verify_parquet_integrity()` validation after close; JSON backup writes
  are also atomic
- **Created** `utils/video_frame_extractor.py` — encapsulates `cv2`
  frame-reading and image-saving so coordinators no longer import `cv2`
- **Created** `core/services/trajectory_data_service.py` — encapsulates
  `pd.read_parquet` so coordinators no longer import `pandas` directly
- **Created** `analysis/roi_builder.py` — encapsulates
  `shapely.geometry.Polygon` import for ROI construction
- **Refactored** `coordinators/report_generation_coordinator.py` — removed
  top-level `cv2`, `numpy`, `pandas`, and `shapely` imports; all 4
  `pd.read_parquet` calls replaced with `TrajectoryDataService`; frame
  operations delegated to `VideoFrameExtractor`; ROI construction via
  `roi_builder`; math.floor/ceil replaces np.floor/ceil; lazy numpy
  import only where `Calibration` constructor requires `ndarray`
- **Refactored** `coordinators/video_processing_coordinator.py` — removed
  top-level `cv2` import; video dimensions obtained via
  `VideoMetadataService` with lazy `cv2` fallback
- **Refactored** `coordinators/_unified_report_mixin.py` — replaced
  `np.nan` with `float('nan')`; removed `numpy` import
- **Wired** all new services (`VideoMetadataService`,
  `TrajectoryDataService`, `VideoFrameExtractor`) into the Composition Root
  (`__main__.py`)
- **Added** 23 new tests: 3 recorder (concurrent writes, atomic write,
  integrity verification), 11 video frame extractor, 6 trajectory data
  service, 9 ROI builder — total 2,642 fast tests passing

### �🔄 Refactored

#### Phase 4.10 — Sub-packetize `core/` into domain sub-packages (February 2026)

- **Reorganized** 40+ flat modules in `src/zebtrack/core/` into 6 domain
  sub-packages, improving discoverability and enforcing bounded contexts:
  - `core/detection/` (8 modules) — Detector implementations, zone scaling,
    detection types, calibration, single-subject tracker, post-processing
  - `core/project/` (14 modules) — Project manager, zone manager, video
    manager, asset/metadata/parquet I/O, schemas, ROI templates
  - `core/video/` (8 modules) — Video processing service, processing worker,
    processing mode, classification/selection/validation/metadata services,
    batch configuration
  - `core/recording/` (5 modules) — Recording service/facade, live camera
    service/mode, Arduino facade
  - `core/services/` (5 modules) — Detector service, model service, weight
    manager, wizard service, zone management facade
  - `core/events/` (4 modules) — Event payload dataclasses (pre-existing
    directory, added `__init__.py`)
- **Created** 6 `__init__.py` files with curated public API re-exports for
  each sub-package
- **Updated** 527 import statements across 167 source and test files — zero
  backward-compatibility shims; all consumers use canonical new paths
- **Deleted** `core/detector.py` facade (47-line re-export shim from
  Phase 4.3) — its exports absorbed into `core/detection/__init__.py`
- **Updated** `core/__init__.py` docstring documenting new sub-package
  structure
- Root-level infrastructure modules remain at `core/`: `state_manager`,
  `main_view_model`, `dependency_container`, `application_bootstrapper`,
  `ui_scheduler`, `orchestrator_registry`, `thread_coordinator`, `exceptions`
- All 2,610 fast tests passing, 0 regressions; `ruff check .` clean

#### Phase 4.9 — Decompose HardwareCoordinator + DetectorCoordinator (February 2026)

- **Decomposed** `HardwareCoordinator` (`coordinators/hardware_coordinator.py`,
  1,692 lines) and `DetectorCoordinator` (`coordinators/detector_coordinator.py`,
  916 lines) — total 2,608 lines — into 2 focused coordinators:
  - `DetectorSetupCoordinator` (~885 lines) — Detector setup, zone
    configuration, tracking parameter updates, single-subject mode,
    factory parameter retrieval, detector restore/reset workflows.
    Consolidates all detector-lifecycle methods from both original files.
  - `ModelDiagnosticsCoordinator` (~580 lines) — Model diagnostic test
    workflows, diagnostic processing thread, progress callbacks,
    cancel/abort handling, UI-safe scheduling via `root.after()`
- **Both original files deleted** — No facades; each consumer imports the
  specific coordinator it needs
- **Dead code removed** — `set_recording_callbacks()`,
  `set_convert_weight_callback()`, legacy `DetectorCoordinator` fallback
  block in `application_bootstrapper.py`, `TestRecordingCallbacks` test
  class, `test_recording_callbacks_integration` test
- Updated 8 consumer source files: `coordinators/__init__.py`,
  `dependency_container.py`, `__main__.py`, `main_view_model.py`,
  `application_bootstrapper.py`, `hardware_status_view_model.py`,
  `ui_state_coordinator.py`, `orchestrator_registry.py`
- Migrated 11 test files (~199 references): renamed
  `test_detector_coordinator.py` → `test_detector_setup_coordinator.py`,
  `test_hardware_coordinator.py` → `test_detector_setup_coordinator_legacy.py`,
  updated `test_coordinator_integration.py`,
  `test_hardware_status_view_model.py`,
  `test_detector_service_integration.py`, `controller_factory.py`,
  `test_main_view_model_commands.py`,
  `test_project_manager_replaced_event.py`, `test_bootstrapper.py`,
  `test_main_view_model_threading.py`, `test_ui_state_coordinator.py`
- All 2,607 fast tests passing, 0 regressions

#### Phase 4.8 — Decompose Reporter (February 2026)

- **Decomposed** `reporter.py` (`analysis/reporter.py`, 1,749 lines) into
  8 focused modules under `analysis/reporters/` sub-package:
  - `reporter_context.py` (~280 lines) — Shared context with two construction
    paths (legacy `__init__` + modern `from_analysis()`), i18n helpers,
    template constants
  - `word_reporter.py` (~420 lines) — Word document export with step-by-step
    progress callback, metadata sections, visualisation attachments
  - `excel_reporter.py` (~80 lines) — Excel summary export with display
    column renaming
  - `parquet_reporter.py` (~65 lines) — Parquet summary export preserving
    internal column names
  - `html_reporter.py` (~230 lines) — Interactive HTML report generation
  - `script_exporter.py` (~350 lines) — R/Python script and Feather export
  - `project_reporter.py` (~260 lines) — Standalone `export_project_report()`
    and `export_multi_aquarium_reports()` functions
  - `__init__.py` — Re-exports all public symbols
- **Original file deleted** — No facade; each consumer imports the specific
  reporter class it needs
- Updated 4 source consumer files: `report_generation_coordinator.py`,
  `video_processing_service.py`, `analysis_control_view_model.py`,
  `live_camera_service.py`
- Updated 6 test files: `test_reporter.py`, `test_reporter_integration.py`,
  `test_reporter_refactoring_compatibility.py`,
  `test_analysis_multi_aquarium.py`, `test_unified_report.py`,
  `test_parallel_detection_benchmark.py`
- All 2,614 fast tests passing, 0 regressions

#### Phase 4.7 — Decompose SessionCoordinator (February 2026)

- **Decomposed** `SessionCoordinator` (`coordinators/session_coordinator.py`,
  2,111 lines) into 3 focused coordinators under `coordinators/`:
  - `LiveCalibrationCoordinator` (~500 lines) — Camera calibration with
    auto-detection, reference frame capture, zone validation,
    `ensure_zones_before_recording()` shared by recording and live sessions
  - `RecordingSessionCoordinator` (~530 lines) — Recording session lifecycle,
    Arduino triggers, session scheduling, start/stop recording
  - `LiveCameraSessionCoordinator` (~680 lines) — Live camera session
    lifecycle, config-based starts, batch registration,
    `start_live_camera_analysis()`, `start_session_from_config()`
- **Original file deleted** — No facade; each consumer imports the specific
  coordinator it needs
- **Deleted 2 dead legacy files** — `recording_coordinator.py` (320 lines)
  and `live_camera_coordinator.py` (686 lines) were unused Phase 3 stubs
- Updated 11 consumer source files: `__init__.py`, `dependency_container.py`,
  `__main__.py`, `main_view_model.py`, `application_bootstrapper.py`,
  `hardware_status_view_model.py`, `analysis_control_view_model.py`,
  `block_detail_dialog.py`, `dialog_manager.py`, `orchestrator_registry.py`,
  `video_processing_coordinator.py`
- Deleted 3 dead test files, updated 10 test files
- All 2,614 fast tests passing, 0 regressions

#### Phase 4.6 — Decompose ProjectViewManager (February 2026)

- **Decomposed** `ProjectViewManager` (`ui/components/project_view_manager.py`,
  2,136 lines) into 3 focused modules under `ui/components/project_views/`:
  - `VideoSelectorTreeManager` (~850 lines) — Video selector tree, project
    overview panel, batch processing triggers, navigation helpers, zone
    summary cards, readiness snapshot application
  - `ReportsTreeManager` (~1,045 lines) — Processing reports tree population,
    report file opening, unified-report generation, right-click context
    menu, delete operations, partial report dispatch
  - `project_view_helpers` (~170 lines) — Pure formatting functions:
    `format_status_label`, `format_status_summary`, `format_status_ratio`,
    `format_status_token`, `format_video_metadata`, `video_sort_key`,
    `summarize_batch_data`, `format_data_badges`
- **Original file deleted** — No facade; `gui.py` instantiates both managers
  directly via composition
- Backward-compat alias `self.project_view_manager = self.video_selector_manager`
  preserved in `gui.py` and `UICoordinator` to minimize test churn
- Updated 5 consumer files: `gui.py`, `ui_coordinator.py`, `event_dispatcher.py`,
  `widget_factory.py`, `components/__init__.py`
- Updated 9 test files: import paths, mock targets, SimpleNamespace attributes
- All 2,720 fast tests passing, 0 regressions

#### Phase 4.5 — Decompose CanvasManager (February 2026)

- **Decomposed** `CanvasManager` (`ui/components/canvas_manager.py`) from
  2,152 → 599 lines (-72%, 1,553 lines removed) by extracting methods
  into 3 focused modules under `ui/components/canvas/`:
  - `MultiAquariumOverlayManager` (~562 lines, 11 methods) — Multi-aquarium
    auto-detection result handling, format conversion, overlay drawing,
    side-by-side preview generation, aquarium indicator display
  - `VideoFrameManager` (~513 lines, 11 methods) — Video frame loading,
    canvas display, analysis track selection/filtering, detection overlay
    rendering, analysis frame caching
  - `ZoneEditor` (~650 lines, 24 methods) — Zone CRUD operations, polygon
    drawing lifecycle, circle drawing, zone clipboard (copy/paste/delete),
    ROI button state, processing mode toggle, geotaxis visualization,
    BGR color name mapping
- **Backward-compatible** via ~30 thin delegation shims on `CanvasManager`
  facade: all public and internal methods remain callable as
  `self.<method>()` and delegate to the appropriate sub-component
- Class-level aliases preserved: `AQUARIUM_COLORS`, `_BGR_COLOR_MAP`
- Shared state (`_bg_scale`, `_bg_offset`, `_raw_bg_image`,
  `_canvas_bg_image`, `dragged_handle_index`, `current_editing_zone`, etc.)
  stays on the facade, accessed by sub-components via `self.canvas_manager`
  back-reference
- Updated `ui/components/__init__.py` with 3 new exports
- Fixed test `@patch` targets in `test_canvas_manager.py` (cv2/Image
  patches now target `canvas.video_frame_manager` module)
- Fixed test fixtures in `test_canvas_manager_multi_aquarium.py` (added
  `MultiAquariumOverlayManager` instantiation after patched `__init__`)
- Fixed mock targets in `test_single_video_workflow_prompt.py` (prompt
  mock now targets `multi_aquarium` sub-component)
- Fixed log patch in `test_live_analysis_integration.py` (log now in
  `video_frame_manager` module)
- Updated source-scanning tests in `test_roi_snap_indicator_arena_clamp.py`
  to also scan `canvas/` sub-directory
- All 2,720 fast tests passing, 0 regressions

#### Phase 4.4 — Decompose ApplicationGUI (February 2026)

- **Decomposed** `ApplicationGUI` (`ui/gui.py`) from 2,261 → 1,217 lines
  (-46%, 1,044 lines removed) by extracting 43 methods into 5 focused
  component classes under `ui/components/`:
  - `AnalysisViewController` (~310 lines, 16 methods) — Analysis tab
    lifecycle, overlays, mode sync, progress tracking, track selector
  - `ProjectInitializer` (~280 lines, 9 methods) — Project loading,
    welcome→project transition, tab building, workflow dialogs
  - `SingleVideoWorkflow` (~210 lines, 4 methods) — Single-video analysis
    flow: file selection, zone setup, processing start
  - `WeightHardwareManager` (~210 lines, 10 methods) — Model weight state,
    OpenVINO toggle, GPU hardware display
  - `ZoneEditGuard` (~180 lines, 4 methods) — Tab navigation guard that
    protects unsaved zone editing sessions
- **Backward-compatible** via thin delegation shims on `ApplicationGUI`:
  all 43 methods remain callable as `self.<method>()` and delegate to
  `self.<component>.<method>()`; `@public_api` contracts preserved
- Components use `gui` back-reference pattern (`self.gui = gui`) to
  access parent state without circular imports
- Component instantiation added in `__init__` after Phase 5 builders
- Updated `ui/components/__init__.py` with all 5 new exports
- Fixed 2 test files using `__new__` to bypass `__init__`:
  - `test_analysis_metadata_display.py` — added `AnalysisViewController`
    mock to `_make_gui_instance()` fixture
  - `test_gui_zone_tab_navigation_guard.py` — replaced direct method mock
    with `ZoneEditGuard` stub using `_make_guard()` helper
- All 2,720 fast tests passing, 0 regressions

#### Phase 4.3 — Decompose Detector God Class (February 2026)

- **Decomposed** Detector (2,607 lines, ~55 methods) into 5 focused modules:
  - `detection_types.py` (~120 lines) — `ZoneData`, `AquariumData`,
    `MultiAquariumZoneData` data classes
  - `zone_scaler.py` (~360 lines) — Polygon scaling, point-in-polygon,
    crop helpers, scaling cache
  - `detection_post_processor.py` (~480 lines) — Stateless detection
    validation, tracking config, ByteTrack helpers
  - `single_detector.py` (~1,035 lines) — Single-aquarium detection,
    tracking (ByteTrack + SingleSubjectTracker), overlay drawing
  - `multi_aquarium_detector.py` (~1,070 lines) — Multi-aquarium
    partitioned/parallel detection with independent per-aquarium trackers
- **Backward-compatible** via gutted `detector.py` re-export shim:
  `Detector = SingleDetector` alias; all existing imports unaffected
- Shared `ZoneScaler` and `DetectionPostProcessor` injected via
  composition into both `SingleDetector` and `MultiAquariumDetector`
- Updated `processing_worker.py` to create `MultiAquariumDetector`
  alongside `SingleDetector` when multi-aquarium zones detected
- Updated `live_camera_service.py` to lazily create
  `MultiAquariumDetector` in `_run_multi_aquarium_detection`
- Updated `detector_service.py` to wire `ZoneScaler` and
  `DetectionPostProcessor` into constructor
- Updated test suites: `test_detector.py`, `test_detector_partitioned.py`,
  `test_processing_worker_unit.py`, `test_parallel_detection_benchmark.py`
- All 2,400 fast tests passing, 0 regressions

#### Phase 4.2 — Decompose ProjectManager God Class (February 2026)

- **Decomposed** ProjectManager (2,737 → 906 lines, -67%) into 5
  domain-specific sub-managers using the callback pattern (static methods
  with explicit params to avoid circular dependencies):
  - ParquetIOManager (~521 lines) — Zone parquet I/O, copy, import
  - OutputRegistrationManager (~745 lines) — Processing output registration
  - MetadataManager (~435 lines) — Experiment metadata, detector state
  - ProjectLifecycleManager (~748 lines) — Project create/load/save/migrate
  - ZoneOrchestrationManager (~365 lines) — Zone persistence orchestration
- Extended AssetManager (~960 lines) with asset removal logic
- Moved ProjectInvalidError to xceptions.py (backward-compat re-export)
- Fixed VideoManager.update_video_status POSIX path comparison
- Simplified create_new_project to use **kwargs forwarding
- Removed 10+ unused private delegates and 10 unused imports from PM
- Consolidated has_*_data methods via shared _has_asset() helper
- All 2,720 fast tests passing, 0 regressions

#### Phase 4 — Decompose ProcessingCoordinator God Class (February 2026)

- **Decomposed** `ProcessingCoordinator` (5,563 lines, 114 methods) into 5
  domain-specific coordinators each under 1,700 lines:
  - `VideoProcessingCoordinator` — Facade owning ProcessingWorker lifecycle
    and proxy methods for backward compatibility (~1,700 lines)
  - `ProgressTrackingCoordinator` — Processing lifecycle, progress UI, batch
    context management (~440 lines)
  - `MultiAquariumCoordinator` — Aquarium detection, zone/arena management,
    processing modes (~800 lines)
  - `SequentialProcessingCoordinator` — Sequential multi-aquarium processing
    with per-aquarium video passes (~460 lines)
  - `ReportGenerationCoordinator` — All report generation workflows (unified,
    individual, parquet summaries) (~1,380 lines)
- Added `processing_types.py` with shared `ValidationResult` dataclass and
  `ProcessingCoordinatorError` exception
- Updated `coordinators/__init__.py`, `dependency_container.py`, and
  `__main__.py` (Composition Root) with 5-coordinator DI wiring
- Deleted monolithic `processing_coordinator.py`
- Fixed production bug: `Events.PROCESSING_MODE_CHANGED` renamed to
  `Events.ZONE_PROCESSING_MODE_CHANGED` in `MultiAquariumCoordinator`
- Fixed production bug: `_on_progress_wrapper` signature mismatch — now
  correctly constructs dict for `ProgressTrackingCoordinator`
- Fixed import error: `Calibration` import path in
  `ReportGenerationCoordinator`
- Added `state_manager.update_processing_state()` call to
  `_on_processing_progress()` for observable state consistency
- Updated 7 test files for new coordinator structure (97 tests passing)
- All 2,720 fast tests passing, 0 regressions
- Ruff lint clean on all coordinator files

#### Phase 0 — Placeholder & Dead Code Cleanup (February 2026)

##### Phase 0.1: Fix placeholder URL in About dialog

- Replaced `YOUR_USERNAME` with `MarkSant` in GitHub/PyPI URLs
  in `ui/components/menu_manager.py`

##### Phase 0.2: Fix placeholder author metadata

- Updated `pyproject.toml` author from
  `"The Project Developers <placeholder@example.com>"` to
  `"Marco A. S. Camargos <marco.sant@unesp.br>"`
- Updated `CITATION.cff`: author name, ORCID (`0009-0000-0014-1485`),
  and `repository-code` URL

##### Phase 0.3 TODO 1: Remove dead `add_videos_to_project` code path

- Removed `ProjectViewModel.add_videos_to_project()` (no UI emits event)
- Removed `PROJECT_ADD_VIDEOS` event constant from `ui/events.py`
- Removed proxy method and handler registration in `MainViewModel`
- Removed 2 associated tests in `test_project_view_model.py`

##### Phase 0.3 TODO 2: Migrate VideoProcessingOrchestrator → ProcessingCoordinator

- Ported `start_project_processing_workflow()` (~120 lines) from
  `VideoProcessingOrchestrator` into `ProcessingCoordinator`
- Added `dialog_coordinator` param to `ProcessingCoordinator` constructor
  (post-construction injection in `__main__.py`)
- `AnalysisControlViewModel` now delegates to
  `processing_coordinator.start_project_processing_workflow()`
- Stubbed `VideoProcessingOrchestrator` with `DeprecationWarning`
- Made `BootstrapResult.video_processing_orchestrator` optional (`None`)
- Updated `OrchestratorRegistry` to accept optional `video_processing`
- Migrated 6 tests to exercise `ProcessingCoordinator` directly
- Updated 5 test/helper files to remove orchestrator mocks

##### Phase 0.3 TODO 3: Remove stale comment in detector.py

- Removed 2-line TODO comment about multi-aquarium tracking dispatch
  (already handled by `detect_partitioned*` methods)

#### Phase 1 — Eliminate Silent Exceptions (February 2026)

Replaced **all ~94 `except...pass`** blocks across the codebase with
structured `log.debug()`/`log.warning()` calls using structlog, enabling
full debugging visibility without changing control flow.

##### Scope

- **31 source files** modified across `src/zebtrack/`
- **0 `except...pass` remaining** in production code (verified via Ruff S110)
- **2778 tests passing**, 12 skipped, 0 failures

##### Key changes

- **DANGEROUS patterns** (8): Changed to `log.warning()` — silent mode
  fallbacks in `processing_coordinator.py`, data loss in
  `video_validation_service.py`, hidden failures in `gui.py`
- **Moderate UI/Tkinter** (29): Widget teardown, config guards, dialog
  destroy — changed to `log.debug()` with `exc_info=True`
- **I/O & hardware** (9): Camera shutdown, recorder cleanup, Arduino
  probing, OpenVINO metadata parsing — changed to `log.debug()`
- **Config/input parsing** (11): Day/group parsing, geotaxis column
  renaming, validation fallbacks — changed to `log.debug()`
- **TclError dialog guards** (2): Destroy-already-destroyed dialogs —
  changed to `log.debug()`
- **Logging bootstrap** (3): `logging_config.py` uses stdlib
  `logging.debug()` since structlog isn't configured yet

##### Ruff S110 guard rail

- Added `"S110"` (flake8-bandit try-except-pass) to Ruff `select` in
  `pyproject.toml` — prevents future regressions
- Tests and scripts exempted via `per-file-ignores`

##### Pre-commit hook

- Added `astral-sh/ruff-pre-commit` (v0.9.7) to `.pre-commit-config.yaml`
  with `ruff` (lint + auto-fix) and `ruff-format` hooks

#### Phase 3 — Structural Unification (February 2026)

Eliminated duplicate base classes, removed the legacy `orchestrators/`
package, and cleaned dead deprecated fields.

##### 3.1 Unified BaseCoordinator

- Merged ABC-based `coordinators/base.py` (305 lines) features into
  concrete `coordinators/base_coordinator.py` — single base class for
  all 10 coordinators
- `validate_dependencies()` changed from `@abstractmethod` to concrete
  default (`return True`)
- `_update_state(category, **kwargs)` signature preserved (31 call sites)
- Exception hierarchy (`CoordinatorError`, `CoordinatorValidationError`,
  `CoordinatorDependencyError`) consolidated in one module
- Deleted `coordinators/base.py`; updated 6 coordinator imports + 7 test
  files

##### 3.2 Removed `orchestrators/` package

- Moved `UIStateController` (653 lines) to
  `coordinators/ui_state_coordinator.py`
- Deleted `VideoProcessingOrchestrator` stub (62 lines, dead code)
- Deleted `orchestrators/__init__.py`
- Updated 7 production imports + 1 test import
- Moved 2 test files to `tests/coordinators/`
- Removed `video_processing` field from `OrchestratorRegistry`

##### 3.3 Removed dead `project_coordinator` field

- Removed dead `project_coordinator` field from
  `MainViewModelDependencies`, `ApplicationBootstrapper` (proxy +
  legacy dict), `MainViewModel`, and 2 test helpers
- Relabelled remaining 5 deprecated fields as `# LEGACY: Migrate to X
  (Phase 4)` to clarify they are still in active use

##### 3.4 Cleaned `ApplicationBootstrapper`

- Removed `VideoProcessingOrchestrator` TYPE_CHECKING import
- Removed `video_processing_orchestrator` from `BootstrapResult`
  dataclass and its construction sites
- Removed empty `TYPE_CHECKING` block and unused `TYPE_CHECKING` import
- Updated `OrchestratorRegistry` instantiation (removed
  `video_processing_orchestrator=None`)
- **2778 tests passing**, 12 skipped, 0 failures, lint clean

##### 3.5 Eliminated dead `AnalysisCoordinator`

- **Deleted** `core/analysis_coordinator.py` (744 lines) — dead code
  fully superseded by `ProcessingCoordinator`
- Removed import and construction block from
  `ApplicationBootstrapper._init_orchestrators()`
- Removed proxy assignment (`controller_proxy.analysis_coordinator`)
- Removed `analysis_coordinator` field from
  `MainViewModelDependencies`
- Removed attribute assignment and `services_to_update` entry from
  `MainViewModel`
- **Deleted** `tests/core/test_analysis_coordinator.py` (599 lines)
- Cleaned 4 test helpers that referenced the dead coordinator

##### 3.6 Eliminated dead `VideoOrchestrator`

- **Deleted** `core/video_orchestrator.py` (911 lines) — dead code
  fully superseded by `ProcessingCoordinator`
- Removed import and construction block from
  `ApplicationBootstrapper._init_orchestrators()`
- Removed proxy assignment (`controller_proxy.video_orchestrator`)
- Removed `video_orchestrator` field from
  `MainViewModelDependencies`
- Removed attribute assignment and `services_to_update` entry from
  `MainViewModel`
- **Deleted** `tests/core/test_video_orchestrator.py` (665 lines)
- Cleaned 4 test helpers that referenced the dead coordinator
- **Net removal**: ~2,919 lines of dead production + test code
- **2718 tests passing**, 12 skipped, lint clean

#### Phase 2 — Narrow Generic Exception Catches (February 2026)

Narrowed **~130 `except Exception`** blocks to specific exception types
and justified **~155** remaining ones with greppable inline comments
across the priority scope (6 UI files + coordinators + core + I/O).

##### Scope

- **~60 source files** modified across `src/zebtrack/`
- **~130 catches narrowed** to specific types (`OSError`, `tk.TclError`,
  `ValueError`, `KeyError`, `AttributeError`, `TypeError`,
  `json.JSONDecodeError`, `pa.ArrowInvalid`, `re.error`, etc.)
- **~155 catches justified** with `# except Exception justified: <reason>`
  inline comments (greppable)
- **~45 catches already justified** via `# pragma: no cover` comments
- **2778 tests passing**, 12 skipped, 0 failures
- **10 test files updated** to raise specific exception types matching
  narrowed production catches

##### By directory

- **6 priority UI files** (80 instances): `window_utils.py`,
  `state_synchronizer.py`, `widget_factory.py`,
  `project_view_manager.py`, `gui.py`, `ui_coordinator.py`
- **coordinators/** (87 instances across 10 files): 15 narrowed,
  68 justified, 4 already justified
- **core/** (136 instances across 30 files): 50 narrowed,
  70 justified, 16 already justified
- **io/** (40 instances across 6 files): 8 narrowed,
  17 justified, 15 already justified

##### Common narrowing patterns

- Tkinter widget operations: `except tk.TclError`
- File/network I/O: `except OSError`
- Data parsing: `except (ValueError, TypeError, KeyError)`
- JSON I/O: `except (OSError, json.JSONDecodeError, KeyError)`
- Parquet I/O: `except (OSError, pa.ArrowInvalid, pa.ArrowIOError)`
- Attribute probing: `except (AttributeError, TypeError)`

##### Justification categories

- Service/facade boundaries wrapping heterogeneous subsystems
- Daemon/worker thread fault-isolation loops
- Hardware I/O (camera, serial, OpenVINO)
- YOLO/cv2 operations (poorly-typed errors)
- Pandas/parquet pipelines (heterogeneous data errors)
- Event-bus handler fault-isolation boundaries

##### Bug fixes during Phase 2

- Fixed `detector_service.py` persist catch: widened `OSError` to
  `(OSError, ValueError)` to handle YAML serialization errors
- Removed duplicate `raise e` dead code at `gui.py` line 535

#### Phase 3.7 — EventBus Unification Decision (February 2026)

Documented the decision to unify on `EventBusV2` as the canonical event
bus and deprecated `EventBus` v1 with `DeprecationWarning`. No consumer
migration in this phase — deferred to Phase 4+ alongside coordinator
decomposition.

##### ADR-009: EventBus Unification

- Created `docs/decisions/ADR-009-event-bus-unification.md` establishing
  `EventBusV2` as the canonical bus (type-safe enums, `RLock` thread
  safety, 100ms slow-handler monitoring)
- Decision: deprecate v1 starting v4.1 (Feb 2026), removal target v5.0
- Migration plan: ~97 `Events` string constants will be progressively
  absorbed into `UIEvents` enum during Phase 4+ coordinator refactoring

##### DeprecationWarning on EventBus v1

- Added `warnings.warn(..., DeprecationWarning, stacklevel=2)` to
  `EventBus.publish_event()`, `EventBus.subscribe()`, and
  `EventBus.publish_callable()` in `ui/event_bus.py`
- Warning message includes migration path (`EventBusV2`), ADR reference,
  and removal timeline (`v5.0`)
- Follows existing deprecation pattern from `analysis/reporter.py`
- Python's default filter shows each unique call site once per process
  (no log flooding)

##### Test noise suppression

- Added `pytest.ini` `filterwarnings` entry to suppress expected v1
  deprecation warnings during test runs
- Narrow filter: matches only `EventBus v1 .*DEPRECATED.*` from
  `zebtrack.ui.event_bus` module
- Will be removed when Phase 4+ migration completes

### �🟢 New Features

#### LiveBatchCoordinator v2.3.0 Integration (January 2026)

##### Unified Batch Reporting

- Activated dormant `LiveBatchCoordinator` (433 lines, fully implemented in v2.2.0)
- Instantiated in composition root (`__main__.py`) with dependency injection
- Integrated with `SessionCoordinator` for automatic session registration after live camera stops
- Added 4 batch metadata fields to `LiveConfigStep` wizard:
  - `experimental_group`: Experimental group name (e.g., "Controle", "Tratado")
  - `experiment_day`: Day identifier (e.g., "Dia_1", "Dia_2")
  - `subject_id`: Subject/cobaia identifier (e.g., "Peixe_01")
  - `is_batch_last_session`: Checkbox to mark last session and trigger unified report

##### Experiment Progress Dashboard

- Enhanced existing "Progresso do Experimento" tab with batch integration
- Replaced `SubjectSelectionDialog` with `BlockDetailDialog` for detailed session management
- Day x Group grid shows session completion status per experimental block
- Click Day/Group cell → Opens `BlockDetailDialog` with subject list and batch actions
- Dialog allows starting new sessions, viewing results, and marking batch complete

##### Multi-Aquarium Batch Support

- Each aquarium treated as separate `subject_id` (e.g., `Peixe_01_Aquario_0`, `Peixe_01_Aquario_1`)
- Automatic batch key generation: `{group}_{day}_{subject_id}`
- Batch ID includes microseconds for uniqueness: `batch_20260103_113918_048070`
- Separate batches per aquarium enable independent reporting

##### Event-Driven Completion

- `BATCH_ANALYSIS_COMPLETED` event published when batch marked complete
- `UICoordinator` handler shows success messagebox and opens file explorer with unified report
- Batch completion triggers `AnalysisService.generate_unified_report()` across all sessions

##### Testing

- 4 integration tests covering wizard → batch coordinator flow
- Multi-aquarium batch registration validation
- Incomplete metadata handling (graceful skips)
- Session coordinator integration with LiveBatchCoordinator

### � Fixed

#### Live Camera v2.2.0 - Audit Fixes (January 2026)

##### Dependency Injection Compliance (BLOCKER)

- Fixed `LiveConfigStep` importing singleton `settings` instead of using constructor injection
- Added `settings_obj` parameter to `LiveConfigStep.__init__()`
- Updated `WizardDialog` to pass settings via constructor
- Eliminates architectural violation preventing headless tests

##### Multi-Aquarium Preview Window (HIGH)

- Fixed `MultiAquariumLivePreviewWindow` never being instantiated
- Added conditional logic in `LiveCameraService._create_preview_window()` to detect `MultiAquariumZoneData`
- Multi-aquarium sessions now correctly show side-by-side preview windows

##### FPS Dynamic Adjustment (MEDIUM)

- Fixed `_adjust_fps_dynamically()` return value being ignored in processing loop
- Now correctly applies dynamic frame skip under heavy load
- Expected 20-40% performance improvement when processing is slow

##### Test Fixes

- Fixed hardware capability detection mocks returning 2 values instead of 4
- Fixed zone control builder undefined variable (`controls_container` → `video_selector_frame`)
- Fixed GUI state observer assertion to use `assert_any_call` for flexibility

##### Documentation

- Added `ADR-006-live-batch-coordinator-future.md` documenting deferred batch coordinator integration
- Created comprehensive audit fixes report in `docs/guides/developer/LIVE_CAMERA_AUDIT_FIXES_REPORT.md`

### �🟢 New Features

#### Multi-Aquarium v2 Improvements (Phase 1-5)

##### Phase 1: Foundation Enhancements

- **ROI Cropping**: `_crop_aquarium_region()` for per-aquarium frame extraction
- **Uncertainty Metrics**: Added `uncertainty` and `bbox_iou` columns to Parquet output
- **Export Formats**: New `export_feather()`, `export_r_script()`, `export_python_script()` in Reporter
- **Thigmotaxis**: Added thigmotaxis metrics calculation in DataTransformer

##### Phase 2: Performance Optimizations

- **Parallel Detection**: `detect_partitioned_parallel()` with ThreadPoolExecutor (~30-40% speedup)
- **Batch Inference**: `detect_batch()` for offline multi-frame batch processing
- **Metrics Cache**: Verified MetricsCache for analysis result caching

##### Phase 3: UI/UX Improvements

- **Side-by-Side Preview**: `create_side_by_side_preview()` in CanvasManager for aquarium comparison
- **Enhanced Validation**: `validate_multi_aquarium_config()` now returns warnings (polygon overlap, small areas)

##### Phase 4: Robustness

- **Tracking Validation**: Multi-aquarium track ID validation (ID bounds, large jumps)
- **Gap Detection**: Per-aquarium frame coverage analysis with gap statistics
- **Error Recovery**: Graceful handling when one aquarium fails in parallel detection

##### Phase 5: Event System

- **New Events**: `ZONE_MULTI_AUTO_DETECT_SUCCESS`, `ZONE_MULTI_AUTO_DETECT_FAILED`, `ZONE_AQUARIUM_CONFIG_UPDATED`
- **Multi-Auto-Detect Handler**: `ProcessingCoordinator._handle_multi_auto_detect()`
- **Config Update Handler**: `ProjectLifecycleCoordinator._handle_aquarium_config_updated()`

#### Zone Copy/Paste/Delete Context Menu

- **NEW**: Right-click context menu on video tree in Zone Configuration tab
- Copy zones from one video and paste to others (arena + all ROIs)
- Delete zones option to clear all zones from a video
- Automatic video tree status update after paste/delete operations
- Uses EventBusV2 `VIDEO_TREE_REFRESH_REQUESTED` for consistent UI updates

#### Finish Drawing Button

- **NEW**: Added "✓ Finalizar Desenho" button for completing polygons
- Alternative to double-click for users who prefer button interaction
- Visible in interactive buttons frame during polygon drawing mode

#### Improved Zone Drawing Colors

- **UI**: Changed zone drawing colors for better visibility on video backgrounds
- Cyan (#00FFFF) → Dark Teal (#008B8B) for arena outlines
- Yellow (#FFFF00) → Goldenrod (#DAA520) for interactive polygons/elastic lines
- Better contrast and readability on light-colored videos

#### Drawing Flickering Fix

- **UI**: Added 16ms debounce (~60fps) to `on_canvas_motion()` in event_handler.py
- Reduces visual flickering during polygon drawing
- Smoother elastic line animation while moving mouse

#### Improved Word Reports (Quality & Robustness)

- **NEW**: Added "Appendix: Trajectory Validation" section to Word reports.
- Includes technical summary table: Total Frames, Frame Range, Temporal Coverage (%), Unique Track IDs, and Gap counts.
- Displays detailed validation warnings (teleportation, gaps, arena violations) directly in the document.
- **UI**: Removed redundant blank pages between trajectory and heatmap figures for a more compact layout.

#### Max Speed Metric (Dec 28, 2025)

- **NEW**: Added `velocidade_maxima_cm_s` / `max_speed_cm_s` metric to behavioral analysis
- Calculated alongside mean, median, and std_dev in `BehavioralAnalyzer.get_velocity_stats()`
- Included in summary parquets, Excel reports, and Word reports
- Added to comparative boxplots in project-level reports

#### Enhanced Column Naming in Word Reports (Dec 28, 2025)

- **IMPROVEMENT**: Word report summary table now uses `DISPLAY_COLUMN_MAPPING` for proper metric formatting
- "max_speed_cm_s" → "Max Speed (cm/s)" instead of generic "Max Speed Cm S"
- All metrics with units now display correctly formatted: "(cm)", "(cm/s)", "(s)", "(count)", etc.

#### Geotaxis Zone Naming Improvements (Dec 28, 2025)

- **IMPROVEMENT**: Geotaxis zones now display with 1-indexed user-friendly names
- "geotaxis_zone_0_pct" → "Geotaxis Zona 1 - Fundo (%)"
- "geotaxis_zone_1_pct" → "Geotaxis Zona 2 (%)"
- Applied in both Word reports and unified Excel reports
- Fallback logic ensures proper naming even when height/num_zones metadata is unavailable

#### Unified Reports Management (Dec 29, 2025)

- **NEW**: Added "Apagar Relatórios Unificados" button to Reports tab
- Safely deletes the `unified_reports` folder
- Features robust retry logic for handling OneDrive file locks and Read-Only permissions

### 🔴 Bug Fixes

#### Geotaxis Data Missing in Unified Reports Fix (Dec 28, 2025)

- **CRITICAL**: Fixed geotaxis zone data appearing empty in unified Excel reports
- **Root Cause**: In legacy Reporter constructor, `behavioral_config` parameter was passed to `run_full_analysis()` but never stored as `self.behavioral_config`. The fallback logic then set it to empty dict `{}`, causing `geotaxis_enabled` to always be `False`
- **Solution**: Changed `reporter.py:280-282` to store `behavioral_config` parameter before creating tidy_data
- **Impact**: All geotaxis zone percentages now correctly appear in unified reports

#### Subject Identification in Unified Reports Fix (Dec 28, 2025)

- **HIGH**: Fixed unified reports not identifying which subject is in each row
- **Solution**: `_enrich_unified_report_metadata()` now always adds identification columns (group, subject, day, experiment_id) with "N/A" fallback
- **Column Ordering**: Priority columns (group, subject, day, experiment_id, aquarium_id) now appear first in unified reports

#### Batch Mode Dialog Suppression Fix (Dec 28, 2025)

- **MEDIUM**: Fixed individual dialogs appearing between videos during batch processing
- Added `_is_batch_processing()` check in `_finalize_report_generation()`
- Dialogs now only appear at the end of the batch, not after each video

#### NameError in Project View Manager Fix (Dec 28, 2025)

- **LOW**: Fixed `NameError: video_paths not defined` in `project_view_manager.py:865`
- Removed erroneous `return video_paths` line that referenced undefined variable

#### Recorder Log Level Fix (Dec 28, 2025)

- **LOW**: Changed `recorder.flush.success` log from INFO to DEBUG
- Prevents terminal spam during analysis; message now only appears in log file

#### Simultaneous Multi-Aquarium Report Generation Fix

- **CRITICAL**: Fixed issue where simultaneous 2-aquarium analysis in single-video mode would stop after tracking without generating Word/Excel reports.
- `ProcessingCoordinator.on_video_completed` now robustly detects output folders (`aquarium_0`, `aquarium_1`) even when the results directory is calculated dynamically.
- Ensures all analysis artifacts (Parquet summaries, Word reports, Excel tables) are generated for both aquariums upon completion.

#### Multi-Aquarium Reporting Fix

- **CRITICAL**: Fixed regression where Aquarium 1 would erroneously use Aquarium 0's zones and background in reports.
- `ProcessingCoordinator` now correctly prioritizes `MultiAquariumZoneData` for per-aquarium report generation.

#### Background Image "Gray Screen" Fix (Windows)

- **CRITICAL**: Fixed background images not displaying in reports on Windows when paths contained spaces or special characters.
- Switched to robust `cv2.imdecode` method for reading background frames.
- Standardized single-aquarium flow to extract cropped background PNGs, consistent with multi-aquarium logic.

#### Trajectory Alignment Fix

- **HIGH**: Fixed trajectory misalignment in cropped reports.
- Normalization logic now drops existing CM columns to force recalculation relative to the aquarium crop origin (0,0).
- Prevents trajectories from "floating" outside the visible aquarium area in Word reports.

#### Batch Processing Video Frame Display Fix

- **CRITICAL**: Fixed frames not displaying during batch processing
- Added missing `update_processing_state(is_processing=True)` call in `process_pending_project_videos()`
- This triggers `UI_NAVIGATE_TO_ANALYSIS_VIEW` event to set `analysis_active = True`
- Frames now correctly display in the Analysis tab during batch video processing

#### Batch Processing Per-Video Zone Data Fix

- **CRITICAL**: Fixed zones/ROIs not being loaded for each video in batch processing
- Modified `_load_zones_for_eligible_videos()` to serialize zone data into each `video_info` dict
- Added `_get_zone_data_for_video()` method in ProcessingWorker for per-video zone lookup
- Worker now uses video-specific zones instead of global default zones
- Zones and ROIs now display correctly during batch processing with proper tracking

#### Unified Report Metadata & Duplicates Fix (Dec 29, 2025)

- **CRITICAL**: Fixed duplicate "Group" columns (group vs group_id) and stale "Experiment ID" in unified reports
- `ProcessingCoordinator` now enforces authoritative metadata from current project structure (Day/Group/Subject), overriding old parquet headers
- **Color Format**: ROI colors in Excel now appear as "Red", "Blue" (names) instead of raw RGB tuples
- **Column Cleanup**: Explicitly drops redundant `group` column in favor of standard `group_id`

#### Batch Processing Results Directory Fix

- **CRITICAL**: Fixed results (parquet, reports) saving to wrong directory in batch processing
- Worker now creates per-video results directory: `{video_name}_results/` next to each video
- Trajectory parquet, arena/ROI parquets, and reports now save in correct location
- `_generate_summaries_impl` can now find the trajectory files correctly

#### Batch Processing Task Status Display Fix

- **HIGH**: Fixed Analysis tab not showing video progress (X de Y), group, day, subject info
- Updated `ProcessingCallbacks.on_progress` signature to include `index`, `total`, `experiment_id`
- Worker `monitor_loop` now passes all progress fields to callback
- `on_progress` callback now publishes `UI_UPDATE_ANALYSIS_TASK_STATUS` event
- Analysis tab displays: "Vídeo X de Y — ExperimentID • Etapa"

#### Batch Processing Selected Videos Fix

- **HIGH**: Fixed batch processing ignoring pre-selected videos from context menu
- Removed duplicate `PROJECT_PROCESS_VIDEOS` handler from `MainViewModel`
- `ProcessingCoordinator` now sole handler, correctly receives `video_paths` parameter
- "Processar Vídeos Selecionados" context menu action now works correctly

### 🟠 Visualization & Report Fixes

#### Trajectory Plot Coordinate System Fix

- **CRITICAL**: Fixed Y-axis inversion in trajectory plots (`visualization_generator.py`)
- Frame now vertically flipped with `cv2.flip(frame_rgb, 0)` for Cartesian alignment
- Changed matplotlib `origin` from "upper" to "lower" for correct coordinate display
- Fixed `extent` calculation using `video_height_for_transform` from BehavioralAnalyzer
- Y-coordinates now display correctly (0 at bottom, height at top)

#### ROI Color Consistency Fix

- **HIGH**: Fixed BGR→RGB color conversion for ROI colors in visualizations
- `analysis_control_view_model.py` now converts BGR tuples to RGB for matplotlib
- Colors in trajectory plots and heatmaps match actual ROI colors defined in zones

#### Word Report Layout Improvements

- **MEDIUM**: Increased image sizes from 3.2" to 5.5" for better readability
- Added page breaks before "Heatmap" and "Cumulative Distance" figures
- Ensures 2 figures per page layout with titles always adjacent to images
- Fixed "Chart" → "Figure" translation in Portuguese reports

#### Zone List Color Display Enhancement

- **UI**: Zone list now displays color names in Portuguese instead of hex codes
- Colors shown with colored text styling (Treeview tags)
- Arena principal also shows "Ciano" with colored text
- Added `_get_color_name_from_bgr()` helper method for color name mapping

### 🟡 Minor Improvements

#### ByteTracker Fallback Log Level

- Changed ByteTracker fallback message from WARNING to DEBUG
- Reduces log noise when simple tracker is used as expected fallback

#### Summary Parquet Generation

- Added summary parquet file creation in analysis workflow
- Trajectory registration now includes results_dir and experiment_id in hierarchy

---

## [2.2.0] - 2025-12-XX

### 🔴 Critical Fixes

#### Fixed Camera Thread Deadlock (Atomic Shutdown Pattern)

- **CRITICAL**: Eliminated camera thread deadlocks during shutdown in `io/camera.py`
- Implemented single ownership pattern: only `_reader_thread` calls `cap.release()` in finally block
- `release()` method now only signals `_shutdown_requested` Event and joins thread with 3s timeout
- Prevents race condition where main thread and reader thread both accessed VideoCapture object
- Shutdown now completes cleanly in <3 seconds with no zombie threads

#### VideoProcessingService UI Decoupling

- **CRITICAL**: Decoupled `VideoProcessingService` from tkinter and ApplicationGUI dependencies
- Removed `view` and `root` parameters from constructor (10 params → 8 params)
- Error handling now publishes `UIEvents.ERROR_OCCURRED` instead of calling `view.show_error()` directly
- ApplicationGUI subscribes to error events and schedules UI updates via `root.after()`
- Enables headless testing and better separation of concerns

#### Graceful Shutdown (Removed Hard Exit)

- **MEDIUM**: Removed `sys.exit(70)` forced termination when camera thread fails to shut down
- Publishes `UIEvents.ERROR_OCCURRED` with fatal error message for user notification
- Allows natural shutdown flow via `root.destroy()` instead of process kill
- Better cleanup and resource management during abnormal shutdown

### 🟢 Performance & Optimization

#### EventBus Performance Monitoring (100ms Fixed Threshold)

- **HIGH**: Added performance monitoring to `event_bus_v2.py` to identify UI-blocking handlers
- Measures handler execution time with `time.perf_counter()`
- Logs warning when handler exceeds 100ms fixed threshold (not configurable)
- Creates healthy pressure to move I/O operations to background threads instead of hiding with config
- Warnings include event name, handler name, elapsed time, and tech debt message

#### Dynamic Frame Skip Calibration

- **PERFORMANCE**: Implemented warm-up + 1 seek calibration in `video_processing_service.py`
- Measures single seek to frame 100 during `_create_video_context()`
- Calculates optimal skip threshold: 120 (<10ms), 80 (<50ms), or 60 (≥50ms) based on storage speed
- Added `_seek_to_frame()` helper using hybrid grab()/set() strategy
- Adapts to hardware capabilities (fast SSD vs network storage)
- Logged for debugging: `seek_time_ms`, `skip_threshold`

#### Memory Optimization (Column Subset Copy)

- **MEMORY**: Reduced memory usage during trajectory analysis by 40-60%
- Added `REQUIRED_TRAJECTORY_COLUMNS` constant in `analysis/analysis_service.py`
- Only copies 9 required columns instead of full DataFrame (15+ columns)
- Faster DataFrame operations and better cache locality
- Estimated savings: ~24MB per 500K-row trajectory

### 🧪 Testing Infrastructure

#### Wait Condition Helpers

- **NEW**: Created `tests/utils/wait_helpers.py` with robust polling-based wait utilities
- Eliminates flaky tests from `time.sleep()` usage
- Provides `wait_for_condition()`, `wait_for_event()`, `wait_for_thread_exit()`, `assert_condition_met()`
- Polling-based approach works reliably across different CPU speeds

#### Nightly Stress Test Workflow

- **NEW**: Created `.github/workflows/stress-tests.yml` scheduled for 2 AM UTC daily
- Threading stress tests (10x repetition of slow tests)
- Memory leak detection with memray profiling
- Flakiness detection (3x full suite runs)
- Auto-creates GitHub Issues on failure with labels and run links
- Keeps `ci.yml` fast for PR feedback

### Changed

- Updated `VideoContext` dataclass to include `skip_threshold` field (default 60)
- Modified `__main__.py` Composition Root to remove view/root from VideoProcessingService instantiation
- ApplicationGUI now subscribes to `UIEvents.ERROR_OCCURRED` in `__init__()`

### Documentation

- Updated `BUGFIX_SUMMARY.md` with v2.2 architectural improvements
- Added detailed explanations for all 8 major changes

---

## [2.1.0] - 2025-11-XX

### 🔄 Event-Driven Architecture (v4.0 Migration - Phase 2)

**Status**: IN PROGRESS (Dual Mode Compatibility)

#### Added

- **Event Bus V2** (`ui/event_bus_v2.py`): Foundation for Event-Driven Architecture v4.0
  - Type-safe event system with `UIEvents` enum (20+ event types)
  - Thread-safe publish/subscribe pattern with RLock
  - Event payload validation with dataclass `Event`
- **ZONES_UPDATED Event**: Migrated `update_zone_listbox()` from direct calls to events
  - 4 publishers now emit ZONES_UPDATED event:
    - `DialogManager.import_and_apply_template()`
    - `ROITemplateManager.apply_template()`
    - `CanvasRenderer.redraw_zones()`
    - `PolygonDrawingService` (ArenaCompletionStrategy + ROICompletionStrategy)
  - `CanvasManager` subscribes to ZONES_UPDATED and processes updates
- **VIDEO_TREE_REFRESH_REQUESTED Event**: Migrated `_populate_video_selector_tree()` from direct calls to events
  - 3 publishers now emit VIDEO_TREE_REFRESH_REQUESTED event:
    - `ZoneControlBuilder._refresh_video_tree_dual_mode()` (2 call sites: refresh button + initialization)
    - `ProjectViewManager._build_readiness_snapshot()`
  - `ProjectViewManager` subscribes to VIDEO_TREE_REFRESH_REQUESTED and processes updates
- **READINESS_SNAPSHOT_UPDATED Event**: Migrated `apply_pending_readiness_snapshot()` from direct calls to events
  - 1 publisher now emits READINESS_SNAPSHOT_UPDATED event:
    - `DialogManager.ask_reuse_zones()`
  - `ProjectViewManager` subscribes to READINESS_SNAPSHOT_UPDATED and processes updates
- **POLYGON_EDIT_REQUESTED Event**: Migrated `setup_interactive_polygon()` from direct calls to events ✨ **NEW + BUG FIX**
  - **CRITICAL BUG FIX**: Method was calling non-existent `EventDispatcher.setup_interactive_polygon()`, making polygon editing non-functional
  - 2 publishers now emit POLYGON_EDIT_REQUESTED event:
    - `CanvasManager.edit_selected_zone_vertices()` (arena editing)
    - `CanvasManager.edit_selected_zone_vertices()` (ROI editing)
  - `CanvasManager` subscribes to POLYGON_EDIT_REQUESTED and implements the MISSING logic:
    - Populates `gui.edited_polygon_points` from polygon data
    - Calls `renderer.draw_interactive_polygon()` to draw interactive handles
  - **This migration restores broken functionality while modernizing the architecture**
- **Integration Tests**: 46 new tests validating event flows (+15 from previous 31)
  - `tests/integration/test_zones_updated_event.py` (12 tests)
  - `tests/integration/test_video_tree_refresh_event.py` (9 tests)
  - `tests/integration/test_readiness_snapshot_event.py` (10 tests)
  - `tests/integration/test_polygon_edit_requested_event.py` (15 tests) ✨ NEW
  - Tests dual mode compatibility, edge cases, multiple subscribers, empty/missing data, polygon shapes, and coordinate precision

#### Changed

- **GUI.**init****: Now creates EventBusV2 instance (`self.event_bus_v2`)
- **Dependency Injection**: Event Bus V2 injected into 6 components:
  - `DialogManager(gui, event_bus_v2)`
  - `ROITemplateManager(project_manager, gui, event_bus_v2)`
  - `PolygonDrawingService(event_bus_v2)`
  - `CanvasManager(gui, event_bus_v2)`
  - `ProjectViewManager(gui, event_bus_v2)` ✨ NEW
  - `ZoneControlBuilder(gui, event_bus_v2)` ✨ NEW
- **Dual Mode Enabled**: All 10 publishers execute BOTH paths:
  - ZONES_UPDATED: 4 publishers (OLD + NEW paths)
  - VIDEO_TREE_REFRESH_REQUESTED: 3 publishers (OLD + NEW paths)
  - READINESS_SNAPSHOT_UPDATED: 1 publisher (OLD + NEW paths)
  - POLYGON_EDIT_REQUESTED: 2 publishers (OLD + NEW paths) ✨ NEW
  - Ensures backward compatibility during migration

#### Deprecated

- **`GUI.update_zone_listbox()`**: Marked with `@deprecated` decorator
  - Reason: "Use Event Bus V2 instead - migrating to Event-Driven Architecture v4.0"
  - Alternative: `event_bus_v2.publish(Event(UIEvents.ZONES_UPDATED, {'zone_data': zone_data}))`
  - Will be removed in v4.0 final (after dual mode phase)
- **`GUI._populate_video_selector_tree()`**: Marked with `@deprecated` decorator
  - Reason: "Use Event Bus V2 instead - migrating to Event-Driven Architecture v4.0"
  - Alternative: `event_bus_v2.publish(Event(UIEvents.VIDEO_TREE_REFRESH_REQUESTED, {'filter_text': filter_text}))`
  - Will be removed in v4.0 final (after dual mode phase)
- **`GUI.apply_pending_readiness_snapshot()`**: Marked with `@deprecated` decorator
  - Reason: "Use Event Bus V2 instead - migrating to Event-Driven Architecture v4.0"
  - Alternative: `event_bus_v2.publish(Event(UIEvents.READINESS_SNAPSHOT_UPDATED, {...}))`
  - Will be removed in v4.0 final (after dual mode phase)
- **`GUI.setup_interactive_polygon()`**: Marked with `@deprecated` decorator ✨ **NEW + BUG FIX**
  - Reason: "Use Event Bus V2 instead - migrating to Event-Driven Architecture v4.0"
  - Alternative: `event_bus_v2.publish(Event(UIEvents.POLYGON_EDIT_REQUESTED, {'polygon': polygon}))`
  - **NOTE**: This method was non-functional (calling non-existent EventDispatcher method). Migration restores functionality.
  - Will be removed in v4.0 final (after dual mode phase)

#### Documentation

- Updated `docs/EVENT_MAPPING.md` with implementation details for all 3 events
- Updated `docs/API_STABILITY.md` with deprecation notices

#### Next Steps (v4.0 Phase 2 Remaining)

- ✅ ~~Migrate `update_zone_listbox()` → `UIEvents.ZONES_UPDATED`~~ (COMPLETE - 4 publishers)
- ✅ ~~Migrate `_populate_video_selector_tree()` → `UIEvents.VIDEO_TREE_REFRESH_REQUESTED`~~ (COMPLETE - 3 publishers)
- ✅ ~~Migrate `apply_pending_readiness_snapshot()` → `UIEvents.READINESS_SNAPSHOT_UPDATED`~~ (COMPLETE - 1 publisher)
- ✅ ~~Migrate `setup_interactive_polygon()` → `UIEvents.POLYGON_EDIT_REQUESTED`~~ (COMPLETE - 2 publishers + BUG FIX) ✨ NEW
- Migrate 1-6 additional methods to events
  - Candidates: `_build_video_hierarchy_snapshot()`, `update_processing_stats()`, `update_social_summary()`, `update_analysis_task_status()`

#### Progress

- **4 of 11+** methods migrated to Event Bus V2 (**36% complete**)

## [3.0.0] - 2025-01-11

### 🔴 Breaking Changes

- **REMOVED**: Legacy thread system for Live projects completely removed
  - `_live_frame_capture_loop()` method removed from GUI
  - `_live_processing_loop()` method removed from GUI
  - `capture_thread` cleanup removed from MainViewModel
  - All Live camera functionality now exclusively through LiveCameraService

### 🧹 Code Cleanup

- Removed ~90 lines of deprecated legacy code
- Simplified project loading flow for Live projects
- Cleaner separation between video processing and live camera threads

## [2.1.0] - 2025-01-11

### 🔴 Breaking Changes

- **Live Projects**: Migrated to unified LiveCameraService architecture
  - Legacy thread system (`_live_frame_capture_loop`, `_live_processing_loop`) deprecated
  - Will be removed in v3.0

### ✨ Features

- Unified camera management for both analysis contexts
- Live projects now respect `camera_index` selected in wizard
- Intervals (analysis/display) properly respected in all workflows

### 🐛 Bug Fixes

- **CRITICAL**: Fixed Live projects always opening camera 0 (now uses wizard selection)
- **CRITICAL**: Fixed analysis intervals being ignored in single video workflow
- **CRITICAL**: Decoupled LiveCameraService from RecordingService (eliminated tight coupling)
  - Fixed multiple cameras activating simultaneously
  - Fixed wrong camera opening (respects camera_index correctly)
  - Fixed preview window delays and display issues
  - Eliminated unwanted side effects on global state
- **CRITICAL**: Fixed `TypeError` in LiveCameraService when starting recording
  - `Recorder.start_recording()` was being called with incorrect parameters
  - Changed from `folder_name`, `video_filename`, `parquet_filename`, `width`, `height`, `fps`
  - To correct parameters: `output_folder`, `frame_width`, `frame_height`, `zones`, `is_video_file`, `base_name`
  - Added regression test to prevent future parameter mismatches
- Fixed LiveStreamSource ignoring camera_index parameter
- Fixed FrameSourceFactory ignoring camera_index parameter

### 🚀 Performance

- Reduced thread count by 50% (4 → 2 threads)
- Reduced frame buffer memory by 50%
- Eliminated lock contention overhead

### 📝 Deprecated

- `gui._live_frame_capture_loop()` - Use LiveCameraService
- `gui._live_processing_loop()` - Use LiveCameraService
- Scheduled for removal: v3.0

### 🏗️ Architecture

- Unified `LiveCameraService` for both contexts:
  - Context 1: Single video analysis with camera
  - Context 2: Live projects with multi-session recording

## [Unreleased]

### Fixed

- **🎯 CRITICAL: Ghost Camera Detection**: Fixed wizard detecting "phantom" cameras that report `isOpened=True` but never return frames (e.g., virtual cameras, disconnected devices)
- **🎯 CRITICAL: Black Frame Detection**: Added detection of cameras that return completely black frames (virtual cameras with no input source)
- **🎯 CRITICAL: Camera Detection Hang**: Fixed wizard freezing during camera detection when encountering ghost cameras by adding 2-second timeout to frame capture test
- **🎯 Camera Name Mapping**: Disabled Windows PnP camera names due to unreliable index mapping between PowerShell enumeration and DirectShow device order
- **Live Camera Warmup**: Added 10-frame warmup period after camera initialization to fix preview lag (exposure/white balance adjustment time)
- **Live Camera Performance**: Added forced 1280x720 resolution for all cameras to prevent performance degradation with high-resolution cameras (e.g., 1920x1080)
- **Live Camera Error Handling**: Added user-friendly error dialog when camera fails to open with troubleshooting suggestions
- **Live Camera Recording**: Fixed `Recorder.start_recording()` TypeError by using correct parameter names (`output_folder`, `frame_width`, `frame_height` instead of deprecated `folder_name`, `width`, `height`)
- **Live Camera DirectShow**: Added DirectShow backend (`cv2.CAP_DSHOW`) to Camera class for Windows consistency with wizard detection
- **Detector Empty Polygon**: Fixed ValueError when zone data contains empty polygons in standalone analysis mode

### Changed

- **🎯 Camera Detection Logic**: Wizard now validates each camera can actually capture frames before adding to list (prevents index misalignment)
- **🎯 Camera Descriptions**: Changed from Windows device names to sequential numbering with resolution + brightness hints (e.g., "Câmera #1 [índice 1] - SD (640x480) (iluminação clara)")
- **Live Camera Resolution**: All cameras now forced to 1280x720 regardless of native resolution for consistent performance
- **Camera Detection Reliability**: Added consecutive failure tracking (stops after 3 consecutive ghost cameras to avoid long scans)
- **Camera Detection Range**: Reduced scan range from 0-9 to 0-5 for faster detection

### Removed

- **Live Camera Health Check**: Removed blocking 3-frame capture test that caused program hangs with slow/ghost cameras

## [v2.1.0] - 2025-11-12

### 🚨 **CRITICAL BUG FIX** - Pytest Hang on Windows

**PROBLEM RESOLVED**: Tests completed successfully (100% pass) but pytest hung indefinitely, causing VSCode and system to freeze and require manual restart. This critical issue blocked all development, testing, and coverage measurement.

### Fixed

- **Non-daemon threads blocking Python shutdown** ([#CRITICAL](https://github.com/MarkSant/ZebTrack-AI/commit/2372a4e))
  - Changed 4 worker threads to `daemon=True` in `LiveCameraService` and `GUI`
  - Allows Python to exit even if threads are running
  - Prevents indefinite hangs waiting for threads to terminate

- **Tkinter callbacks persisting after window destruction**
  - Added `pytest_sessionfinish` hook to force cleanup before exit
  - Cancels ALL pending `root.after()` callbacks (30+ locations in code)
  - Enhanced fixture cleanup in `tests/conftest.py`:
    - `tkinter_session_root`: Cancel callbacks before destroy
    - `tkinter_root`: Cancel Toplevel callbacks before destroy
    - `cleanup_threads`: New autouse fixture for thread leak detection

- **Added pytest-timeout plugin**
  - 300s (5 min) timeout per test
  - Thread-based method (safer on Windows)
  - Prevents infinite hangs in future

### Validation

- ✅ **2568 tests pass** (8 skip, 1 xfail) in **6min40s** - no hang
- ✅ **Coverage: 61%** measured successfully
- ✅ Works in terminal and VSCode Test Explorer
- ✅ System remains responsive throughout test execution

### Changed

- **Code quality improvements**
  - Ran `ruff check --fix` and `ruff format` on entire codebase
  - Fixed 37 auto-fixable linting issues
  - Reformatted 35 files for consistency

### Files Modified

- `tests/conftest.py` - Added hooks and enhanced fixtures
- `src/zebtrack/core/live_camera_service.py` - `daemon=True` for 2 threads
- `src/zebtrack/ui/gui.py` - `daemon=True` for 2 threads
- `pyproject.toml` - pytest-timeout configuration
- `poetry.lock` - Added pytest-timeout 2.4.0

---

## [2.0.0] - 2025-10-XX

### ⚠️ Breaking Changes

- Wizard live projects now require experimental design configuration (groups/days/subjects)
- Existing projects may need metadata added for full compatibility with new features

### ✨ New Features

**Architecture & Code Quality**:

- **Wizard Service Layer**: Extracted all wizard business logic to `zebtrack.core.wizard_service`
  - Centralized hardware detection (cameras, Arduino)
  - Reusable validation functions
  - Calculation utilities (experiment metrics, interval suggestions)
  - Fully testable independent of UI
  - **Hardware Detection Caching**: 30-second TTL cache for camera/Arduino detection (~5x faster on repeated calls)
- **Pydantic Data Models**: Type-safe validation for wizard data
  - `LiveConfigData`, `ExperimentalDesignData`, `CalibrationData`
  - Cross-field validations (e.g., external trigger requires Arduino)
  - Auto-generated error messages
- **Dialog Modularization**: Extracted 13 dialog classes from `gui.py` to `zebtrack.ui.dialogs/`
  - Reduced `gui.py` from 13,473 to 10,759 lines (~20% reduction)
  - Improved modularity, testability, and maintainability
  - Dialogs: CalibrationDialog, ManageWeightsDialog, ColorSelectionDialog, etc.
  - Resolved circular dependencies with `ui/format_utils.py`
- **Single-Video Mode Enhancement**: CalibrationDialog now hides "Project Preferences" section when in single-video analysis mode (no project context)

**Wizard Improvements** (from previous phases):

- Express/Advanced wizard modes
- External Trigger Mode for Arduino-based experiments
- Zone-based Arduino command triggers
- ROI inclusion rules (per-project configuration)
- Project template system (save/load wizard configurations)
- Unified preferences dialog with CollapsibleFrame UI

**Hardware Integration**:

- Arduino port detection with handshake validation
- Port descriptions (e.g., "COM3 - Arduino Uno")
- Connection test button with detailed error messages
- Camera detection with DirectShow backend (Windows) and early stopping optimization
- OpenCV log suppression during detection

**UI Enhancements**:

- NumberInput widget for intuitive numeric entry (+/- buttons)
- CollapsibleFrame widget for organized UI sections
- Treeview color harmonization (consistent green/yellow/red indicators)
- Interactive regex examples in CustomRegexDialog
- Improved tooltip coverage (100% of wizard fields)

### 🔧 Improvements

- **Performance**: Hardware detection caching reduces wizard navigation lag
  - Camera detection: ~5x faster on repeated calls (cached for 30 seconds)
  - Arduino port scanning: Instant results when navigating back/forward in wizard
  - Manual cache clearing available via `WizardService.clear_hardware_cache()`
- Model selection now available for live projects
- Configurable analysis/display intervals per project
- Automatic camera/Arduino detection with status feedback
- Intelligent suggestions (e.g., analysis interval based on FPS)
- Validation moved from UI to service layer (better testability)
- Removed legacy `LiveConfigDialog` (replaced by wizard `LiveConfigStep`)
- Code organization: Major cleanup with dialog extraction reducing `gui.py` complexity

### 📝 Documentation

- **NEW**: `docs/DEVELOPER_GUIDE_WIZARD.md` - Comprehensive wizard architecture guide
  - Service layer patterns
  - Pydantic model usage
  - How to add new wizard steps
  - Testing strategies
  - Best practices and anti-patterns
- **UPDATED**: `docs/WIZARD_LIVE_IMPROVEMENTS.md` - Phase 0-4 improvements
- **UPDATED**: `CLAUDE.md` - Project instructions with v2.0 features

### 🧪 Testing

- **712 tests passing** (24 new tests, 0 regressions)
  - 16 E2E tests for WizardService integration (`tests/ui/wizard/test_wizard_live_e2e.py`)
  - 8 hardware caching tests (`tests/test_wizard_service_caching.py`)
- Service layer fully unit tested
- Wizard steps validated with integration tests
- Code coverage maintained at 70%+
- Removed 1 redundant skipped test (architectural rule already enforced by other tests)

### 🐛 Bug Fixes

- Fixed line length violations in `project_manager.py`
- Reduced cyclomatic complexity in `gui.py` (_VideoPathResolverContext helper class)
- Removed unused imports

### 🔄 Refactoring

- **Dialog Extraction**: Moved 13 dialog classes from `gui.py` to `zebtrack.ui.dialogs/`
  - Created AST-based extraction scripts for reliable code extraction
  - Fixed all missing imports and circular dependencies
  - Updated tests to reference new dialog locations
- Extracted wizard validation logic to `WizardService`
- Moved hardware detection to service layer with caching
- Created Pydantic models for type safety
- Simplified wizard step `validate()` methods (delegate to service)
- Created `ui/format_utils.py` to resolve circular dependencies

### 📦 Dependencies

- No new dependencies added
- Pydantic v2 already in use (existing dependency)

---

## [1.6.0] - Previous Release

### Added

- Wizard-based project creation (5-step flow)
- Live project support with camera/Arduino integration
- Experimental design fields (groups, days, subjects)
- Template persistence

### Changed

- Wizard is now the default project creation method
- Legacy dialogs maintained for backward compatibility

---

## How to Upgrade

### From v1.x to v2.0

1. **No action required** for existing projects - they will continue to work
2. **New live projects** must use the wizard and provide experimental design
3. **Developers**: Review `docs/DEVELOPER_GUIDE_WIZARD.md` for new patterns
4. **Tip**: Use `WizardService` for any new validation/hardware logic

### Template Migration

If you have saved wizard templates from v1.6+, they are compatible with v2.0.
New fields (experimental design) will use defaults if not present in old templates.

---

## Support

- Report issues: <https://github.com/anthropics/claude-code/issues>
- Documentation: See `docs/` directory
- Developer Guide: `docs/DEVELOPER_GUIDE_WIZARD.md`

<!-- markdownlint-enable MD024 -->
