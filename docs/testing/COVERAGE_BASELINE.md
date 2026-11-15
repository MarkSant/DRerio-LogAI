# Coverage baseline and ratchet

The coverage gates are a **ratchet**: they only ever go up. A PR that raises coverage raises the
threshold in the same PR, so the gain is locked in and cannot quietly erode.

## Why this file exists

Between PRs #482 and #509, 28 "mega-batch" test PRs added roughly 1 500 test functions. The gates
never moved. `git log -S"cov-fail-under"` shows no change to `50 / 32 / 44` across the whole
series, so none of that work was ever protected — deleting half of it would still have left CI
green.

Two things made the drift invisible:

1. `--cov-fail-under=50` sat in the `addopts` of `pytest.ini`, so **every** partial local run
   printed `FAIL Required test coverage of 50% not reached`. The message was about the 99 % of the
   suite that had not run, so developers learned to ignore the line — and with it the real signal.
   The threshold now lives only in `.github/workflows/ci.yml`, where the full suite actually runs.
2. Narrowing `--cov` to a single module (the natural way to ask "did this batch cover anything?")
   crashed during collection with `AttributeError: module 'cv2.dnn' has no attribute 'DictValue'`.
   `tests/conftest.py` now imports `cv2` eagerly, which fixes the import order.

## Current baseline

Measured by CI on 2026-11-14 at `ec86f146` (PR #717, the TASK-087 coverage campaign). The
previous baseline, 2026-08-19 at `e313a5ed`, was 58.19 / 33.18 / 51.92 %.

| Suite            | CI command                                             | Measured | Gate    |
| ---------------- | ------------------------------------------------------ | -------- | ------- |
| core (Linux)     | `pytest -m "not gui"`                                  | 66.32 %  | 65.0 %  |
| GUI (Linux)      | `pytest -m gui -n0`                                    | 36.12 %  | 35.5 %  |
| core (Windows)   | `pytest -m "not gui" --ignore=tests/ui`                | 58.24 %  | 57.0 %  |

The gate sits roughly one point below the measurement (0.7 pp for GUI, whose absolute headroom is
smallest). That margin absorbs the platform differences between this measurement (Windows) and the
Linux runners, plus GUI rerun flakiness — it is **not** room for a regression to hide in. Numbers came from `coverage-*.xml`
(`lines-covered / lines-valid`), and the authoritative Linux values come from CI:

```bash
gh run view <run-id> --log | grep "Required test coverage"
```

## Per-package floors

One global number cannot see a package eroding: with ~60 000 statements, `plugins/` could lose
every test it has and move the core gate by one point. Packages that a focused campaign has raised
therefore get a floor of their own, checked right after the core suite on Linux:

```bash
python scripts/coverage_summary.py coverage-core.xml \
    --fail-under plugins=94 --fail-under utils=92 \
    --fail-under core.viewmodels=96 --fail-under core.video=94
```

| Package    | Before (`b03e5546`) | Measured (2026-11-14) | Floor  |
| ---------- | ------------------- | --------------------- | ------ |
| `plugins`  | 70.9 %              | 96.7 %                | 94.0 % |
| `utils`    | 66.4 %              | 97.5 %                | 92.0 % |
| `core.viewmodels` | 63.7 %       | 99.2 %                | 96.0 % |
| `core.video` | 80.1 %            | 97.3 %                | 94.0 % |

A floor covers the package and its sub-packages, fails with exit code 1, and exits 2 when the
package is not in the report at all — a typo must not pass as "nothing to check". The margin under
the measurement absorbs the platform difference between this measurement (Windows) and the Linux
runner; like the global gate, it is not room for a regression.

### Where the rest stands

Line and branch coverage of the core suite (`pytest -m "not gui" --cov-branch`), measured on
Windows on 2026-11-14. Branch coverage is recorded here for reference only: the CI gates are still
line-only, so these numbers are not directly comparable with the table above.

| Package                        | Line    | Branch  | Statements | Missed |
| ------------------------------ | ------- | ------- | ---------- | ------ |
| `ui.dialogs`                   | 24.4 %  | 16.8 %  | 4 578      | 3 463  |
| `ui.wizard`                    | 27.2 %  | 16.2 %  | 4 637      | 3 378  |
| `ui.components.project_views`  | 33.8 %  | 15.8 %  | 1 531      | 1 014  |
| `ui.components`                | 35.3 %  | 25.5 %  | 10 565     | 6 837  |
| `ui.builders`                  | 46.3 %  | 37.4 %  | 872        | 468    |
| `ui.components.canvas`         | 50.4 %  | 37.2 %  | 1 939      | 961    |
| `core.viewmodels`              | 63.7 %  | 39.3 %  | 868        | 315    |
| `ui` (root)                    | 66.9 %  | 38.4 %  | 2 365      | 782    |
| `core.project`                 | 73.7 %  | 60.1 %  | 4 359      | 1 145  |
| `core.video`                   | 80.1 %  | 61.7 %  | 1 875      | 374    |
| `core.recording`               | 82.5 %  | 70.5 %  | 3 144      | 550    |
| `core` (root)                  | 83.8 %  | 62.4 %  | 1 555      | 252    |
| `io`                           | 87.1 %  | 82.5 %  | 2 077      | 267    |
| `coordinators`                 | 87.5 %  | 72.3 %  | 6 436      | 806    |
| top-level modules              | 90.3 %  | 81.0 %  | 936        | 91     |
| `tracker`                      | 91.3 %  | 81.2 %  | 578        | 50     |
| `core.detection`               | 91.6 %  | 81.6 %  | 2 498      | 209    |
| `analysis`                     | 92.4 %  | 83.4 %  | 3 893      | 294    |
| `core.services`                | 92.9 %  | 88.4 %  | 3 691      | 262    |
| `analysis.reporters`           | 92.9 %  | 84.8 %  | 649        | 46     |
| `plugins`                      | 96.7 %  | 93.5 %  | 675        | 22     |
| `utils`                        | 97.5 %  | 97.1 %  | 1 369      | 34     |
| `core.conditions`              | 100 %   | 100 %   | 654        | 0      |

The UI packages are low in this table partly by construction: it is the core suite, and the GUI
suite (`-m gui`) is what exercises them.

`__init__.py` files are measured since 2026-11-14. They used to be omitted, which hid the lazy
plugin registry and `utils.calculate_sha256`/`set_seed` from every number on this page. The global
gates in the table above were re-measured by CI with that change included.

## Raising the gate

1. Run the suite for the affected matrix leg with `--cov-fail-under=0`.
2. Read the real number out of the XML, not the terminal summary:

   ```bash
   python -c "import xml.etree.ElementTree as ET; r=ET.parse('coverage-core.xml').getroot(); print(float(r.attrib['line-rate'])*100)"
   ```

3. Update the value in `.github/workflows/ci.yml` **and** the table above in the same PR.

`scripts/coverage_summary.py` reads `coverage.xml` and prints the per-package breakdown, which is
the fastest way to see where a subsystem is actually weak.

## What the number does not tell you

Coverage says a line RAN. It never says a wrong value on that line would have failed a test. An
audit of `weight_manager` found four test files whose 30 tests executed the module end to end and
detected **none** of five deliberately introduced defects. Line coverage was perfect; behavioural
coverage was zero.

That is what `scripts/mutation_check.py` measures — see
[`MUTATION_BASELINE.md`](MUTATION_BASELINE.md). Treat the two as a pair: the ratchet stops coverage
falling, the mutation score stops it becoming meaningless.
