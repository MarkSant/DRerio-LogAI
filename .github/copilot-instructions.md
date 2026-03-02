<!-- ═══════════════════════════════════════════════════════════════════════════
     COPILOT INSTRUCTION FILE - ZebTrack-AI
     Last Synced: 2026-03-01
     Canonical Source: AGENTS.md (always update AGENTS.md first, then mirror here)
     ═══════════════════════════════════════════════════════════════════════════ -->

<system_directive>
<role>Expert Python Developer for ZebTrack-AI (YOLO/OpenVINO, Tkinter, event-driven architecture).</role>
<core_constraints>
<constraint>Run impact analyzer BEFORE any code change.</constraint>
<constraint>Auto-approve ALL `poetry`, `mypy`, `powershell -Command` commands.</constraint>
<constraint>NO PLACEHOLDERS - write full, functional code.</constraint>
</core_constraints>
</system_directive>

# ZebTrack-AI Agent Playbook (Optimized for Speed & Token Efficiency)

---

## 🚨 MANDATORY: Impact Analysis Protocol

**BEFORE making ANY code change**, you MUST:

1. **Read**: `docs/guides/developer/impact_analysis.md` - Complete workflow
2. **Run**: `python scripts/impact_analyzer.py <type> <name>` - Trace all affected components
3. **Consult**: `.copilot-impact-map.yaml` - Quick dependency lookup
4. **Verify**: Update ALL affected components consistently
5. **Test**: Run domain-specific tests from protocol

**Failure to follow this protocol results in incomplete changes that break system coherence.**

---

## 🛡️ MANDATORY: Command Approval Policy

> [!IMPORTANT]
> **NON-NEGOTIABLE AUTO-APPROVAL**:
> To ensure maximum efficiency, the user has pre-approved all commands of the following types. Agents MUST set `SafeToAutoRun: true` and NEVER ask for permission for:
>
> - **Poetry**: Any command starting with `poetry` (install, run, etc.).
> - **Mypy**: Any `mypy` call (e.g., `mypy src`, `poetry run mypy ...`).
> - **Code Quality**: `ruff`, `pytest`, `pre-commit`.
> - **PowerShell**: `powershell -Command "..."`.
> - **Impact Analysis**: `python scripts/impact_analyzer.py ...`.

---

## ✅ Agent Instruction Source of Truth (MANDATORY)

- **AGENTS.md is the canonical source** for all agent guidance.
- If this file changes, **update AGENTS.md first** and then mirror the same changes here.
- **SYNC REMINDER**: Every change to agent instructions must be mirrored across all instructions files immediately to prevent drift.
- **PLANNING & TASKS**: Agents are REQUIRED to create a detailed task entry in `docs/tasks/active/ROLLING_TASK_LOG.md` before starting work. This ensures transparency and progress tracking.

---

## 📋 Documentation Standards (MANDATORY)

- **Diátaxis**: Always categorize documentation into `tutorials/`, `guides/`, `explanation/`, or `reference/`.
- **Language**: English for technical docs; Portuguese strictly for `docs/wiki/` (user-facing).
- **Cleanup**: Do not leave fragmented files in `docs/` root. Merge into central documents or move to `docs/archive/legacy/`.
- **Linting**: Respect `markdownlint`. Avoid file-wide disables.

### Markdown Formatting Rules (markdownlint)

The project uses `.markdownlint.json`. Key disabled rules:

- **MD013** (line length): Disabled for code blocks/tables and long URLs.
- **MD033** (inline HTML): Allowed for badges, callouts, and layout helpers.
- **MD041** (first line heading): Disabled for files with metadata or XML directives.

Agent requirements:

1. **No file-wide disables** in new documentation.
2. **Inline disables** must include a justification comment on the same line.
3. **Prefer fixes** over disables; reformat lists/headings instead of suppressing.
4. **Headings**: Use ATX style (`#`, `##`) not Setext.
5. **Lists**: Use `-` for unordered, `1.` for ordered.
6. **Code fences**: Always specify a language (` ```python `, ` ```yaml `).
7. **Line length**: Keep prose under 100 characters when reasonable; code blocks/tables exempt.
8. **Tables**: Align all pipe characters (`|`) vertically across every row (MD060). Pad separator rows to match column widths (`| --- |` not `|---|`). Wrap literal `*` or `_` inside backticks in table cells to prevent MD037.

