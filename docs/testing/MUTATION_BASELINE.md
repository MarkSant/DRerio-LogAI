# Mutation baseline

Coverage says a line RAN. It never says a wrong value on that line would have failed a test.

`scripts/mutation_check.py` closes that gap: it applies a curated defect from
`scripts/mutation_catalog.yaml`, runs the tests that claim to cover it, and records whether they
noticed.

```bash
poetry run python scripts/mutation_check.py --all
poetry run python scripts/mutation_check.py --changed-since origin/main   # what CI runs
poetry run python scripts/mutation_check.py --module mask_capture --verbose
poetry run python scripts/mutation_check.py --list
```

## Why this exists

`core/services/weight_manager.py` had eleven test files. Five deliberate defects were introduced
and the tests re-run per file group:

| Defect                                            | Parts 1–3 | Parts 8–11 |
| ------------------------------------------------- | --------- | ---------- |
| default seg/det target inverted                   | 4 failing | none       |
| `is_default_{method}_{target}` key order swapped  | 5 failing | none       |
| `"fish"` alias dropped                            | 2 failing | none       |
| lateral perspective detection broken              | 3 failing | none       |
| `_oi.pt → det` classification broken              | 3 failing | none       |

Thirty tests in the four most recent files, every line of the module executed, **zero** defects
detected. That is the failure mode this file guards against, and it is invisible to any coverage
percentage.

## Current baseline

Measured 2026-11-04 on `release/8.0` (v8.0.0) with `--all`. **312 mutations in
65 blocks, 312 killed, 0 survivors.** Before
v8 the catalogue had 58 mutations in 15 blocks; the v8 fronts added the blocks marked (v8) and
extended `external_trigger_gate` (4 → 8) and `weight_manager` (5 → 10).

