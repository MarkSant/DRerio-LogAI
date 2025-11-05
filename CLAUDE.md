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

# Testing (fast by default, 712 tests)
poetry run pytest                 # Fast tests only (excludes GUI/slow)
poetry run pytest -m gui -n0      # GUI tests (sequential)
poetry run pytest -m slow         # Slow tests only
poetry run pytest -m "" -n0       # All tests

# Code Quality
poetry run ruff check .           # Lint
poetry run ruff check --fix .     # Auto-fix
poetry run pre-commit run --all-files  # Full pre-commit
```

**Detailed Guides**:
- `docs/CHEATSHEET.md` - Quick developer reference
- `README_TESTS.md` - Complete testing guide

## Architecture (MVVM-S + DI)

### Composition Root
- **`__main__.py`** (lines 140-280): All dependencies wired here
- Never use global settings: always `load_settings()` then inject `settings_obj`

### Core Layers
| Layer | Key Files | Purpose |
|-------|-----------|---------|
| **Model** | `core/{state_manager,project_manager,detector_service}.py` | State, project data, detection |
| **View** | `ui/gui.py`, `ui/wizard/*.py`, `ui/dialogs/*.py` | Tkinter UI (10759 lines gui.py) |
| **ViewModel** | `core/main_view_model.py` | Orchestrator (11+ injected deps) |
| **Services** | `core/{wizard_service,video_processing_service,live_camera_service,recording_service}.py` | Business logic |
| **I/O** | `io/{recorder,video_source,camera,live_stream_source}.py` | Persistence, frame sources |
| **Analysis** | `analysis/{analysis_service,behavior,roi,reporter}.py` | Behavioral metrics, reports |

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

**Full Details**: `docs/WIZARD_LIVE_IMPROVEMENTS.md`, `docs/archive/LIVE_*.md` (historical context)

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

- **v2.0 (Oct 2025)**: WizardService, dialog extraction, hardware caching, E2E tests
- **v1.8**: StateManager (observable, thread-safe)
- **v1.7**: Pydantic v2 settings, in-app config editor
- **v1.6**: 5-step wizard flow
- **v1.x**: ROI templates, track overlays, social proximity

## Quick Navigation

| Task | Document |
|------|----------|
| **Quick Reference** | `docs/CHEATSHEET.md`, `docs/QUICK_DEBUG_GUIDE.md` |
| **Architecture** | `docs/ARCHITECTURE.md` |
| **Wizard Development** | `docs/DEVELOPER_GUIDE_WIZARD.md` |
| **Testing** | `README_TESTS.md` |
| **Operational Guide** | `docs/REFERENCE_GUIDE.md` |
| **Coordinates** | `docs/COORDINATE_SYSTEMS.md` |
| **State Management** | `docs/STATE_MANAGER_GUIDE.md` |
| **DI Patterns** | `docs/DEPENDENCY_INJECTION_GUIDE.md` |
| **Workflows** | `docs/WORKFLOWS.md` |
| **Performance** | `docs/PERFORMANCE_TUNING.md` |
| **Known Issues** | `docs/KNOWN_ISSUES.md` |
| **Historical Context** | `docs/archive/` |

## Development Workflow

1. **Before Coding**: Read relevant files in `docs/` and existing tests
2. **Coding**: Follow DI patterns, use `structlog`, inject `settings_obj`
3. **Testing**: Write tests before/during implementation, run `pytest -q`
4. **Quality**: `ruff check --fix .`, run pre-commit
5. **Documentation**: Update relevant docs in `docs/` if user-facing
6. **Commit**: Clear message, reference issue if applicable

**For detailed workflows**: `docs/WORKFLOWS.md`
