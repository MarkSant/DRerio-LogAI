# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

**DRerio LogAI** (internally packaged as `zebtrack`) is a desktop Tkinter application for multi-animal behavioral tracking and analysis in *Danio rerio* (zebrafish) research. It automates video tracking (live/recorded), behavioral analysis, and scientific report generation using YOLO/OpenVINO models. The codebase follows an **MVVM-S architecture with Dependency Injection (DI)**, where `__main__.py` acts as the Composition Root.

**Note on Naming**: The product name is "DRerio LogAI", but the internal Python package remains `zebtrack` for compatibility.

## Essential Commands

### Environment Setup
```powershell
# Install dependencies (first time)
poetry install

# Run the application
poetry run zebtrack

# Alternative entry point
poetry run python -m zebtrack
```

### Testing

**Important**: Tests are now organized with markers for better performance and cross-platform compatibility.

```powershell
# Run fast tests only (default - excludes GUI and slow tests)
poetry run pytest

# Run GUI tests (sequential, no parallelization)
poetry run pytest -m gui -n0

# Run slow tests
poetry run pytest -m slow

# Run all tests (fast + slow + GUI)
poetry run pytest -m "" -n0

# Run specific test modules
poetry run pytest tests/test_wizard_integration.py
poetry run pytest tests/test_overlay_integration.py

# Generate HTML coverage report
poetry run pytest --cov-report=html

# Run without coverage (faster)
poetry run pytest --no-cov
```

**Test Markers**:
- `@pytest.mark.gui`: Tkinter GUI tests (run sequentially, cross-platform)
- `@pytest.mark.slow`: Tests taking >1s (excluded by default)
- `@pytest.mark.integration`: Integration tests
- `@pytest.mark.unit`: Unit tests

See `README_TESTS.md` for complete testing guide.

### Code Quality
```powershell
# Run linting and formatting checks
poetry run ruff check .

# Auto-fix issues
poetry run ruff check --fix .

# Pre-commit hooks
poetry run pre-commit install        # Install hooks (once)
poetry run pre-commit run --all-files  # Run manually
```

### Development Utilities
```powershell
# Build shared templates
poetry run python scripts/build_templates.py

# Compile translations
poetry run python scripts/compile_translations.py
```

## Architecture

### MVVM-S Architecture with Dependency Injection

The application uses **MVVM-S** (Model-View-ViewModel-Service) with **Dependency Injection (DI)**:

- **Composition Root** (`src/zebtrack/__main__.py`):
  - All dependencies are instantiated and wired here (lines 140-280)
  - `Settings` loaded via `load_settings()` (never use global `from zebtrack.settings import settings`)
  - Services receive `settings_obj` parameter via constructor injection

- **Model Layer** (`zebtrack.core`, `zebtrack.analysis`):
  - `StateManager`: Centralized, thread-safe state with observable pattern (single source of truth)
  - `ProjectManager`: In-memory project state (videos, zones, intervals) - receives `settings_obj` via DI
  - `DetectorService`: Wraps plugin detectors with zone scaling - receives `settings_obj` via DI
  - `VideoProcessingService`: Background analysis - receives `settings_obj` via DI
  - `WeightManager`: Manages YOLO/OpenVINO weights - receives `settings_obj` via DI
  - `AnalysisService`: Orchestrates behavioral analysis - receives `settings_obj` via DI
  - `Recorder`: Parquet/MP4 persistence with immutable schema

- **View Layer** (`zebtrack.ui`):
  - `ApplicationGUI`: Main window container that mounts UI components
  - Component-based widgets (e.g., `VideoDisplayWidget`, `ZoneControlsWidget`) emit events via `EventBus`
  - `WizardDialog`: 5-step project creation wizard (default since v1.6)

- **ViewModel Layer** (`zebtrack.core.main_view_model`):
  - `MainViewModel`: Orchestrates application flow with 11+ injected dependencies
  - Subscribes to `EventBus` events, updates `StateManager`
  - Backward-compatible alias as `AppController`