| Block | Module | Mutations | Killed |
| --- | --- | --- | --- |
| `mask_capture` | `core/services/mask_capture.py` | 4 | 4 |
| `external_trigger_gate` (v8 extended) | `core/services/external_trigger_gate.py` | 8 | 8 |
| `session_duration_resolver` | `core/services/session_duration_resolver.py` | 3 | 3 |
| `experiment_notes` | `core/services/experiment_notes.py` | 4 | 4 |
| `arduino_bindings` | `core/services/arduino_bindings.py` | 2 | 2 |
| `roi_rule_resolver` | `core/services/roi_rule_resolver.py` | 3 | 3 |
| `arena_detection_policy` | `core/services/arena_detection_policy.py` | 5 | 5 |
| `project_settings_snapshot` | `core/services/project_settings_snapshot.py` | 3 | 3 |
| `weight_manager` (v8 extended) | `core/services/weight_manager.py` | 10 | 10 |
| `live_calibration_scale` | `core/services/live_calibration_scale.py` | 4 | 4 |
| `arena_candidate_selection` | `core/detection/arena_candidate_selection.py` | 4 | 4 |
| `zone_scaler` | `core/detection/zone_scaler.py` | 3 | 3 |
| `animal_confidence` | `settings.py` | 3 | 3 |
| `aquarium_detector` | `core/detection/aquarium_detector.py` | 7 | 7 |
| `sharp_turn_threshold` | `analysis/analysis_service.py` | 3 | 3 |
| `zone_autoimport_policy` | `core/services/zone_autoimport_policy.py` | 5 | 5 |
| `class_aliases` (v8) | `core/detection/class_aliases.py` | 4 | 4 |
| `v8_settings` (v8) | `settings.py` | 2 | 2 |
| `conditions_model` (v8) | `core/conditions/model.py` | 5 | 5 |
| `conditions_evaluator` (v8) | `core/conditions/evaluator.py` | 5 | 5 |
| `conditions_artifact` (v8) | `core/conditions/artifact.py` | 5 | 5 |
| `time_base` (v8) | `analysis/time_base.py` | 8 | 8 |
| `roi_latency` (v8) | `analysis/roi.py` | 9 | 9 |
| `video_duration` (v8) | `analysis/analysis_service.py` | 3 | 3 |
| `report_fps` (v8) | `coordinators/report_generation_coordinator.py` | 3 | 3 |
| `class_roles` (v8) | `core/detection/class_roles.py` | 6 | 6 |
| `worker_model_resolution` (v8) | `core/services/worker_model_resolution.py` | 5 | 5 |
| `processing_worker_model_spec` (v8) | `core/video/processing_worker.py` | 3 | 3 |
| `single_detector_class_roles` (v8) | `core/detection/single_detector.py` | 6 | 6 |
| `multi_aquarium_detector_class_roles` (v8) | `core/detection/multi_aquarium_detector.py` | 4 | 4 |
| `detection_post_processor_class_roles` (v8) | `core/detection/detection_post_processor.py` | 4 | 4 |
| `detector_service_class_roles` (v8) | `core/services/detector_service.py` | 2 | 2 |
| `openvino_nms` (v8) | `plugins/openvino_detector.py` | 3 | 3 |
| `project_v8_migrations` (v8) | `core/project/project_lifecycle_manager.py` | 4 | 4 |
| `project_workflow_model_selection` (v8) | `core/project/project_workflow_service.py` | 2 | 2 |
| `conditions_presets` (v8) | `core/conditions/presets.py` | 7 | 7 |
| `analysis_window_panel` (v8) | `ui/components/analysis_window_panel.py` | 15 | 15 |
| `wizard_templates` (v8) | `ui/wizard/templates.py` | 8 | 8 |
| `object_capture` (v8) | `core/services/object_capture.py` | 3 | 3 |
| `object_sidecar` (v8) | `io/object_sidecar.py` | 7 | 7 |
| `recorder_object_sidecar` (v8) | `io/recorder.py` | 10 | 10 |
| `processing_worker_object_sidecar` (v8) | `core/video/processing_worker.py` | 3 | 3 |
| `parquet_import_sidecars` (v8) | `core/project/parquet_io_manager.py` | 2 | 2 |
| `session_output_labels` (v8) | `utils/report_files.py` | 2 | 2 |
| `class_roles_panel` (v8) | `ui/components/class_roles_panel.py` | 15 | 15 |
| `overlay_roles` (v8) | `ui/components/canvas/overlay_roles.py` | 7 | 7 |
| `arduino_event_stamp` (v8) | `io/arduino_manager.py` | 3 | 3 |
| `condition_runtime` (v8) | `core/recording/condition_runtime.py` | 8 | 8 |
| `arduino_event_routing` (v8) | `core/main_view_model.py` | 1 | 1 |
| `arduino_trigger_session` (v8) | `coordinators/live_camera_session_coordinator.py` | 3 | 3 |
| `live_window_pipeline` (v8) | `core/recording/frame_processing_pipeline.py` | 9 | 9 |
| `live_post_processor_v8` (v8) | `core/recording/live_analysis_post_processor.py` | 4 | 4 |
| `analysis_window_cut` (v8) | `analysis/behavior.py` | 5 | 5 |
| `analysis_window_cut_roi` (v8) | `analysis/roi.py` | 6 | 6 |
| `window_observations` (v8) | `analysis/window_observations.py` | 8 | 8 |
| `analysis_window_service` (v8) | `analysis/analysis_window_service.py` | 8 | 8 |
| `analysis_window_cut_service` (v8) | `analysis/analysis_service.py` | 5 | 5 |
| `metrics_cache_window` (v8) | `analysis/metrics_cache.py` | 1 | 1 |
| `report_window_columns` (v8) | `analysis/data_transformer.py` | 4 | 4 |
| `word_report_window` (v8) | `analysis/reporters/word_reporter.py` | 4 | 4 |
| `visualization_window_axes` (v8) | `analysis/visualization_generator.py` | 2 | 2 |
| `reporter_context_window` (v8) | `analysis/reporters/reporter_context.py` | 1 | 1 |
| `report_window_wiring` (v8) | `coordinators/report_generation_coordinator.py` | 3 | 3 |
| `pipeline_runner_window` (v8) | `core/video/analysis_pipeline_runner.py` | 1 | 1 |
| `live_post_analysis_window` (v8) | `core/recording/live_analysis_post_processor.py` | 3 | 3 |

The sharp-turn entry was added with the fix for a threshold that never reached the number: the
metrics table was computed with a hardcoded `90.0` while the plot used the DTO default of `45.0`.
Its `threshold-ignored-by-the-computation` mutation restores exactly that literal, so the defect
cannot return silently — which matters because it survived for as long as it did by being
invisible rather than by being hard.

The `zone_autoimport_policy` entry was added in 2026-09 with the fix for zones that adopted
themselves: a pre-recorded project built over a folder holding an earlier study's
`1_ProcessingArea_*`/`2_AreasOfInterest_*` loaded those polygons on the first double-click,
even though the wizard's import had been declined. Nothing raised and nothing degraded
visibly — the reports came out complete, measured against the previous experiment's arena.
That is precisely the shape this catalogue exists for, so all five branches of the new
decision are pinned.

The two detection entries were added in 2026-09 together with the fix for "segmentation returned
the whole screen". Four of their ten mutations SURVIVED on first run — the degeneracy filter and
the entire low-confidence retry branch had no test that could fail. That is the intended use of
this tool: the tests were written to kill them, and the mutations stay in the catalogue.

