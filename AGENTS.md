<!-- ═════════════════════════════════════════════════════════════════════════
     AGENTS.md — Pointer file
     Canonical source: CLAUDE.md (this file mirrors only the universal essentials)
     Last refreshed: 2026-05-09
     ═════════════════════════════════════════════════════════════════════════ -->

# Agent Instructions: DRerio LogAI

> **The canonical agent guide is [`CLAUDE.md`](CLAUDE.md).** Read it first.
> This file exists for tools that look for `AGENTS.md` by convention; it
> intentionally only restates rules that **every** agent must follow,
> regardless of which tool is driving.

## What this project is

Python 3.12 Tkinter app for zebrafish behavioral tracking and analysis using
YOLO/OpenVINO. MVVM-S architecture with dependency injection. See
[`CLAUDE.md`](CLAUDE.md) for the full guide.

## Universal rules (apply to every agent)

1. **Impact analysis is mandatory** before any code change. Run
   `python scripts/impact_analyzer.py <type> <name>` and consult
   [`.copilot-impact-map.yaml`](.copilot-impact-map.yaml).
2. **No placeholders** — write full, functional code. Do not leave `...` in
   place of existing code.
3. **DI**: never `from zebtrack import settings` outside the composition root
   (`core/application_bootstrapper.py`). Inject `settings_obj` everywhere else.
4. **Multi-aquarium**: use `ProjectManager.get_multi_aquarium_zone_data()` in
   report-generation contexts; `get_zone_data()` returns aquarium 0 only.
5. **Threading**: every UI update from a worker thread goes through
   `root.after(0, ...)`. Worker threads must be `daemon=True`.
6. **Parquet schema** in `io/recorder.py` is **immutable** — column order is
   fixed.
7. **Auto-approval**: `poetry`, `mypy`, `ruff`, `pytest`, `pre-commit`, and
   `powershell -Command` calls run with `SafeToAutoRun: true` without prompting.

## Where to look next

| Need                          | Document                                                                 |
| ----------------------------- | ------------------------------------------------------------------------ |
| Full agent guide              | [`CLAUDE.md`](CLAUDE.md)                                                 |
| Domain vocabulary             | [`docs/reference/DOMAIN_GLOSSARY.md`](docs/reference/DOMAIN_GLOSSARY.md) |
| Source → tests map            | [`docs/testing/TEST_MAP.md`](docs/testing/TEST_MAP.md)                  |
| Event flows / payloads        | [`docs/reference/system_integration.md`](docs/reference/system_integration.md) |
| Coordinate systems            | [`docs/reference/COORDINATE_SYSTEMS.md`](docs/reference/COORDINATE_SYSTEMS.md) |
| Phase / version history       | [`docs/archive/PHASES.md`](docs/archive/PHASES.md)                      |
| Recent fixes (Dec 2025)       | [`docs/archive/fixes/2025-12.md`](docs/archive/fixes/2025-12.md)        |
| Contributing & PR workflow    | [`CONTRIBUTING.md`](CONTRIBUTING.md)                                     |

## Updating this file

If a rule above changes, update [`CLAUDE.md`](CLAUDE.md) **first**, then
mirror only the universal rule here. Do not duplicate the rest of CLAUDE.md
content into this file — it is intentionally a pointer.
