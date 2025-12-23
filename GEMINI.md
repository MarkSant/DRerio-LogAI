# Gemini Project Context: ZebTrack-AI

This document provides essential context for the Gemini AI assistant to effectively collaborate on the ZebTrack-AI project.

## 1. Project Overview

ZebTrack-AI is a Python-based application for real-time zebrafish tracking and behavioral analysis. It utilizes computer vision models (like YOLO via Ultralytics and OpenVINO) for detection and tracking. The application has a GUI built with Tkinter and a sophisticated architecture involving services, state management, and dependency injection.

## 2. Core Technologies

- **Programming Language:** Python 3.11+
- **Dependency Management:** Poetry (`poetry.lock`, `pyproject.toml`)
- **Testing Framework:** Pytest (`pytest.ini`, `tests/`)
- **Linter & Formatter:** Ruff (`.ruff_cache`, configured in `pyproject.toml`)
- **Pre-commit Hooks:** Managed via `.pre-commit-config.yaml` to enforce standards before commits.
- **GUI Framework:** Tkinter (with ttkbootstrap)
- **Computer Vision:** Ultralytics (YOLO), OpenVINO, OpenCV.

## 3. Development Workflow

### Setup
To set up the development environment, run:
```bash
poetry install
```

### Running the Application
To run the main application GUI, use the script defined in `pyproject.toml`:
```bash
poetry run zebtrack
```

### Running Tests
The project has a comprehensive test suite. Run all tests using:
```bash
poetry run pytest
```
For specific tests, you can pass the file path, e.g., `poetry run pytest tests/test_state_manager.py`.

### Linting and Formatting
Code quality is maintained with Ruff. To check for issues, run:
```bash
poetry run ruff check .
```
To automatically fix issues, run:
```bash
poetry run ruff check . --fix
```

## 4. Key Architectural Concepts

- **State Management:** The application uses a central `StateManager` to manage application state immutably. See `docs/architecture/STATE_MANAGEMENT_GUIDE.md`.
- **Dependency Injection:** Services are injected into components to promote loose coupling. See `docs/architecture/DEPENDENCY_INJECTION_GUIDE.md`.
- **Event Bus:** A system for cross-component communication.
- **Service Layer:** Business logic is encapsulated in services (e.g., `DetectorService`, `ArduinoManager`).
- **Coordinator Layer (Phase 3):** Super coordinators consolidate orchestration: `ProcessingCoordinator`, `HardwareCoordinator`, `SessionCoordinator`, `ProjectLifecycleCoordinator`. See `docs/architecture/SYSTEM_INTEGRATION_MAP.md`.
- **UIScheduler vs UICoordinator:** `core/ui_scheduler.UIScheduler` schedules Tkinter updates via `root.after()`. `ui/ui_coordinator.UICoordinator` is the EventBus mediator. Different purposes, no conflict.
- **Multi-Aquarium v2:** Parallel detection (`detect_partitioned_parallel`), batch inference (`detect_batch`), ROI cropping, uncertainty/IoU tracking, thigmotaxis metrics, validation with warnings, trajectory gap detection, error recovery. Events: `ZONE_MULTI_AUTO_DETECT_SUCCESS`, `ZONE_MULTI_AUTO_DETECT_FAILED`, `ZONE_AQUARIUM_CONFIG_UPDATED`. Track ID: `aquarium_id * 1000 + local_track_id` (Aquarium 0: 0-999, Aquarium 1: 1000-1999).

## 5. Important Rules & Conventions

1.  **Adhere to Existing Patterns:** Before adding new code, analyze the surrounding files to understand and replicate the existing architectural and styling patterns.
2.  **Test Everything:** All new features, bug fixes, or refactors must be accompanied by corresponding tests. The project relies heavily on `pytest` and `pytest-mock`.
3.  **Imports:** Follow the existing import structure (standard library, third-party, then project-specific imports, sorted alphabetically).
4.  **Immutability:** Respect the immutable state management pattern. Do not mutate state objects directly.
5.  **Configuration:** Application settings are managed via `config.yaml`. Do not hardcode configuration values.
6.  **Documentation:**
    *   **CRITICAL - System Map:** See `docs/architecture/SYSTEM_INTEGRATION_MAP.md` for strict contracts on Event Bus payloads, component dependencies, and control flows. **Read this before debugging integration issues.**
    *   **Architecture:** Refer to `docs/architecture/` for in-depth information on architecture (e.g., `ARCHITECTURE_V4.md`), developer guides, and decision logs.

