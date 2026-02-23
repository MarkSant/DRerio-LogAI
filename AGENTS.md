<!-- ═══════════════════════════════════════════════════════════════════════════
     AGENTS.md - CANONICAL SOURCE OF TRUTH
     Last Synced: 2026-02-03
     All other agent files (CLAUDE.md, GEMINI.md, copilot-instructions.md) must
     mirror changes from this file. Update here FIRST, then sync to others.
     ═══════════════════════════════════════════════════════════════════════════ -->

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
>
> - **Poetry**: `poetry install`, `poetry run ...` (including `pytest`, `ruff`, `mypy`, `zebtrack`, `pre-commit`).
> - **Mypy**: Any `mypy` call, with or without `poetry run` prefix.
> - **PowerShell**: `powershell -Command "..."` or simple script executions.
> - **Impact Analysis**: `python scripts/impact_analyzer.py ...`.

1. **Impact Analysis**: Before _any_ change, check `docs/guides/developer/impact_analysis.md` and `docs/reference/system_integration.md`.
2. **Multi-Aquarium Support**:
   - Track ID format: `aquarium_id * 1000 + local_track_id`.
   - Use `MultiAquariumZoneData` for zone operations.
   - Verify features across multiple aquariums.
3. **Testing**:
   - Run tests heavily.
   - GUI tests require `xvfb` in headless environments.
   - Coverage gates: Linux core 50%, Linux GUI 32%, Windows core 28% (see `.github/workflows/ci.yml`).
4. **Linting**: Strict adherence to `ruff` rules.
5. **Approved Commands**: Both `poetry` (run/install) and `powershell -Command` calls are pre-approved by the user and MUST be executed with `SafeToAutoRun: true` by agents. You can run these commands WITHOUT seeking explicit authorization.

---

## ✅ Agent Instruction Source of Truth (MANDATORY)

- **AGENTS.md is the canonical source** for all agent guidance.
- If any other agent file changes (CLAUDE/GEMINI/Copilot), **update AGENTS.md first** and then mirror the same changes.
- **SYNC REMINDER**: Every change to agent instructions must be mirrored across all instructions files immediately to prevent drift.
- **TASK LOGGING**: Agents MUST maintain a detailed entry in [docs/tasks/active/ROLLING_TASK_LOG.md](docs/tasks/active/ROLLING_TASK_LOG.md) for every session. Plan tasks by writing to this log and update progress incrementally.

---

## 📋 Documentation Standards (MANDATORY)

When creating or updating documentation, follow these rules:

### Diátaxis Structure

| Folder                 | Purpose                                     |
| ---------------------- | ------------------------------------------- |
| `docs/tutorials/`      | Learning-oriented (Step-by-step)            |
| `docs/guides/`         | Goal-oriented (How-to)                      |
| `docs/explanation/`    | Understanding-oriented (Concepts)           |
| `docs/reference/`      | Information-oriented (API, Config, Metrics) |
| `docs/tasks/`          | Dynamic task tracking (Active/Completed)    |
| `docs/archive/legacy/` | Obsolete or historical documents            |
| `docs/wiki/`           | Portuguese end-user documentation           |

### Rules

1. **Language**: English for all technical/developer docs. Portuguese ONLY in `docs/wiki/`.
2. **Unified Docs**: Never create "Feature_V2_Fix.md". Update the existing canonical doc in the appropriate folder.
3. **No Root Docs**: All docs (except README and INDEX) must reside in a subfolder.
4. **Archive, don't delete**: Move obsolete information to `docs/archive/legacy/`.
5. **Markdown**: Use `markdownlint` standards. Avoid file-wide disables.

### Markdown Formatting Rules (markdownlint)

The project uses `.markdownlint.json`. Key disabled rules:

- **MD013** (line length): Disabled for code blocks/tables and long URLs.
- **MD033** (inline HTML): Allowed for badges, callouts, and layout helpers.
- **MD041** (first line heading): Disabled for files with metadata or XML directives.

Agent requirements:

1. **No file-wide disables** in new documentation.
2. **Inline disables** must include a justification comment on the same line.
3. **Prefer fixes** over disables; reformat lists/headings instead of suppressing.
4. **Headings**: Use ATX style (`#`, `##`) not Setext.
5. **Lists**: Use `-` for unordered, `1.` for ordered.
6. **Code fences**: Always specify a language (` ```python `, ` ```yaml `).
7. **Line length**: Keep prose under 100 characters when reasonable; code blocks/tables exempt.

**Change Note Template**:

- `YYYY-MM-DD`: Short summary of what changed and why.

**Change Notes**:

