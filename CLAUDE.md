# CLAUDE.md

**AI Assistant Guidance for ZebTrack-AI Development**

## Quick Context

**DRerio LogAI** (`zebtrack` package) - Python 3.12+ Tkinter app for zebrafish behavioral tracking and analysis.
**Architecture**: MVVM-S with Dependency Injection (DI). Entry: `src/zebtrack/__main__.py` (Composition Root)
**Tech Stack**: Poetry, Tkinter, YOLO/OpenVINO, Parquet, structlog, Pydantic v2

## Essential Commands

```bash
# Setup & Run
poetry install                    # First time
poetry run zebtrack               # Run app

# Testing (fast by default, 2568 tests total)
poetry run pytest                 # Fast tests only (excludes GUI/slow) - ~1586 tests
poetry run pytest -m gui -n0      # GUI tests (sequential) - ~949 tests
poetry run pytest -m slow         # Slow tests only - ~35 tests
poetry run pytest -m "" -n0       # All tests - ~2568 tests (6-7 min)

# Code Quality
poetry run ruff check .           # Lint
poetry run ruff check --fix .     # Auto-fix
poetry run pre-commit run --all-files  # Full pre-commit
```

**Detailed Guides**:
- `docs/architecture/SYSTEM_INTEGRATION_MAP.md` - **CRITICAL**: Event payloads & Component contracts
- `docs/guides/developer/CHEATSHEET.md` - Quick developer reference
- `README_TESTS.md` - Complete testing guide

## Architecture (MVVM-S + DI)

### Composition Root
- **`__main__.py`** (lines 140-280): All dependencies wired here
- Never use global settings: always `load_settings()` then inject `settings_obj`

### Core Layers (Phase 3/4 Architecture - Dec 2025)
| Layer | Key Files | Purpose |
|-------|-----------|---------|
| **Model** | `core/{state_manager,project_manager,detector_service}.py` | State, project data, detection |
| **View** | `ui/gui.py`, `ui/wizard/*.py`, `ui/dialogs/*.py` | Tkinter UI (10759 lines gui.py) |
| **ViewModel** | `core/main_view_model.py` | Orchestrator (11+ injected deps) |
| **Coordinators** | `coordinators/{processing,hardware,session,project_lifecycle}_coordinator.py` | Super coordinators (Phase 3) |
| **Services** | `core/{wizard_service,video_processing_service,live_camera_service,recording_service}.py` | Business logic |
| **I/O** | `io/{recorder,video_source,camera,live_stream_source,recorder_factory}.py` | Persistence, frame sources |
| **Analysis** | `analysis/{analysis_service,behavior,roi,reporter}.py` | Behavioral metrics, reports |

### Performance Optimizations (v2.1+)
- **RecorderFactory**: Lazy-loads `Recorder` (pandas/pyarrow) only when analysis starts
  - Located in `io/recorder_factory.py`, delegates via `__getattr__` + context manager support
  - Thread-safe double-checked locking pattern prevents duplicate initialization
  - Saves ~2.9s startup time + 150 MB memory by deferring heavy dependency imports
- **Splash Screen**: Professional loading UI (`ui/splash_screen.py`) with progress indicators
  - Platform-specific fonts (Segoe UI on Windows, Helvetica elsewhere)
  - Color constants: `BG_COLOR`, `ACCENT_COLOR`, `TEXT_PRIMARY`, `TEXT_SECONDARY`, `TEXT_MUTED`
  - Configurable display duration via `SPLASH_DISPLAY_DURATION_MS` in `__main__.py`
- **Lazy Imports**: Pandas imports deferred in `project_manager.py`, `zone_manager.py`, `project_service.py`
  - Only loaded when accessing existing project data, not during app startup
  - Total impact: Startup time reduced from ~6.0s to ~2.0s (-67%)

### Data Flow
1. **User → Event → ViewModel → State → UI**:
   UI emits events to `EventBus` → `MainViewModel` handles → `StateManager` updates → UI refreshes via `root.after(0, ...)`

2. **Processing Pipeline** (Pre-recorded):
   `VideoSource` → `DetectorService` (zones + detection) → `Recorder` (Parquet + MP4) → `AnalysisService` → `Reporter`

3. **Live Camera Analysis** (v2.0+):
   `LiveAnalysisDialog` → `LiveCameraService` → `[CaptureThread, ProcessingThread]` → `Camera` → `DetectorService` → `Recorder` + `LivePreviewWindow`
   - Output: `live_analysis_sessions/{experiment_id}_{timestamp}/`
   - Features: Time-limited sessions, real-time preview, parallel threads