7. **Documentation Maintenance (Meta-Protocol):**
    *   **Mandatory Updates:** You MUST update `docs/architecture/SYSTEM_INTEGRATION_MAP.md` whenever you:
        *   Add, remove, or modify an Event Bus event (`Events.*`).
        *   Change payload structures (keys, types).
        *   Alter cross-component dependencies or injection graphs.
        *   Refactor critical control flows (e.g., Analysis, Cancellation, Saving).
    *   **Discovery:** If you discover undocumented behavior or "hidden" events while debugging, add them to the map immediately. Treat the map as a living part of the codebase, not a static artifact.

## 6. 📋 Documentation Standards

When creating or updating documentation, follow these rules to maintain organization:

### Folder Structure (MANDATORY)

| Folder | Purpose | Naming Convention |
|--------|---------|-------------------|
| `docs/architecture/` | System design, patterns, DI, events | `TOPIC.md` |
| `docs/guides/developer/` | Developer workflows, debugging, features | `GUIDE_TOPIC.md` or `TOPIC.md` |
| `docs/guides/user/` | End-user docs (English) | `TOPIC.md` |
| `docs/reference/` | API docs, operational reference | `TOPIC.md` or `topic_api.md` |
| `docs/performance/` | Benchmarks, optimization, threading | `TOPIC.md` |
| `docs/testing/` | Test patterns, pytest fixes | `TESTING_TOPIC.md` |
| `docs/decisions/` | Architecture Decision Records | `ADR-NNN-short-title.md` |
| `docs/migration/` | Version upgrade guides | `vX.Y-to-vX.Z.md` |
| `docs/wiki/` | User guides (Portuguese) | Numbered: `N_Title.md` |
| `docs/archive/` | Historical/completed docs | Move here, don't delete |

### Documentation Rules

1. **NEVER create docs in `docs/` root** - Use appropriate subfolder
2. **English for technical docs** - Portuguese only in `wiki/`
3. **Line length 100 chars** - Match Ruff standard
4. **Relative links** - Use `../` paths, not absolute
5. **Update INDEX.md** - When adding new docs
6. **Archive, don't delete** - Move obsolete docs to `docs/archive/`

### When to Update Docs

- **New feature**: Add to `guides/developer/` + update INDEX.md
- **API change**: Update `reference/` + `architecture/SYSTEM_INTEGRATION_MAP.md`
- **Bug fix with lessons**: Add to `docs/archive/fixes/` if significant
- **Architecture change**: Update `architecture/` docs
- **Performance change**: Update `performance/` docs

### ADR Format (for `docs/decisions/`)

```markdown
# ADR-NNN: Title

## Status
Accepted | Proposed | Deprecated

## Context
What is the issue?

## Decision
What was decided?

## Consequences
What are the results?
```

## 7. Recent Critical Fixes (Dec 2025)

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

**5. Infinite Loop & Crash Fixes (Dec 2025):**
*   **Infinite Detection Loop**: Fixed a recursive event cycle where `MainViewModel` subscribed to `ZONE_AUTO_DETECT` and called a method that re-published it. Removed the redundant subscription in `MainViewModel` (line 143), letting `ProcessingCoordinator` handle it exclusively.
*   **Multi-Aquarium Analysis Crash**: Fixed `AttributeError: 'MultiAquariumZoneData' object has no attribute 'polygon'` in `ProcessingCoordinator.start_single_video_processing`. Added logic to detect `MultiAquariumZoneData` and correctly calculate `has_arena`/`has_rois` by checking the `aquariums` list.
*   **Serialization Crash**: Fixed `ZoneManager.save_zone_data` blindly calling `zone_data_to_dict` (which expects single-aquarium data). Added detection to route `MultiAquariumZoneData` to `save_multi_aquarium_zone_data` automatically.
*   **GUI Safety**: Updated `gui.py` to check for `MultiAquariumZoneData` before accessing `polygon`, and `ZoneControlBuilder` to handle `ProjectInvalidError` gracefully when clicking "Conclude" in Single Video Mode.

