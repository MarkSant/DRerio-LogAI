<!-- ═══════════════════════════════════════════════════════════════════════════
     COPILOT INSTRUCTION FILE — DRerio LogAI
     Last refreshed: 2026-05-09
     Canonical source: CLAUDE.md (this file is a Copilot-friendly summary)
     ═══════════════════════════════════════════════════════════════════════════ -->

# DRerio LogAI — Copilot Playbook

GitHub Copilot loads this file automatically in VS Code. It is a **Copilot-sized
summary** of the canonical agent guide. For anything not covered here, point
Copilot at [`CLAUDE.md`](../CLAUDE.md).

## What this project is

Python 3.12 Tkinter app for zebrafish behavioral tracking and analysis using
YOLO/OpenVINO. MVVM-S architecture with dependency injection.

- **Entry**: `src/zebtrack/__main__.py` → `ApplicationBootstrapper` → `DependencyContainer`
- **Stack**: Poetry, Tkinter, YOLO/OpenVINO, Parquet, structlog, Pydantic v2
- **Domain vocabulary**: see [`docs/reference/DOMAIN_GLOSSARY.md`](../docs/reference/DOMAIN_GLOSSARY.md)

## Universal rules (apply to every code change)

1. **Impact analysis first.** Run `.\scripts\dev.ps1 impact <type> <name>` and
   consult [`.copilot-impact-map.yaml`](../.copilot-impact-map.yaml) before
   editing.
2. **No placeholders.** Write full, functional code. Never use `...` for
   existing code.
3. **DI**: never `from zebtrack import settings` outside the composition root.
   Inject `settings_obj` everywhere else.
4. **Multi-aquarium**: use `ProjectManager.get_multi_aquarium_zone_data()` in
   report-generation contexts. `get_zone_data()` returns aquarium 0 only.
5. **Threading**: every UI update from a worker thread goes through
   `root.after(0, ...)`. Worker threads must be `daemon=True`.
6. **Parquet schema** in `io/recorder.py` is **immutable** — column order is
   fixed.
7. **Pre-merge gate**: `.\scripts\dev.ps1 check-all` (Ruff + fast tests) must
   pass.

## Day-to-day commands

All everyday operations go through `scripts/dev.ps1`:

```powershell
.\scripts\dev.ps1 help              # full command list
.\scripts\dev.ps1 test-fast         # ~2778 fast tests, <2 min
.\scripts\dev.ps1 test-gui          # ~949 GUI tests, sequential
.\scripts\dev.ps1 lint              # Ruff check
.\scripts\dev.ps1 lint-fix          # Ruff auto-fix
.\scripts\dev.ps1 check-all         # lint + tests
.\scripts\dev.ps1 impact class WeightManager
.\scripts\dev.ps1 run               # launch the GUI
```

Auto-approved commands: `poetry`, `mypy`, `ruff`, `pytest`, `pre-commit`, and
`powershell -Command` calls. Run them with `SafeToAutoRun: true`.

## Critical constraints (do not violate)

### Parquet schema (`io/recorder.py`) — IMMUTABLE

```text
timestamp, frame, track_id, x1, y1, x2, y2, confidence,
[x_center_px, y_center_px, x_cm, y_cm]?, [uncertainty, bbox_iou]?
```

Calibration columns appear only when calibration exists. Multi-aquarium adds
`uncertainty` and `bbox_iou`. Schema change requires updating
`tests/test_recorder.py`.

### Configuration

- Use `from zebtrack import settings` only at composition root.
- Hierarchy: `config.yaml` (defaults) → `config.local.yaml` (per-machine) →
  `ProjectManager.project_data` (per-project).
- Pydantic v2, `extra="forbid"`.

### Multi-aquarium track IDs

`global_id = aquarium_id * 1000 + local_track_id`. Local IDs MUST stay <1000.

### Threading & UI

- All worker→UI updates: `root.after(0, ...)`.
- Worker threads: `daemon=True` (otherwise pytest hangs at shutdown).
- `StateManager` is thread-safe.

## Where to look next

| Need                          | Document                                                              |
| ----------------------------- | --------------------------------------------------------------------- |
| Full agent guide              | [`CLAUDE.md`](../CLAUDE.md)                                           |
| Domain vocabulary             | [`docs/reference/DOMAIN_GLOSSARY.md`](../docs/reference/DOMAIN_GLOSSARY.md) |
| Source → tests map            | [`docs/testing/TEST_MAP.md`](../docs/testing/TEST_MAP.md)             |
| Event flows & payloads        | [`docs/reference/system_integration.md`](../docs/reference/system_integration.md) |
| Coordinate systems            | [`docs/reference/COORDINATE_SYSTEMS.md`](../docs/reference/COORDINATE_SYSTEMS.md) |
| Phase / version history       | [`docs/archive/PHASES.md`](../docs/archive/PHASES.md)                 |
| Recent fixes (Dec 2025)       | [`docs/archive/fixes/2025-12.md`](../docs/archive/fixes/2025-12.md)   |
| Contributing & PR workflow    | [`CONTRIBUTING.md`](../CONTRIBUTING.md)                               |
| Refactor plans                | [`docs/tasks/active/REFACTOR_GIANTS.md`](../docs/tasks/active/REFACTOR_GIANTS.md) |

## Tone & output style

- Match the project language: Portuguese in code/comments, English in docs.
- Line length 100 chars (Ruff).
- Default to terse responses; expand only when asked.
- Don't paste full file contents back in chat unless asked.

## Updating this file

If a rule above changes, update [`CLAUDE.md`](../CLAUDE.md) **first**, then
mirror only the new rule here. Do not duplicate full sections of CLAUDE.md
into this file — it is intentionally short so Copilot can carry it cheaply
in every conversation.