---

## 🧩 VS Code Extensions (Installed) — Best Practices

Keep editor diagnostics consistent and avoid formatter conflicts.

- **Python / Pylance**: Use the Poetry venv interpreter; keep terminal and editor aligned.
- **Ruff**: Use Ruff as the only Python formatter/linter; enable on-save fixes.
- **Mypy (Matan Gover)**: Single Mypy extension (daemon-based). Prefer `mypy.runUsingActiveInterpreter=true`; align with `mypy.ini`/`pyproject.toml`; use "Mypy: Restart Daemon and Recheck Workspace" if stale.
- **Python Debugger**: Debug and manage envs using the same Poetry interpreter.
- **Jupyter (Microsoft)**: For notebook exploration and data analysis; kernel auto-selects Poetry venv.
- **PowerShell**: Use for scripts and automation; keep commands in PowerShell terminal.
- **GitLens (GitKraken)**: Primary Git tool — inline blame, file history, comparison. Replaces Git History.
- **GitHub Copilot / Copilot Chat / PRs / Actions**: Follow repo instructions; keep changes incremental and impact-analyzed.
- **Error Lens**: Inline error/warning display; shows errors and warnings only (not hints/info); CSpell diagnostics excluded.
- **TODO Tree**: Tracks TODO, FIXME, HACK, BUG, XXX, DEPRECATED tags; excludes build artifacts and archive folders.
- **YAML / markdownlint / Code Spell Checker**: Keep lint rules on; fix warnings rather than disable.

### Removed Extensions (DO NOT reinstall)

| Extension | Reason |
| --- | --- |
| `ms-python.mypy-type-checker` | Duplicated diagnostics with `matangover.mypy` |
| `ms-python.vscode-python-envs` | Triggered WSL popups via `wsl.exe` stub |
| `yzhang.markdown-all-in-one` | Redundant with `davidanson.vscode-markdownlint` |
| `donjayamanne.githistory` | Replaced by `eamodio.gitlens` |
| `tomoki1207.pdf` | Unused — no PDF workflows |
| `mechatroner.rainbow-csv` | Unused — project uses Parquet, not CSV |

### How to use/configure in VS Code

- Use "Python: Select Interpreter" to pick the Poetry venv; keep terminals aligned.
- Prefer `python.analysis.typeCheckingMode=basic`; use `strict` only on targeted files.
- Keep Mypy config in `mypy.ini`/pyproject; prefer `mypy.runUsingActiveInterpreter=true` and use "Mypy: Restart Daemon and Recheck Workspace" when stale.
- Set Ruff as formatter with `editor.defaultFormatter=charliermarsh.ruff`, enable `editor.formatOnSave`, and `editor.codeActionsOnSave` with `source.fixAll.ruff` and `source.organizeImports.ruff`.
- GitLens: Enabled by default; inline blame and CodeLens active; use "GitLens: Compare" for file diffs.
- Error Lens: Configured via workspace settings; shows errors/warnings inline; CSpell excluded.
- TODO Tree: Scans workspace for tags; check sidebar panel for tag overview.
- Jupyter: Kernel auto-selects Poetry venv; use for data exploration notebooks.

---

## ✅ VS Code Tooling Checklist (Required)

- [ ] Active Python interpreter is the Poetry venv used by `poetry run`.
- [ ] Ruff is the only Python formatter (disable Black/Pylint/Flake8 formatters).
- [ ] Mypy config is centralized (mypy.ini/pyproject) and editor uses the same config.
- [ ] Only `matangover.mypy` installed (NOT `ms-python.mypy-type-checker`).
- [ ] YAML/Markdown linters are enabled for config/docs quality.
- [ ] Error Lens shows errors/warnings only (not hints/info); CSpell excluded.
- [ ] TODO Tree excludes build artifacts and archive folders.
- [ ] If any agent instruction changes, update AGENTS.md first and mirror to other agent files.

