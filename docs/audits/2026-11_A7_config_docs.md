# A7 — Configuration and stale documentation: findings

Scope: the stale configuration and documentation items of register section A7 in
`docs/audits/2026-11_loose_ends.md`. Verified on 2026-11-14 against the tree of branch
`claude/frosty-swanson-9fd811` (fast-forwarded to `worktree-cov-plugins-utils`).

Status values: `fixed` (changed in this branch), `reported` (needs a decision or is out of scope),
`refuted` (the claim does not hold).

## Summary

| Id      | Item                                              | Status   |
| ------- | ------------------------------------------------- | -------- |
| A7-C-01 | `impact_analyzer.py` crashes on cp1252            | fixed    |
| A7-C-02 | `KNOWN_ISSUES.md` describes a vanished suite      | fixed    |
| A7-C-03 | `.copilot-impact-map.yaml` stale paths            | fixed    |
| A7-C-04 | `pytest.ini` says the default run is parallel     | fixed    |
| A7-C-05 | `scripts/audit_events.py` cannot run              | reported |
| A7-C-06 | `conftest.py` docstring names a missing hook      | reported |
| A7-C-07 | Settings fields with no reader                    | reported |
| A7-C-08 | `load_settings()` outside the composition root    | reported |
| A7-C-09 | Other docs that contradict the code               | partly fixed, rest reported |

## Items

### A7-C-01 — `impact_analyzer.py` crashes on a Windows console

- **Claimed:** the script, mandatory before every change, raises `UnicodeEncodeError` under
  cp1252.
- **True:** confirmed. `PYTHONIOENCODING=cp1252 python scripts/impact_analyzer.py file
  src/zebtrack/settings.py` died with `'charmap' codec can't encode character '\U0001f4e6'`.
- **Fix:** `main()` in `scripts/impact_analyzer.py` now calls `reconfigure(errors="backslashreplace")`
  on `sys.stdout` and `sys.stderr`. The console encoding is kept; only what it cannot encode is
  escaped (`\U0001f4e6 DIRECT DEPENDENTS`). On a UTF-8 console the output is byte-identical.
- **Evidence:** `tests/quality/test_impact_analyzer_console.py` runs the real script in a
  subprocess under `cp1252` and `utf-8`. With the fix reverted, the cp1252 test fails (exit code
  1); with it, both pass.
- **Status:** fixed.

### A7-C-02 — `KNOWN_ISSUES.md` describes a 519-test suite

- **Claimed:** 519 tests, 11 failures in `tests/ui/test_components.py`.
- **True:** that file does not exist (`ls tests/ui/test_components.py`). `pytest --collect-only`
  gives 10033 tests: 8635 fast, 1374 `gui`, 24 `slow` (no overlap). `pytest -m gui -n0` finished
  with `1374 passed` in 73 s. The `ttkbootstrap_singleton` marker is declared in `pytest.ini:66`
  and carried by no test.
- **Fix:** the document was rewritten with those numbers, the real xdist constraint and the one
  still-open test issue (the `sys.modules["openvino"]` leak, `tests/test_openvino_batch_inference.py:44-45`,
  register A7-08). No issue was invented.
- **Not verified:** a mixed `pytest -m "" -n0` run was not repeated here, so the document makes no
  claim about it.
- **Status:** fixed.

### A7-C-03 — `.copilot-impact-map.yaml` names paths that do not exist

- **Claimed:** `src/zebtrack/plugins/detector.py` and `ui/dialogs/dialog_manager.py`.
- **True:** both missing. Every string in the file was checked against the tree by the new test;
  it found two more: `widgets/` and `dialogs/` in `tests.gui.covers`.
- **Fix:** `plugins/detector.py` became `core/detection/multi_aquarium_detector.py` (the
  multi-aquarium detector; `plugins/` holds only `base.py`, `openvino_detector.py`,
  `ultralytics_detector.py`); `ui/dialogs/dialog_manager.py` became
  `ui/components/dialog_manager.py`; `covers` now lists `ui/`, `ui/components/`, `ui/dialogs/`,
  `ui/wizard/`. The stale suite counts in the same file were also corrected (see A7-C-09).
- **Evidence:** `tests/quality/test_impact_map_paths.py` (fails when the map names a missing path;
  also asserts it found more than 50 paths so it cannot pass vacuously). It resolves each path
  against the repository root and `src/zebtrack`, and expands globs.
