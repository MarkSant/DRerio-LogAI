---
description: Run the fast test suite (excludes GUI and slow markers; ~2778 tests, <2 min)
argument-hint: [optional pytest args, e.g. -k pattern, path]
allowed-tools: Bash(poetry run pytest:*)
---

Run the fast pytest subset for ZebTrack-AI:

```bash
poetry run pytest -q $ARGUMENTS
```

Notes:

- Default markers exclude `gui` and `slow` automatically (configured in `pyproject.toml`).
- Pass extra args to narrow the scope, e.g. `/test-fast tests/coordinators/` or `/test-fast -k multi_aquarium`.
- For GUI tests, use `/test-gui` (if defined) or `poetry run pytest -m gui -n0` directly.
- For everything (~3660+ tests, 6-7 min): `poetry run pytest -m "" -n0`.

After it finishes, report only failures or surprising warnings — don't paste the full output.
