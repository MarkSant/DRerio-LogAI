## ZebTrack-AI – Copilot Coding Agent Guide

Purpose: Desktop Tkinter application for multi-animal tracking (live or prerecorded video) that produces trajectories (Parquet), behavioral/ROI metrics (Excel), and rich per-experiment reports (Word, Excel, CSV). Optimize for small, well-tested changes that keep schemas and UI workflows stable.

### Quick Start Workflow

1. Launch GUI: `python -m zebtrack` (entry point `core/controller.MainViewModel`, aliased as `AppController` for backward compatibility).
2. Use the project wizard (`ui/wizard`) to create/select a project; the legacy dialog remains available only for backwards compatibility hooks in `core/project_manager.py`.
3. Choose a detector plugin from `plugins/` (registry in `plugins/__init__.py`).
4. Configure arenas/zones and optional pixel-per-cm calibration through `core/calibration.py`.
5. Frames arrive from `io/video_source.py`; detections flow through `core/detector.py` (zone state machine + optional Arduino commands).
6. Results stream to `io/recorder.py` (Parquet + optional MP4).
7. Project file I/O operations (save/load config, ROI templates, metadata) are handled by `core/project_service.py`.
8. Analysis orchestration happens in `analysis/analysis_service.py`, which coordinates `analysis/behavior.py` and `analysis/roi.py`.
9. Reports are generated via `analysis/reporter.py`.

### Environment & Tooling

- Python is managed with Poetry (`pyproject.toml`). Install dependencies with `poetry install`.
- Run the app/tests inside the Poetry shell or via `poetry run ...`.
- Windows default shell is PowerShell; commands here assume that environment.
- Use `structlog` for logging (`structlog.get_logger()`), maintaining the `domain.action.result` naming convention.

### Configuration Contract

- Settings load order: `config.yaml` → optional `config.local.yaml` (merged in `settings.load_settings()`).
- Never hardcode configuration values; import `from zebtrack import settings`.
- When adding a configuration field: update the Pydantic models in `settings.py`, adjust `config.yaml`, and extend `tests/test_settings.py`.
- Per-project runtime overrides (`analysis_interval_frames`, `display_interval_frames`, etc.) live in `ProjectManager.project_data`; persist them via `ProjectManager.save_project()` so the GUI can restore interval widgets on reload.

### Data & File Schemas

- Recorder Parquet column order is strict: `timestamp, frame, track_id, x1, y1, x2, y2, confidence`. Optional columns appended only when calibration is available: `x_center_px, y_center_px, x_cm, y_cm`.
- Maintain zone metadata structure: `polygon`, `squares` (list of ((x1, y1), (x2, y2))), `bgr_color`, `enter_commands`, `exit_commands`.
- Output naming prefixes `1_`, `2_`, `3_` are user-facing and must remain unchanged.

### Detector & Plugin Guardrails

- Plugins implement `DetectorPlugin` (`plugins/base.py`) and expose `get_name()`.
- Register new plugins in `plugins/__init__.py` (`DETECTOR_PLUGINS`).
- Handle missing `track_id` values gracefully.
- Keep inference non-blocking; heavy work belongs in detector threads, not the GUI loop.
- OpenVINO weights require matching `.xml`/`.bin`; conversion is handled in `core/weight_manager.py`.
- Arena inclusion uses the "4 corners OR center" logic via `_is_inside_polygon`; use `bbox_hits_roi_polygon` for ROI checks when appropriate.

### Project Creation Wizard

- The wizard is now the default path (v1.6+). The `settings.ui_features.use_wizard_for_project_creation` flag is retained for legacy scenarios but should remain enabled for parity with current UI flows.
- Wizard flow lives under `src/zebtrack/ui/wizard/` (steps, dialog, adapter). It feeds controller inputs through `wizard_adapter.adapt_wizard_data_to_controller_format()` to preserve backward compatibility.
- **v1.7+ UI Architecture**: The wizard dialog (`wizard_dialog.py`) uses a wide fixed-size window (1150×550px) designed for 3-column horizontal layouts. Discovery Step has all 3 questions side-by-side with compact spacing (padding 8-10px, column gaps 3px). Reserves 220px vertical space to ensure navigation buttons are never hidden by taskbar. Resizable 75%-120% width, 75%-110% height. Design steps with 3-column horizontal layouts - do NOT stack content vertically or create content that pushes buttons off-screen.
- **Scrollbar Factory**: Wizard steps that need internal scrollbars (e.g., file lists) must use `window_utils.create_scrollbar()` instead of direct `ttk.Scrollbar()` to handle ttkbootstrap Style singleton teardown gracefully in tests.
- Maintain parity with the legacy dialogs: every wizard change must still populate `ProjectManager.project_data` fields expected elsewhere (intervals, batches, calibration defaults).
- Update wizard-specific tests when modifying the flow or adapter logic: `tests/test_wizard_adapter.py`, `tests/test_wizard_confirmation.py`, `tests/test_wizard_integration.py`, related step tests, and the controller regression `tests/test_controller.py::TestAppController::test_open_project_workflow_success_loads_view_and_zones` when project-loading side effects change.
- Manual wizard scenarios now reside in `test_scenarios/` (documentation) and `tests/manual/`; legacy generator scripts were removed.

### Analysis Progress & Intervals

