<!-- ═════════════════════════════════════════════════════════════════════════
     CLAUDE INSTRUCTION FILE — DRerio LogAI
     Last refreshed: 2026-05-09
     Canonical source: CLAUDE.md (sync changes to AGENTS.md when applicable)
     ═════════════════════════════════════════════════════════════════════════ -->

<system_directive>
<role>
You are an expert Senior Python Developer and Systems Architect for DRerio LogAI.
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

# CLAUDE.md — DRerio LogAI Development Guide

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

### 🌳 Working inside a git worktree — do this FIRST

```bash
source scripts/wt-env.sh      # PowerShell: . .\scripts\wt-env.ps1
```

Run it once per shell, **before** the first `pytest`/`mypy`/`ruff` and before any
`git commit` or `git push`. Two traps make it mandatory, and only one of them
announces itself:

- **The worktree's `.venv` is a poetry stub** — Python 3.14 with pip and nothing
  else, while the project runs on 3.12. `mypy`, `pytest` and `ruff` are absent,
  so every pre-commit/pre-push hook that shells out to them dies with
  `'mypy' is not recognized`. Loud, but it hits at `git push`, after the work is
  done. Never answer it with `--no-verify`: those hooks are the CI gates.
- **`.venv/Lib/site-packages/drerio_logai.pth` hardcodes the MAIN repo's `src`.**
  Borrowing the main venv without fixing `PYTHONPATH` runs *main's* code from
  inside your worktree — the suite goes green without touching one line of your
  branch. This one is silent, and it is the reason to source the script rather
  than just putting the venv on `PATH` by hand.

Git hooks inherit the environment of the process that launches them, so sourcing
once makes commit and push work with the real gates running.

Avoid `poetry run` inside a worktree — it selects that stub 3.14 venv. Use the
bare tool names after sourcing.

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
- **`seg_overlap` needs masks that only exist if they were RECORDED.** It reads the
  `3b_Mascaras_<base>.parquet` sidecar, written only when all three hold:
  `recorder.persist_masks` **and** `model_selection.animal_method == "seg"` **and**
  the effective rule is `seg_overlap`. That conjunction lives in exactly one place —
  `core/services/mask_capture.should_capture_masks()`; never re-derive it at a call site.
- **Missing masks DEGRADE, never raise.** `seg_overlap` falls back to `bbox_intersects`,
  logs `roi.seg_overlap.fallback` and appends to `ROIAnalyzer.degradation_warnings`, which
  `AnalysisService` merges into `validation_warnings` **before** reports are generated.
  Its threshold is `roi_min_seg_overlap_ratio` (default 0.3) — **not**
  `roi_min_bbox_overlap_ratio` (0.10): the denominators differ (mask vs. bbox), so the
  two fractions are not comparable.
- Full guide: [`docs/reference/COORDINATE_SYSTEMS.md`](docs/reference/COORDINATE_SYSTEMS.md).

### 🐟 Multi-Aquarium (CRITICAL)

- **Always use `ProjectManager.get_multi_aquarium_zone_data()`** in report-generation contexts. `get_zone_data()` returns only aquarium 0 (legacy compatibility shim).
- Track IDs: `global_id = aquarium_id * 1000 + local_track_id`. Local IDs MUST stay <1000.
- Sequential vs parallel processing toggle: `MultiAquariumZoneData.sequential_processing` (UI in `ui/components/zone_controls.py`).
- See [`docs/reference/DOMAIN_GLOSSARY.md`](docs/reference/DOMAIN_GLOSSARY.md) and [`docs/archive/PHASES.md`](docs/archive/PHASES.md) for full data model.

### ⏱️ Duração da sessão ao vivo

- **`core/services/session_duration_resolver.resolve_session_duration()` é a fonte única.**
  Precedência: override da cobaia > padrão do bloco (dia × grupo) > `project_data["recording_duration_s"]` > 300 s.
  Overrides ficam em `project_data["session_duration_overrides"]`, com chaves montadas por
  `duration_override_key()` — **nunca** monte a string `"Dia_1|Grupo|3"` à mão: o dia chega
  como `1`, `"1"` ou `"Dia_1"` conforme o call site, e o resolver é quem normaliza.
- Um override corrompido **degrada, não levanta**: cai para o próximo nível com aviso no log.
  Duração zero perderia a gravação tão silenciosamente quanto uma exceção.
- **Durações heterogêneas dentro de um bloco invalidam a comparação de métricas ABSOLUTAS**
  (distância total, nº de entradas, tempo em ROI). O app não normaliza sozinho — a decisão é do
  pesquisador — mas avisa antes de gerar o relatório parcial/lote e carimba a ressalva dentro do
  `.docx`. A coluna `video_duration_s` está no `.xlsx` justamente para permitir a normalização.

### 🔌 Modo de gatilho externo (Arduino inicia a gravação)