- `2026-02-03`: Added XML prompt engineering framework (system_directive, constraints, verbosity, deep_think_protocol) and Last Synced header to all agent files.
- `2026-02-01`: Added VS Code extensions best practices, checklist, and source-of-truth sync rule for all agent instruction files.

---

## 🏷️ XML Vocabulary Conventions (for Model-Specific Files)

The following XML tags are approved for use in model-specific instruction files (GEMINI.md, CLAUDE.md, copilot-instructions.md). These tags help LLMs parse instructions more accurately.

| Tag                           | Purpose                                                     | Required In          |
| ----------------------------- | ----------------------------------------------------------- | -------------------- |
| `<system_directive>`          | Root container for role, constraints, and verbosity         | All files            |
| `<role>`                      | Defines the AI persona and expertise areas                  | All files            |
| `<core_constraints>`          | Container for critical rules (wrap each in `<constraint>`)  | All files            |
| `<constraint>`                | Single mandatory rule                                       | All files            |
| `<output_verbosity_spec>`     | Controls output detail level and style                      | GEMINI.md, CLAUDE.md |
| `<deep_think_protocol>`       | Forces chain-of-thought reasoning for complex tasks         | GEMINI.md, CLAUDE.md |
| `<instruction_persistence>`   | Soft reminder for Gemini to keep file open in IDE           | GEMINI.md only       |
| `<instruction_reinforcement>` | Critical rules repeated at file end for context persistence | All files            |
| `<thinking>`, `<answer>`      | Claude-specific CoT tags (optional)                         | CLAUDE.md            |

**Rules**:

1. Use semantic tag names that describe their content.
2. Be consistent—use the same tag names across all files.
3. Nest tags logically: `<system_directive>` → `<role>` + `<core_constraints>` → `<constraint>`.
4. Place critical instructions both at the START (`<system_directive>`) and END (`<instruction_reinforcement>`) for context persistence.

---

## 🧩 VS Code Extensions (Installed) — Best Practices

Use these conventions to get consistent diagnostics and avoid tool conflicts.

### How to find information (Source of Truth)

- **System Architecture**: Consult `docs/explanation/architecture.md` (EDA v4.0).
- **Communication**: Consult `docs/reference/events.md` for all event bus payloads.
- **Data/IO**: Consult `docs/reference/data_schema.md` for Parquet and directory formats.
- **Performance/Threading**: Consult `docs/explanation/state_management.md` and `docs/explanation/performance.md`.
- **Active Progress**: Check `docs/tasks/active/ROLLING_TASK_LOG.md` before starting work.
- **Legacy Context**: Look in `docs/archive/decisions/` (ADRs) and `docs/archive/legacy/`.

### Core Python Tooling

- **Python (Microsoft)**: Select the Poetry venv as the active interpreter; keep terminal and editor on the same interpreter.
- **Pylance (Microsoft)**: Prefer `basic` type checking by default; go `strict` only on targeted files when needed.
- **Ruff (Astral Software)**: Use Ruff as the **only** Python formatter and linter; enable on-save fixes.
- **Mypy (Matan Gover)**: Prefer daemon checks; align with `mypy.ini`/`pyproject.toml`; use “Mypy: Restart Daemon and Recheck Workspace” if stale.
- **Mypy Type Checker (Microsoft)**: Keep aligned with the same config; if diagnostics duplicate, disable one in workspace or limit one to on-demand runs.
- **Python Debugger / Python Environments**: Debug with the same Poetry interpreter; do not mix interpreters across tasks.
- **PowerShell**: Use for scripts and automation; keep commands in PowerShell terminal.

### Git & Collaboration

- **GitHub Copilot / Copilot Chat**: Follow repository instructions; keep changes incremental and impact-analyzed.
- **GitHub Pull Requests**: Use for reviewing PRs; avoid direct edits on default branch.
- **GitHub Actions**: Use for workflow review only; validate any workflow edits with repo standards.
- **Git History**: Use for quick blame/history; prefer small diffs and clear commit rationale.

### Containers & Environment

- **Docker / Container Tools / Dev Containers**: Use only when the project is containerized; keep Compose files and devcontainer settings in sync.
- **WSL**: Use only when workspace is opened in WSL; avoid mixing Windows and WSL paths.

### Docs & Config

- **YAML (Red Hat)**: Use for config validation; keep schemas in sync where provided.
- **Markdown All in One**: Use for editing Markdown; respect markdownlint rules.
- **markdownlint**: Follow repo lint settings; fix doc warnings instead of disabling.
- **Code Spell Checker**: Add domain terms to workspace dictionary; avoid disabling globally.
- **vscode-pdf**: Read-only PDF viewing; no code changes.

### Language-Specific

- **MATLAB / matlab-formatter**: Apply only to `.m` files; keep Python tooling unaffected.

### How to use/configure in VS Code

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
