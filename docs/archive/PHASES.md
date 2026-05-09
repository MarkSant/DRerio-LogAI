# Phase History (v2.0 — v3.x)

Historical record of major phases. Moved out of `CLAUDE.md` on 2026-05-09 to
keep agent context lean. The current code state is the source of truth — this
file documents **how we got there**.

---

## Phase 4: Wizard Service Layer (Oct–Nov 2025)

- **WizardService** (`core/services/wizard_service.py`): business logic separated from UI
  - Hardware detection (cameras, Arduino) with **30s TTL caching** (5x faster)
  - Validation methods for all wizard steps
- **Pydantic Models** (`ui/wizard/models.py`): type-safe validation
- **Dialog Extraction**: 13 dialogs moved from `gui.py` to `ui/dialogs/` (~20% reduction)

## Phase 5: Testing & Performance

- **E2E Tests**: 16 integration tests (`test_wizard_live_e2e.py`)
- **Cache Tests**: 8 tests (`test_wizard_service_caching.py`)
- **Total**: 2778+ tests passing (as of Mar 2026)

## Phase 6: Live Camera Analysis (Nov 2025)

- **LiveCameraService** (`core/recording/live_camera_service.py`): dedicated service for live camera sessions
  - Parallel threads: `_capture_loop()` + `_processing_loop()` for frame acquisition & detection
  - Integrated with `RecordingService` for timed sessions & coordination
  - Real-time preview via `LivePreviewWindow`
- **LiveAnalysisDialog** (`ui/dialogs/live_analysis_dialog.py`): configuration UI
- **LiveStreamSource** (`io/live_stream_source.py`): time-limited Camera wrapper (FrameSource compatible)
- **Access**: Menu File → "Analisar Câmera ao Vivo..." or `controller.start_live_camera_analysis()`
- **Output**: `live_analysis_sessions/{experiment_id}_{timestamp}/` with standard Parquet + optional video

## Phase 7: Critical Pytest Fixes (Nov 2025) ⚠️ BREAKING FIX

**PROBLEM RESOLVED**: Tests completed successfully but pytest hung indefinitely,
causing VSCode and system freezes requiring manual restart.

**Root causes:**

1. Non-daemon threads in `LiveCameraService` and `GUI` blocked Python shutdown
2. Tkinter `root.after()` callbacks persisted after `root.destroy()` (30+ locations)
3. No pytest sessionfinish hook to force cleanup

**Solution** (commit 2372a4e):

- Changed 4 worker threads to `daemon=True` (allows Python to exit)
- Added `pytest_sessionfinish` hook with forced cleanup (5s timeout, cancels Tkinter callbacks)
- Enhanced fixture cleanup: `tkinter_session_root`, `tkinter_root`, `cleanup_threads` (autouse)
- Added `pytest-timeout` plugin (300s per test, thread-based)

**Validation:**

- 2778+ tests pass (12 skip) — no hang (as of Mar 2026)
- Coverage: 61% measured successfully
- Works in terminal and VSCode Test Explorer
- System remains responsive

**Files modified**: `tests/conftest.py`, `src/zebtrack/core/recording/live_camera_service.py`,
`src/zebtrack/ui/gui.py`, `pyproject.toml`

## Phase 8: Live Camera Unification (Jan 2026) 🔴 CRITICAL

**PROBLEM RESOLVED**: Dual parallel systems for live camera management caused
critical bugs: wrong camera selection, multiple cameras activating, preview
failures, and ignored configuration settings.

**Root causes:**

1. **Bug #1 (CRITICAL)**: Live projects ignored `camera_index` from wizard (always opened camera 0)
2. **Bug #2 (CRITICAL)**: Analysis intervals ignored in single video workflow
3. **Bug #6 (CRITICAL)**: LiveCameraService coupled to RecordingService (caused multiple cameras, wrong camera, preview issues)
4. **Bugs #3-4**: LiveStreamSource and FrameSourceFactory ignored `camera_index` parameter

**Solution:**

- **Unified Architecture**: both contexts now use `LiveCameraService`
  - Context 1: Single video analysis with camera
  - Context 2: Live projects with multi-session recording
- **Decoupled LiveCameraService**: no longer depends on RecordingService
  - Lightweight recording directly in service
  - Own session timer management
  - No global state pollution
- **Respect All Settings**: `camera_index`, `analysis_interval_frames`,
  `display_interval_frames` properly passed and used
- **Deprecated Legacy**: thread system in `gui.py` marked for v3.0 removal

**Performance improvements:**

- 50% reduction in threads (4 → 2)
- 50% reduction in memory (eliminated duplicate buffers)
- Eliminated lock contention overhead

**Files modified:**

- `src/zebtrack/ui/components/event_dispatcher.py`
- `src/zebtrack/core/main_view_model.py` (2 new methods)
- `src/zebtrack/ui/gui.py`
- `src/zebtrack/core/recording/live_camera_service.py` (major refactor)
- `src/zebtrack/io/live_stream_source.py`
- `src/zebtrack/io/frame_source_factory.py`

## Phase 9: Legacy Code Removal — v3.0 (Jan 2026) ✅ COMPLETE