**Full Details**: `docs/ARCHITECTURE.md`, `docs/DEPENDENCY_INJECTION_GUIDE.md`

## Critical Constraints

### 🔒 Parquet Schema (IMMUTABLE)
```
timestamp, frame, track_id, x1, y1, x2, y2, confidence, [x_center_px, y_center_px, x_cm, y_cm]*
```
- Column order **FIXED** - defined in `io/recorder.py`
- Calibration columns (`*_cm`) only when calibration exists
- Any changes require updates to `tests/test_recorder.py`

### ⚙️ Configuration System
- **Never hardcode**: Always use `from zebtrack import settings`
- Hierarchy: `config.yaml` (base) → `config.local.yaml` (overrides, git-ignored)
- Pydantic v2 models with `extra="forbid"` in `settings.py`
- Per-project overrides: `ProjectManager.project_data`

### 🗺️ Zone and Coordinate Systems
- Zones defined in reference coords (`camera.desired_width` × `camera.desired_height`)
- **MUST call `Detector.set_zones()` after video dimensions known** to rescale
- Arena: "4 corners OR center" logic
- ROI: `centroid_in`, `centroid_in_on_buffered_roi`, `bbox_intersects`, `seg_overlap`
- **Full Guide**: `docs/COORDINATE_SYSTEMS.md`

### 🧵 Threading & UI
- **All UI updates MUST use `root.after(0, ...)`** (Tkinter main thread)
- Heavy processing in worker threads
- `StateManager` is thread-safe
- Progress callbacks: `total_frames`, `processed_frames`, `detected_frames`, `start_time`

### 🧙 Project Wizard (Default Flow v1.6+)
- 5-step wizard (`ui/wizard/`) is primary project creation
- Layout: 1150×550px, reserves 220px for nav buttons
- `wizard_adapter.adapt_wizard_data_to_controller_format()` for backward compatibility
- **Guide**: `docs/DEVELOPER_GUIDE_WIZARD.md`

## Recent Major Features (v2.0 - Oct-Nov 2025)

### Phase 4: Wizard Service Layer
- **WizardService** (`core/wizard_service.py`): Business logic separate from UI
  - Hardware detection (cameras, Arduino) with **30s TTL caching** (5x faster)
  - Validation methods for all wizard steps
- **Pydantic Models** (`ui/wizard/models.py`): Type-safe validation
- **Dialog Extraction**: 13 dialogs moved from `gui.py` to `ui/dialogs/` (~20% reduction)

### Phase 5: Testing & Performance
- **E2E Tests**: 16 integration tests (`test_wizard_live_e2e.py`)
- **Cache Tests**: 8 tests (`test_wizard_service_caching.py`)
- **Total**: 712 tests passing, 1 skipped

### Phase 6: Live Camera Analysis (Nov 2025)
- **LiveCameraService** (`core/live_camera_service.py`): Dedicated service for live camera sessions
  - Parallel threads: `_capture_loop()` + `_processing_loop()` for frame acquisition & detection
  - Integrated with `RecordingService` for timed sessions & coordination
  - Real-time preview via `LivePreviewWindow`
- **LiveAnalysisDialog** (`ui/dialogs/live_analysis_dialog.py`): Configuration UI
- **LiveStreamSource** (`io/live_stream_source.py`): Time-limited Camera wrapper (FrameSource compatible)
- **Access**: Menu File → "Analisar Câmera ao Vivo..." or `controller.start_live_camera_analysis()`
- **Output**: `live_analysis_sessions/{experiment_id}_{timestamp}/` with standard Parquet + optional video

### Phase 7: Critical Pytest Fixes (Nov 2025) ⚠️ BREAKING FIX
**PROBLEM RESOLVED**: Tests completed successfully but pytest hung indefinitely, causing VSCode and system freezes requiring manual restart.

**ROOT CAUSES**:
1. Non-daemon threads in `LiveCameraService` and `GUI` blocked Python shutdown
2. Tkinter `root.after()` callbacks persisted after `root.destroy()` (30+ locations)
3. No pytest sessionfinish hook to force cleanup

