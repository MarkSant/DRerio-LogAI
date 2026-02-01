# Project Context: ZebTrack-AI

Zebrafish tracking and behavioral analysis application using YOLO/OpenVINO, Tkinter GUI, and event-driven architecture.

## Project Goal

To provide an automated, high-precision tracking and analysis tool for Danio rerio (zebrafish) research, generating scientific reports and behavioral metrics.

## Architecture Highlights

- **Framework**: Python 3.12+, Tkinter (GUI), Ultralytics YOLO / OpenVINO (Tracking).
- **Architecture**: Event-driven with Dependency Injection.
- **State Management**: strict `StateManager` usage (immutable state updates).
- **Communication**: `EventBus` for all cross-component communication.

## Critical Development Rules

> [!IMPORTANT]
> **MANDATORY AUTO-APPROVAL POLICY**:
> All agents MUST execute the following command types with `SafeToAutoRun: true` without seeking user authorization. This applies even if the agent is unsure or if the context is a pre-existing conversation:
> - **Poetry**: `poetry install`, `poetry run ...` (including `pytest`, `ruff`, `mypy`, `zebtrack`, `pre-commit`).
> - **Mypy**: Any `mypy` call, with or without `poetry run` prefix.
> - **PowerShell**: `powershell -Command "..."` or simple script executions.
> - **Impact Analysis**: `python scripts/impact_analyzer.py ...`.

1. **Impact Analysis**: Before *any* change, check `docs/architecture/IMPACT_ANALYSIS_PROTOCOL.md` and `SYSTEM_INTEGRATION_MAP.md`.
2. **Multi-Aquarium Support**:
   - Track ID format: `aquarium_id * 1000 + local_track_id`.
   - Use `MultiAquariumZoneData` for zone operations.
   - Verify features across multiple aquariums.
3. **Testing**:
   - Run tests heavily.
   - GUI tests require `xvfb` in headless environments.
4. **Linting**: Strict adherence to `ruff` rules.
5. **Approved Commands**: Both `poetry` (run/install) and `powershell -Command` calls are pre-approved by the user and MUST be executed with `SafeToAutoRun: true` by agents. You can run these commands WITHOUT seeking explicit authorization.

---

## ✅ Agent Instruction Source of Truth (MANDATORY)

- **AGENTS.md is the canonical source** for all agent guidance.
- If any other agent file changes (CLAUDE/GEMINI/Copilot), **update AGENTS.md first** and then mirror the same changes.
- When syncing instructions, add a short “Change Note” entry here to preserve intent and reduce drift.

**Change Note Template**:
- `YYYY-MM-DD`: Short summary of what changed and why.

**Change Notes**:
- `2026-02-01`: Added VS Code extensions best practices, checklist, and source-of-truth sync rule for all agent instruction files.

---

## 🧩 VS Code Extensions (Installed) — Best Practices

Use these conventions to get consistent diagnostics and avoid tool conflicts.

**Core Python Tooling**
- **Python (Microsoft)**: Select the Poetry venv as the active interpreter; keep terminal and editor on the same interpreter.
- **Pylance (Microsoft)**: Prefer `basic` type checking by default; go `strict` only on targeted files when needed.
- **Ruff (Astral Software)**: Use Ruff as the **only** Python formatter and linter; enable on-save fixes.
- **Mypy (Matan Gover)**: Prefer daemon checks; align with `mypy.ini`/`pyproject.toml`; use “Mypy: Restart Daemon and Recheck Workspace” if stale.
- **Mypy Type Checker (Microsoft)**: Keep aligned with the same config; if diagnostics duplicate, disable one in workspace or limit one to on-demand runs.
- **Python Debugger / Python Environments**: Debug with the same Poetry interpreter; do not mix interpreters across tasks.
- **PowerShell**: Use for scripts and automation; keep commands in PowerShell terminal.

