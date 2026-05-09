---
description: Run the full pre-merge check — Ruff lint + fast tests
allowed-tools: Bash(poetry run ruff check:*), Bash(poetry run pytest:*)
---

Run the standard pre-merge gate:

```bash
poetry run ruff check .
```

```bash
poetry run pytest -q
```

After both finish, summarize in 3-5 bullets:

1. Ruff: PASS / FAIL (count of lint errors if any)
2. Pytest: PASS / FAIL (totals: passed / failed / skipped)
3. Any unexpected warnings worth surfacing.
4. If anything failed, point at the exact files/tests and propose the next action.
5. Do **not** auto-fix or auto-commit — report only.

For a deeper check before merging a sensitive change, also run mypy manually:

```bash
poetry run mypy src/zebtrack
```

Mypy isn't included by default because it's the slowest and noisiest of the three.