**SOLUTION** (commit 2372a4e):
- ✅ Changed 4 worker threads to `daemon=True` (allows Python to exit)
- ✅ Added `pytest_sessionfinish` hook with forced cleanup (5s timeout, cancels Tkinter callbacks)
- ✅ Enhanced fixture cleanup: `tkinter_session_root`, `tkinter_root`, `cleanup_threads` (autouse)
- ✅ Added `pytest-timeout` plugin (300s per test, thread-based)

**VALIDATION**:
- ✅ 2568 tests pass (8 skip, 1 xfail) in 6min40s - **no hang**
- ✅ Coverage: 61% measured successfully
- ✅ Works in terminal and VSCode Test Explorer
- ✅ System remains responsive

**FILES MODIFIED**: `tests/conftest.py`, `src/zebtrack/core/live_camera_service.py`, `src/zebtrack/ui/gui.py`, `pyproject.toml`

**Full Details**: `docs/WIZARD_LIVE_IMPROVEMENTS.md`, `docs/archive/LIVE_*.md` (historical context)

### Phase 8: Live Camera Unification (Jan 2025) 🔴 CRITICAL
**PROBLEM RESOLVED**: Dual parallel systems for live camera management caused critical bugs: wrong camera selection, multiple cameras activating, preview failures, and ignored configuration settings.

**ROOT CAUSES**:
1. **Bug #1 (CRITICAL)**: Live projects ignored `camera_index` from wizard (always opened camera 0)
2. **Bug #2 (CRITICAL)**: Analysis intervals ignored in single video workflow
3. **Bug #6 (CRITICAL)**: LiveCameraService coupled to RecordingService (caused multiple cameras, wrong camera, preview issues)
4. **Bugs #3-4**: LiveStreamSource and FrameSourceFactory ignored `camera_index` parameter

**SOLUTION** (PLANO_CORRECAO_FLUXOS_CAMERA_LIVE.md):
- ✅ **Unified Architecture**: Both contexts now use `LiveCameraService`
  - Context 1: Single video analysis with camera
  - Context 2: Live projects with multi-session recording
- ✅ **Decoupled LiveCameraService**: No longer depends on RecordingService
  - Lightweight recording directly in service
  - Own session timer management
  - No global state pollution
- ✅ **Respect All Settings**: `camera_index`, `analysis_interval_frames`, `display_interval_frames` properly passed and used
- ✅ **Deprecated Legacy**: Thread system in `gui.py` marked for v3.0 removal

**PERFORMANCE IMPROVEMENTS**:
- 50% reduction in threads (4 → 2)
- 50% reduction in memory (eliminated duplicate buffers)
- Eliminated lock contention overhead

**FILES MODIFIED**:
- `src/zebtrack/ui/components/event_dispatcher.py`
- `src/zebtrack/core/main_view_model.py` (2 new methods)
- `src/zebtrack/ui/gui.py`
- `src/zebtrack/core/live_camera_service.py` (major refactor)
- `src/zebtrack/io/live_stream_source.py`
- `src/zebtrack/io/frame_source_factory.py`

**Full Details**: `docs/LIVE_CAMERA_UNIFICATION.md`, `PLANO_CORRECAO_FLUXOS_CAMERA_LIVE.md`

### Phase 9: Legacy Code Removal - v3.0 (Jan 2025) ✅ COMPLETE
**BREAKING CHANGE**: Removed all deprecated legacy thread system code from Live camera workflows.

**REMOVED CODE**:
- ❌ `_live_frame_capture_loop()` method (~30 lines) - replaced by LiveCameraService
- ❌ `_live_processing_loop()` method (~60 lines) - replaced by LiveCameraService
- ❌ `capture_thread` initialization and cleanup in `gui.py` - no longer needed
- ❌ Legacy thread join logic in `main_view_model.py` - simplified

**IMPACT**:
- 🧹 Removed ~90 lines of deprecated code
- ✅ Simplified project loading flow for Live projects
- ✅ All Live camera functionality exclusively through LiveCameraService
- ✅ Cleaner separation between video processing and live camera threads
- ⚠️ **BREAKING**: Code depending on legacy threads will fail (use LiveCameraService API)

**VERSION**: v3.0.0 (2025-01-11)

**Full Details**: `docs/LIVE_CAMERA_UNIFICATION.md`, `PLANO_CORRECAO_FLUXOS_CAMERA_LIVE.md`

### Phase 10: Multi-Aquarium Support (Dec 2025)
**Feature**: Enables tracking in 2 independent aquariums per video with separate ROIs and zones.

