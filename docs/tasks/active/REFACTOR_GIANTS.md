# Refactor plan — `calibration_dialog.py` then `weight_manager.py`

This plan exists so a **fresh Claude Code conversation** can pick up the
refactor of two oversized files without re-discovering context. It is
self-contained: paste the kickoff prompt below into a new session and the
agent has everything it needs.

---

## Why these two files

Identified during the 2026-05-09 doc-system audit as the two highest-cost
files for AI-assisted work:

| File                                                  | Lines | Concern                                              |
| ----------------------------------------------------- | ----: | ---------------------------------------------------- |
| `src/zebtrack/ui/dialogs/calibration_dialog.py`       |  2161 | God-dialog: holds calibration + weights + OpenVINO + maintenance + system info |
| `src/zebtrack/core/services/weight_manager.py`        |  1544 | God-service: load/CRUD/validate/classify/convert + persistence |

Both have **strong test coverage** already (see "Existing test coverage"
sections below) — the refactor is safe to do in small commits.

> **Why not as part of the doc-system PR?**
> Refactoring a 2k-line file is its own PR. Bundling docs + refactor
> creates a hard-to-review change. Each refactor here should land on its own
> branch with focused commits.

---

## How to start the new conversation

Open a new Claude Code session in this repo and paste **exactly** this prompt
to begin Refactor 1:

> I'm starting the refactor of `src/zebtrack/ui/dialogs/calibration_dialog.py`
> as planned in [`docs/tasks/active/REFACTOR_GIANTS.md`](docs/tasks/active/REFACTOR_GIANTS.md). Read that file in full, then walk
> through Phase 0 → Phase 4 for **Refactor 1 only**. Stop after Phase 2
> (proposed division) and wait for my approval before doing any code change.
> Commit incrementally, run `/test-fast` after each step, and update
> `.copilot-impact-map.yaml` if any event subscription moves.

When Refactor 1 is merged, start a second new session for Refactor 2 with the
same prompt but pointing at `weight_manager.py` and the Refactor 2 section.

---

## Common rules (apply to both refactors)

1. **Branch per refactor.** `refactor/calibration-dialog-split` and
   `refactor/weight-manager-split`. Never mix them.
2. **Commit per logical extraction.** A 600-line move belongs in one commit;
   the test fixes for that move belong in the same commit.
3. **No behavior change.** This is a pure rearrangement. If you find a bug
   along the way, file it as a separate task — do not fix it inside the
   refactor commits.
4. **Public API stays stable.** External callers should not have to change
   imports. Keep backward-compatible re-exports in the original module if
   needed.
5. **Tests run green at every commit.** `poetry run pytest -q` (use
   `/test-fast`). If a commit can't pass tests, split it smaller.
6. **Run `/impact <type> <name>`** before extracting anything to confirm
   external dependencies.
7. **Update [`.copilot-impact-map.yaml`](.copilot-impact-map.yaml) and
   [`docs/testing/TEST_MAP.md`](docs/testing/TEST_MAP.md)** if file paths
   change.
8. **Avoid premature abstraction.** Extracting a method into another class
   is fine; introducing a new design pattern (Visitor, Strategy, etc.) is
   not — that is a different task.

---

## Refactor 1 — `calibration_dialog.py` (2161 lines)

### What this file actually contains today

A single `CalibrationDialog(simpledialog.Dialog)` class with 4 public + 59
private methods spanning **seven distinct concerns**:

| Concern                  | Approx. line range | Marker methods                                                              |
| ------------------------ | ------------------ | --------------------------------------------------------------------------- |
| Dialog scaffolding       | 52–256             | `__init__`, `body`, `_make_scrollable_container`, `_clear_frame`            |
| Calibration (px↔cm)      | 257–296, 542–905   | `_build_calibration_section`, `_build_global_calibration_ui`                |
| Project preferences      | 297–540            | `_build_preferences_section`, `_get_preferences_overrides`, `_save_project_preferences` |
| Detector parameters      | 906–1414           | `_build_project_calibration_ui`, `_create_detector_params_section`, `_apply_detector_parameters`, `_toggle_bytetrack_options` |
| Weights catalog          | 1416–1718          | `_populate_weights_dropdown`, `_populate_weights_treeview`, `_on_add_weight`, `_on_delete_weight`, `_on_change_target` |
| OpenVINO conversion/cache| ~1719–1900         | `_on_convert_openvino`, `_on_clear_cache_selected`, `_on_clear_cache_all`   |
| Maintenance / system     | 823–905, ~1900–2161| `_build_maintenance_section`, `_build_system_section`, validation handlers   |

The first three concerns are the dialog's **original purpose**. The last
four accumulated over time — they are the bulk of the bloat.

### Existing test coverage

`tests/test_calibration.py`, `tests/test_property_calibration.py`,
`tests/test_calibration_injection.py`,
`tests/test_processing_worker_calibration.py`. GUI tests for the dialog
itself live in `tests/ui/dialogs/` (run with `pytest -m gui -n0`).

