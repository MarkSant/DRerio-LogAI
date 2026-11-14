# Mutation baseline

Coverage says a line RAN. It never says a wrong value on that line would have failed a test.

`scripts/mutation_check.py` closes that gap: it applies a curated defect from
`scripts/mutation_catalog.yaml`, runs the tests that claim to cover it, and records whether they
noticed.

```bash
poetry run python scripts/mutation_check.py --all
poetry run python scripts/mutation_check.py --changed-since origin/main   # what CI runs
poetry run python scripts/mutation_check.py --all --jobs 4                # override the default
poetry run python scripts/mutation_check.py --module mask_capture --verbose
poetry run python scripts/mutation_check.py --list
```

Exit codes: `0` every mutation killed, `1` at least one survivor, `2` the run cannot vouch for
its verdicts (a red baseline, the runner's own tests failing, a copy that drifted from the
checkout or could not be built, the checkout edited during the run).

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

Measured 2026-11-05 on `release/8.0` (v8.0.0, `de65c06d`) with `--all`. **321 mutations in
70 blocks, 321 killed, 0 survivors**, with the serial runner and with the parallel one alike
(see [Speed](#speed)). Before v8 the catalogue had 58 mutations in 15 blocks; the v8 fronts added
the blocks marked (v8) and extended `external_trigger_gate` (4 → 8) and `weight_manager` (5 → 10).
The five `*_source_fps` / `*_tracker_fps` / `byte_tracker_lost_pool` blocks came with the fix for
issue #630 (ByteTrack using the source's real fps).

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
| `byte_tracker_lost_pool` (v8) | `tracker/byte_tracker.py` | 2 | 2 |
| `detection_post_processor_tracker_fps` (v8) | `core/detection/detection_post_processor.py` | 2 | 2 |
| `single_detector_source_fps` (v8) | `core/detection/single_detector.py` | 2 | 2 |
| `multi_aquarium_detector_source_fps` (v8) | `core/detection/multi_aquarium_detector.py` | 2 | 2 |
| `processing_worker_source_fps` (v8) | `core/video/processing_worker.py` | 1 | 1 |

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
| Every PR and every push to `main` — step of the `test (ubuntu-latest, core)` job | `--changed-since HEAD^ --jobs 4` | **yes** |
| Nightly, `mutation-catalogue` job in `stress-tests.yml` | `--all --jobs 4 --json` | yes, opens an issue |

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
that arrives through a shared dependency. The consequences, all deliberate:

- **`tests/conftest.py` widens the scope back to everything.** It owns the autouse fixtures
  every module's tests run under, and one neutered fixture can hide a defect in a module the diff
  never named. Its effect differs block by block, so a sample of blocks says nothing about the
  blocks left out.
- **A change to the runner (`scripts/mutation_check.py`) runs a sample, not the catalogue.** It
  runs the runner's own tests (`tests/quality/test_mutation_check.py`, in the checkout; failing
  ⇒ exit 2 before any mutant) and then **the first mutation of every block** (`mutations[0]`),
  added to whatever the diff selects in full. The reason is that a runner defect is uniform: a lost
  `PYTHONPATH`, a broken copy, a mis-parsed pytest summary or a scheduler that mixes up results
  breaks every block alike, and one mutant per block still pushes every source file and every test
  list in the catalogue through the new code. Until 2026-11 the runner forced the whole
  catalogue, which made the v8 release PR (#629) exceed the step's 20 minutes. Every mutant of
  every block still runs nightly.
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

## Speed

Every mutant costs a fresh pytest process, and most of that cost is interpreter start-up and
the `torch`/`ultralytics` imports (issue #643), not the tests. So the runner gets its speed from
running several processes at once, each in its own copy of the tree. `--jobs` defaults to one
per core, capped by free RAM at ~1.5 GB per process.

Measured 2026-11-05 on the development machine (Core Ultra 5 225H: 4 P + 10 E cores, 31 GB), full
catalogue (`--all`, 70 blocks, 391 pytest processes):

| Runner | Workers | Wall clock | Score |
| --- | --- | --- | --- |
| serial, mutant patched in the checkout (`de65c06d`) | 1 | 4010 s (66.8 min) | 321/321 |
| parallel, one copy per worker | 7 (default; RAM-bound) | 841 s (14.0 min) | 321/321 |

The two JSON reports list the same verdicts in the same order. Both runs shared the machine with
other work (the serial run overlapped the fast suite and another session's mutation runs, the
parallel run overlapped another session's GUI suite), so the 4.8× is indicative, not a
benchmark. The serial run took ~55 min when measured alone the day before.

**What CI should expect.** GitHub's `ubuntu-latest` runner has 4 vCPUs. To approximate it, six
blocks (48 pytest processes) were run pinned to four logical CPUs (`ProcessorAffinity = 0xF`):
533 s with `--jobs 1`, 169 s with `--jobs 4`, a **3.15×** speedup, 42/42 killed both times.
The PR #629 log gives the serial cost on the runner itself: 149 processes in 1212 s, ~8.1 s each.
Its diff against `main` selects 61 blocks in full (288 mutants), plus the runner sample for the
other 9 blocks: ~367 processes, ~2970 s serially, so **~16 min** at 3.15×, inside the step's 20.
If the runner's 4 vCPUs are two SMT cores the speedup will be lower; if the step comes close to
the limit, raising it to 30 still fits the job's 45 minutes (the steps before it took 12 min
in that run). The limit was left at 20 because none of these numbers comes from a run on the
GitHub runner itself.

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

Details it gets right, all learned the hard way:

- It parses pytest's outcome counts rather than the **exit code**. While `--cov-fail-under` lived
  in `pytest.ini`, every partial run exited non-zero, so an exit-code-based runner reported all
  mutations as killed and proved nothing.
- It never patches the checkout. Until 2026-11 it patched the real file and restored it in a
  `finally`; killing the process between the two left the mutant on disk, which happened twice
  during v8 and was restored by hand both times. Now each worker builds one copy of the tree
  (`src/`, `tests/`, `scripts/`, `resources/` and the root files, in a temporary directory) and
  every mutant it runs is applied there. The final check compares the checkout's sources with the
  bytes read when the run started. Comparing bytes, not `git status`, means a developer's own
  uncommitted edit to a catalogued source is not reported as a leak, and an empty selection cannot
  turn into a repository-wide pathspec.
- The copy's `src/` goes **first on `PYTHONPATH`**, and each new copy is probed once
  (`importlib.util.find_spec("zebtrack")` must resolve inside it) before any pytest runs there.
  The venv resolves `zebtrack` through `site-packages/drerio_logai.pth`, an absolute path to the
  main repository's `src/`, and `scripts/wt-env.sh` adds the worktree's. Without the prepend a
  pytest in the copy would import the unmutated checkout and every verdict would be about the wrong
  file. `test_the_pytest_in_a_copy_imports_the_copy_not_the_checkout` reproduces that trap with real
  pytest runs.
- A copy is **verified before each mutant** (its bytes must equal the checkout's) and its cached
  bytecode for the mutated file is dropped after applying and after restoring. CPython validates a
  `.pyc` by whole-second mtime and size, so a same-length mutant (`!=` for `==`) restored within
  one second could otherwise be served from the cache to the next run.
- It patches and restores **bytes**, not text. Text I/O rewrote LF as CRLF on Windows.
- Each worker's pytest gets its own `--basetemp`. The shared default (`pytest-of-<user>`) prunes
  old numbered directories, so one worker could delete another's `tmp_path` in the middle of a
  test.
- A block's mutants are queued **only after its baseline is green**, and a red baseline exits 2.
  Until 2026-11 it was a "skip" that left the exit code at 0, so a runner that broke every pytest
  would have reported a clean run scoring 0/0.
- Output and `--json` follow **catalogue order** whatever finishes first: a block's section is
  printed once it and every block before it are complete.
- An **empty selection returns before anything else runs**: no copy is built and no pytest
  starts. Pinned by
  `tests/quality/test_mutation_check.py::test_empty_scope_exits_clean_without_running_anything`.