- **`core/services/external_trigger_gate.decide_external_trigger()` é a regra única.** Existem
  DOIS caminhos que iniciam gravação ao vivo — o legado (`RecordingSessionCoordinator`, botão do
  painel) e o da grade de Progresso (`LiveCameraSessionCoordinator.start_live_project_session`).
  Até o gate existir, só o legado consultava `external_trigger_mode`, e gravar pela grade
  ignorava o sinal em silêncio.
- Gatilho ligado **sem** `use_arduino` ⇒ sessão **recusada**, nunca iniciada às cegas: uma
  gravação começada na hora errada é dado inútil que só se descobre na análise.
- `start_live_project_session` retorna `False` em três situações — falha real, aguardando zonas,
  e armado aguardando o gatilho. Quem mostra erro nesse `False` **precisa** sondar
  `pending_zone_confirmation` e `has_pending_external_trigger()` antes.

### 🌐 Idioma da interface (i18n)

- **`zebtrack.i18n` é a fonte única do idioma.** `_()` resolve o catálogo **na chamada**, não no
  import — é isso que permite importar módulos de UI antes de o idioma ser escolhido. Uma chamada a
  `_()` em corpo de módulo ou de classe congela a tradução no import e é reprovada por
  `tests/i18n/test_no_import_time_translation.py`.
- **O locale do SO NÃO é consultado.** Só `ui.language` (em `config.local.yaml`) decide, com
  `ZEBTRACK_LANGUAGE` como escape para testes/CI. Antes da v5.0.0 uma máquina pt-BR gerava
  relatórios em português sem ninguém pedir.
- `i18n.install()` precisa rodar **antes** de `_warm_container()` construir a árvore de UI. A ordem
  em `core/app_runner.run_app()` é: root Tk → prompt de primeiro uso → `load_settings()` →
  `i18n.install()` → splash → UI.
- **Nem toda string em português é texto de interface.** `Grupo_*`/`Dia_*`/`Sujeito_*`, as chaves de
  `session_duration_overrides`, a aba `por_animal` e as chaves do dict `report` são contratos de
  persistência: traduzir qualquer um deles não gera um app em inglês, gera um app que não lê os
  projetos que ele mesmo gravou. Lista completa em `scripts/i18n_allowlist.txt`.
- **Nunca ramifique pelo texto de uma exceção** (`if "caminho não definido" in str(e)`): a tradução
  quebra o `if` em silêncio, tomando o ramo errado. Use o tipo da exceção.
- Guia completo: [`docs/guides/developer/i18n.md`](docs/guides/developer/i18n.md).

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
  3b_Mascaras_<video>.parquet         # Segmentation masks (only with recorder.persist_masks)
  <video>_summary.xlsx                # Sheet1: metrics per ROI; por_animal: long table
                                      #   (experiment x track_id x roi), written only
                                      #   when per-animal metrics exist
  <video>_report.docx                 # Word report with plots