**Core Data Structures** (in `core/detector.py`):
- `AquariumData`: Holds `id`, `polygon`, `roi_mode`, `roi_data` for each aquarium
- `MultiAquariumZoneData`: Container with `aquariums: list[AquariumData]`, `calibration`, `active_aquarium_id`

**Key Methods**:
- `Detector.set_multi_aquarium_zones(zone_data: MultiAquariumZoneData)` - Configure multi-aquarium mode
- `Detector.detect_partitioned(frame)` - Returns `dict[aquarium_id, list[detections]]`
- `Detector.detect_partitioned_parallel(frame)` - Parallel detection with ThreadPoolExecutor (~30-40% speedup)
- `Detector.detect_batch(frames, batch_size)` - Batch inference for offline processing
- `Detector._crop_aquarium_region(frame, aq_id)` - ROI cropping for per-aquarium extraction
- `ProjectManager.resolve_multi_aquarium_results_directories()` - Creates `<video>_aquarium_1/`, `<video>_aquarium_2/`
- `AnalysisService.run_multi_aquarium_analysis()` - Runs analysis per aquarium
- `TrajectoryQualityValidator._validate_multi_aquarium_ids()` - Validates track IDs per aquarium
- `TrajectoryQualityValidator._detect_per_aquarium_gaps()` - Detects missing frames per aquarium

**Track ID Convention**:
- Global ID = `aquarium_id * 1000 + local_track_id`
- Example: Aquarium 0, track 5 → ID 5; Aquarium 1, track 3 → ID 1003
- Aquarium 0: IDs 0-999; Aquarium 1: IDs 1000-1999; Aquarium 2: IDs 2000-2999
- **CRITICAL**: `local_track_id` MUST be < 1000 to prevent overflow collisions

**Parquet Schema Extensions**:
- `uncertainty`: Detection confidence uncertainty (1 - confidence)
- `bbox_iou`: Bounding box IoU with previous frame (tracking stability)

**Events** (in `ui/events.py`):
- `ZONE_MULTI_AUTO_DETECT` - Trigger multi-aquarium detection
- `ZONE_MULTI_AUTO_DETECT_SUCCESS` - Detection succeeded (payload: `{video_path, polygons}`)
- `ZONE_MULTI_AUTO_DETECT_FAILED` - Detection failed (payload: `{video_path, reason}`)
- `ZONE_AQUARIUM_SELECTED` - User selected aquarium (payload: `{aquarium_id: int}`)
- `ZONE_MULTI_DETECT_COMPLETED` - Detection done (payload: `{count: int, aquariums: list}`)
- `ZONE_AQUARIUM_CONFIG_CONFIRMED` - Config confirmed (payload: `{configs: list[AquariumConfig]}`)
- `ZONE_AQUARIUM_CONFIG_UPDATED` - Config updated (payload: `{aquarium_id, config, video_path}`)
- `ZONE_AQUARIUM_COUNT_CONFIRMED` - Count confirmed (payload: `{count: int}`)
- `ZONE_AQUARIUM_ASSIGNMENT_COMPLETED` - Assignment done (payload: `{configs, apply_to_all}`)
- `ZONE_SHOW_AQUARIUM_COUNT_DIALOG` / `ZONE_SHOW_AQUARIUM_ASSIGNMENT_DIALOG` - Dialog requests

**Event Handlers** (Phase 5):
- `ProcessingCoordinator._handle_multi_auto_detect()` - Handles ZONE_MULTI_AUTO_DETECT
- `ProjectLifecycleCoordinator._handle_aquarium_config_updated()` - Handles ZONE_AQUARIUM_CONFIG_UPDATED

**UI Components**:
- `CanvasManager.create_side_by_side_preview()` - Side-by-side aquarium comparison
- `WizardService.validate_multi_aquarium_config()` - Returns (is_valid, errors, warnings)

**UI Dialogs** (in `ui/dialogs/`):
- `AquariumAssignmentDialog` - Assign groups/subjects to detected aquariums
- `MultiAquariumConfirmDialog` - Confirm detected aquarium count

**Pydantic Models** (in `ui/wizard/models.py`):
- `AquariumConfig`: `aquarium_id`, `group_name`, `subject_name`, `enabled`
- `MultiAquariumData`: `enabled`, `count`, `detection_method`, `configs`

**Testing**: 250+ tests in `tests/core/test_*_multi*.py`, `tests/ui/test_*_multi*.py`, `tests/integration/test_multi_aquarium_e2e.py`, `tests/analysis/test_trajectory_validator.py`

