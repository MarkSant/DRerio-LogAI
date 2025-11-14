# Developer Automation Helper

This repo now ships with `scripts/dev_automation.py`, a lightweight CLI that
runs common lint/test pipelines so both humans and Copilot can trigger
consistent flows with a single command (or VS Code task).

## Quick start

```bash
poetry run python scripts/dev_automation.py fast
```

The default `fast` suite runs `ruff check` followed by `pytest -q`. The script
runs inside the existing Poetry environment, so no extra activation steps are
required.

## Available suites

| Suite | Description |
| --- | --- |
| `fast` | `ruff check .` + `pytest -q` |
| `full` | `ruff check .` + `pytest -n0` (serial full suite) |
| `gui` | `pytest -m gui -n0` |
| `coverage` | `ruff check .` + `pytest --cov=zebtrack --cov-report=html` |

Add `--skip-lint` to avoid the `ruff` step for any suite.

## Targeted runs

- `--changed-tests` automatically appends a pytest invocation for modified
  files under `tests/` based on `git status`.
- `--tests path/to/test_file.py tests/dir` appends explicit pytest targets.
- `--pytest-cmd "-m gui -n0"` appends a *raw* pytest command (provide only the
  argument string). You can pass the flag multiple times to queue several
  commands, ensuring any ad-hoc pytest invocation is captured by the
  automation script.
- `--keep-going` keeps executing remaining steps even if one fails.
- `--dry-run` prints the commands without executing them.

## VS Code tasks

Three new tasks wire into this script so the Copilot agent (or you) can run
flows without typing commands manually:

- **Dev Flow: Fast** → `poetry run python scripts/dev_automation.py fast`
- **Dev Flow: Full** → `poetry run python scripts/dev_automation.py full`
- **Dev Flow: GUI** → `poetry run python scripts/dev_automation.py gui`

You can trigger these via the VS Code command palette ("Run Task") or ask the
agent to run them.

## Extending

Add new suites by editing `_build_suite` inside `scripts/dev_automation.py`.
Use the optional `tags` tuple to mark steps as `"lint"` or other future
selectors so command-line filters keep working.
