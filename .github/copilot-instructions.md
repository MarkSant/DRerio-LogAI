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
- **Docs first**: Validate changes against `docs/architecture/ARCHITECTURE.md`, `docs/reference/REFERENCE_GUIDE.md`, `docs/architecture/DEPENDENCY_INJECTION_GUIDE.md` before rerouting flows.
- **Config**: Settings loaded via `load_settings()` in `__main__.py` (Composition Root) and injected as `settings_obj` parameter; precedence `config.yaml` < `config.local.yaml`; Pydantic v2 models enforce `extra="forbid"`. **Never import singleton** `from zebtrack import settings`—use constructor injection instead.
- **Architecture**: MVVM with DI—`MainViewModel` receives all dependencies via constructor (11 parameters including `settings_obj`); `StateManager` tracks observable state; `EventBus` only enabled when `settings_obj.ui_features.enable_event_queue` is true. Composition Root in `__main__.py` wires all services.
- **Lifecycle**: `io/video_source.py` feeds frames → `core/detector_service.DetectorService` wraps plugin detectors (`plugins/`) and zone scaling → `core/processing_worker.ProcessingWorker` handles background analysis → `io/recorder.Recorder` persists Parquet/MP4. All services receive `settings_obj` via constructor. **Threading** (v2.1): All worker threads (LiveCameraService, GUI live analysis) are daemon=True to allow Python shutdown.
- **UI**: Tk widgets under `zebtrack.ui` never block main thread; schedule updates with `root.after(0, ...)` or via `core/ui_scheduler.UIScheduler`.
- **Wizard**: `ui/wizard/` drives the 5-step project setup through `core/project_workflow_service.ProjectWorkflowService`; respect 1150×550 layout and keep SKIP/IMPORT/PARTIAL/FULL semantics.
- **Project data**: `core/project_manager.ProjectManager` stores ROI templates, arenas, intervals; call `Detector.set_zones()` after getting actual video dimensions to rescale coordinates.
- **Processing modes**: `core/processing_mode.ProcessingMode` toggles multi vs single subject; overlay locks UI when single subject forced—check tests in `tests/test_overlay_integration.py`.
- **Hardware**: Startup runs `utils/hardware_detection.get_hardware_summary()` and `recommend_backend()`; OpenVINO auto-enabled only if `WeightManager` reports converted XML under `openvino_model_cache/`.
- **Logging**: Use `structlog` with `domain.action.result` keys, e.g. `logger.info("controller.load_project.success", project=...)`.
- **Data schema**: Recorder outputs `timestamp, frame, track_id, x1, y1, x2, y2, confidence, uncertainty, bbox_iou` with derived centers/cm appended; confirm schema in `tests/test_recorder.py`. Multi-aquarium adds per-aquarium directories `<video>_aquarium_N/`.
- **Analysis**: `analysis/analysis_service.py` coordinates ROI metrics (`analysis/behavior.py`) and reporting (`analysis/reporter.py`); aggregated outputs saved under `<video>_results/` prefixed `1_`, `2_`, `3_`. Multi-aquarium: `run_multi_aquarium_analysis()` processes each aquarium separately; `data_transformer.py` includes thigmotaxis metrics.
- **Multi-Aquarium v2**: Parallel detection via `detect_partitioned_parallel()` with ThreadPoolExecutor (~30-40% speedup); batch inference `detect_batch()` for offline; ROI cropping `_crop_aquarium_region()`; uncertainty/IoU tracking; thigmotaxis metrics; validation with warnings; trajectory gap detection per aquarium; error recovery with fallback. Events: `ZONE_MULTI_AUTO_DETECT_SUCCESS`, `ZONE_MULTI_AUTO_DETECT_FAILED`, `ZONE_AQUARIUM_CONFIG_UPDATED`. Track ID: `aquarium_id * 1000 + local_track_id` (Aquarium 0: 0-999, Aquarium 1: 1000-1999). Export R/Python scripts via `reporter.export_r_script()`, `export_python_script()`. Handlers: `ProcessingCoordinator._handle_multi_auto_detect()`, `ProjectLifecycleCoordinator._handle_aquarium_config_updated()`.
- **Diagnostics**: `MainViewModel.run_model_diagnostic` drives `ui/gui.py`’s `DiagnosticProgressDialog`; keep cancel callbacks responsive via `root.after`.
- **Plugins**: Implement detectors via `plugins/base.py` and register in `plugins/__init__.py`; handle missing `track_id` gracefully for integrations.
- **Testing** (v2.1 fixes applied): Total 2568 tests (1586 fast, 949 GUI, 35 slow). `poetry run pytest -q` for fast suite (~1586 tests), `poetry run pytest -m gui -n0` for Tk tests (~949 tests, sequential), `poetry run pytest -m slow` for slow tests (~35 tests), `poetry run pytest -m "" -n0` for all tests (~6-7 min). **CRITICAL**: All worker threads are daemon=True (prevents pytest hangs); pytest-timeout plugin configured (300s per test); pytest_sessionfinish hook forces cleanup. Minimum 70% coverage tracked in CI.
- **Scenario coverage**: Consult fixtures in `tests/fixtures/` and flows in `tests/test_wizard_*.py`, `tests/test_interval_frames_config.py`, `test_scenarios/` for realistic data.
- **Lint & Format**: `poetry run ruff check .` (line length 100); use `--fix` carefully.
- **Pre-commit**: `poetry run pre-commit install` then `poetry run pre-commit run --all-files` mirrors CI checks.
- **Scripts**: Tools like `scripts/build_templates.py` and `scripts/compile_translations.py` refresh shared assets; run before release branches.
- **Thread safety**: `StateManager` is thread-safe for cross-thread updates; still pass updates through it instead of mutating view state directly.
- **Dependency Injection**: All services use constructor injection. Add `settings_obj: Settings` parameter to new services; pass it from `__main__.py` Composition Root (lines 140-280). See `docs/architecture/DEPENDENCY_INJECTION_GUIDE.md` for patterns (RuntimeError vs graceful fallback).
- **Common pitfalls**: Forgetting to rescale zones, skipping `root.after`, writing new columns mid-Parquet, or importing singleton `from zebtrack import settings`—existing tests catch these.
- **When extending**: Prefer augmenting services/adapters (e.g., `ProjectWorkflowService`, `DetectorService`) over bypassing them to keep UI/state synchronization intact. Inject settings via constructor, never use singleton.
- **Support**: If unexpected user edits exist, coordinate rather than reverting; log domain events using existing patterns.