### Key Data Flow

1. **User Interaction → Event → ViewModel → State Update → UI Refresh**:
   - UI components emit events to `EventBus` (e.g., `"recording.start_requested"`)
   - `MainViewModel` handles events, executes business logic, updates `StateManager`
   - `StateManager` notifies observers (UI) which update via `root.after()` to stay on main thread

2. **Processing Pipeline**:
   - Video frames from `io/video_source.py`
   - Detections through `core/detector.py` (zone state machine + optional Arduino commands)
   - Results stream to `io/recorder.py` (Parquet + optional MP4)
   - Analysis via `analysis/analysis_service.py` → `behavior.py`, `roi.py` → `reporter.py`

## Critical Constraints

### Parquet Schema (IMMUTABLE)
The output Parquet schema is **fixed** and must not be reordered:
```
timestamp, frame, track_id, x1, y1, x2, y2, confidence, [x_center_px, y_center_px, x_cm, y_cm]*
```
- Core columns are always present
- Calibration columns (`*_cm`) appended only when calibration exists
- Any schema changes require test updates in `tests/test_recorder.py`
- Column order defined in `io/recorder.py`

### Configuration System
- **Never hardcode values**: Always `from zebtrack import settings`
- Hierarchy: `config.yaml` (base) → `config.local.yaml` (overrides, git-ignored)
- All settings validated via Pydantic v2 models with `extra="forbid"`
- Per-project overrides stored in `ProjectManager.project_data`
- Changes to settings require updates to:
  - Pydantic models in `settings.py`
  - Default values in `config.yaml`
  - Tests in `tests/test_settings.py`

### Zone and Coordinate Systems
- Zones defined in reference coordinates (`camera.desired_width` × `camera.desired_height`)
- **Must call `Detector.set_zones()` after video dimensions are known** to rescale properly
- Arena inclusion uses "4 corners OR center" logic (`_is_inside_polygon`)
- ROI inclusion configurable: `centroid_in`, `centroid_in_on_buffered_roi`, `bbox_intersects`, `seg_overlap`

### Threading and UI Updates
- All UI updates **must** use `root.after(0, ...)` to stay on Tkinter main thread
- Heavy processing (detection, analysis) runs in worker threads
- `StateManager` is thread-safe for cross-thread state updates
- Progress callbacks provide granular stats: `total_frames`, `processed_frames`, `detected_frames`, `start_time`

### Project Wizard (Default Flow)
- 5-step wizard (`ui/wizard/`) is the primary project creation path since v1.6
- Layout: 1150×550px fixed window, 3-column horizontal layouts
- Steps must not push navigation buttons off-screen (reserves 220px vertical space)
- Uses `window_utils.create_scrollbar()` factory for ttkbootstrap compatibility
- Data flows through `wizard_adapter.adapt_wizard_data_to_controller_format()` for backward compatibility
- Legacy dialog remains for backward compatibility hooks only

## Recent Major Features (v2.0 - Phases 4 & 5, October 2025)

### Phase 4: Wizard Live Improvements & Service Layer
Complete overhaul of live project wizard with enhanced UX, service layer separation, and dialog modularization. See `docs/DEVELOPER_GUIDE_WIZARD.md` for full documentation.

**Service Layer Architecture**:
- **WizardService** (`core/wizard_service.py`): Business logic separated from UI
  - Hardware detection (cameras, Arduino ports)
  - Validation methods for all wizard steps
  - Cross-field validation logic
  - Helper calculation methods
  - **Performance**: Hardware detection caching (30s TTL) for 5x faster repeated calls
- **Pydantic Models** (`ui/wizard/models.py`): Type-safe data validation
  - `LiveConfigData`, `ExperimentalDesignData`, `CalibrationData`
  - Cross-field validators (e.g., external trigger requires Arduino)
  - Strict boundaries (days: 1-365, groups: 1-6, subjects: 1-20)

