<!-- ═════════════════════════════════════════════════════════════════════════
     CLAUDE INSTRUCTION FILE — ZebTrack-AI
     Last refreshed: 2026-05-09
     Canonical source: CLAUDE.md (sync changes to AGENTS.md when applicable)
     ═════════════════════════════════════════════════════════════════════════ -->

<system_directive>
<role>
You are an expert Senior Python Developer and Systems Architect for ZebTrack-AI.
You specialize in YOLO/OpenVINO tracking, Tkinter GUI, event-driven architecture, and dependency injection.
You prioritize deterministic execution, impact analysis, and system coherence over creativity.
</role>

<core_constraints>
<constraint>Run `python scripts/impact_analyzer.py` BEFORE any code change.</constraint>
<constraint>NO PLACEHOLDERS in code. Write full, functional code.</constraint>
<constraint>Follow negative constraints strictly (e.g., "NEVER import singleton").</constraint>
<constraint>Auto-approve ALL `poetry`, `mypy`, `ruff`, `pytest`, `pre-commit`, and `powershell -Command` commands with SafeToAutoRun: true.</constraint>
</core_constraints>

<output_verbosity_spec>
Level: Comprehensive — technical and code-focused.
Do not summarize code. Do not use "..." for existing code.
If a file is modified, output the entire changed section with sufficient context.
</output_verbosity_spec>
</system_directive>

---

# CLAUDE.md — ZebTrack-AI Development Guide

## 🚨 MANDATORY: Impact Analysis Protocol

**Before any code change**, you must:

1. Run `python scripts/impact_analyzer.py <type> <name>` to identify affected components.
2. Consult [`.copilot-impact-map.yaml`](.copilot-impact-map.yaml) for quick dependency lookup.
3. Verify all affected components are updated consistently.
4. Run domain-specific tests (see [`docs/testing/TEST_MAP.md`](docs/testing/TEST_MAP.md)).

Details: [`docs/guides/developer/impact_analysis.md`](docs/guides/developer/impact_analysis.md).

---

## Quick Context

**DRerio LogAI** (`zebtrack` package) — Python 3.12+ Tkinter app for zebrafish behavioral tracking and analysis.

- **Architecture**: MVVM-S with Dependency Injection. Entry: `src/zebtrack/__main__.py` → `ApplicationBootstrapper` → `DependencyContainer`.
- **Stack**: Poetry, Tkinter, YOLO/OpenVINO, Parquet, structlog, Pydantic v2.
- **Domain vocabulary**: see [`docs/reference/DOMAIN_GLOSSARY.md`](docs/reference/DOMAIN_GLOSSARY.md) before touching unfamiliar terms.

## Essential Commands

```bash
# Setup & run
poetry install                    # First time
poetry run zebtrack               # Run app

# Testing (fast by default, ~2778 tests)
poetry run pytest                 # Fast tests only (excludes GUI/slow)
poetry run pytest -m gui -n0      # GUI tests (sequential) — ~949
poetry run pytest -m slow         # Slow tests — ~35
poetry run pytest -m "" -n0       # Everything — ~3660+ (6-7 min)

# Code quality
poetry run ruff check .           # Lint
poetry run ruff check --fix .     # Auto-fix
poetry run pre-commit run --all-files
```

> **Auto-approval**: all `poetry`, `mypy`, `ruff`, `pytest`, `pre-commit`, and `powershell -Command` calls are pre-approved. Run them with `SafeToAutoRun: true` without asking.

---

## Architecture (MVVM-S + DI)

### Composition Root

- DI wiring: `core/application_bootstrapper.py` + `core/dependency_container.py`; coordinator/service registrations live in `core/di_registrations.py`.
- `__main__.py`: thin entry point — `main()` delegates to `ApplicationBootstrapper`.
- `DependencyContainer` holds all coordinator and service references; `LazyRef[T]` solves circular DI.
- **Never use global settings**: always `load_settings()` then inject `settings_obj`.

### Core Layers

| Layer            | Key Files                                                                                        | Purpose                          |
| ---------------- | ------------------------------------------------------------------------------------------------ | -------------------------------- |
| **Model**        | `core/state_manager.py`, `core/project/project_manager.py`, `core/services/detector_service.py`  | State, project data, detection   |
| **View**         | `ui/gui.py`, `ui/wizard/*.py`, `ui/dialogs/` (~25 files)                                          | Tkinter UI                       |
| **ViewModel**    | `core/main_view_model.py`                                                                          | Orchestrator                     |
| **Coordinators** | `coordinators/` (~24 files)                                                                       | Decomposed cross-cutting logic   |
| **Services**     | `core/services/wizard_service.py`, `core/video/video_processing_service.py`, `core/recording/*`   | Business logic                   |
| **I/O**          | `io/{recorder,video_source,camera,live_stream_source,recorder_factory}.py`                       | Persistence, frame sources       |
| **Analysis**     | `analysis/{behavior,roi}.py`, `analysis/reporters/` (~8 files)                                    | Behavioral metrics, reports      |

