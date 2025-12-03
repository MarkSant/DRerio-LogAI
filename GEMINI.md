# Gemini Project Context: ZebTrack-AI

This document provides essential context for the Gemini AI assistant to effectively collaborate on the ZebTrack-AI project.

## 1. Project Overview

ZebTrack-AI is a Python-based application for real-time zebrafish tracking and behavioral analysis. It utilizes computer vision models (like YOLO via Ultralytics and OpenVINO) for detection and tracking. The application has a GUI built with Tkinter and a sophisticated architecture involving services, state management, and dependency injection.

## 2. Core Technologies

- **Programming Language:** Python 3.11+
- **Dependency Management:** Poetry (`poetry.lock`, `pyproject.toml`)
- **Testing Framework:** Pytest (`pytest.ini`, `tests/`)
- **Linter & Formatter:** Ruff (`.ruff_cache`, configured in `pyproject.toml`)
- **Pre-commit Hooks:** Managed via `.pre-commit-config.yaml` to enforce standards before commits.
- **GUI Framework:** Tkinter (with ttkbootstrap)
- **Computer Vision:** Ultralytics (YOLO), OpenVINO, OpenCV.

## 3. Development Workflow

### Setup
To set up the development environment, run:
```bash
poetry install
```

### Running the Application
To run the main application GUI, use the script defined in `pyproject.toml`:
```bash
poetry run zebtrack
```

### Running Tests
The project has a comprehensive test suite. Run all tests using:
```bash
poetry run pytest
```
For specific tests, you can pass the file path, e.g., `poetry run pytest tests/test_state_manager.py`.

### Linting and Formatting
Code quality is maintained with Ruff. To check for issues, run:
```bash
poetry run ruff check .
```
To automatically fix issues, run:
```bash
poetry run ruff check . --fix
```

## 4. Key Architectural Concepts

- **State Management:** The application uses a central `StateManager` to manage application state immutably. See `docs/architecture/STATE_MANAGEMENT_GUIDE.md`.
- **Dependency Injection:** Services are injected into components to promote loose coupling. See `docs/architecture/DEPENDENCY_INJECTION_GUIDE.md`.
- **Event Bus:** A system for cross-component communication.
- **Service Layer:** Business logic is encapsulated in services (e.g., `DetectorService`, `ArduinoManager`).
- **Coordinator Layer (Phase 3):** Super coordinators consolidate orchestration: `ProcessingCoordinator`, `HardwareCoordinator`, `SessionCoordinator`, `ProjectLifecycleCoordinator`. See `docs/architecture/SYSTEM_INTEGRATION_MAP.md`.
- **UIScheduler vs UICoordinator:** `core/ui_scheduler.UIScheduler` schedules Tkinter updates via `root.after()`. `ui/ui_coordinator.UICoordinator` is the EventBus mediator. Different purposes, no conflict.

## 5. Important Rules & Conventions

1.  **Adhere to Existing Patterns:** Before adding new code, analyze the surrounding files to understand and replicate the existing architectural and styling patterns.
2.  **Test Everything:** All new features, bug fixes, or refactors must be accompanied by corresponding tests. The project relies heavily on `pytest` and `pytest-mock`.
3.  **Imports:** Follow the existing import structure (standard library, third-party, then project-specific imports, sorted alphabetically).
4.  **Immutability:** Respect the immutable state management pattern. Do not mutate state objects directly.
5.  **Configuration:** Application settings are managed via `config.yaml`. Do not hardcode configuration values.
6.  **Documentation:**
    *   **CRITICAL - System Map:** See `docs/architecture/SYSTEM_INTEGRATION_MAP.md` for strict contracts on Event Bus payloads, component dependencies, and control flows. **Read this before debugging integration issues.**
    *   **Architecture:** Refer to `docs/architecture/` for in-depth information on architecture (e.g., `ARCHITECTURE_V4.md`), developer guides, and decision logs.

7. **Documentation Maintenance (Meta-Protocol):**
    *   **Mandatory Updates:** You MUST update `docs/architecture/SYSTEM_INTEGRATION_MAP.md` whenever you:
        *   Add, remove, or modify an Event Bus event (`Events.*`).
        *   Change payload structures (keys, types).
        *   Alter cross-component dependencies or injection graphs.
        *   Refactor critical control flows (e.g., Analysis, Cancellation, Saving).
    *   **Discovery:** If you discover undocumented behavior or "hidden" events while debugging, add them to the map immediately. Treat the map as a living part of the codebase, not a static artifact.

## 6. 📋 Documentation Standards

When creating or updating documentation, follow these rules to maintain organization:

### Folder Structure (MANDATORY)

| Folder | Purpose | Naming Convention |
|--------|---------|-------------------|
| `docs/architecture/` | System design, patterns, DI, events | `TOPIC.md` |
| `docs/guides/developer/` | Developer workflows, debugging, features | `GUIDE_TOPIC.md` or `TOPIC.md` |
| `docs/guides/user/` | End-user docs (English) | `TOPIC.md` |
| `docs/reference/` | API docs, operational reference | `TOPIC.md` or `topic_api.md` |
| `docs/performance/` | Benchmarks, optimization, threading | `TOPIC.md` |
| `docs/testing/` | Test patterns, pytest fixes | `TESTING_TOPIC.md` |
| `docs/decisions/` | Architecture Decision Records | `ADR-NNN-short-title.md` |
| `docs/migration/` | Version upgrade guides | `vX.Y-to-vX.Z.md` |
| `docs/wiki/` | User guides (Portuguese) | Numbered: `N_Title.md` |
| `docs/archive/` | Historical/completed docs | Move here, don't delete |

### Documentation Rules

1. **NEVER create docs in `docs/` root** - Use appropriate subfolder
2. **English for technical docs** - Portuguese only in `wiki/`
3. **Line length 100 chars** - Match Ruff standard
4. **Relative links** - Use `../` paths, not absolute
5. **Update INDEX.md** - When adding new docs
6. **Archive, don't delete** - Move obsolete docs to `docs/archive/`

### When to Update Docs

- **New feature**: Add to `guides/developer/` + update INDEX.md
- **API change**: Update `reference/` + `architecture/SYSTEM_INTEGRATION_MAP.md`
- **Bug fix with lessons**: Add to `docs/archive/fixes/` if significant
- **Architecture change**: Update `architecture/` docs
- **Performance change**: Update `performance/` docs

### ADR Format (for `docs/decisions/`)

```markdown
# ADR-NNN: Title

## Status
Accepted | Proposed | Deprecated

## Context
What is the issue?

## Decision
What was decided?

## Consequences
What are the results?
```