**UI Modularization**:
- **Dialog Extraction**: 13 dialog classes moved from `gui.py` to `ui/dialogs/`
  - `gui.py` reduced: 13473 → 10759 lines (~20% reduction)
  - Dialogs: CalibrationDialog, ManageWeightsDialog, ColorSelectionDialog, etc.
  - Circular dependency resolved with `ui/format_utils.py`
- **Component-Based Widgets**:
  - NumberInput widget with +/- buttons (`ui/wizard/experimental_design_step.py`)
  - CollapsibleFrame for expandable sections (`ui/collapsible_frame.py`)

**Hardware Detection Improvements**:
- **Camera Detection**:
  - OpenCV log suppression via context manager
  - Early stopping after 3 consecutive failures
  - DirectShow backend on Windows for reliability
  - **Caching**: Results cached for 30 seconds to avoid re-probing
- **Arduino Detection**:
  - Port descriptions: "COM3 - Arduino Uno" display
  - Test button: `🔌 Testar` validates serial connection
  - Recheck: Dashboard button to update port post-creation
  - **Caching**: Serial port scanning cached to reduce latency

**Template & UI/UX**:
- Experimental design fields now saved in templates
- Treeview color harmonization (green/yellow/red consistency)
- CustomRegexDialog interactive examples (📚 4 common patterns)
- ConfirmationStep: Canvas → Text widget (-40% code, +30% space)

### Phase 5: Testing & Performance
**E2E Tests** (`tests/ui/wizard/test_wizard_live_e2e.py`):
- 16 comprehensive integration tests for WizardService
- Validates Pydantic models, cross-field validation, service methods
- Tests all wizard data flows (LiveConfig, ExperimentalDesign, Calibration)

**Performance Optimizations**:
- Hardware detection caching (~5x faster on repeated calls)
- Independent caches for cameras and Arduino
- Configurable TTL (30 seconds default)
- Manual cache clearing via `WizardService.clear_hardware_cache()`

**Test Coverage** (`tests/test_wizard_service_caching.py`):
- 8 tests for caching behavior (cache hit/miss, TTL expiration, force refresh)
- Total: **712 tests passing**, 1 skipped, 0 regressions

---

## Common Patterns

### Logging
Uses `structlog` with `domain.action.result` convention:
```python
import structlog

logger = structlog.get_logger()
logger.info("controller.load_project.success", project_name=name)
logger.error("recorder.save_parquet.error", error=str(e))
```

### Detector Plugins
- Implement `DetectorPlugin` interface from `plugins/base.py`
- Register in `plugins/__init__.py` (`DETECTOR_PLUGINS` dict)
- Handle missing `track_id` values gracefully
- OpenVINO conversion handled by `core/weight_manager.py`

### ROI Templates
- Save/load via `ProjectService` (stored in `templates/` folder)
- Geometry helpers in `utils/geometry.py` for snapping/clamping
- Templates persist polygon definitions with colors and commands

### Analysis Intervals
- Two independent intervals:
  - `analysis_interval_frames`: How often to run detection (default: 10)
  - `display_interval_frames`: How often to update UI overlay (default: 10)
- Persist via `ProjectManager.save_project()` in `project_data`
- Tests: `tests/test_interval_frames_config.py`

## File Organization

Key entry points and modules:

- `src/zebtrack/__main__.py`: CLI/GUI entry point
- `src/zebtrack/core/main_view_model.py`: Application orchestrator
- `src/zebtrack/core/state_manager.py`: Centralized state (v1.8+)
- `src/zebtrack/core/project_service.py`: Project I/O service layer
- `src/zebtrack/core/wizard_service.py`: Wizard business logic with hardware detection caching (v2.0+)
- `src/zebtrack/core/detector.py`: AI model abstraction + zone logic
- `src/zebtrack/io/recorder.py`: Parquet/MP4 writers
- `src/zebtrack/analysis/analysis_service.py`: Analysis orchestration
- `src/zebtrack/analysis/behavior.py`: Behavioral metrics
- `src/zebtrack/analysis/roi.py`: ROI analysis logic
- `src/zebtrack/analysis/reporter.py`: Multi-format report generation
- `src/zebtrack/ui/gui.py`: Main application window (10759 lines after dialog extraction)
- `src/zebtrack/ui/dialogs/`: Dialog classes (extracted from gui.py in v2.0)
- `src/zebtrack/ui/wizard/`: Project creation wizard
- `src/zebtrack/ui/wizard/models.py`: Pydantic models for wizard data validation (v2.0+)
- `src/zebtrack/plugins/`: Detector implementations (YOLO, OpenVINO)
- `src/zebtrack/settings.py`: Pydantic configuration models

Output structure per video:
```
<video>_results/
  1_ArenaROI_<video>.parquet          # Arena/ROI definitions
  2_Zones_<video>.parquet             # Zone metadata
  3_CoordMovimento_<video>.parquet    # Trajectory data (immutable schema)
  <video>_summary.xlsx                # Metrics per ROI
  <video>_report.docx                 # Word report with plots
```

## Testing Requirements

- All public API changes require test coverage
- UI workflows covered by: `test_overlay_integration.py`, `test_interval_frames_config.py`, `test_wizard*.py`
- Wizard service layer: `test_wizard_live_e2e.py` (16 E2E tests), `test_wizard_service_caching.py` (8 caching tests)
- Minimum coverage: 70% (enforced by pytest)
- Use fixtures from `tests/conftest.py`
- Mock Tkinter components when testing controllers/services
- Edge cases documented in `test_scenarios/`
- **Current status**: 712 tests passing, 1 skipped (Tkinter environment issue)

Pre-merge checklist:
1. Read relevant test files before modifying modules
2. Run `poetry run pytest -q` (all tests pass)
3. Run `poetry run ruff check .` (no linting errors)
4. Update docs if changing user-facing workflows (README, ARCHITECTURE.md, wiki)
5. Verify no regressions in wizard flows after WizardService changes

## Major Features by Version

- **v2.0 (Oct 2025)**: WizardService layer, dialog extraction, Pydantic models, hardware caching, E2E tests (see Phases 4 & 5 above)
- **v1.8+**: StateManager - Observable pattern, thread-safe, centralized state. See `docs/STATE_MANAGER_GUIDE.md`
- **v1.7+**: Enhanced Settings - Pydantic v2 with strict validation, in-app config editor
- **v1.6+**: Wizard Flow - 5-step guided project creation with auto-detection of experimental design
- **v1.x**: ROI Template System, Track-Specific Overlays, social proximity metrics

## Hardware Integration

- Optional Arduino integration via `arduino.port` setting
- Zone-based command triggers (`enter_commands`, `exit_commands`)
- Application remains functional without hardware (graceful degradation)
- Camera index configurable via `camera.index` (use `config.local.yaml` for machine-specific settings)

## Performance Considerations

- Parallel video processing: `performance.max_parallel_videos` (default: 2)
- Parallel plotting: `performance.max_parallel_plots` (default: 3)
- Parquet compression: `performance.parquet_compression` (default: "snappy")
- Parallel analysis: `performance.enable_parallel_analysis` (default: true)
- OpenVINO model cache in `openvino_model_cache/` for faster startup

## Important Notes

- Project language: Portuguese (code/comments), but use English for new documentation unless matching existing style
- Ruff line length: 100 characters (not 88 as mentioned in README)
- Python version: ≥3.12 required
- setuptools pinned to <81 due to `docxcompose` dependency on deprecated `pkg_resources`
- Processing modes (calibration, diagnostic) force single-subject tracking
- EventBus is opt-in (`ui_features.enable_event_queue: false` by default) - migration in progress
