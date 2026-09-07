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

Measured 2026-09-05. **53 mutations, 53 killed, 0 survivors.**

| Module                                            | Mutations | Killed |
| ------------------------------------------------- | --------- | ------ |
| `core/services/mask_capture.py`                   | 4         | 4      |
| `core/services/external_trigger_gate.py`          | 4         | 4      |
| `core/services/session_duration_resolver.py`      | 3         | 3      |
| `core/services/arduino_bindings.py`               | 2         | 2      |
| `core/services/roi_rule_resolver.py`              | 3         | 3      |
| `core/services/arena_detection_policy.py`         | 5         | 5      |
| `core/services/project_settings_snapshot.py`      | 3         | 3      |
| `core/services/weight_manager.py`                 | 5         | 5      |
| `core/services/live_calibration_scale.py`         | 4         | 4      |
| `core/detection/arena_candidate_selection.py`     | 4         | 4      |
| `core/detection/aquarium_detector.py`             | 7         | 7      |
| `core/detection/zone_scaler.py`                   | 3         | 3      |
| `settings.py` (animal confidence + atomic save)   | 3         | 3      |
| `analysis/analysis_service.py` (sharp-turn resolver) | 3      | 3      |

The sharp-turn entry was added with the fix for a threshold that never reached the number: the
metrics table was computed with a hardcoded `90.0` while the plot used the DTO default of `45.0`.
Its `threshold-ignored-by-the-computation` mutation restores exactly that literal, so the defect
cannot return silently — which matters because it survived for as long as it did by being
invisible rather than by being hard.

The two detection entries were added in 2026-09 together with the fix for "segmentation returned
the whole screen". Four of their ten mutations SURVIVED on first run — the degeneracy filter and
the entire low-confidence retry branch had no test that could fail. That is the intended use of
this tool: the tests were written to kill them, and the mutations stay in the catalogue.

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
catalogue is 67 such processes:

| | Full catalogue | Scoped by diff |
| --- | --- | --- |
| pytest processes | 67 (14 baselines + 53 mutants) | 2–9 for a typical module |
| CI wall clock | 443 s, on the longest job | 0 s for ~76 % of changes |

That 76 % is measured, not assumed: of the last 25 commits on `main`, 6 touched a catalogued
source or test file. Paying seven minutes on the critical path for the other nineteen is what kept
the step at `continue-on-error` — and a check that cannot fail the build is a check nobody reads.

Scoping is exact for the defect a change introduces **in the module itself**, and blind to one
that arrives through a shared dependency. Three consequences, all deliberate:

- **The runner, the catalogue and `tests/conftest.py` widen the scope back to everything.** The
  first two define what a mutation is; the third owns the autouse fixtures every module's tests run
  under, and one neutered fixture can hide a defect in a module the diff never named.
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