- **Limit:** only whole-string path values are checked, not paths mentioned inside prose
  sentences.
- **Status:** fixed.

### A7-C-04 — `pytest.ini` comments say the default run is parallel

- **Claimed:** comments say `poetry run pytest` is parallel; `addopts` has `-n0`.
- **True:** `-n0` starts no xdist workers, so the default run is sequential. Comments said
  "Default (fast tests only, parallel)", "Non-GUI tests (parallel, fast)" and "-n0 required" as if
  parallel were the baseline.
- **Fix:** the usage block now says the default is sequential, gives `-n auto` as the explicit way
  to parallelise, and states that the last `-n`/`-m` on the command line wins. No option changed.
- **Evidence:** `pytest.ini` lines 4 and 74-90.
- **Status:** fixed.

### A7-C-05 — `scripts/audit_events.py` reads a file that no longer exists

- **Claimed:** it reads `src/zebtrack/ui/events.py`.
- **True:** confirmed, and it cannot run: `python scripts/audit_events.py` ends with
  `FileNotFoundError: ... 'src/zebtrack/ui/events.py'` at `scripts/audit_events.py:106`
  (called from `main()` at line 124). The bus is `EventBusV2` and the enum is `UIEvents` in
  `src/zebtrack/ui/event_bus_v2.py`; the script matches `Events.NAME` attributes and
  `publish`/`publish_event` names, which no longer exist in that form.
- **References:** `git grep audit_events` finds only `docs/archive/legacy/mypy_fix_evolution.md:17`
  (a historical checklist line) and the register row A1-06. No workflow, pre-commit hook or doc
  invokes it.
- **Overlap:** `tests/quality/test_no_orphan_ui_events.py` already enforces "no `UIEvents` member
  published without a subscriber" in CI.
- **Recommendation:** delete the script. Decision left to the maintainer; nothing changed.
- **Status:** reported.

### A7-C-06 — `tests/conftest.py` docstring names a missing hook

- **Claimed:** the `pytest_configure` docstring says serial GUI enforcement "was moved to
  `pytest_cmdline_main`".
- **True:** `tests/conftest.py:323-324` says so, but the file defines only `pytest_configure`,
  `pytest_collection_modifyitems` and `pytest_sessionfinish`; no `pytest_cmdline_main` exists
  anywhere in the repository. Serial GUI execution is not enforced by code; it comes from `-n0` in
  `pytest.ini` addopts.
- **Decision:** not edited. `scripts/mutation_check.py:65` lists `tests/conftest.py` in
  `_SCOPE_FORCING_PATHS`, so any edit, even to a docstring, makes CI run the whole mutation
  catalogue. Fold the correction into the next change that has to touch `tests/conftest.py`.
- **Proposed text** (replace the two-line `Note:` at lines 323-324): "Note: serial execution of
  GUI tests is not enforced here; it comes from `-n0` in `pytest.ini` `addopts`."
- **Status:** reported.

### A7-C-07 — Settings fields with no reader

Method: the leaves of `Settings` were enumerated recursively through `model_fields` (121 leaf
fields). For each, a reader was searched in `src/` outside `settings.py` as attribute access,
quoted string key or `getattr` argument; leaf names shared by several sections, or short ones,
were re-checked requiring the parent section name within the six preceding lines. Zero-hit fields
were then searched across the whole tree (`config.yaml`, docs, tests, scripts, and
`ui/components/config_editor.py`, whose sections are hand-built and name none of them).
`model_dump` consumers (`ProjectLifecycleManager`, `project_settings_snapshot`, `gui.py`,
`validation_manager`) copy whole objects and do not read single fields.