The v8 blocks guard the contracts that degrade silently by design: a class with no role that
would be tracked by position, a sidecar that would be written only when something was
detected, a window evaluated on the processing clock instead of the capture clock, a latency
censored without its flag, a window that would be reused after its inputs changed. Each one
produces plausible numbers when broken, which is exactly what a test count cannot see.

The catalogue covers the contracts `CLAUDE.md` flags as critical — the ones written to **degrade
silently** rather than raise. A silent degradation that no test detects is indistinguishable from
correct behaviour until the data is already wrong.

## Where it runs

| When | Command | Blocking |
| --- | --- | --- |
| Every PR and every push to `main` — step of the `test (ubuntu-latest, core)` job | `--changed-since HEAD^` | **yes** |
| Nightly, `mutation-catalogue` job in `stress-tests.yml` | `--all --json` | yes, opens an issue |

`--changed-since REF` keeps only the modules whose **source or test files** the diff touches. The
reason is arithmetic: each mutation is a fresh pytest process, and in this repository a fresh
process spends ~4 s importing `torch`/`torchvision`/`ultralytics` before running a single
assertion — the plugin registry is pulled in eagerly by `core/services/__init__.py`. The full
catalogue was 67 such processes before v8 (it is now 377):

| | Full catalogue | Scoped by diff |
| --- | --- | --- |
| pytest processes | 67 (14 baselines + 53 mutants) | 2–9 for a typical module |
| CI wall clock | 443 s, on the longest job | 0 s for ~76 % of changes |

That 76 % is measured, not assumed: of the last 25 commits on `main`, 6 touched a catalogued
source or test file. Paying seven minutes on the critical path for the other nineteen is what kept
the step at `continue-on-error` — and a check that cannot fail the build is a check nobody reads.

Scoping is exact for the defect a change introduces **in the module itself**, and blind to one
that arrives through a shared dependency. Three consequences, all deliberate:

- **The runner and `tests/conftest.py` widen the scope back to everything.** The first defines
  what a mutation is; the second owns the autouse fixtures every module's tests run under, and one
  neutered fixture can hide a defect in a module the diff never named.
- **A catalogue edit selects only the blocks it added or changed**, compared with the catalogue at
  the merge base (or at the ref itself on a shallow clone). A block that did not change, guarding a
  module the diff did not touch, cannot change its verdict. Until v8 any catalogue edit ran every
  module, and since every front appends its own blocks a front adding a dozen mutations re-ran over
  a hundred. If the base catalogue cannot be read, the scope widens to everything.
- **When git cannot answer** — an unfetched base on a shallow clone — the runner says so and runs
  the whole catalogue. It never degrades to running nothing: that would report success while
  checking nothing, which is the failure mode this whole file exists to prevent.
- **The nightly `--all` closes the rest.** Anything that drifts through a shared dependency is
  caught within a day, off the PR critical path.

CI passes `HEAD^` rather than a branch name because that is the correct baseline under both
triggers: on a `pull_request` the checked-out commit is the merge of the branch into the base, so
its first parent is the base tip; on a push to `main` it is the previous `main` commit. It requires
`fetch-depth: 2` on `actions/checkout` — with the default depth of 1 there is no parent to diff
against and the run falls back to the full catalogue.

## Rules

- **A survivor is a missing test.** Add the test. Never delete or weaken the mutation to get a
  green run — that converts a known hole into an unknown one.
- **A mutation must change behaviour**, not a log line or a comment, and its `find` string must
  appear exactly once in the file (the runner refuses an ambiguous patch, because which occurrence
  got hit would then depend on file layout).
- **Prefer inverting a decision to deleting a branch.** A deleted branch often fails to import, and
  then the tests "catch" it for the wrong reason.
- **Extend the catalogue when you add a silently-degrading contract.** If the code chooses to log
  and continue instead of raising, a mutation is the only thing that proves anyone would notice.

## Notes for maintainers

The runner is deliberately dependency-free and deterministic — no `mutmut`, no random operator
generation — so it behaves the same on the Windows development machine and on the Linux runners.

Two details it gets right, both learned the hard way:

- It parses pytest's outcome counts rather than the **exit code**. While `--cov-fail-under` lived
  in `pytest.ini`, every partial run exited non-zero, so an exit-code-based runner reported all
  mutations as killed and proved nothing.
- It patches and restores **bytes**, not text. Text I/O rewrote LF as CRLF on Windows, leaving four
  source files dirty in git after a run that changed nothing. The final `git status` check exists
  so that a restoration failure can never pass unnoticed.
- An **empty selection returns before anything else runs**. That final `git status` builds its
  pathspec from the selected sources, so with nothing selected the pathspec vanishes and git
  reports the whole repository — every unrelated edit in the working tree would be announced as a
  mutation leak and exit 2. Pinned by
  `tests/quality/test_mutation_check.py::test_empty_scope_exits_clean_without_running_anything`.
