# v8.0.0 implementation plan — fronts, branches, rules

Decisions: [AUDIT](AUDIT.md), [ADR-009](ADR-009-class-roles.md),
[ADR-010](ADR-010-object-sidecar.md), [ADR-011](ADR-011-conditions-and-time.md),
[ADR-012](ADR-012-migrations.md), [ADR-013](ADR-013-zebrafish-compatibility.md).

## Branches and worktrees

`release/8.0` was cut from `feat/generic-class-aliases` (`5fa0f8d2`). Each front is a branch
`feat/v8-<front>` cut from `release/8.0`, checked out in `C:\dev\DRerio-v8-<front>`. Fronts are
merged locally into `release/8.0` by the integrator, in this order:

```text
F0 contracts → F4a conditions-core → F1 time-foundation → F2 class-roles → F3 object-sidecar
→ F4b window-analysis → F5 live-integration → F6 ui-editors → F7 i18n-docs-release
```

`main` and the main checkout under OneDrive are never touched. No PR, no merge to `main`, no tag
without the maintainer's order.

| Front | Branch | Owns |
|---|---|---|
| F0 | `feat/v8-contracts` | this folder, new `UIEvents`/payloads, new settings fields + `config.yaml`, new `WorkerConfig` fields, `project_workflow_service` allowlist, `mutation_catalog.yaml` stubs, `.pot` sync test |
| F1 | `feat/v8-time-foundation` | `analysis/time_base.py`, `duracao_video_s`, ROI latency, real fps in report coordinators, `retime_from_ledger`, `run_full_analysis(window=None)`, golden |
| F2 | `feat/v8-class-roles` | `core/detection/class_roles.py`, detectors, `detection_post_processor`, `weight_manager`, `worker_model_resolution`, worker model init, OpenVINO NMS, `detector_service` validation, wizard → project `model_selection`, project migrations, legacy 7.2.0 fixture |
| F3 | `feat/v8-object-sidecar` | recorder `3c`, `core/services/object_capture.py`, `io/object_sidecar.py`, worker loop writes, import copy, stale sidecar cleanup |
| F4a | `feat/v8-conditions-core` | `core/conditions/**` (pure) |
| F4b | `feat/v8-window-analysis` | observation builder, `AnalysisWindowService`, window cut in `analysis_service`/`roi`/`behavior`, reporters, Barnes E2E |
| F5 | `feat/v8-live-integration` | live `ConditionRuntime`, external-trigger gate, Arduino stamping/routing, session end, live `3c`, post-processor |
| F6 | `feat/v8-ui-editors` | class-role panel, condition editor, window status, wizard templates v4, role colours/labels |
| F7 | `feat/v8-i18n-docs-release` | `.po`/`.pot`, msgid generalisation, CLAUDE.md, docs/wiki, version 8.0.0, CHANGELOG, baselines |

### File ownership rules

- F1 and F4b both edit `analysis_service.py`, `roi.py`, `behavior.py`,
  `report_generation_coordinator.py` → F4b starts after F1 is merged.
- F2 and F3 both edit `processing_worker.py` → F3 starts after F2 is merged.
- **Only F7 edits `src/zebtrack/locales/*`, `CHANGELOG.md`, `CLAUDE.md`, `TEST_MAP.md`.**
  Other fronts write their changelog fragment to `docs/tasks/v8/changelog/<front>.md` and may add
  new `_()` msgids in code freely (F7 catalogues them).
- **Only F1 regenerates `tests/fixtures/golden/*`.**
- `scripts/mutation_catalog.yaml`: append only inside your front's module blocks.

## Rules every implementation agent follows

1. Work only inside your own worktree. First command in every shell:
   `source scripts/wt-env.sh` (bash) or `. .\scripts\wt-env.ps1` (PowerShell). Never `poetry run`
   inside a worktree.
2. Before editing any `src/` file: `python scripts/impact_analyzer.py file <path>` (or `class`,
   `function`, `settings`, `event`). Update every flagged component.
3. TDD: write the failing test first, then the code. One test file per module (extend the
   existing main test file; never create `_extended2`). No hollow tests
   (`tests/quality/test_no_hollow_tests.py`).
4. Gates before every commit: `ruff check .`, `ruff format --check .`, `mypy .`,
   `pytest -q` (plus `pytest -m gui -n0` if UI changed, `-m slow` if relevant),
   `python scripts/mutation_check.py --changed-since release/8.0` with no survivors. Commit
   through the pre-commit hooks; **never `--no-verify`**.
5. Small conventional commits in Brazilian Portuguese, matching the history
   (`feat(roles): …`, `fix(time): …`), ending with the attribution trailer.
6. English for code, comments, docstrings and technical docs; every user-visible string in
   `_()`, resolved at call time (no `_()` at module or class body).
7. DI: never `from zebtrack import settings` outside the composition root; inject `settings_obj`.
   Logging via structlog, `domain.action.result`.
8. Do not merge into `release/8.0`, do not push, do not touch other worktrees. Report back with
   the commit list, gate results and anything left undone.
