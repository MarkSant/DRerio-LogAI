# ZebTrack-AI Agent Playbook (Optimized for Speed & Token Efficiency)

## 🎯 Quick Navigation Index
**ALWAYS check `.copilot-context.yaml` first** - auto-generated file index and decision trees.

### File Quick Access (Minimize Search Time)
- **Entry Point**: `src/zebtrack/__main__.py` (lines 140-280: Composition Root)
- **Main UI**: `src/zebtrack/ui/gui.py` (MainWindow + MainViewModel)
- **Settings**: `src/zebtrack/settings.py` (Pydantic v2 models)
- **Core Services**: `src/zebtrack/core/{detector_service,project_manager,state_manager,processing_worker}.py`
- **Data I/O**: `src/zebtrack/io/{video_source,recorder}.py`
- **Wizard**: `src/zebtrack/ui/wizard/wizard_dialog.py` (5 steps)

## ⚡ Fast Decision Trees (Avoid Unnecessary Reads)
**UI Change?** → Check `ui/widgets/` → Update `MainViewModel` → Use `root.after()` → Test `tests/test_*_integration.py`
**Processing Change?** → Check `core/detector_service.py` or `plugins/` → Inject `settings_obj` → Update schema if needed
**Config Change?** → Edit `settings.py` → Update `config.yaml` → Pass from `__main__.py` constructor → NEVER singleton import
**Debug UI?** → Check logs (structlog) → Verify `StateManager` → Check `root.after()` → Run `pytest -m gui -n0`
**Debug Processing?** → Check zone scaling → Verify `ProcessingWorker` → Validate `Recorder` schema → Run `pytest -q`

## 📋 Core Architecture (Read This Once)
- **Product**: Desktop Tkinter app branded DRerio LogAI; Python package `zebtrack`.
- **Runtime**: Python 3.12+, Poetry-managed; launch with `poetry run zebtrack` or `python -m zebtrack`.
- **Docs first**: Validate changes against `docs/ARCHITECTURE.md`, `TRANSITION_NOTE.md`, `docs/REFERENCE_GUIDE.md`, `docs/DEPENDENCY_INJECTION_GUIDE.md` before rerouting flows.
- **Config**: Settings loaded via `load_settings()` in `__main__.py` (Composition Root) and injected as `settings_obj` parameter; precedence `config.yaml` < `config.local.yaml`; Pydantic v2 models enforce `extra="forbid"`. **Never import singleton** `from zebtrack import settings`—use constructor injection instead.
- **Architecture**: MVVM with DI—`MainViewModel` receives all dependencies via constructor (11 parameters including `settings_obj`); `StateManager` tracks observable state; `EventBus` only enabled when `settings_obj.ui_features.enable_event_queue` is true. Composition Root in `__main__.py` wires all services.
- **Lifecycle**: `io/video_source.py` feeds frames → `core/detector_service.DetectorService` wraps plugin detectors (`plugins/`) and zone scaling → `core/processing_worker.ProcessingWorker` handles background analysis → `io/recorder.Recorder` persists Parquet/MP4. All services receive `settings_obj` via constructor. **Threading** (v2.1): All worker threads (LiveCameraService, GUI live analysis) are daemon=True to allow Python shutdown.
- **UI**: Tk widgets under `zebtrack.ui` never block main thread; schedule updates with `root.after(0, ...)` or via `core/ui_coordinator.UICoordinator`.
- **Wizard**: `ui/wizard/` drives the 5-step project setup through `core/project_workflow_service.ProjectWorkflowService`; respect 1150×550 layout and keep SKIP/IMPORT/PARTIAL/FULL semantics.
- **Project data**: `core/project_manager.ProjectManager` stores ROI templates, arenas, intervals; call `Detector.set_zones()` after getting actual video dimensions to rescale coordinates.
- **Processing modes**: `core/processing_mode.ProcessingMode` toggles multi vs single subject; overlay locks UI when single subject forced—check tests in `tests/test_overlay_integration.py`.
- **Hardware**: Startup runs `utils/hardware_detection.get_hardware_summary()` and `recommend_backend()`; OpenVINO auto-enabled only if `WeightManager` reports converted XML under `openvino_model_cache/`.
- **Logging**: Use `structlog` with `domain.action.result` keys, e.g. `logger.info("controller.load_project.success", project=...)`.
- **Data schema**: Recorder outputs `timestamp, frame, track_id, x1, y1, x2, y2, confidence` with derived centers/cm appended; confirm schema in `tests/test_recorder.py`.
- **Analysis**: `analysis/analysis_service.py` coordinates ROI metrics (`analysis/behavior.py`) and reporting (`analysis/reporter.py`); aggregated outputs saved under `<video>_results/` prefixed `1_`, `2_`, `3_`.
- **Diagnostics**: `MainViewModel.run_model_diagnostic` drives `ui/gui.py`’s `DiagnosticProgressDialog`; keep cancel callbacks responsive via `root.after`.
- **Plugins**: Implement detectors via `plugins/base.py` and register in `plugins/__init__.py`; handle missing `track_id` gracefully for integrations.
- **Testing** (v2.1 fixes applied): Total 2568 tests (1586 fast, 949 GUI, 35 slow). `poetry run pytest -q` for fast suite (~1586 tests), `poetry run pytest -m gui -n0` for Tk tests (~949 tests, sequential), `poetry run pytest -m slow` for slow tests (~35 tests), `poetry run pytest -m "" -n0` for all tests (~6-7 min). **CRITICAL**: All worker threads are daemon=True (prevents pytest hangs); pytest-timeout plugin configured (300s per test); pytest_sessionfinish hook forces cleanup. Minimum 70% coverage tracked in CI.
- **Scenario coverage**: Consult fixtures in `tests/fixtures/` and flows in `tests/test_wizard_*.py`, `tests/test_interval_frames_config.py`, `test_scenarios/` for realistic data.
- **Lint & Format**: `poetry run ruff check .` (line length 100); use `--fix` carefully.
- **Pre-commit**: `poetry run pre-commit install` then `poetry run pre-commit run --all-files` mirrors CI checks.
- **Scripts**: Tools like `scripts/build_templates.py` and `scripts/compile_translations.py` refresh shared assets; run before release branches.
- **Thread safety**: `StateManager` is thread-safe for cross-thread updates; still pass updates through it instead of mutating view state directly.
- **Dependency Injection**: All services use constructor injection. Add `settings_obj: Settings` parameter to new services; pass it from `__main__.py` Composition Root (lines 140-280). See `docs/DEPENDENCY_INJECTION_GUIDE.md` for patterns (RuntimeError vs graceful fallback).
- **Common pitfalls**: Forgetting to rescale zones, skipping `root.after`, writing new columns mid-Parquet, or importing singleton `from zebtrack import settings`—existing tests catch these.
- **When extending**: Prefer augmenting services/adapters (e.g., `ProjectWorkflowService`, `DetectorService`) over bypassing them to keep UI/state synchronization intact. Inject settings via constructor, never use singleton.
- **Support**: If unexpected user edits exist, coordinate rather than reverting; log domain events using existing patterns.
