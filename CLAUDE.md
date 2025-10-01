# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ZebTrack-AI is a desktop Tkinter application for multi-animal tracking and behavioral analysis of aquatic organisms (primarily zebrafish). It combines computer vision models (YOLO/OpenVINO), real-time detection, trajectory recording (Parquet), behavioral metrics, and scientific report generation (Excel/Word/CSV).

## Commands

### Running the Application

```powershell
# Install dependencies
poetry install

# Launch GUI
poetry run zebtrack

# CLI help
poetry run python -m zebtrack --help
```

### Testing

```powershell
# Run full test suite
poetry run pytest -q

# Run specific test module
poetry run pytest tests/test_overlay_integration.py

# Run specific test class
poetry run pytest tests/test_interval_frames_config.py::TestIntervalFramesConfig
```

### Linting

```powershell
# Check code style with Ruff
poetry run ruff check .

# Auto-fix issues
poetry run ruff check . --fix
```

## Architecture

### Core Components

The application follows a **three-layer architecture**:

1. **UI Layer** (`zebtrack.ui.gui.ApplicationGUI`): Tkinter interface with dual-view canvas (zone drawing vs. analysis overlay)
2. **Orchestration Layer** (`zebtrack.core.controller.AppController`): Coordinates video processing, detection, recording, and analysis
3. **Analysis/IO Layer** (`zebtrack.analysis.*`, `zebtrack.io.*`): Behavioral metrics, ROI analysis, Parquet/MP4 recording, report generation

### Critical Flow: Video Processing

```
Controller → VideoSource → Detector (plugin) → Recorder (Parquet/MP4)
         ↓                                    ↓
         UI Updates (root.after)              BehavioralAnalyzer → Reporter
```

**Key architectural constraint**: All GUI updates MUST be scheduled via `root.after(0, lambda: ...)` to avoid blocking Tkinter's main thread.

### Detector Plugin System

New detection models implement `DetectorPlugin` interface (see `plugins/base.py`) and register in `plugins/__init__.py`. The system supports:
- YOLO (via Ultralytics)
- OpenVINO converted models (requires paired `.xml`/`.bin` files)

### Dual-View Canvas System

The GUI has two mutually exclusive canvas views:
- **Zones view** (`roi_canvas`): For drawing arenas and ROIs
- **Analysis view** (`analysis_overlay_frame`): Shows real-time detection frames + progress stats

The `overlay_progress_frame` must be packed **before** `analysis_video_label` to ensure progress bars and statistics remain visible at the bottom during analysis.

## Critical Implementation Details

### Parquet Schema (IMMUTABLE)

Column order in `io/recorder.py` is **fixed** and must not change:
```
timestamp, frame, track_id, x1, y1, x2, y2, confidence
```

Optional columns (only when calibration is available):
```
x_center_px, y_center_px, x_cm, y_cm
```

New columns can only be appended to the end and require test coverage.

### Progress Callback Contract

`progress_callback` in `controller.py` must provide:
- `progress_fraction` (0.0 to 1.0)
- `status_message` (str)
- `frame` (numpy array, optional)
- `stats` (dict with keys: `total_frames`, `processed_frames`, `detected_frames`, `start_time`)

Both `progress_labels` (zones view) and `overlay_progress_labels` (analysis view) must be updated simultaneously via `update_processing_stats()`.

### Zone Scaling

Zones are defined in pixel coordinates relative to video dimensions. Always call `Detector.set_zones(...)` **after** video dimensions are known to prevent ROI misalignment.

### Interval Persistence

`analysis_interval_frames` and `display_interval_frames` are:
- Stored in `ProjectManager.project_data`
- Persisted via `ProjectManager.save_project()`
- Restored when project is reopened

Default value is `10` for both intervals.

### ROI Inclusion Rules

Supported inclusion modes (configured per ROI in `config.yaml`):
- `bbox_intersects` (default): Bounding box intersects ROI polygon
- `centroid_in`: Object centroid is inside ROI
- `centroid_in_on_buffered_roi`: Centroid is inside buffered ROI
- `seg_overlap`: Segmentation mask overlaps ROI

## Configuration System

- Settings load from `config.yaml` (default) → `config.local.yaml` (optional override)
- Managed via Pydantic models in `settings.py`
- **Never hardcode values**: Always `from zebtrack import settings`
- Per-project runtime overrides are stored in `ProjectManager.project_data`

## Logging Convention

Use `structlog` with `domain.action.result` pattern:
```python
log.info("controller.load_project.success", project_path=path)
log.error("recorder.save_parquet.error", error=str(e))
```

## Testing Requirements

- All public API changes require test coverage
- Schema changes require explicit column/field assertions
- UI workflows have dedicated integration tests:
  - `tests/test_overlay_integration.py` (overlay preservation)
  - `tests/test_interval_frames_config.py` (interval dialogs + persistence)

## Common Pitfalls

1. **UI blocking**: Never call long-running operations directly from GUI callbacks. Use threads and `root.after()` for updates.

2. **Widget packing order**: In Tkinter, pack order determines layout. The `overlay_progress_frame` must be packed before `analysis_video_label` to stay visible.

3. **Lambda variable capture**: When scheduling callbacks with `root.after()`, capture variables explicitly:
   ```python
   # WRONG: stats dict reference may change
   root.after(0, lambda: update(stats.get('x')))

   # CORRECT: capture values at lambda creation time
   root.after(0, lambda x=stats.get('x'): update(x))
   ```

4. **Zone definition timing**: Set zones after video dimensions are known, not before.

5. **Missing hardware gracefully**: The app must work without Arduino or live cameras. Always check for hardware availability.

## Key Files

- `src/zebtrack/core/controller.py` - Main workflow orchestration, `_process_videos()`, `_run_tracking_if_needed()`
- `src/zebtrack/ui/gui.py` - Tkinter interface, dual-view canvas, progress overlay system
- `src/zebtrack/io/recorder.py` - Parquet/MP4 schema enforcement
- `src/zebtrack/analysis/behavioral_analyzer.py` - Behavioral metrics orchestration
- `src/zebtrack/analysis/reporter.py` - Excel/Word report generation
- `src/zebtrack/plugins/` - Detector implementations
- `src/zebtrack/settings.py` - Configuration models

## Additional Documentation

- `docs/ARCHITECTURE.md` - Detailed component diagrams and architectural decisions
- `CONTRIBUTING.md` - Development workflow and PR standards
- `.github/copilot-instructions.md` - Quick reference for coding agents
