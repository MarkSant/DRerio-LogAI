---
description: Run tests for the DRerio LogAI project
---

# Run Tests Workflow

// turbo-all

## Quick Test Run

1. Run all fast tests (excludes slow, gui, integration):

```bash
poetry run pytest -m "not slow and not gui and not integration"
```

1. Run specific test file:

```bash
poetry run pytest tests/test_<name>.py -v
```

1. Run tests matching keyword:

```bash
poetry run pytest -k "keyword" -v
```

## Full Test Suite

1. Run all tests including slow:

```bash
poetry run pytest --run-slow
```

1. Run GUI tests only:

```bash
poetry run pytest -m gui --run-gui
```

## Debugging

1. Run with verbose output and stop on first failure:

```bash
poetry run pytest -v -x --tb=short
```

1. Run with coverage:

```bash
poetry run pytest --cov=src/zebtrack --cov-report=html
```