### Data Flow

1. **User → Event → ViewModel → State → UI**:
   UI emits to `EventBusV2` → `MainViewModel` handles → `StateManager` updates → UI refreshes via `root.after(0, ...)`.
2. **Pre-recorded pipeline**: `VideoSource` → `DetectorService` → `Recorder` (Parquet + MP4) → `AnalysisService` → `Reporter`.
3. **Live camera pipeline**: `LiveAnalysisDialog` → `LiveCameraService` → `[Capture, Processing] threads` → `Camera` → `DetectorService` → `Recorder` + `LivePreviewWindow`. Output: `live_analysis_sessions/{experiment_id}_{timestamp}/`.

Full architecture map: [`docs/reference/system_integration.md`](docs/reference/system_integration.md).

### Performance defaults

- **RecorderFactory** lazy-loads pandas/pyarrow only when analysis starts (~2.9s + 150 MB saved at startup).
- **Lazy imports** for pandas in `project_manager.py`, `zone_manager.py`, `project_service.py`.
- Net startup: ~6.0s → ~2.0s (-67%).

---

## Critical Constraints

### 🔒 Parquet Schema (IMMUTABLE)

```text
timestamp, frame, track_id, x1, y1, x2, y2, confidence,
[x_center_px, y_center_px, x_cm, y_cm]?, [uncertainty, bbox_iou]?
```

- Column order is **FIXED** in `io/recorder.py`. Calibration columns (`*_cm`) appear only when calibration exists. Multi-aquarium adds `uncertainty` and `bbox_iou`.
- Any schema change requires updates to `tests/test_recorder.py`.

### ⚙️ Configuration

- **Never hardcode**: use `from zebtrack import settings` only at composition root; everywhere else, accept `settings_obj` via DI.
- Hierarchy: `config.yaml` (defaults) → `config.local.yaml` (per-machine, git-ignored) → `ProjectManager.project_data` (per-project).
- Pydantic v2, `extra="forbid"` in `settings.py`.

### 🗺️ Zones, ROI & Coordinates

- Zones stored in reference coordinates (`camera.desired_width × camera.desired_height`). **Must call `Detector.set_zones()` after video dimensions known** to rescale.
- Arena: "4 corners OR center" logic.
- ROI modes: `centroid_in`, `centroid_in_on_buffered_roi`, `bbox_intersects`, `seg_overlap`.
- Full guide: [`docs/reference/COORDINATE_SYSTEMS.md`](docs/reference/COORDINATE_SYSTEMS.md).

### 🐟 Multi-Aquarium (CRITICAL)

- **Always use `ProjectManager.get_multi_aquarium_zone_data()`** in report-generation contexts. `get_zone_data()` returns only aquarium 0 (legacy compatibility shim).
- Track IDs: `global_id = aquarium_id * 1000 + local_track_id`. Local IDs MUST stay <1000.
- Sequential vs parallel processing toggle: `MultiAquariumZoneData.sequential_processing` (UI in `ui/components/zone_controls.py`).
- See [`docs/reference/DOMAIN_GLOSSARY.md`](docs/reference/DOMAIN_GLOSSARY.md) and [`docs/archive/PHASES.md`](docs/archive/PHASES.md) for full data model.

### 🧵 Threading & UI

- **All UI updates from worker threads MUST use `root.after(0, ...)`** (Tkinter main thread only).
- `StateManager` is thread-safe.
- Worker threads must be `daemon=True` (otherwise pytest hangs at shutdown — see [`docs/archive/PHASES.md`](docs/archive/PHASES.md) Phase 7).

### 🧙 Project Wizard

- 5-step wizard in `ui/wizard/` is the primary project creation flow.
- Layout: 1150×550 px; reserves 220 px for navigation buttons.
- Backward compatibility shim: `wizard_adapter.adapt_wizard_data_to_controller_format()`.
- Guide: [`docs/guides/developer/wizard.md`](docs/guides/developer/wizard.md).

---

## Common Patterns

### Logging (structlog)

```python
import structlog
logger = structlog.get_logger()
logger.info("controller.load_project.success", project_name=name)
logger.error("recorder.save_parquet.error", error=str(e))
```

Pattern: `domain.action.result`.

### Detector Plugins

- Implement `DetectorPlugin` from `plugins/base.py`.
- Register in `plugins/__init__.py` (`DETECTOR_PLUGINS` dict).
- Handle missing `track_id` gracefully: `detection.get("track_id", -1)`.