- Progress callbacks now supply granular stats (`total_frames`, `processed_frames`, `detected_frames`, `start_time`); keep `ApplicationGUI.update_processing_stats()` and overlay labels in sync.
- `ApplicationGUI` handles dual views (zone drawing vs. analysis overlay). Preserve detector-drawn overlays by routing frames through `display_analysis_frame()` without redrawing zones.
- Interval controls (`analysis_interval_var`, `display_interval_var`) exist on both project and single-video dialogs; keep defaults at `10` unless project data overrides them and update the respective tests if behavior changes.
- When adjusting controller workflows, ensure `progress_callback` continues scheduling UI updates via `root.after(0, ...)` to avoid blocking Tkinter.

### Behavioral & ROI Analysis

- Behavioral metrics live in `analysis/behavior.py`; orchestration in `analysis/analysis_service.py`.
- ROI logic is in `analysis/roi.py`. Supported inclusion rules: `centroid_in`, `centroid_in_on_buffered_roi`, `bbox_intersects` (default), `seg_overlap`.
- Reporting is centralized in `analysis/reporter.py`. Adding a metric requires wiring it through analyzer → reporter and creating a synthetic trajectory test under `tests/analysis/`.

### Calibration & Units

- Pixel-to-centimeter calibration comes from `core/calibration.py`.
- `io/recorder` only appends cm columns when calibration is known. Downstream consumers must gracefully fall back to pixel coordinates if cm columns are absent.

### Testing & Validation

- Run the full test suite with `poetry run pytest -q`.
- Run Ruff style checks with `poetry run ruff check` before handing off changes.
- Tests mirror modules; consult them before modifying behavior (e.g., `tests/test_detector.py`, `tests/test_recorder.py`).
- After feature changes, update or add tests covering the new behavior. For schema updates, assert new columns/fields explicitly.
- UI/analysis workflows now have dedicated coverage: `tests/test_overlay_integration.py` (overlay preservation) and `tests/test_interval_frames_config.py` (interval dialogs + persistence). Keep them passing.
- For wizard-related work, run the focused suite: `poetry run pytest tests/test_wizard*.py -q`.
- Manual inspection scripts live under `tests/manual/`; the legacy Wizard scenario generators were removed, so reproduce edge cases via current pytest fixtures or these manual helpers.

### Safety Checklist Before Merging

- Read the relevant test file(s) tied to the module you're editing.
- Keep GUI responsive—avoid blocking calls on the main thread.
- Ensure zone definitions are rescaled to match the actual capture size via `Detector.set_zones(...)` after dimensions are known.
- Handle empty detection batches without creating output artifacts.
- Guard for missing settings/configuration and absent hardware (e.g., Arduino).

### Recent Features (v1.7+)

- **Advanced Configuration Tab** (`gui.py::_create_configuration_tab()`): In-app editor for `config.local.yaml` with live Pydantic validation, tooltips, and load/save/reset handlers. See `REFERENCE_GUIDE.md` for user docs.
- **ROI Template System** (`gui.py` + `project_manager.py`): Save/import/apply ROI designs across projects via combobox selector. Templates persist in `templates/` folder. Geometry helpers in `utils/geometry.py` support centroid-aware snapping. Tests in `test_project_manager.py::test_save_roi_template_*`.
- **Track-Specific Overlays** (`gui.py::update_detection_overlay()`): Analysis view now supports profile labels, track selector comboboxes, and social proximity percentage display. Covered by `test_overlay_integration.py` and `test_analysis_view_toggle.py`.
- **Event Bus (Opt-in)** (`ui/event_bus.py`): Optional controller→GUI decoupling via `UIFeatureFlags.enable_event_queue` (default: False). Still in staged migration—continue using `root.after` for UI updates.
- **Window Utilities** (`ui/window_utils.py`): Centralized helpers for window maximization and `create_scrollbar()` factory that handles ttkbootstrap Style singleton teardown gracefully.

### Repository Landmarks

- `src/zebtrack/core/controller.py`: MainViewModel (renamed from AppController) - UI-facing state and command handlers. Backward-compatible alias exists.
- `src/zebtrack/core/project_service.py`: Service layer for project file I/O (create, load, save, ROI templates, metadata).
- `src/zebtrack/core/project_manager.py`: In-memory project state management, zone/video tracking.
- `src/zebtrack/core/detector.py`: Zone management and detection state machine.
- `src/zebtrack/io/recorder.py`: Parquet/MP4 writers.
- `src/zebtrack/plugins/`: Detector implementations.
- `src/zebtrack/analysis/analysis_service.py`: Service layer for analysis orchestration (BehavioralAnalyzer + ROIAnalyzer + Reporter).
- `src/zebtrack/analysis/`: Behavioral metrics, ROI analysis, reporting.
- `src/zebtrack/settings.py`: Pydantic settings models + feature flags.
- `src/zebtrack/utils/geometry.py`: Geometry helpers including centroid-aware snapping.
- `tests/`: Pytest suite (unit, integration, GUI regression tests).
- `src/zebtrack/ui/gui.py`: Main application GUI with config editor, ROI templates, track overlays.
- `src/zebtrack/ui/wizard/`: Wizard dialog, step implementations, and adapter.
- `src/zebtrack/ui/window_utils.py`: Window management and scrollbar factory.
- `src/zebtrack/ui/event_bus.py`: Optional event bus (staged migration).

### When in Doubt

- Prefer reading the closest test to understand expectations.
- Keep public APIs, file schemas, and user-visible naming stable.
- Update README/CONTRIBUTING/docs when changing user-facing workflows.
- Document recurring patterns here only after confirming they are covered by tests.
