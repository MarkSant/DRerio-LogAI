# Mutation baseline

Coverage says a line RAN. It never says a wrong value on that line would have failed a test.

`scripts/mutation_check.py` closes that gap: it applies a curated defect from
`scripts/mutation_catalog.yaml`, runs the tests that claim to cover it, and records whether they
noticed.

```bash
poetry run python scripts/mutation_check.py --all
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

Measured 2026-08-26. **30 mutations, 30 killed, 0 survivors.**

| Module                                        | Mutations | Killed |
| --------------------------------------------- | --------- | ------ |
| `core/services/mask_capture.py`               | 4         | 4      |
| `core/services/external_trigger_gate.py`      | 4         | 4      |
| `core/services/session_duration_resolver.py`  | 3         | 3      |
| `core/services/arduino_bindings.py`           | 2         | 2      |
| `core/services/roi_rule_resolver.py`          | 3         | 3      |
| `core/services/arena_detection_policy.py`     | 5         | 5      |
| `core/services/weight_manager.py`             | 5         | 5      |
| `core/services/live_calibration_scale.py`     | 4         | 4      |

The catalogue covers the contracts `CLAUDE.md` flags as critical — the ones written to **degrade
silently** rather than raise. A silent degradation that no test detects is indistinguishable from
correct behaviour until the data is already wrong.

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
