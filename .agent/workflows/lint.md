---
description: Lint and format code with Ruff
---

# Lint Code Workflow

// turbo-all

## Quick Fix

1. Check and auto-fix linting issues:

```bash
poetry run ruff check . --fix
```

1. Format code:

```bash
poetry run ruff format .
```

## Analysis Only

1. Check without fixing:

```bash
poetry run ruff check .
```

1. Check specific file:

```bash
poetry run ruff check path/to/file.py
```

## Pre-commit

1. Run all pre-commit hooks:

```bash
poetry run pre-commit run --all-files
```