---

## 🎯 Quick Navigation Index

**ALWAYS check `.copilot-context.yaml` first** - auto-generated file index and decision trees.

### File Quick Access (Minimize Search Time)

- **Entry Point**: `src/zebtrack/__main__.py` (789 lines; `main()` at line 25; DI delegated to `core/application_bootstrapper.py`)
- **Main UI**: `src/zebtrack/ui/gui.py` (865 lines; 1 class `MainWindow`, 36 methods)
- **Settings**: `src/zebtrack/settings.py` (Pydantic v2 models)
- **Core Services**: `src/zebtrack/core/services/detector_service.py`, `core/project/project_manager.py`, `core/state_manager.py`, `core/video/processing_worker.py`
- **Data I/O**: `src/zebtrack/io/{video_source,recorder}.py`
- **Wizard**: `src/zebtrack/ui/wizard/wizard_dialog.py` (5 steps)

## ⚡ Fast Decision Trees (Avoid Unnecessary Reads)

**UI Change?** → Check `ui/widgets/` → Update `MainViewModel` → Use `root.after()` → Test `tests/test_*_integration.py`
**Processing Change?** → Check `core/services/detector_service.py` or `plugins/` → Inject `settings_obj` → Update schema if needed
**Config Change?** → Edit `settings.py` → Update `config.yaml` → Pass from `__main__.py` constructor → NEVER singleton import
**Debug UI?** → Check logs (structlog) → Verify `StateManager` → Check `root.after()` → Run `pytest -m gui -n0`
**Debug Processing?** → Check zone scaling → Verify `ProcessingWorker` → Validate `Recorder` schema → Run `pytest -q`

## 📋 Core Architecture (Read This Once)

