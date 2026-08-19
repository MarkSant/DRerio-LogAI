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

Measured on 2026-08-19 at `e313a5ed` (mega-batch 32), before any cleanup.

| Suite            | CI command                                             | Measured | Gate    |
| ---------------- | ------------------------------------------------------ | -------- | ------- |
| core (Linux)     | `pytest -m "not gui"`                                  | 58.19 %  | 57.0 %  |
| GUI (Linux)      | `pytest -m gui -n0`                                    | 33.18 %  | 32.5 %  |
| core (Windows)   | `pytest -m "not gui" --ignore=tests/ui`                | 51.92 %  | 51.0 %  |

The gate sits roughly one point below the measurement (0.7 pp for GUI, whose absolute headroom is
smallest). That margin absorbs the platform differences between this measurement (Windows) and the
Linux runners, plus GUI rerun flakiness — it is **not** room for a regression to hide in. Numbers came from `coverage-*.xml`
(`lines-covered / lines-valid`), and the authoritative Linux values come from CI:

```bash
gh run view <run-id> --log | grep "Required test coverage"
```

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