```

Multi-aquarium adds `aquarium_0/`, `aquarium_1/` subfolders mirroring this layout.

Live sessions additionally produce, per session folder:

```text
5_ClosedLoop_<base>.{csv,parquet}     # Frame->LED latency (only with Arduino bindings)
6_FrameLedger_<base>.{csv,parquet}    # One row per captured frame (always)
6_FrameLedger_<base>_anchor.json      # t0_perf/t0_wall pair + session metadata
```

`6_FrameLedger` is what makes the session timeline reconstructible: it maps
`3_CoordMovimento.frame` → real capture instant → real MP4 frame index, and
records every frame loss (`dropped_queue_full`, `write_failed`,
`not_recording`). **`3_CoordMovimento.timestamp` is a PROCESSING clock** — never
use it for latency or to date an event. See
[`docs/reference/system_integration.md`](docs/reference/system_integration.md)
§ 5.9.

---

## Testing Requirements

- **Coverage gates**: a **ratchet** — current values in
  [`docs/testing/COVERAGE_BASELINE.md`](docs/testing/COVERAGE_BASELINE.md), enforced only in
  [`.github/workflows/ci.yml`](.github/workflows/ci.yml). A PR that raises coverage raises the gate
  in the same PR. `--cov-fail-under` must **never** go back into `pytest.ini`: there it fires on
  every partial local run, which is how 28 consecutive test PRs shipped without the number moving.
- **Markers**: `@pytest.mark.{gui,slow,integration,unit}`.
- **Fixtures**: `tests/conftest.py`.
- **Source → tests lookup**: [`docs/testing/TEST_MAP.md`](docs/testing/TEST_MAP.md).

### 🧪 What counts as a test

**A test PR is judged by mutation score, not by test count.** Coverage says a line RAN; only a
failing assertion proves the line is CHECKED. Run
`poetry run python scripts/mutation_check.py --all` — a surviving mutation is a missing test.
Baseline in [`docs/testing/MUTATION_BASELINE.md`](docs/testing/MUTATION_BASELINE.md).

Three shapes are rejected automatically by `tests/quality/test_no_hollow_tests.py`:

- **Tautology** — building an instance with `object.__new__`, assigning attributes, and asserting
  those same attributes back. It is a round trip through `setattr`; the class never runs.
- **Hollow stub** — an `object.__new__` instance no method is ever called on.
- **Duplicate body** — the same statements as a test in another file.

`object.__new__` is fine for Tk widgets that cannot be built headless, **as long as a real method
is driven on the instance**. Legacy offenders live in `tests/quality/hollow_tests_allowlist.txt`;
that file only ever shrinks — never add to it.

**One test file per module.** No `test_x_extended2.py`, `_extended3.py`, … — the fragmentation is
what produced 47 byte-identical duplicates and made it impossible to see what was already covered.

### Pre-Merge Checklist

1. Read relevant test files before modifying.
2. `poetry run pytest -q` (all pass).
3. `poetry run pytest -m gui -n0` if `tests/ui/**` or any dialog changed — the fast suite skips GUI.
4. `poetry run python scripts/mutation_check.py --all` (no survivors) when touching a module in the
   catalogue or the tests that cover it.
5. `poetry run ruff check .` (no errors) and `poetry run mypy .` (CI runs it repo-wide, `tests/`
   included).
6. Update docs if user-facing changes.
7. Verify no wizard regressions.

---

## Hardware & Performance

- **Arduino**: optional, via `arduino.port`/`arduino.baud_rate`/`arduino.handshake`/`arduino.ack`/`arduino.roi_exit_grace_frames` settings. Per-zone live commands are configured as **bindings** in `project_data["arduino_bindings"]` (`ArduinoBinding{roi, on_enter, on_exit}`, see `core/services/arduino_bindings.py`): the live pipeline sends the integer token on ROI enter/exit (edge-triggered, fire-and-forget via `ArduinoManager.enqueue`); the firmware decides what each token does. Graceful degradation without hardware.
  - **Every token must have ONE role.** Reusing an integer as one ROI's `on_enter` and another's `on_exit` latches a device on and breaks the session-end sweep (which is built from the exit tokens). `ArduinoBindingConfig.token_conflicts()` detects it; the app warns but never rewrites — only the sketch knows the semantics. Reference sketch layout: `Z1=1/2, Z2=3/4, Z3=5/6, Z4=7/8` (ON/OFF are **consecutive pairs**, not an "enters 1-4 / exits 5-8" split).
  - **The ACK text names the channel from the sketch's point of view.** `"Red LED 1 ON"` is whatever the sketch prints — it is wrong the moment that pin drives a relay or pump instead. `ArduinoBinding.label` ("Dispositivo" in the panel) is where the operator records what is really wired; it is cosmetic, never sent to the device, and blank normalizes to `None`.
  - **Verify bindings against the firmware's ACK, not against intent.** `token_conflicts()` is blind to a layout where every token is unique but bound to the wrong edge. `arduino_ack_semantics.edge_ack_is_inverted(edge, ack)` reads the firmware's own reply — an `enter` answering `"… OFF"` is proof of inversion. Pre-flight via the bindings panel's "Testar comandos" (`ArduinoManager.probe_tokens`); at runtime the pipeline warns `arduino_zone_commands.ack_inverted`.
  - **Never put `delay()` in the sketch's `loop()`.** It blocks the serial read for its full duration, so an enter/exit pair collapses into an invisible flash when the queue finally drains, and `serial_act_ms` in the closed-loop log measures the block rather than the pipeline. Use `millis()` timing and `INPUT_PULLUP` on button pins (a floating `INPUT` pin self-triggers).
- **Camera**: `camera.index` in `config.local.yaml` (machine-specific).
- **OpenVINO**: model cache in `openvino_model_cache/`.
- **Parallelism**: `performance.max_parallel_videos` (2), `performance.max_parallel_plots` (3), `performance.parquet_compression` ("snappy"), `performance.enable_parallel_analysis` (true).

Tuning details: [`docs/guides/developer/performance-tuning.md`](docs/guides/developer/performance-tuning.md), [`docs/performance/HARDWARE_OPTIMIZATION_GUIDE.md`](docs/performance/HARDWARE_OPTIMIZATION_GUIDE.md).

---

## Conventions

- **Language**: **English is the source language.** Every user-visible string is written in English
  and wrapped in `_()` (`from zebtrack.i18n import _`); Portuguese lives in the pt_BR catalogue under
  `src/zebtrack/locales/`. New comments and docstrings are English too; existing Portuguese ones are
  converted as their file is migrated. Technical docs are English; `docs/wiki/` keeps Portuguese
  alongside the English pages. See [`docs/guides/developer/i18n.md`](docs/guides/developer/i18n.md).
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
| **Coverage ratchet**         | [`docs/testing/COVERAGE_BASELINE.md`](docs/testing/COVERAGE_BASELINE.md) |
| **Mutation baseline**        | [`docs/testing/MUTATION_BASELINE.md`](docs/testing/MUTATION_BASELINE.md) |
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