| Field                                         | Verdict                      | Evidence |
| --------------------------------------------- | ---------------------------- | -------- |
| `live_analysis.auto_stop_on_limit`            | written but never read       | defined `settings.py:168`, default in `config.yaml:54`; no other reference anywhere |
| `live_analysis.show_countdown`                | written but never read       | `settings.py:172`, `config.yaml:57`; no other reference |
| `detection_zones.max_aquarium_area_ratio`     | unused                       | `settings.py:757` only (its sibling `min_aquarium_area_ratio` is read in `core/recording/frame_processing_pipeline.py`) |
| `ui_features.use_wizard_for_project_creation` | written but never read       | `settings.py:1087`, `config.yaml:472`; read only by `tests/test_settings.py:67,255` and documented as a switch in `docs/wiki/*` and `docs/tutorials/first_tracking_run.md:9`, which tell users to set it to bring the wizard back; no code branches on it, so the documented switch does nothing |
| `performance.max_parallel_videos`             | written but never read       | `settings.py:1145`, `config.yaml:506`, documented in `CLAUDE.md:586`, `docs/reference/QUICK_REFERENCE.md:193`, `docs/wiki/user-guide/FAQ.md:522`, `TROUBLESHOOTING.md:434`. Tests set `settings.processing.max_parallel_videos` (a different section, which does not have the field) on mocks. The sibling `performance.max_parallel_plots` is read by `analysis/visualization_generator.py:1279` |
| `yolo_model.animal_confidence_threshold`      | refuted (false positive)     | read by `settings.resolve_animal_confidence` through `getattr` |

No other leaf field is without a reader: the remaining 115 have at least one reader in `src/`.
The weakest are single-site fields (for instance `weights.top_down.det_filename`,
`yolo_model.device`, `logging.levels`, `camera.max_reconnect_attempts`); those are read, so they
are not listed. Limit: a one-hit match proves a textual reader, not that the reader is reachable.

Decision needed per field: delete (and drop it from `config.yaml` and the docs), or wire it up.
Deleting the three documented ones (`use_wizard_for_project_creation`, `max_parallel_videos`,
`auto_stop_on_limit`/`show_countdown` if the live dialog should honour them) also means fixing the
documentation that advertises them. Because the model uses `extra="forbid"`, removing a field makes
an existing `config.local.yaml` that sets it fail to load; keep a deprecation shim for one release.

**Status:** reported.

### A7-C-08 — `load_settings()` outside the composition root

| Site                                  | Injected settings available?                                          | Effect today |
| ------------------------------------- | --------------------------------------------------------------------- | ------------ |
| `ui/wizard/calibration_step.py:292-294` | Yes, indirectly. `CalibrationStep.__init__` takes no `settings_obj`, but `WizardDialog` holds `self.settings` (`wizard_dialog.py:113`, optional) and already passes it to `LiveConfigStep` and `ModelSelectionStep` (`wizard_dialog.py:156,170`). The call is in `build_ui`, not at import. | The behavioural defaults (thigmotaxis and geotaxis distances, zone counts, perspective, geotaxis mode, `max_plausible_speed_cm_s`) come from a fresh read of `config.yaml` + `config.local.yaml` on every wizard build. An in-memory settings object that differs from the files (edits applied but not saved, a test double, the settings the app was started with) is ignored, so the wizard can show different defaults from the rest of the session. The new-project wizard runs before any project override exists, so no per-project override is lost today. |
| `i18n.py:147`                         | No, by design. `_resolve_language_from_environment()` is the fallback when `install()` never ran (library/CLI/test path); i18n loads before the DI container exists (`CLAUDE.md`, i18n section). | None in the app: `install()` receives the language from `app_runner` after `load_settings()`. Only the script/test path reads the disk, which is its purpose. Keep. |
| `io/frame_source_factory.py:188,202`  | n/a: both sit inside `if __name__ == "__main__":` (manual smoke test of the factory). | None. The settings are passed on as `settings_obj=settings`. |
| `io/live_stream_source.py:169`        | n/a: inside `if __name__ == "__main__":`. | None. |

Two further sites the register did not list, both also demo code: `io/arduino.py:313` (`main()`,
a manual serial test) and `ui/dialogs/live_analysis_dialog.py:1162` (`__main__` block). Neither
affects the app. The only call that matters is `calibration_step.py`: the fix is to add an
optional `settings_obj` to `CalibrationStep`, pass `self.settings` from `WizardDialog`, and fall
back to `load_settings()` only when it is `None`. Not done here: it changes a constructor signature
that the wizard tests build directly, and the task scoped this item to reporting.

**Status:** reported.

### A7-C-09 — Other docs that contradict the code

Measured values: 10033 tests collected; 8635 fast; 1374 `gui`; 24 `slow`.

