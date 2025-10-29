# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

**DRerio LogAI** (internally packaged as `zebtrack`) is a desktop Tkinter application for multi-animal behavioral tracking and analysis in *Danio rerio* (zebrafish) research. It automates video tracking (live/recorded), behavioral analysis, and scientific report generation using YOLO/OpenVINO models. The codebase follows an MVVM-like architecture with a component-based UI system.

**Note on Naming**: The product name is "DRerio LogAI", but the internal Python package remains `zebtrack` for compatibility. See `TRANSITION_NOTE.md` for full context.

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

### MVVM Pattern with Component-Based UI

The application uses a **Model-View-ViewModel (MVVM)** architecture with reactive state management:

- **Model Layer** (`zebtrack.core`, `zebtrack.analysis`):
  - `StateManager`: Centralized, thread-safe state with observable pattern (single source of truth)
  - `ProjectService`: Project file I/O (create, load, save, templates)
  - `AnalysisService`: Orchestrates behavioral analysis and reporting
  - `ProjectManager`: In-memory project state (videos, zones, intervals)
  - `Detector`: AI model abstraction with zone state machine
  - `Recorder`: Parquet/MP4 persistence with immutable schema

- **View Layer** (`zebtrack.ui`):
  - `ApplicationGUI`: Main window container that mounts UI components
  - Component-based widgets (e.g., `VideoDisplayWidget`, `ZoneControlsWidget`) emit events via `EventBus`
  - `WizardDialog`: 5-step project creation wizard (default since v1.6)

- **ViewModel Layer** (`zebtrack.core.main_view_model`):
  - `MainViewModel`: Orchestrates application flow, subscribes to `EventBus` events, updates `StateManager`
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

## Recent Major Features (v2.0 - Phase 4, October 2025)

### Wizard Live Improvements
Complete overhaul of live project wizard with enhanced UX and device management. See `docs/WIZARD_LIVE_IMPROVEMENTS.md` for full documentation.

**Key Components**:
- **NumberInput widget**: Direct input with +/- buttons
  - Location: `ui/wizard/experimental_design_step.py:24-118`
  - Usage: Days (1-30), groups (1-6), animals/group (1-20)
  - Features: Auto-validation, clamp, visual feedback

- **CollapsibleFrame widget**: Reusable expandable sections
  - Location: `ui/collapsible_frame.py` (102 lines)
  - API: `get_content_frame()` returns internal frame
  - Used in: `CalibrationDialog` (gui.py:298-320)
  - Features: Click-to-toggle, hover highlight, ▼/▶ indicator

- **Arduino Improvements**:
  - Port descriptions: "COM3 - Arduino Uno" display
  - Test button: `🔌 Testar` validates serial connection
  - Recheck: Dashboard button to update port post-creation
  - Locations: `ui/wizard/live_config_step.py:175-202,567-628` + `ui/gui.py:4885-5004`

- **Camera Detection**:
  - OpenCV log suppression via context manager
  - Early stopping after 3 consecutive failures
  - DirectShow backend on Windows for reliability
  - Location: `ui/wizard/live_config_step.py:487-566`

- **Template Persistence**:
  - Experimental design fields now saved in templates
  - Fields: `experiment_days`, `num_groups`, `subjects_per_group`, `group_names`
  - Location: `ui/wizard/templates.py:100-104`

**UI/UX Refinements**:
- Treeview color harmonization (green/yellow/red consistency)
- CustomRegexDialog interactive examples (📚 4 common patterns)
- ConfirmationStep: Canvas → Text widget (-40% code, +30% space)
- ModelSelectionStep: Grid → PanedWindow (resizable 60/40 split)

**Testing**: 688 tests passing, 0 regressions, backward-compatible

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
- `src/zebtrack/core/detector.py`: AI model abstraction + zone logic
- `src/zebtrack/io/recorder.py`: Parquet/MP4 writers
- `src/zebtrack/analysis/analysis_service.py`: Analysis orchestration
- `src/zebtrack/analysis/behavior.py`: Behavioral metrics
- `src/zebtrack/analysis/roi.py`: ROI analysis logic
- `src/zebtrack/analysis/reporter.py`: Multi-format report generation
- `src/zebtrack/ui/gui.py`: Main application window
- `src/zebtrack/ui/wizard/`: Project creation wizard
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
- Minimum coverage: 70% (enforced by pytest)
- Use fixtures from `tests/conftest.py`
- Mock Tkinter components when testing controllers/services
- Edge cases documented in `test_scenarios/`

Pre-merge checklist:
1. Read relevant test files before modifying modules
2. Run `poetry run pytest -q` (all tests pass)
3. Run `poetry run ruff check .` (no linting errors)
4. Update docs if changing user-facing workflows (README, ARCHITECTURE.md, wiki)

## Recent Major Features

- **StateManager (v1.8+)**: Observable pattern, thread-safe, centralized state. See `docs/STATE_MANAGER_GUIDE.md`
- **Enhanced Settings (v1.7+)**: Pydantic v2 with strict validation, in-app config editor
- **ROI Template System**: Reusable zone definitions across projects
- **Track-Specific Overlays**: Per-track display with social proximity metrics
- **Wizard Flow (v1.6+)**: 5-step guided project creation with auto-detection of experimental design

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