**BREAKING CHANGE**: Removed all deprecated legacy thread system code from Live
camera workflows.

**Removed code:**

- `_live_frame_capture_loop()` method (~30 lines) — replaced by LiveCameraService
- `_live_processing_loop()` method (~60 lines) — replaced by LiveCameraService
- `capture_thread` initialization and cleanup in `gui.py` — no longer needed
- Legacy thread join logic in `main_view_model.py` — simplified

**Impact:**

- Removed ~90 lines of deprecated code
- Simplified project loading flow for Live projects
- All Live camera functionality exclusively through LiveCameraService
- Cleaner separation between video processing and live camera threads
- ⚠️ **BREAKING**: code depending on legacy threads will fail (use LiveCameraService API)

**Version**: v3.0.0 (2025-01-11)

## Phase 10: Multi-Aquarium Support (Dec 2025)

**Feature**: Tracking in 2 independent aquariums per video with separate ROIs and zones.

### Phase 11: Multi-Aquarium Reporting + Reports Tree (Dec 2025)

**Problems resolved:**

- Aquarium 1 report using Aquarium 0 cropped background
- Aquarium 1 trajectory/heatmap misaligned
- Reports tab showing only one aquarium
- Summary indicator not persisting reliably after generation

**Root causes:**

1. `get_zone_data()` returns only Aquarium 0 in multi-mode (backward compatibility)
2. Reports tree sometimes receives simplified hierarchy entries without `multi_aquarium_outputs`
3. `multi_aquarium_outputs` keys can be mixed (`0` vs `"0"`), causing Treeview iid collisions

**Fixes / guard rails:**

- Reporting: always prefer `ProjectManager.get_multi_aquarium_zone_data()` with safe fallback
- Persistence: after summary/report generation, re-register outputs via `register_multi_aquarium_outputs(...)`
- UI: in Reports tree, fall back to `ProjectManager.find_video_entry(video_path)` and normalize aquarium keys

**Regression tests:**

- `tests/ui/components/test_project_view_manager_reports_tree_multi_aquarium.py`
- `tests/analysis/test_visualization_generator_background_image.py`

**Core data structures** (in `core/detection/`):

- `AquariumData`: holds `id`, `polygon`, `roi_mode`, `roi_data` for each aquarium
- `MultiAquariumZoneData`: container with `aquariums: list[AquariumData]`,
  `calibration`, `active_aquarium_id`, `sequential_processing`

**Key methods:**

- `Detector.set_multi_aquarium_zones(zone_data: MultiAquariumZoneData)` — configure multi-aquarium mode
- `Detector.detect_partitioned(frame)` — returns `dict[aquarium_id, list[detections]]`
- `Detector.detect_partitioned_parallel(frame)` — parallel detection with ThreadPoolExecutor (~30-40% speedup)
- `Detector.detect_batch(frames, batch_size)` — batch inference for offline processing
- `Detector._crop_aquarium_region(frame, aq_id)` — ROI cropping for per-aquarium extraction
- `ProjectManager.resolve_multi_aquarium_results_directories()` — creates `<video>_aquarium_1/`, `<video>_aquarium_2/`
- `AnalysisService.run_multi_aquarium_analysis()` — runs analysis per aquarium
- `TrajectoryQualityValidator._validate_multi_aquarium_ids()` — validates track IDs per aquarium
- `TrajectoryQualityValidator._detect_per_aquarium_gaps()` — detects missing frames per aquarium

**Track ID convention:**

- Global ID = `aquarium_id * 1000 + local_track_id`
- Aquarium 0: IDs 0–999; Aquarium 1: IDs 1000–1999; Aquarium 2: IDs 2000–2999
- **CRITICAL**: `local_track_id` MUST be < 1000 to prevent overflow collisions

**Parquet schema extensions:**

- `uncertainty`: detection confidence uncertainty (1 - confidence)
- `bbox_iou`: bounding box IoU with previous frame (tracking stability)

**Events** (UIEvents enum in `ui/event_bus_v2.py`):

- `ZONE_MULTI_AUTO_DETECT` — trigger multi-aquarium detection
- `ZONE_MULTI_AUTO_DETECT_SUCCESS` — detection succeeded (payload: `{video_path, polygons}`)
- `ZONE_MULTI_AUTO_DETECT_FAILED` — detection failed (payload: `{video_path, reason}`)
- `ZONE_AQUARIUM_SELECTED` — user selected aquarium (payload: `{aquarium_id: int}`)
- `ZONE_MULTI_DETECT_COMPLETED` — detection done (payload: `{count: int, aquariums: list}`)
- `ZONE_AQUARIUM_CONFIG_CONFIRMED` — config confirmed (payload: `{configs: list[AquariumConfig]}`)
- `ZONE_AQUARIUM_CONFIG_UPDATED` — config updated (payload: `{aquarium_id, config, video_path}`)
- `ZONE_AQUARIUM_COUNT_CONFIRMED` — count confirmed (payload: `{count: int}`)
- `ZONE_AQUARIUM_ASSIGNMENT_COMPLETED` — assignment done (payload: `{configs, apply_to_all}`)
- `ZONE_SHOW_AQUARIUM_COUNT_DIALOG` / `ZONE_SHOW_AQUARIUM_ASSIGNMENT_DIALOG` — dialog requests
- `ZONE_PROCESSING_MODE_CHANGED` — processing mode toggle (payload: `{sequential: bool}`)

