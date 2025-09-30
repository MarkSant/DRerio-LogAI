## ZebTrack-AI – Copilot Coding Agent Guide

Purpose: Desktop Tkinter application for multi-animal tracking (live or prerecorded video) that produces trajectories (Parquet), behavioral/ROI metrics (Excel), and rich per-experiment reports (Word, Excel, CSV). Optimize for small, well-tested changes that keep schemas and UI workflows stable.

### Quick Start Workflow

1. Launch GUI: `python -m zebtrack` (entry point `core/controller.AppController`).
2. Create/select a project via `core/project_manager.py`.
3. Choose a detector plugin from `plugins/` (registry in `plugins/__init__.py`).
4. Configure arenas/zones and optional pixel-per-cm calibration through `core/calibration.py`.
5. Frames arrive from `io/video_source.py`; detections flow through `core/detector.py` (zone state machine + optional Arduino commands).
6. Results stream to `io/recorder.py` (Parquet + optional MP4).
7. Analysis happens in `analysis/behavioral_analyzer.py`, `analysis/behavior.py`, and `analysis/roi.py`.
8. Reports are generated via `analysis/reporter.py`.

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

### Analysis Progress & Intervals

- Progress callbacks now supply granular stats (`total_frames`, `processed_frames`, `detected_frames`, `start_time`); keep `ApplicationGUI.update_processing_stats()` and overlay labels in sync.
- `ApplicationGUI` handles dual views (zone drawing vs. analysis overlay). Preserve detector-drawn overlays by routing frames through `display_analysis_frame()` without redrawing zones.
- Interval controls (`analysis_interval_var`, `display_interval_var`) exist on both project and single-video dialogs; keep defaults at `10` unless project data overrides them and update the respective tests if behavior changes.
- When adjusting controller workflows, ensure `progress_callback` continues scheduling UI updates via `root.after(0, ...)` to avoid blocking Tkinter.

### Behavioral & ROI Analysis

- Behavioral metrics live in `analysis/behavior.py`; orchestration in `analysis/behavioral_analyzer.py`.
- ROI logic is in `analysis/roi.py`. Supported inclusion rules: `centroid_in`, `centroid_in_on_buffered_roi`, `bbox_intersects` (default), `seg_overlap`.
- Reporting is centralized in `analysis/reporter.py`. Adding a metric requires wiring it through analyzer → reporter and creating a synthetic trajectory test under `tests/analysis/`.

### Calibration & Units

- Pixel-to-centimeter calibration comes from `core/calibration.py`.
- `io/recorder` only appends cm columns when calibration is known. Downstream consumers must gracefully fall back to pixel coordinates if cm columns are absent.

### Testing & Validation

- Run the full test suite with `poetry run pytest -q`.
- Tests mirror modules; consult them before modifying behavior (e.g., `tests/test_detector.py`, `tests/test_recorder.py`).
- After feature changes, update or add tests covering the new behavior. For schema updates, assert new columns/fields explicitly.
- UI/analysis workflows now have dedicated coverage: `tests/test_overlay_integration.py` (overlay preservation) and `tests/test_interval_frames_config.py` (interval dialogs + persistence). Keep them passing.

### Safety Checklist Before Merging

- Read the relevant test file(s) tied to the module you're editing.
- Keep GUI responsive—avoid blocking calls on the main thread.
- Ensure zone definitions are rescaled to match the actual capture size via `Detector.set_zones(...)` after dimensions are known.
- Handle empty detection batches without creating output artifacts.
- Guard for missing settings/configuration and absent hardware (e.g., Arduino).

### Repository Landmarks

- `src/zebtrack/core/controller.py`: Application workflow hub.
- `src/zebtrack/core/detector.py`: Zone management and detection state machine.
- `src/zebtrack/io/recorder.py`: Parquet/MP4 writers.
- `src/zebtrack/plugins/`: Detector implementations.
- `src/zebtrack/analysis/`: Behavioral metrics, ROI analysis, reporting.
- `src/zebtrack/settings.py`: Pydantic settings models.
- `tests/`: Pytest suite (unit, integration, GUI regression tests).

### When in Doubt

- Prefer reading the closest test to understand expectations.
- Keep public APIs, file schemas, and user-visible naming stable.
- Document recurring patterns here only after confirming they are covered by tests.