### Phase 0 — Pre-conditions

- [ ] Branch from `main`: `git checkout -b refactor/calibration-dialog-split`
- [ ] Confirm clean working tree: `git status` shows no other uncommitted work
- [ ] Run `/test-fast` — must be green before starting
- [ ] Run `/impact class CalibrationDialog` — note all consumers
- [ ] Run `poetry run python scripts/impact_analyzer.py file src/zebtrack/ui/dialogs/calibration_dialog.py` — note imports

### Phase 1 — Investigation (read-only, ~15 min)

Use the **Explore** agent (single call) to confirm:

- All call sites of `CalibrationDialog(...)` — likely from `coordinators/calibration_coordinator.py` and `ui/gui.py`.
- All event subscriptions/publications inside the dialog (`UIEvents.MODEL_*`, `UIEvents.CALIBRATION_*`).
- Any state on `self.controller` mutated by the dialog (calibration values, weight registry).
- Whether `_build_global_calibration_ui` is reused elsewhere (probably not).
- The exact line ranges per concern (the table above is approximate).

Output: a 1-page summary with the precise method-to-concern mapping.

### Phase 2 — Proposed division (stop here, wait for approval)

Target structure (5 files in `src/zebtrack/ui/dialogs/calibration/`):

```text
ui/dialogs/calibration/
  __init__.py                         # re-export CalibrationDialog
  calibration_dialog.py               # ~400 lines — only Dialog scaffold + tab orchestration
  _calibration_panel.py               # ~250 lines — px↔cm UI + handlers (concerns 1–2)
  _detector_params_panel.py           # ~500 lines — model + bytetrack params (concern 4)
  _weights_panel.py                   # ~400 lines — weights catalog UI (concern 5)
  _openvino_panel.py                  # ~250 lines — conversion + cache (concern 6)
  _maintenance_panel.py               # ~200 lines — maintenance + system info (concern 7)
```

Each `_*_panel.py` exposes a single class with the contract:

```python
class CalibrationPanel:
    def __init__(self, parent, controller, dialog_state): ...
    def build(self, master: ttk.Frame) -> ttk.Frame: ...
    def collect(self) -> dict: ...   # values to apply on OK
    def reset(self) -> None: ...     # restore defaults
```

`dialog_state` is a small dataclass passed by reference so panels can read
each other's values without coupling. `controller` is the existing project
controller — unchanged.

External imports stay valid: `from zebtrack.ui.dialogs import CalibrationDialog`.

> **Decision point:** approve, tweak the split, or ask to investigate
> deeper before committing.

### Phase 3 — Refactor steps (one commit each)

Order matters — do the most independent panels first to keep PR-by-PR risk
low.

1. **Skeleton commit**: create `ui/dialogs/calibration/` package with empty
   `__init__.py` re-exporting today's class. Verify `/test-fast` still green.
2. **Extract `_maintenance_panel.py`** (smallest, least coupled). Move
   methods, update `body()` to call panel. Run `/test-fast`.
3. **Extract `_openvino_panel.py`**. Same pattern. Run tests.
4. **Extract `_weights_panel.py`**. Higher risk because it shares state with
   detector params — be careful with the weight selection callbacks.
5. **Extract `_detector_params_panel.py`**. The largest panel; this is
   probably worth two commits (UI build + parameter apply/restore).
6. **Extract `_calibration_panel.py`**. The original concern of the dialog.
7. **Final cleanup**: remaining `calibration_dialog.py` should be ~400
   lines — pure scaffolding. Add docstring, sort imports, run `/test-fast`
   one more time.

After each commit, also run `pytest -m gui -n0 tests/ui/dialogs/` to catch
GUI regressions. The full GUI suite (~949 tests) doesn't have to pass on
every commit but **must** pass before opening the PR.

### Phase 4 — Validation

- [ ] All tests green (`/test-fast` + `pytest -m gui -n0`)
- [ ] Each new file under target line count (largest ≤500)
- [ ] No new circular imports (`poetry run python -c "from zebtrack.ui.dialogs import CalibrationDialog"`)
- [ ] [`docs/testing/TEST_MAP.md`](../../docs/testing/TEST_MAP.md) updated if dialog path changed
- [ ] [`.copilot-impact-map.yaml`](../../.copilot-impact-map.yaml) updated if any event subscription moved
- [ ] PR description lists what moved where, with line counts before/after

---

## Refactor 2 — `weight_manager.py` (1544 lines)

### What this file actually contains today

A single `WeightManager` class with 23 public + 12 private methods, plus 2
top-level helpers and 1 exception class. Concerns:

| Concern                       | Approx. line range | Marker methods                                                                |
| ----------------------------- | ------------------ | ----------------------------------------------------------------------------- |
| Loading & discovery           | 145–520            | `_resolve_weights_dir`, `_load_weights`, `discover_perspective_weights`, `_maybe_relocate_path` |
| Classification                | 391–435            | `_classify_weight_type`, `_classify_perspective`                              |
| Persistence                   | 522–650            | `_initialize_default_weight`, `save_weights`                                   |
| CRUD (single weight)          | 654–1056           | `get_weight_*`, `set_default_weight*`, `add_weight`, `delete_weight`           |
| Targets / aliases             | 1057–1100          | `set_weight_target`, `_normalize_target_alias`                                 |
| Maintenance / OS              | 1075–1244          | `_rmtree_with_unlock`, `clear_openvino_cache`, `rescan_source_folder`, `reset_registry`, `validate_weight_files` |
| OpenVINO conversion           | 1251–1544          | `convert_to_openvino`, `convert_to_openvino_int8`                              |

### Existing test coverage

8 dedicated test files: `test_weight_manager.py`,
`test_weight_manager_targets.py` (newly added — currently untracked),
`test_weight_manager_logic.py`, `test_weight_manager_conversion.py`,
`test_weight_manager_threading.py`, `test_weight_manager_dual_init.py`,
`test_weight_type_classification.py`. Plus integration via
`test_calibration_injection.py`.

### Phase 0 — Pre-conditions

Same as Refactor 1, but on a fresh branch:
`git checkout -b refactor/weight-manager-split`.

Run `/impact class WeightManager` — this is wired into many places
(`coordinators/detector_setup_coordinator.py`,
`core/services/wizard_service.py`, multiple dialogs). The split must keep
`WeightManager`'s **public surface unchanged**.

### Phase 1 — Investigation

Confirm with one Explore agent:

- Every public method's call sites (23 methods × call sites is a lot —
  group by concern in the report).
- Whether `convert_to_openvino*` is genuinely independent of CRUD (it
  reads `self.weights[name]` but doesn't write — should be extractable).
- Whether `_rmtree_with_unlock` is used outside this module (unlikely but
  check).
- The threading model: `test_weight_manager_threading.py` exists for a
  reason — note any locks or thread-safety contract.

### Phase 2 — Proposed division (stop here, wait for approval)

Target: keep `WeightManager` as the **public facade** (no caller changes),
delegate to internal helpers organized by concern.

```text
core/services/weight_manager/
  __init__.py                       # re-export WeightManager + OpenVINOExportError
  weight_manager.py                 # ~400 lines — public facade, holds self.weights
  _registry.py                      # ~350 lines — load/save/discover/classify
  _crud.py                          # ~300 lines — get/set/add/delete (operates on dict)
  _openvino.py                      # ~350 lines — convert_to_openvino, convert_to_openvino_int8, clear_openvino_cache
  _filesystem.py                    # ~150 lines — _rmtree_with_unlock, _maybe_relocate_path, _resolve_weight_filename
```

Each helper module exposes free functions (not classes) that take the
`weights` dict and `weights_dir` Path explicitly. No state, no inheritance.
The facade calls them.

> Why functions and not classes? `WeightManager` already holds the state.
> Sub-classes would just split the state — that's worse, not better.
> Free functions keep the data flow explicit.

External callers continue to use `from zebtrack.core.services.weight_manager
import WeightManager` because `__init__.py` re-exports it.

### Phase 3 — Refactor steps (one commit each)

1. **Skeleton commit**: convert `weight_manager.py` to a package, empty
   `__init__.py` re-exports today's class. Run `/test-fast`.
2. **Extract `_filesystem.py`** (smallest, no behavior). Move
   `_rmtree_with_unlock` and path helpers as free functions. Update
   facade. Tests stay green.
3. **Extract `_registry.py`** (loading/saving/discovery/classification).
   Free functions take `weights_dir` and return the loaded dict. Facade
   calls them on init.
4. **Extract `_crud.py`**. This is delicate — many CRUD methods read AND
   write `self.weights`. Pass the dict in/out explicitly. Test after every
   sub-step.
5. **Extract `_openvino.py`**. Likely independent enough to move in one
   commit. `test_weight_manager_conversion.py` is the safety net.
6. **Final cleanup**: remaining facade should be ~400 lines and read like
   a thin coordinator.

### Phase 4 — Validation

Same checklist as Refactor 1, plus:

- [ ] `test_weight_manager_threading.py` passes — the threading contract
  was preserved.
- [ ] `poetry run python -c "from zebtrack.core.services.weight_manager import WeightManager, OpenVINOExportError; print(WeightManager.__module__)"` — confirms the public surface didn't move.

---

## What this plan does NOT cover

- Replacing `simpledialog.Dialog` with a custom Tk dialog framework.
- Moving panels to a different package (e.g. `ui/components/`).
- Adding new features.
- Touching `dialog_manager.py` (the next-largest dialog file at 1318 lines)
  — that is a separate refactor.

If any of those become tempting during the work, **stop and propose them as
follow-up tasks**, don't sneak them into the refactor PRs.