**Event handlers:**

- `MultiAquariumCoordinator._handle_multi_auto_detect()` — handles ZONE_MULTI_AUTO_DETECT
- `ProjectLifecycleCoordinator._handle_aquarium_config_updated()` — handles ZONE_AQUARIUM_CONFIG_UPDATED

**UI components:**

- `CanvasManager.create_side_by_side_preview()` — side-by-side aquarium comparison
- `WizardService.validate_multi_aquarium_config()` — returns (is_valid, errors, warnings)

**UI dialogs** (in `ui/dialogs/`):

- `AquariumAssignmentDialog` — assign groups/subjects to detected aquariums
- `MultiAquariumConfirmDialog` — confirm detected aquarium count

**Pydantic models** (in `ui/wizard/models.py`):

- `AquariumConfig`: `aquarium_id`, `group_name`, `subject_name`, `enabled`
- `MultiAquariumData`: `enabled`, `count`, `detection_method`, `configs`

**Testing**: 250+ tests in `tests/core/test_*_multi*.py`, `tests/ui/test_*_multi*.py`,
`tests/integration/test_multi_aquarium_e2e.py`, `tests/analysis/test_trajectory_validator.py`

## Phase 10.1: Sequential Multi-Aquarium Processing (Dec 2025)

**Feature**: Option to process each aquarium separately with 2 complete video
passes instead of simultaneously.

**Processing modes:**

- **Parallel (default)**: `sequential_processing=False` — both aquariums processed in 1 video pass
- **Sequential**: `sequential_processing=True` — complete video for aquarium 0, then complete video for aquarium 1

**Data flow (sequential mode):**

```text
┌─ Pass 1: Aquarium 0 ────────────────────────────────────────────────┐
│   AquariumData[0].to_zone_data() → ZoneData → detect() → aquarium_0/│
└─────────────────────────────────────────────────────────────────────┘
                               ↓ (automatic)
┌─ Pass 2: Aquarium 1 ────────────────────────────────────────────────┐
│   AquariumData[1].to_zone_data() → ZoneData → detect() → aquarium_1/│
└─────────────────────────────────────────────────────────────────────┘
                               ↓
┌─ Finalization ──────────────────────────────────────────────────────┐
│   register_multi_aquarium_outputs() → generate_project_reports()    │
└─────────────────────────────────────────────────────────────────────┘
```

**UI toggle** (in `ui/components/zone_controls.py`):

- Radio buttons: "Simultâneo (1 passagem)" vs "Sequencial (2 passagens)"
- Only visible when multi-aquarium mode is active
- Emits `ZONE_PROCESSING_MODE_CHANGED` event

**Key methods** (in `coordinators/sequential_processing_coordinator.py`):

- `_start_sequential_multi_aquarium_processing()` — initializes sequential context
- `_process_next_aquarium_in_sequence()` — processes next aquarium, generates reports when done
- `_start_single_aquarium_for_sequential()` — runs single-aquarium flow for each aquarium

**Output structure** (identical to parallel mode):

```text
video_results/
├── aquarium_0/
│   ├── 3_CoordMovimento_{video}.parquet
│   ├── 4_Relatorio_{video}_aq0.docx
│   ├── 4_Relatorio_{video}_aq0.xlsx
│   └── {video}_aq0_summary.parquet
└── aquarium_1/
    └── (mirror)
```

**Advantages of sequential mode:**

- Uses 100% resources per aquarium (no resource splitting)
- Lower memory usage (1 ByteTracker at a time)
- Easier debugging (1 flow at a time)
- Reuses battle-tested single-aquarium code path

**Trade-offs:**

- 2x total processing time
- Video read twice from disk

**Serialization**: `ZoneManager.multi_aquarium_zone_data_to_dict/from_dict()`
includes `sequential_processing` field.

## Version History (concise)

- **v3.3** (Dec 29, 2025): Unified Report Robustness — deletion button (OneDrive safe), metadata authority fix, duplicate column cleanup
- **v3.2** (Dec 28, 2025): Unified Report Fixes + Max Speed Metric — geotaxis data in unified reports, column naming, subject identification
- **v3.1** (Dec 2025): Sequential Multi-Aquarium Processing
- **v3.0** (Jan 2026): 🔴 BREAKING — removed legacy live-camera thread system (~90 lines)
- **v2.1** (Jan 2026): Live Camera Unification
- **v2.0** (Nov 2025): ⚠️ Critical pytest fixes
- **v1.9** (Oct 2025): WizardService, dialog extraction, hardware caching, E2E tests, LiveCameraService
- **v1.8**: StateManager (observable, thread-safe)
- **v1.7**: Pydantic v2 settings, in-app config editor
- **v1.6**: 5-step wizard flow
- **v1.x**: ROI templates, track overlays, social proximity