**6. Multi-Aquarium Detector Logic Fixes (Dec 2025):**
*   **Empty Aquarium List**: Fixed silent failure where `Detector.set_zones` was not populating `self._aquariums`, causing `detect_partitioned_optimized` to loop 0 times. Added explicit population of `self._aquariums = self.zones.aquariums` when in multi-aquarium mode.
*   **Tracker Initialization Crash**: Fixed `KeyError: 0` by ensuring `self._byte_trackers_multi` is initialized for each aquarium ID in `set_zones`.
*   **Tracker Arguments Error**: Fixed `TypeError` in `BYTETracker` initialization. `BYTETracker` expects a namespace object `args` (not kwargs). Updated instantiation to use `SimpleNamespace` wrapping `track_thresh`, `track_buffer`, etc.

**Agent Instructions:**
*   When modifying `ProjectManager` or `ZoneManager`, ensure `MultiAquariumZoneData` compatibility is maintained.
*   Do NOT revert the explicit parquet export in `save_multi_aquarium_zone_data`—it is essential for the legacy validation scanner.
*   Ensure `EventDispatcher` subscriptions are kept in sync with `ZoneControls` events.
*   **Always check for infinite event loops** when adding new subscriptions to `MainViewModel`.

**7. Multi-Aquarium Reporting + Reports UI (Dec 2025):**
*   **Reporting Accessor**: report generation must use `ProjectManager.get_multi_aquarium_zone_data()` (NOT `get_zone_data()`), otherwise Aquarium 1 can reuse Aquarium 0 crop/geometry.
*   **Outputs Persistence (Option B)**: after generating summary/report artifacts, re-register updated `multi_aquarium_outputs` via `ProjectManager.register_multi_aquarium_outputs(...)` so `has_summary` and file paths persist.
*   **Reports Tree Source of Truth**: hierarchy video dict may omit `multi_aquarium_outputs`; fall back to `ProjectManager.find_video_entry(video_path)`.
*   **Key Normalization**: normalize `multi_aquarium_outputs` keys (`0` vs `"0"`) to avoid Treeview iid collisions.
- Fixed regression in multi-aquarium report generation: `ProcessingCoordinator.generate_project_reports` now correctly prioritizes `get_multi_aquarium_zone_data` over `get_zone_data`, preventing the second aquarium from using the first one's data.
- Standardized single-aquarium reports: now uses the same robust logic as multi-aquarium (cropped PNG background extraction, coordinate normalization to local aquarium space).
- Improved image loading in `VisualizationGenerator`: switched to `cv2.imdecode` with `np.fromfile` to support Windows file paths with spaces or non-ASCII characters, resolving the "gray background" issue.
- Enhanced `AnalysisResult` DTO and `AnalysisService`: now includes `validation_warnings` and `validation_stats` to propagate technical quality metrics to reports.
- Added "Appendix: Trajectory Validation" to Word reports: includes a summary table with total frames, coverage, and frame range, plus detailed validation warnings.
- Fixed coordinate misalignment in reports: `ProcessingCoordinator` now drops existing CM columns during local normalization, forcing `BehavioralAnalyzer` to recalculate positions relative to the aquarium crop origin (0,0).

**8. Interval Persistence & UI Help (Dec 2025):**
*   **New Parameter**: Added `display_interval` to `VideoProcessingSettings` in `settings.py`.
*   **Global Sync**: Updated `SingleVideoConfigDialog` and `LiveAnalysisDialog` to sync form values with the global `Settings` object upon starting analysis.
*   **Project Persistence**: `ProcessingCoordinator.start_single_video_processing` now persists `analysis_interval_frames` and `display_interval_frames` into `project_data` (and thus `project.json`).
*   **Wizard Support**: `CalibrationStep` and `LiveConfigStep` now collect and persist processing intervals during project creation.
*   **Contextual Help**: Implemented a unified help system using `create_help_label` (ⓘ icon) with detailed tooltips in `CalibrationDialog`, `ConfigEditorWidget`, and all configuration dialogs.
