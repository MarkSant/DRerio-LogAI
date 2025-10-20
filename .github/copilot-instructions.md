# Copilot coding agent quick guide — ZebTrack-AI

Purpose: desktop Tkinter app (package: `zebtrack`) for multi-animal tracking, analysis and report generation (internally: DRerio LogAI).

Quick commands (Poetry):
- Install: `poetry install`
- Run app: `poetry run zebtrack` or `poetry run python -m zebtrack`
- Tests (fast): `poetry run pytest -q`
- Lint: `poetry run ruff check .` (auto-fix: `--fix`)

Essential architecture (read these first):
- Orchestrator / VM: `src/zebtrack/core/main_view_model.py` (MainViewModel / AppController alias)
- Central state: `src/zebtrack/core/state_manager.py` (v1.8+, observable, thread-safe)
- Detector pipeline: `src/zebtrack/core/detector.py`, `src/zebtrack/io/video_source.py`
- Persistence (immutable schema): `src/zebtrack/io/recorder.py` (+ `tests/test_recorder.py`)
- Analysis & reporting: `src/zebtrack/analysis/` (`analysis_service.py`, `behavior.py`, `roi.py`, `reporter.py`)
- UI & wizard: `src/zebtrack/ui/gui.py`, `src/zebtrack/ui/wizard/` (5-step default wizard)

Non-negotiable conventions (explicit):
- Parquet column order MUST stay: `timestamp, frame, track_id, x1, y1, x2, y2, confidence` (+ optional `x_center_px, y_center_px, x_cm, y_cm` when calibrated).
- Always import settings from the package: `from zebtrack import settings`. Settings use Pydantic v2 with `extra='forbid'`.
- Call `Detector.set_zones()` after video dimensions are known so zone coordinates are rescaled correctly.
- UI updates must use `root.after(0, ...)`; heavy work runs in worker threads; `StateManager` is thread-safe.

Selected CLAUDE.md excerpts (expanded):
- Product name: DRerio LogAI (package: `zebtrack`). See `TRANSITION_NOTE.md` for naming history.

- MVVM architecture summary (from CLAUDE.md):
  - Model layer: `StateManager`, `ProjectService`, `AnalysisService`, `ProjectManager`, `Detector`, `Recorder`.
  - View layer: `ApplicationGUI` and component widgets; components emit events via `EventBus`.
  - ViewModel: `MainViewModel` orchestrates flows and updates `StateManager` (alias `AppController` for backwards compatibility).

- Key data flow (processing pipeline):
  1. Frames from `src/zebtrack/io/video_source.py` →
  2. Detections in `src/zebtrack/core/detector.py` (zone state machine, optional Arduino commands) →
  3. Persistence in `src/zebtrack/io/recorder.py` (Parquet, MP4) →
  4. Analysis in `src/zebtrack/analysis/` → reporting in `src/zebtrack/analysis/reporter.py`.

- Output layout per video (filenames you must preserve):
  - `1_ArenaROI_<video>.parquet` — arena/ROI definitions
  - `2_Zones_<video>.parquet` — zone metadata
  - `3_CoordMovimento_<video>.parquet` — trajectories (immutable schema)
  - `<video>_summary.xlsx`, `<video>_report.docx`

- Critical constraints from CLAUDE.md:
  - Parquet schema is IMMUTABLE; changes require test updates in `tests/test_recorder.py`.
  - Settings hierarchy: `config.yaml` → `config.local.yaml`; do not hardcode values; update `src/zebtrack/settings.py` and `tests/test_settings.py` on changes.
  - Zone coordinates are defined relative to `camera.desired_width` × `camera.desired_height` and must be rescaled with `Detector.set_zones()`.
  - UI updates must use `root.after(0, ...)` and long tasks must run off the main thread.

- Testing & validation (from CLAUDE.md):
  - Test markers: `gui`, `slow`, `integration`, `unit`.
  - GUI tests must run serially (`-n0`).
  - Minimum coverage target: 70%.
  - Use fixtures in `tests/conftest.py`; mock Tkinter in controller/service tests when needed.

- Hardware & performance notes (useful excerpts):
  - Optional Arduino integration (`arduino.port`) with zone-enter/exit commands; app must gracefully degrade without hardware.
  - OpenVINO model cache at `openvino_model_cache/` speeds startup.
  - Performance knobs: `performance.max_parallel_videos`, `performance.max_parallel_plots`, `performance.parquet_compression` (default `snappy`).

Concrete code examples (copy-paste ready):
- Logging convention with structlog:
```python
import structlog
logger = structlog.get_logger()
logger.info("controller.load_project.success", project_name=project_name)
```
- Ensure UI update happens on main thread:
```python
# inside a background thread
root.after(0, lambda: gui.update_processing_stats(stats))
```
- Call to rescale zones after video opened:
```python
# after video_source reports width/height
detector.set_zones(project_manager.project_data['zones'], video_width, video_height)
```

How to run focused tests locally (exact commands):
- Fast unit tests (exclude GUI & slow):
```powershell
poetry run pytest -q
```
- GUI tests (always run sequentially, no parallel):
```powershell
poetry run pytest -m gui -n0 -q
```
- Slow tests only:
```powershell
poetry run pytest -m slow -q
```
- Integration tests (example wizard integration):
```powershell
poetry run pytest tests/test_wizard_integration.py -q
```
- Run a specific test function:
```powershell
poetry run pytest tests/test_recorder.py::test_parquet_column_order -q
```

Testing notes:
- Use markers: `gui`, `slow`, `integration`, `unit`.
- GUI tests must run with `-n0` to avoid parallel UI conflicts.
- Minimum coverage target: 70%.

Small PR checklist for agents (practical):
1. Read the nearest test(s) that exercise the module you're changing.
2. Preserve Parquet schema and any user-visible naming.
3. Run focused tests locally (see commands above).
4. Run linter: `poetry run ruff check .` and fix issues.
5. Add/update tests when behavior or schema changes.

Files to inspect for examples:
- `src/zebtrack/io/recorder.py` (Parquet schema)
- `src/zebtrack/core/state_manager.py` (thread-safe patterns)
- `src/zebtrack/core/detector.py` (zone state machine; call sites for `set_zones`)
- `src/zebtrack/ui/wizard/wizard_adapter.py` (adapter responsibility for backward compatibility)

Want more?
- I can fold additional CLAUDE.md sections (e.g., exact wizard layout constraints, EventBus migration notes, or hardware wiring examples) into this guide. Tell me which parts to include.