**Git & Collaboration**
- **GitHub Copilot / Copilot Chat**: Follow repository instructions; keep changes incremental and impact-analyzed.
- **GitHub Pull Requests**: Use for reviewing PRs; avoid direct edits on default branch.
- **GitHub Actions**: Use for workflow review only; validate any workflow edits with repo standards.
- **Git History**: Use for quick blame/history; prefer small diffs and clear commit rationale.

**Containers & Environment**
- **Docker / Container Tools / Dev Containers**: Use only when the project is containerized; keep Compose files and devcontainer settings in sync.
- **WSL**: Use only when workspace is opened in WSL; avoid mixing Windows and WSL paths.

**Docs & Config**
- **YAML (Red Hat)**: Use for config validation; keep schemas in sync where provided.
- **Markdown All in One**: Use for editing Markdown; respect markdownlint rules.
- **markdownlint**: Follow repo lint settings; fix doc warnings instead of disabling.
- **Code Spell Checker**: Add domain terms to workspace dictionary; avoid disabling globally.
- **vscode-pdf**: Read-only PDF viewing; no code changes.

**Language-Specific**
- **MATLAB / matlab-formatter**: Apply only to `.m` files; keep Python tooling unaffected.

**How to use/configure in VS Code**
- **Interpreter**: Use “Python: Select Interpreter” and choose the Poetry venv; keep terminals aligned.
- **Pylance**: Prefer `python.analysis.typeCheckingMode=basic`; use `strict` only for targeted files.
- **Mypy (both extensions)**: Keep config in `mypy.ini`/pyproject and point with `mypy.configFile` if needed. Prefer `mypy.runUsingActiveInterpreter=true`. Use “Mypy: Recheck Workspace” and “Mypy: Restart Daemon and Recheck Workspace” when stale.
- **Ruff**: Set `editor.defaultFormatter=charliermarsh.ruff`, `editor.formatOnSave=true`, and `editor.codeActionsOnSave` with `source.fixAll.ruff` and `source.organizeImports.ruff`.
- **GitHub Actions / PRs / Git History**: Use for review only; do not change workflows without impact analysis.
- **Dev Containers / WSL**: Use “Dev Containers: Reopen in Container” or “Remote-WSL: Reopen Folder in WSL” only when the project is running there.

---

## ✅ VS Code Tooling Checklist (Required)

- [ ] Active Python interpreter is the Poetry venv used by `poetry run`.
- [ ] Ruff is the only Python formatter (disable Black/Pylint/Flake8 formatters).
- [ ] Mypy config is centralized (mypy.ini/pyproject) and editor uses the same config.
- [ ] If Mypy diagnostics duplicate, disable one Mypy extension or restrict one to on-demand runs.
- [ ] YAML and Markdown linters are enabled for config/docs quality.
- [ ] If any agent instruction changes, update AGENTS.md first and mirror to other agent files.

## Setup & Commands

### Installation

The environment is set up via `scripts/jules_setup.sh`.
Dependencies are managed with Poetry.

```bash
# Install dependencies (if not already done by setup script)
poetry install
```

### Running Tests

```bash
# Run all tests (excluding GUI if no display)
poetry run pytest

# Run fast unit tests
poetry run pytest -m "not (gui or slow)"

# Run impact analysis (required before changes)
poetry run python scripts/impact_analyzer.py <type> <name>
```

### Formatting & Linting

```bash
poetry run ruff check . --fix
```

## Code Style

- **Type Hinting**: Strict typing; use `typing.TYPE_CHECKING` for circular imports.
- **Docstrings**: Google-style docstrings for all public methods and classes.
- **Naming**: `snake_case` for variables/functions, `PascalCase` for classes.
- **Imports**: Sorted by `isort` (handled by Ruff).

## File Structure

- `src/zebtrack`: Main source code.
  - `core`: Business logic, services, coordinators.
  - `ui`: Tkinter views and viewmodels.
  - `analysis`: Scientific calculation modules.
- `tests`: Pytest suite (mirrors source structure).
- `docs`: Documentation.