- **Product**: Desktop Tkinter app branded DRerio LogAI; Python package `zebtrack`.
- **Runtime**: Python 3.12+, Poetry-managed; launch with `poetry run zebtrack` or `python -m zebtrack`.
- **Docs first**: Validate changes against `docs/explanation/architecture.md`, `docs/reference/operational_reference.md`, `docs/explanation/dependency_injection.md` before rerouting flows.
- **Config**: Settings loaded via `load_settings()` in `__main__.py` (Composition Root) and injected as `settings_obj` parameter; precedence `config.yaml` < `config.local.yaml`; Pydantic v2 models enforce `extra="forbid"`. **Never import singleton** `from zebtrack import settings`—use constructor injection instead.
- **Architecture**: MVVM with DI—`MainViewModel` receives all dependencies via `MainViewModelDependencies` dataclass + `DependencyContainer`; `StateManager` tracks observable state; `EventBusV2` (sole event bus; v1 removed) handles all cross-component communication. Composition Root in `core/application_bootstrapper.py` wires all services.
- **Lifecycle**: `io/video_source.py` feeds frames → `core/services/detector_service.DetectorService` wraps plugin detectors (`plugins/`) and zone scaling → `core/video/processing_worker.ProcessingWorker` handles background analysis → `io/recorder.Recorder` persists Parquet/MP4. All services receive `settings_obj` via constructor. **Threading** (v2.1): All worker threads (LiveCameraService, GUI live analysis) are daemon=True to allow Python shutdown.
- **UI**: Tk widgets under `zebtrack.ui` never block main thread; schedule updates with `root.after(0, ...)` or via `core/ui_scheduler.UIScheduler`.
- **Wizard**: `ui/wizard/` drives the 5-step project setup through `core/project_workflow_service.ProjectWorkflowService`; respect 1150×550 layout and keep SKIP/IMPORT/PARTIAL/FULL semantics.
- **Project data**: `core/project/project_manager.ProjectManager` stores ROI templates, arenas, intervals; call `Detector.set_zones()` after getting actual video dimensions to rescale coordinates.
- **Processing modes**: `core/video/processing_mode.ProcessingMode` toggles multi vs single subject; overlay locks UI when single subject forced—check tests in `tests/test_overlay_integration.py`.
- **Hardware**: Startup runs `utils/hardware_detection.get_hardware_summary()` and `recommend_backend()`; OpenVINO auto-enabled only if `WeightManager` reports converted XML under `openvino_model_cache/`.
- **Logging**: Use `structlog` with `domain.action.result` keys, e.g. `logger.info("controller.load_project.success", project=...)`.
- **Data schema**: Recorder outputs `timestamp, frame, track_id, x1, y1, x2, y2, confidence, uncertainty, bbox_iou` with derived centers/cm appended; confirm schema in `tests/test_recorder.py`. Multi-aquarium adds per-aquarium directories `<video>_aquarium_N/`.
- **Analysis**: `analysis/analysis_service.py` coordinates ROI metrics (`analysis/behavior.py`) and reporting (`analysis/reporters/` sub-package with 8 files); aggregated outputs saved under `<video>_results/` prefixed `1_`, `2_`, `3_`. Multi-aquarium: `run_multi_aquarium_analysis()` processes each aquarium separately; `data_transformer.py` includes thigmotaxis metrics.
- **Multi-Aquarium v2**: Parallel detection via `detect_partitioned_parallel()` with ThreadPoolExecutor (~30-40% speedup); batch inference `detect_batch()` for offline; ROI cropping `_crop_aquarium_region()`; uncertainty/IoU tracking; thigmotaxis metrics; validation with warnings; trajectory gap detection per aquarium; error recovery with fallback. Events: `ZONE_MULTI_AUTO_DETECT_SUCCESS`, `ZONE_MULTI_AUTO_DETECT_FAILED`, `ZONE_AQUARIUM_CONFIG_UPDATED`. Track ID: `aquarium_id * 1000 + local_track_id` (Aquarium 0: 0-999, Aquarium 1: 1000-1999). Export R/Python scripts via `reporter.export_r_script()`, `export_python_script()`. Handlers: `MultiAquariumCoordinator._handle_multi_auto_detect()`, `ProjectLifecycleCoordinator._handle_aquarium_config_updated()`.
- **Diagnostics**: `MainViewModel.run_model_diagnostic` drives `ui/gui.py`’s `DiagnosticProgressDialog`; keep cancel callbacks responsive via `root.after`.
- **Plugins**: Implement detectors via `plugins/base.py` and register in `plugins/__init__.py`; handle missing `track_id` gracefully for integrations.
- **Testing** (v2.1 fixes applied): Total ~2778 fast tests (+ ~949 GUI, ~35 slow). `poetry run pytest -q` for fast suite (~2778 tests), `poetry run pytest -m gui -n0` for Tk tests (~949 tests, sequential), `poetry run pytest -m slow` for slow tests (~35 tests), `poetry run pytest -m "" -n0` for all tests (~6-7 min). **CRITICAL**: All worker threads are daemon=True (prevents pytest hangs); pytest-timeout plugin configured (300s per test); pytest_sessionfinish hook forces cleanup. CI coverage gates: 50% Linux core, 32% Linux GUI, 28% Windows core.
- **Scenario coverage**: Consult fixtures in `tests/fixtures/` and flows in `tests/test_wizard_*.py`, `tests/test_interval_frames_config.py`, `test_scenarios/` for realistic data.
- **Lint & Format**: `poetry run ruff check .` (line length 100); use `--fix` carefully.
- **Pre-commit**: `poetry run pre-commit install` then `poetry run pre-commit run --all-files` mirrors CI checks.
- **Scripts**: Tools like `scripts/build_templates.py` and `scripts/compile_translations.py` refresh shared assets; run before release branches.
- **Thread safety**: `StateManager` is thread-safe for cross-thread updates; still pass updates through it instead of mutating view state directly.
- **Dependency Injection**: All services use constructor injection. Add `settings_obj: Settings` parameter to new services; pass it from `core/application_bootstrapper.py` Composition Root. See `docs/architecture/DEPENDENCY_INJECTION_GUIDE.md` for patterns (RuntimeError vs graceful fallback).
- **Common pitfalls**: Forgetting to rescale zones, skipping `root.after`, writing new columns mid-Parquet, or importing singleton `from zebtrack import settings`—existing tests catch these. **See `.copilot-impact-map.yaml` Section `pitfalls` for top 8 errors.**
- **When extending**: Prefer augmenting services/adapters (e.g., `ProjectWorkflowService`, `DetectorService`) over bypassing them to keep UI/state synchronization intact. Inject settings via constructor, never use singleton.
- **Impact Analysis**: **ALWAYS run `python scripts/impact_analyzer.py` before completing any change.** This tool traces all affected files, events, and DI chains.
- **Support**: If unexpected user edits exist, coordinate rather than reverting; log domain events using existing patterns.