| Where | Claimed | True | Status |
| ----- | ------- | ---- | ------ |
| `CLAUDE.md:60,62,63,64` | ~2778 fast, ~949 gui, ~35 slow, ~3660+ all with "6-7 min" | ~8635, ~1374, ~24, ~10033; the duration was removed because it was not re-measured for the full run | fixed |
| `docs/testing/TEST_MAP.md:207-210` | same four numbers | same corrections | fixed |
| `.copilot-impact-map.yaml:682,703` | gui "~949", full "~2778" | ~1374, ~10033 | fixed |
| `docs/guides/developer/ERROR_HANDLING.md` (every reference) | `src/zebtrack/core/processing_worker.py` | the file is `src/zebtrack/core/video/processing_worker.py` | fixed |
| `docs/guides/developer/ERROR_HANDLING.md:413` | `tests/test_processing_worker.py` | `tests/core/test_processing_worker_unit.py` and `tests/core/video/test_processing_worker_extended.py` | fixed |
| `docs/guides/developer/ERROR_HANDLING.md` line numbers (`:28-90`, `:272-297`, `:301-317`, `:302-315`, `:15-50`) | fixed line ranges in `processing_worker.py` and `__main__.py` | the ranges predate the move and refactors; `__main__.py` is now 78 lines and only delegates to `ApplicationBootstrapper` (logging is configured in `logging_config.py`, not at `__main__.py:15-50`) | reported: needs a rewrite, not a number swap |
| `docs/guides/developer/ERROR_HANDLING.md:153,411` | `SerialError` lives in `io/arduino_manager.py` | `arduino_manager.py:37` defines `_FallbackSerialError` for when `pyserial` is missing; the real class comes from `pyserial` | reported |
| `.claude/commands/test-fast.md:2,18`, `.cursor/rules/main.mdc:35`, `.github/copilot-instructions.md:46-47`, `.vscode/settings.json:94` | ~2778 fast ("<2 min"), ~949 gui, ~3660+ | same stale counts; "<2 min" is wrong too (the fast suite takes about 6 minutes) | reported: tooling files outside the scope of this task |
| `.copilot-impact-map.yaml:703-705` | full run "6-7 minutes", coverage "45% (Linux CI), 28% (Windows CI)" | the coverage gates are a ratchet documented in `docs/testing/COVERAGE_BASELINE.md` (`CLAUDE.md` quotes 57/32.5/51); the time was not re-measured | reported |
| `docs/testing/TEST_MAP.md` (source-to-test rows) | not audited row by row | the new impact-map test does not cover this file; the paths in its tables should get the same existence test | reported |

## Verification

Run from the worktree with `source scripts/wt-env.sh`: see the commit messages and the final
report of the session for the exact `ruff`, `mypy` and `pytest` results.

## Guard that stays (2026-11-19)

`tests/quality/test_settings_fields_have_readers.py` walks `Settings.model_fields` recursively
(145 fields, sections included, into `Optional`/`list`/`dict` models) and fails on a field whose
name nothing in `src/zebtrack` reads: attribute load, `getattr`/`hasattr` argument, subscript or
`.get()` key, or a string key constant (`_KEY_ENTER: Final[str] = "roi_flutter_enter_frames"`,
the way `roi_rule_resolver` reads the ROI fields). An assignment is a store, not a reader. The
match is by name, like A7-C-07, so a field whose name is read elsewhere looks read.

`ALLOWED_UNREAD` (shrink-only, stale entries fail) holds the five fields of A7-01 with the
`extra="forbid"` reason, and two this guard found on its first run, missed by A7-C-07 because
its textual search counted a write as a reader:

| Field | Evidence |
| --- | --- |
| `performance.enable_parallel_analysis` | Added with the comment `# (futuro)` in the first commit; never read. `core/app_runner.py` sets it to `False` when the startup benchmark recommends low memory, and `docs/performance/HARDWARE_OPTIMIZATION_GUIDE.md` promises "Sequential analysis"; `CLAUDE.md` lists it under Parallelism. |
| `performance.memory_mode` | Written by the same benchmark step (`settings_obj.performance.memory_mode = rec.recommended_memory_mode`); read by nothing. The guide promises "Reduces peak RAM usage". |

The low-memory mode therefore changes `openvino.batch_nireq` (which is read) and nothing
through these two fields (register row A7-02).

### Proof that the guard sees

Added `planted_unread_knob: int = 0` to the performance section of `src/zebtrack/settings.py`,
right above `enable_parallel_analysis`. The guard failed with `performance.planted_unread_knob`.
Restored by copy; SHA-256 prefix `6ba43b799f3e3e69` before and after.
