## ZebTrack-AI – AI Contributor Guide (Concise)
Purpose: Desktop Tkinter app for multi‑animal tracking (live camera or batch video) → trajectories (Parquet), behavioral & ROI metrics (Excel), rich per‑experiment / project reports (Word, Excel, CSV). Keep changes minimal, schema‑safe, and test‑backed.

### 1. Core Flow (Typical Pre‑Recorded Run)
`python -m zebtrack` → GUI (`core/controller.AppController`) → project created (`core/project_manager.py`) → detector plugin chosen (`plugins/` via registry) → zones & calibration (optional pixel/cm via `core/calibration.py`) → frames from `io/video_source.py` → detections processed by `core/detector.py` (zone enter/exit state machine → optional Arduino commands) → rows streamed to `io/recorder.py` (Parquet + optional MP4) → analysis phase (`analysis/behavioral_analyzer.py`, `analysis/behavior.py`, `analysis/roi.py`) → reporting (`analysis/reporter.py`).

### 2. Configuration Contract
Load order: `config.yaml` then optional `config.local.yaml` merged in `settings.load_settings()` → singleton `settings`. NEVER hardcode config—import `from zebtrack import settings`. Adding a field: edit Pydantic models in `settings.py`, update `config.yaml`, extend `tests/test_settings.py`.

### 3. Critical Data Schemas
Recorder Parquet strict column order: `timestamp, frame, track_id, x1, y1, x2, y2, confidence` (+ `x_center_px, y_center_px, x_cm, y_cm` only if pixel_per_cm provided). Do NOT reorder; extend only by appending and update tests.
ZoneData (`core/detector.py`): polygon, squares list[((x1,y1),(x2,y2))], BGR colors, enter_commands, exit_commands. Always call `Detector.set_zones(zones, actual_w, actual_h)` after you know real capture size.
Output naming stages: user-visible prefixes `1_`, `2_`, `3_` must remain stable (tests + docs rely on them).

### 4. Detector / Plugin Rules
Plugins implement `DetectorPlugin` (see `plugins/base.py`) + `get_name()`. Register in `plugins/__init__.py: DETECTOR_PLUGINS`. Guard for missing track IDs (some models). Maintain non-blocking inference (no GUI thread stalls). OpenVINO path must contain paired `.xml` + `.bin`; conversion handled lazily by `core/weight_manager.py`.
Arena inclusion uses "4 corners OR center" logic (`_is_inside_polygon`). Helper `bbox_hits_roi_polygon` available for ROI checking.

### 5. Behavioral & ROI Analysis
Behavior metrics live in `analysis/behavior.py`; orchestration in `behavioral_analyzer.py`; ROI computations in `roi.py`; reporter aggregates & emits Excel/Docx (`reporter.py`). Adding a metric: implement function or extend analyzer, add to reporter export mapping, create synthetic trajectory test in `tests/analysis/`.
ROI analysis supports configurable inclusion rules: `centroid_in`, `centroid_in_on_buffered_roi`, `bbox_intersects` (default), `seg_overlap`. Settings: `roi_inclusion_rule`, `roi_buffer_radius_value`, `roi_min_bbox_overlap_ratio`.

### 6. Calibration & Units
Calibration (`core/calibration.py`) yields pixel_per_cm ratio; only then `recorder` appends `x_cm,y_cm`. Code consuming cm coords must tolerate absence (fallback to px if columns missing).

### 7. Logging & Events
Use `structlog.get_logger()` with pattern `domain.action.result` (e.g. `recorder.save_parquet.success`, `detector.setup.error`). Preserve existing event names where referenced in tests.

### 8. Safe Modification Checklist
Before change: locate corresponding test (mirrors module name). After change: run `poetry run pytest -q`. Adding dep: modify `[tool.poetry.dependencies]` then `poetry lock`. Never block the GUI loop (heavy work stays in worker threads / detector loop). Avoid silent schema drift—add test asserting new columns.

### 9. Edge / Failure Cases
Empty detection batches: recorder must no-op (don’t create Parquet prematurely). Missing settings or load failure: guard `settings is None`. Dimension mismatch: ALWAYS rescale zones. Optional Arduino: code must degrade gracefully if unavailable.

### 10. Quick File Landmarks
`core/controller.py` (workflow hub) | `core/detector.py` (zones + state) | `io/recorder.py` (Parquet/MP4 writer) | `plugins/` (detectors) | `analysis/*` (metrics + reporting) | `settings.py` (config models) | `tests/` (executable spec – read first when uncertain).

Unsure? Read the nearest test, mirror the pattern, keep output names & column order stable. When adding something new, document briefly in this file only if it becomes a repeated pattern.

End of concise guide – propose updates only after validating against tests.