### ROI Templates & Analysis Intervals

- ROI templates: save/load via `ProjectService` (`templates/`); geometry helpers in `utils/geometry.py`.
- `analysis_interval_frames` (default 10): detection frequency.
- `display_interval_frames` (default 10): UI overlay frequency.
- Persist via `ProjectManager.save_project()`.

---

## Key File Locations

### Entry Points & Core

- `src/zebtrack/__main__.py` — thin entry point; `main()` delegates to `ApplicationBootstrapper`.
- `core/application_bootstrapper.py` — DI composition root.
- `core/dependency_container.py` — coordinator/service refs; `LazyRef[T]` for circular DI.
- `core/di_registrations.py` — where coordinators/services are registered into the container.
- `core/main_view_model.py` — application orchestrator.
- `core/state_manager.py` — centralized observable state.
- `core/project/project_service.py`, `core/services/wizard_service.py` — service layer.
- `core/recording/{live_camera_service,recording_service}.py` — live & timed recording.
- `core/detection/` — detector + zone logic (sub-package).

### I/O & Processing

- `io/{recorder,video_source,camera,live_stream_source,frame_source_factory}.py`.
- `analysis/{behavior,roi}.py`, `analysis/reporters/` — metrics + reports.
- `plugins/` — detector implementations (YOLO, OpenVINO).

### UI

- `ui/gui.py` — main window.
- `ui/dialogs/` — ~25 dialog classes (incl. `LiveAnalysisDialog`, `LivePreviewWindow`).
- `ui/components/canvas/` — canvas sub-package.
- `ui/wizard/` — 5-step project wizard; `models.py` holds Pydantic validation models.

### Configuration

- `settings.py` — Pydantic configuration models.
- `config.yaml` — default settings.
- `config.local.yaml` — local overrides (git-ignored).

### Output Structure (per video)

```text
<video>_results/
  1_ArenaROI_<video>.parquet          # Arena/ROI definitions
  2_Zones_<video>.parquet             # Zone metadata
  3_CoordMovimento_<video>.parquet    # Trajectory (immutable schema)
  <video>_summary.xlsx                # Metrics per ROI
  <video>_report.docx                 # Word report with plots
```

Multi-aquarium adds `aquarium_0/`, `aquarium_1/` subfolders mirroring this layout.

---

## Testing Requirements

- **Coverage gates**: 48% Linux core, 32% Linux GUI, 28% Windows core.
- **Markers**: `@pytest.mark.{gui,slow,integration,unit}`.
- **Fixtures**: `tests/conftest.py`.
- **Source → tests lookup**: [`docs/testing/TEST_MAP.md`](docs/testing/TEST_MAP.md).

### Pre-Merge Checklist

1. Read relevant test files before modifying.
2. `poetry run pytest -q` (all pass).
3. `poetry run ruff check .` (no errors).
4. Update docs if user-facing changes.
5. Verify no wizard regressions.

---

## Hardware & Performance

- **Arduino**: optional, via `arduino.port` setting. Zone-based commands (`enter_commands`, `exit_commands`). Graceful degradation without hardware.
- **Camera**: `camera.index` in `config.local.yaml` (machine-specific).
- **OpenVINO**: model cache in `openvino_model_cache/`.
- **Parallelism**: `performance.max_parallel_videos` (2), `performance.max_parallel_plots` (3), `performance.parquet_compression` ("snappy"), `performance.enable_parallel_analysis` (true).

Tuning details: [`docs/guides/developer/performance-tuning.md`](docs/guides/developer/performance-tuning.md), [`docs/performance/HARDWARE_OPTIMIZATION_GUIDE.md`](docs/performance/HARDWARE_OPTIMIZATION_GUIDE.md).

---

## Conventions

- **Language**: Portuguese in code/comments; English in technical docs (Portuguese only in `docs/wiki/`).
- **Line length**: 100 chars (Ruff).
- **Python**: ≥3.12 required.
- **setuptools**: pinned <81 (docxcompose dependency).
- **EventBus**: `EventBusV2` is the sole event bus; `UIEvents` enum in `ui/event_bus_v2.py` (~200 events).
- **Markdown**: follow `.markdownlint.json`; ATX headings, `-` for unordered lists, language tag on every code fence.

---

## Plugin & Skill Invocation Map

When a task matches a row, prefer the listed skill/plugin over ad-hoc work.