**ADR**: `docs/decisions/ADR-001-multi-aquarium-support.md`

## Common Patterns

### Logging (structlog)
```python
import structlog
logger = structlog.get_logger()
logger.info("controller.load_project.success", project_name=name)
logger.error("recorder.save_parquet.error", error=str(e))
```
**Pattern**: `domain.action.result`

### Detector Plugins
- Implement `DetectorPlugin` from `plugins/base.py`
- Register in `plugins/__init__.py` (`DETECTOR_PLUGINS` dict)
- Handle missing `track_id` gracefully: `detection.get("track_id", -1)`

### ROI Templates
- Save/load via `ProjectService` (stored in `templates/`)
- Geometry helpers: `utils/geometry.py`

### Analysis Intervals
- `analysis_interval_frames`: Detection frequency (default: 10)
- `display_interval_frames`: UI overlay frequency (default: 10)
- Persist via `ProjectManager.save_project()`

## Key File Locations

### Entry Points & Core
- `src/zebtrack/__main__.py` - CLI/GUI entry, DI wiring (lines 140-280)
- `core/main_view_model.py` - Application orchestrator (`start_live_camera_analysis()` at line 2588)
- `core/state_manager.py` - Centralized state (v1.8+)
- `core/{project_service,wizard_service,live_camera_service,recording_service}.py` - Service layer
- `core/detector.py` - AI model + zone logic

### I/O & Processing
- `io/{recorder,video_source,camera,live_stream_source,frame_source_factory}.py` - Persistence, frame sources
- `analysis/{analysis_service,behavior,roi,reporter}.py` - Metrics, reports
- `plugins/` - Detector implementations (YOLO, OpenVINO)

### UI
- `ui/gui.py` - Main window (10759 lines after dialog extraction)
- `ui/dialogs/` - Dialog classes (14 dialogs including `LiveAnalysisDialog`, `LivePreviewWindow`)
- `ui/wizard/` - 5-step project wizard
- `ui/wizard/models.py` - Pydantic validation models (v2.0)

### Configuration & Settings
- `settings.py` - Pydantic configuration models
- `config.yaml` - Default settings
- `config.local.yaml` - Local overrides (git-ignored)

### Output Structure (per video)
```
<video>_results/
  1_ArenaROI_<video>.parquet          # Arena/ROI definitions
  2_Zones_<video>.parquet             # Zone metadata
  3_CoordMovimento_<video>.parquet    # Trajectory (immutable schema)
  <video>_summary.xlsx                # Metrics per ROI
  <video>_report.docx                 # Word report with plots
```

## Testing Requirements

- **Coverage**: 70% minimum (enforced)
- **Markers**: `@pytest.mark.{gui,slow,integration,unit}`
- **Fixtures**: `tests/conftest.py`
- **Current Status**: 712 passing, 1 skipped

### Pre-Merge Checklist
1. ✅ Read relevant test files before modifying
2. ✅ `poetry run pytest -q` (all pass)
3. ✅ `poetry run ruff check .` (no errors)
4. ✅ Update docs if user-facing changes
5. ✅ Verify no wizard regressions

## Hardware Integration

- **Arduino**: Optional, via `arduino.port` setting
  - Zone-based commands: `enter_commands`, `exit_commands`
  - Graceful degradation without hardware
- **Camera**: `camera.index` in `config.local.yaml` (machine-specific)
- **OpenVINO**: Model cache in `openvino_model_cache/`

## Performance Settings

- `performance.max_parallel_videos`: 2 (default)
- `performance.max_parallel_plots`: 3 (default)
- `performance.parquet_compression`: "snappy" (default)
- `performance.enable_parallel_analysis`: true (default)

**Full Guide**: `docs/PERFORMANCE_TUNING.md`

## Important Notes

- **Language**: Portuguese (code/comments), English (docs unless matching existing)
- **Line Length**: 100 chars (Ruff)
- **Python**: ≥3.12 required
- **setuptools**: Pinned <81 (docxcompose dependency)
- **EventBus**: Opt-in (`ui_features.enable_event_queue: false` by default)

## Version History (Quick Reference)