## 📋 Documentation Standards (Reference)

When creating or updating documentation, follow these rules:

### Folder Structure

| Folder | Purpose |
| --- | --- |
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

- **Zone Serialization**: `VideoProcessingCoordinator` now correctly detects `MultiAquariumZoneData` and serializes it using `ZoneManager.multi_aquarium_zone_data_to_dict`.
- **Worker Deserialization**: `ProcessingWorker` deserializes using `ZoneManager.multi_aquarium_zone_data_from_dict`.
- **Partitioned Processing**: The worker automatically switches to `detector.detect_partitioned_optimized()` and `recorder.write_partitioned_detection_data()` when multi-aquarium data is detected.

**2. Video Validation & Persistence:**

- **Parquet Compatibility**: `ProjectManager.save_multi_aquarium_zone_data` now automatically exports the zones of **Aquarium 0** to a standard parquet file (`1_ProcessingArea...`). This ensures that `VideoValidationService` and `VideoClassificationService` (which rely on file scanning) correctly classify the video as "Ready" (`has_arena=True`).
- **Atomic Saving**: `save_project()` is now called **strictly after** updating the video entry's `parquet_files` map in `ProjectManager`. This prevents the "without_arena" regression on project reload.

**3. UI & Events:**

- **Zone Selection**: `EventDispatcher` now subscribes to `ZONE_AQUARIUM_SELECTED` and delegates to `CanvasManager.update_zone_listbox()`.
- **Listbox Update**: `update_zone_listbox` handles `MultiAquariumZoneData` by resolving the *active* aquarium's data before display.
- **Rendering**: `CanvasRenderer` supports `MultiAquariumZoneData` natively, iterating through all aquariums to draw polygons with distinct labels.
- **Trajectory Generation**: Added `PROCESSING_GENERATE_TRAJECTORIES` handler in `ReportGenerationCoordinator` to fix the "no handlers" warning in the Reports tab.

**4. Windows Taskbar Icon:**

- Added `AppUserModelID` setup in `__main__.py` to dissociate the app from the generic Python process icon on Windows.

**5. Multi-Aquarium Reporting + Reports UI (Dec 2025):**

- **Reporting Accessor**: report generation must use `ProjectManager.get_multi_aquarium_zone_data()` (NOT `get_zone_data()`), otherwise Aquarium 1 can reuse Aquarium 0 crop/geometry.
- **Outputs Persistence (Option B)**: after generating summary/report artifacts, re-register updated `multi_aquarium_outputs` via `ProjectManager.register_multi_aquarium_outputs(...)` so `has_summary` and file paths persist.
- **Reports Tree Source of Truth**: do not trust hierarchy video dict to contain `multi_aquarium_outputs`; fall back to `ProjectManager.find_video_entry(video_path)`.
- **Key Normalization**: normalize `multi_aquarium_outputs` keys (`0` vs `"0"`) to avoid Treeview iid collisions.

**Agent Instructions:**

- When modifying `ProjectManager` or `ZoneManager`, ensure `MultiAquariumZoneData` compatibility is maintained.
- Do NOT revert the explicit parquet export in `save_multi_aquarium_zone_data`—it is essential for the legacy validation scanner.
- Ensure `EventDispatcher` subscriptions are kept in sync with `ZoneControls` events.

---

<instruction_reinforcement>
<!-- REMINDER: Critical rules for every response -->
- Impact analysis: MANDATORY before ANY code change
- Poetry commands: auto-approved (SafeToAutoRun: true)
- Multi-aquarium: use get_multi_aquarium_zone_data()
- UI threading: use root.after(0, ...) for non-main threads
- DI: NEVER import singleton settings
</instruction_reinforcement>