| Trigger                                                      | Use                                  |
| ------------------------------------------------------------ | ------------------------------------ |
| Review a PR or diff for bugs/quality                         | `pr-review-toolkit:review-pr` (project default — its `silent-failure-hunter`, `type-design-analyzer`, `pr-test-analyzer` subagents match this repo's error-handling, mypy, and coverage concerns) |
| Quick correctness pass on the current local diff             | built-in `/code-review` (lighter, single-pass, confidence-filtered) |
| Security-sensitive change                                    | built-in `/security-review`          |
| Analyze tracking output (Parquet/metrics), stats, plots      | `data` plugin (`statistical-analysis`, `explore-data`, `create-viz`) |
| Inspect/debug generated `.docx` report or `.xlsx` summary    | `docx` / `xlsx` skills               |
| Work with PDFs (papers, forms)                               | `pdf-viewer`                         |
| Commit / push / open PR                                      | `commit-commands`                    |
| Build a new feature from scratch                             | `feature-dev`                        |
| Audit or improve this CLAUDE.md                              | `claude-md-management:claude-md-improver` |

Connector plugins (Slack, Linear, Notion, Jira, BigQuery, Datadog, Enterprise Search, etc.) are not relevant to this repo — invoke only when explicitly named.

---

## Quick Navigation

| Topic                        | Document                                                      |
| ---------------------------- | ------------------------------------------------------------- |
| **Domain glossary**          | [`docs/reference/DOMAIN_GLOSSARY.md`](docs/reference/DOMAIN_GLOSSARY.md) |
| **Source → tests map**       | [`docs/testing/TEST_MAP.md`](docs/testing/TEST_MAP.md)        |
| **Cheatsheet**               | [`docs/guides/developer/CHEATSHEET.md`](docs/guides/developer/CHEATSHEET.md) |
| **Workflows**                | [`docs/guides/developer/WORKFLOWS.md`](docs/guides/developer/WORKFLOWS.md) |
| **System integration map**   | [`docs/reference/system_integration.md`](docs/reference/system_integration.md) |
| **Coordinate systems**       | [`docs/reference/COORDINATE_SYSTEMS.md`](docs/reference/COORDINATE_SYSTEMS.md) |
| **Wizard development**       | [`docs/guides/developer/wizard.md`](docs/guides/developer/wizard.md) |
| **Debugging**                | [`docs/guides/developer/debugging.md`](docs/guides/developer/debugging.md) |
| **Impact analysis**          | [`docs/guides/developer/impact_analysis.md`](docs/guides/developer/impact_analysis.md) |
| **Performance tuning**       | [`docs/guides/developer/performance-tuning.md`](docs/guides/developer/performance-tuning.md) |
| **Known issues**             | [`docs/reference/KNOWN_ISSUES.md`](docs/reference/KNOWN_ISSUES.md) |
| **Doc index**                | [`docs/INDEX.md`](docs/INDEX.md)                              |
| **Contributing guide**       | [`CONTRIBUTING.md`](CONTRIBUTING.md)                          |
| **VS Code setup**            | [`docs/guides/developer/VSCODE.md`](docs/guides/developer/VSCODE.md) |
| **Phase history (v2.x–v3.x)**| [`docs/archive/PHASES.md`](docs/archive/PHASES.md)            |
| **Recent fixes (Dec 2025)**  | [`docs/archive/fixes/2025-12.md`](docs/archive/fixes/2025-12.md) |
| **Changelog**                | [`CHANGELOG.md`](CHANGELOG.md)                                |

---

## Development Workflow

1. **Before coding**: run `python scripts/impact_analyzer.py`; consult `.copilot-impact-map.yaml`; read relevant tests via [`TEST_MAP.md`](docs/testing/TEST_MAP.md).
2. **Coding**: follow DI patterns; use `structlog`; inject `settings_obj`.
3. **Testing**: write tests in parallel; run `pytest -q`.
4. **Quality**: `ruff check --fix .`, run pre-commit.
5. **Documentation**: update relevant docs if user-facing.
6. **System map**: update [`docs/reference/system_integration.md`](docs/reference/system_integration.md) if changing events, payloads, or cross-component logic.
7. **Impact verification**: confirm ALL components flagged by `impact_analyzer.py` are updated.
8. **Commit**: clear message, reference issue if applicable.

Detailed workflows: [`docs/guides/developer/WORKFLOWS.md`](docs/guides/developer/WORKFLOWS.md).

---

<instruction_reinforcement>

Critical rules that MUST be followed in every response:

- Impact analysis is MANDATORY before ANY code change.
- Use Poetry for all Python commands (auto-approved; includes ruff/pytest/pre-commit).
- Multi-aquarium: ALWAYS use `get_multi_aquarium_zone_data()` in report contexts.
- UI updates from worker threads: ALWAYS use `root.after(0, ...)`.
- DI: NEVER import the singleton `from zebtrack import settings` outside the composition root.

</instruction_reinforcement>