- **v3.0 (Jan 2025)**: 🔴 **BREAKING** - Removed all legacy thread system code for Live cameras (~90 lines)
- **v2.1 (Jan 2025)**: Live Camera Unification - Fixed critical bugs (camera selection, intervals, preview)
- **v2.0 (Nov 2025)**: ⚠️ **CRITICAL PYTEST FIXES** - Resolved system-freezing test hangs, daemon threads, Tkinter cleanup hooks
- **v1.9 (Oct 2025)**: WizardService, dialog extraction, hardware caching, E2E tests, LiveCameraService
- **v1.8**: StateManager (observable, thread-safe)
- **v1.7**: Pydantic v2 settings, in-app config editor
- **v1.6**: 5-step wizard flow
- **v1.x**: ROI templates, track overlays, social proximity

## Quick Navigation

| Task | Document |
|------|----------|
| **Quick Reference** | `docs/guides/developer/CHEATSHEET.md`, `docs/guides/developer/QUICK_DEBUG_GUIDE.md` |
| **Architecture** | `docs/architecture/ARCHITECTURE.md` |
| **Wizard Development** | `docs/guides/developer/DEVELOPER_GUIDE_WIZARD.md` |
| **Testing** | `README_TESTS.md` |
| **Operational Guide** | `docs/reference/REFERENCE_GUIDE.md` |
| **Coordinates** | `docs/reference/COORDINATE_SYSTEMS.md` |
| **State Management** | `docs/architecture/STATE_MANAGEMENT_GUIDE.md` |
| **DI Patterns** | `docs/architecture/DEPENDENCY_INJECTION_GUIDE.md` |
| **Workflows** | `docs/guides/developer/WORKFLOWS.md` |
| **Performance** | `docs/performance/PERFORMANCE_TUNING.md` |
| **Known Issues** | `docs/reference/KNOWN_ISSUES.md` |
| **Historical Context** | `docs/archive/` |

## 📋 Documentation Standards

When creating or updating documentation, follow these rules to maintain organization:

### Folder Structure (MANDATORY)

| Folder | Purpose | Naming Convention |
|--------|---------|-------------------|
| `docs/architecture/` | System design, patterns, DI, events | `TOPIC.md` |
| `docs/guides/developer/` | Developer workflows, debugging, features | `GUIDE_TOPIC.md` or `TOPIC.md` |
| `docs/guides/user/` | End-user docs (English) | `TOPIC.md` |
| `docs/reference/` | API docs, operational reference | `TOPIC.md` or `topic_api.md` |
| `docs/performance/` | Benchmarks, optimization, threading | `TOPIC.md` |
| `docs/testing/` | Test patterns, pytest fixes | `TESTING_TOPIC.md` |
| `docs/decisions/` | Architecture Decision Records | `ADR-NNN-short-title.md` |
| `docs/migration/` | Version upgrade guides | `vX.Y-to-vX.Z.md` |
| `docs/wiki/` | User guides (Portuguese) | Numbered: `N_Title.md` |
| `docs/archive/` | Historical/completed docs | Move here, don't delete |

### Documentation Rules

1. **NEVER create docs in `docs/` root** - Use appropriate subfolder
2. **English for technical docs** - Portuguese only in `wiki/`
3. **Line length 100 chars** - Match Ruff standard
4. **Relative links** - Use `../` paths, not absolute
5. **Update INDEX.md** - When adding new docs
6. **Archive, don't delete** - Move obsolete docs to `docs/archive/`

### When to Update Docs

- **New feature**: Add to `guides/developer/` + update INDEX.md
- **API change**: Update `reference/` + `architecture/SYSTEM_INTEGRATION_MAP.md`
- **Bug fix with lessons**: Add to `docs/archive/fixes/` if significant
- **Architecture change**: Update `architecture/` docs
- **Performance change**: Update `performance/` docs

### ADR Format (for `docs/decisions/`)

```markdown
# ADR-NNN: Title

## Status
Accepted | Proposed | Deprecated

## Context
What is the issue?

## Decision
What was decided?

## Consequences
What are the results?
```

## Development Workflow

1. **Before Coding**: Read relevant files in `docs/` and existing tests
2. **Coding**: Follow DI patterns, use `structlog`, inject `settings_obj`
3. **Testing**: Write tests before/during implementation, run `pytest -q`
4. **Quality**: `ruff check --fix .`, run pre-commit
5. **Documentation**: Update relevant docs in `docs/` if user-facing
6. **System Map**: Update `docs/SYSTEM_INTEGRATION_MAP.md` immediately if changing events, payloads, or cross-component logic.
7. **Commit**: Clear message, reference issue if applicable

**For detailed workflows**: `docs/WORKFLOWS.md`