## 📋 Documentation Standards (MANDATORY)

When creating or updating documentation, follow these rules:

### Folder Structure

| Folder | Purpose |
|--------|---------|
| `docs/architecture/` | System design, patterns, DI, events |
| `docs/guides/developer/` | Developer workflows, debugging, features |
| `docs/guides/user/` | End-user docs (English) |
| `docs/reference/` | API docs, operational reference |
| `docs/performance/` | Benchmarks, optimization, threading |
| `docs/testing/` | Test patterns, pytest fixes |
| `docs/decisions/` | Architecture Decision Records (ADR-NNN-title.md) |
| `docs/migration/` | Version upgrade guides |
| `docs/wiki/` | User guides (Portuguese) |
| `docs/archive/` | Historical/completed docs |

### Rules

1. **NEVER create docs in docs/ root** - Use appropriate subfolder
2. **English for technical docs** - Portuguese only in wiki/
3. **Update INDEX.md** - When adding new docs
4. **Archive, don't delete** - Move obsolete docs to docs/archive/

## Recent Critical Fixes (Dec 2025)

**1. Multi-Aquarium Data Flow:**
*   **Zone Serialization**: `ProcessingCoordinator` now correctly detects `MultiAquariumZoneData` and serializes it using `ZoneManager.multi_aquarium_zone_data_to_dict`.
*   **Worker Deserialization**: `ProcessingWorker` deserializes using `ZoneManager.multi_aquarium_zone_data_from_dict`.
*   **Partitioned Processing**: The worker automatically switches to `detector.detect_partitioned_optimized()` and `recorder.write_partitioned_detection_data()` when multi-aquarium data is detected.

**2. Video Validation & Persistence:**
*   **Parquet Compatibility**: `ProjectManager.save_multi_aquarium_zone_data` now automatically exports the zones of **Aquarium 0** to a standard parquet file (`1_ProcessingArea...`). This ensures that `VideoValidationService` and `VideoClassificationService` (which rely on file scanning) correctly classify the video as "Ready" (`has_arena=True`).
*   **Atomic Saving**: `save_project()` is now called **strictly after** updating the video entry's `parquet_files` map in `ProjectManager`. This prevents the "without_arena" regression on project reload.

**3. UI & Events:**
*   **Zone Selection**: `EventDispatcher` now subscribes to `ZONE_AQUARIUM_SELECTED` and delegates to `CanvasManager.update_zone_listbox()`.
*   **Listbox Update**: `update_zone_listbox` handles `MultiAquariumZoneData` by resolving the *active* aquarium's data before display.
*   **Rendering**: `CanvasRenderer` supports `MultiAquariumZoneData` natively, iterating through all aquariums to draw polygons with distinct labels.
*   **Trajectory Generation**: Added `PROCESSING_GENERATE_TRAJECTORIES` handler in `ProcessingCoordinator` to fix the "no handlers" warning in the Reports tab.

**4. Windows Taskbar Icon:**
*   Added `AppUserModelID` setup in `__main__.py` to dissociate the app from the generic Python process icon on Windows.

**5. Multi-Aquarium Reporting + Reports UI (Dec 2025):**
*   **Reporting Accessor**: report generation must use `ProjectManager.get_multi_aquarium_zone_data()` (NOT `get_zone_data()`), otherwise Aquarium 1 can reuse Aquarium 0 crop/geometry.
*   **Outputs Persistence (Option B)**: after generating summary/report artifacts, re-register updated `multi_aquarium_outputs` via `ProjectManager.register_multi_aquarium_outputs(...)` so `has_summary` and file paths persist.
*   **Reports Tree Source of Truth**: do not trust hierarchy video dict to contain `multi_aquarium_outputs`; fall back to `ProjectManager.find_video_entry(video_path)`.
*   **Key Normalization**: normalize `multi_aquarium_outputs` keys (`0` vs `"0"`) to avoid Treeview iid collisions.

**Agent Instructions:**
*   When modifying `ProjectManager` or `ZoneManager`, ensure `MultiAquariumZoneData` compatibility is maintained.
*   Do NOT revert the explicit parquet export in `save_multi_aquarium_zone_data`—it is essential for the legacy validation scanner.
*   Ensure `EventDispatcher` subscriptions are kept in sync with `ZoneControls` events.
