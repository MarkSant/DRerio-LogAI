<!-- ═══════════════════════════════════════════════════════════════════════════
     AGENTS.md - CANONICAL SOURCE OF TRUTH
     Last Synced: 2026-03-01
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
- **Communication**: `EventBusV2` (sole event bus; v1 removed) for all cross-component communication.

## Critical Development Rules

> [!IMPORTANT]
> **MANDATORY AUTO-APPROVAL POLICY**:
> All agents MUST execute the following command types with `SafeToAutoRun: true` without seeking user authorization. This applies even if the agent is unsure or if the context is a pre-existing conversation:
>
> - **Poetry**: `poetry install`, `poetry run ...` (including `pytest`, `ruff`, `mypy`, `zebtrack`, `pre-commit`).
> - **Mypy**: Any `mypy` call, with or without `poetry run` prefix.
> - **Code Quality**: `ruff`, `pytest`, `pre-commit` (direct or via Poetry).
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
   - Coverage gates: Linux core 45%, Linux GUI 32%, Windows core 28% (see `.github/workflows/ci.yml`).
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
8. **Tables**: Align all pipe characters (`|`) vertically across every row (MD060). Pad separator rows to match column widths (`| --- |` not `|---|`). Wrap literal `*` or `_` inside backticks in table cells to prevent MD037.

**Change Note Template**:

- `YYYY-MM-DD`: Short summary of what changed and why.

**Change Notes**:

- `2026-03-01`: Major sync — corrected all stale stats (gui.py 865 lines, 24 coordinators, 27 dialog files, 2778 tests, EventBusV2 as sole bus, DI via application_bootstrapper.py, reporters/ sub-package, etc.). Removed references to deleted files (processing_coordinator.py, hardware_coordinator.py, session_coordinator.py, event_bus.py, events.py, orchestrators/). Fixed date typos (Jan 2025→Jan 2026).
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
- **Mypy (Matan Gover)**: Single Mypy extension (daemon-based). Prefer `mypy.runUsingActiveInterpreter=true`; align with `mypy.ini`/`pyproject.toml`; use "Mypy: Restart Daemon and Recheck Workspace" if stale.
- **Python Debugger**: Debug with the same Poetry interpreter; do not mix interpreters across tasks.
- **Jupyter (Microsoft)**: For notebook exploration and data analysis; kernel auto-selects Poetry venv.
- **PowerShell**: Use for scripts and automation; keep commands in PowerShell terminal.

### Git & Collaboration

- **GitLens (GitKraken)**: Primary Git tool — inline blame, file history, comparison. Replaces Git History.
- **GitHub Copilot / Copilot Chat**: Follow repository instructions; keep changes incremental and impact-analyzed.
- **GitHub Pull Requests**: Use for PR metadata/review workflows; avoid direct edits on default branch.
- **GitHub Actions**: Use for workflow review only; validate edits against coverage gates in `.github/workflows/ci.yml` and existing Poetry + pre-commit patterns.
- **Authority Matrix**: Use GitLens as source of truth for local commit graph/history; use GitHub Pull Requests extension as source of truth for PR linkage/base metadata.

### Code Quality & Diagnostics

- **Error Lens**: Inline error/warning display; configured to show errors and warnings only (not hints/info); CSpell diagnostics excluded to reduce noise.
- **TODO Tree**: Tracks TODO, FIXME, HACK, BUG, XXX, DEPRECATED tags across the codebase; excludes `__pycache__/`, `openvino_model_cache/`, `htmlcov/`, `docs/archive/` from scan.

### Docs & Config

- **YAML (Red Hat)**: Use for config validation; keep schemas in sync where provided.
- **markdownlint**: Follow repo lint settings; fix doc warnings instead of disabling.
- **Code Spell Checker**: Add domain terms to workspace dictionary; avoid disabling globally.

### Removed Extensions (DO NOT reinstall)

| Extension | Reason |
| --- | --- |
| `ms-python.mypy-type-checker` | Duplicated diagnostics with `matangover.mypy` |
| `ms-python.vscode-python-envs` | Triggered WSL popups via `wsl.exe` stub |
| `yzhang.markdown-all-in-one` | Redundant with `davidanson.vscode-markdownlint` |
| `donjayamanne.githistory` | Replaced by `eamodio.gitlens` |
| `tomoki1207.pdf` | Unused — no PDF workflows |
| `mechatroner.rainbow-csv` | Unused — project uses Parquet, not CSV |

### MCP Server Configuration (Agent Integration)

- **GitHub MCP** (`.vscode/mcp.json`): Configured via `@modelcontextprotocol/server-github`. Enables agents to interact with issues, PRs, code search, and repository metadata directly from VS Code.
- **Root-level** (`.mcp.json`): Same GitHub server config for agents using root-level MCP (e.g., Claude CLI). Requires `GITHUB_TOKEN` env var.
- **Requirement**: Node.js must be installed (for `npx`). A GitHub PAT with `repo` scope is needed.

### Workspace Performance (OneDrive Optimization)

- **`files.watcherExclude`**: Configured in `.vscode/settings.json` to exclude `openvino_model_cache/`, `htmlcov/`, `MagicMock/`, `live_analysis_sessions/`, `logs/`, `__pycache__/`, `.ruff_cache/`, `.pytest_cache/`, `.hypothesis/`, `.mypy_cache/` from file watching. Critical for reducing CPU/disk I/O on OneDrive-synced workspaces.
- **`search.exclude`**: Extended to also exclude `htmlcov/`, `MagicMock/`, `live_analysis_sessions/`, `logs/`, `.ruff_cache/`, `.pytest_cache/`, `.hypothesis/` from global search results.
- **Deprecated settings removed** (Mar 2026): `python.linting.*`, `python.formatting.provider`, `python-envs.defaultEnvManager` — all deprecated by the Python extension. Ruff handles all formatting/linting.

### How to use/configure in VS Code

- **Interpreter**: Use “Python: Select Interpreter” and choose the Poetry venv; keep terminals aligned.
- **Terminal**: Set `terminal.integrated.defaultProfile.windows` to `PowerShell` for command parity with repo scripts.
- **Pylance**: Prefer `python.analysis.typeCheckingMode=basic`; use `strict` only for targeted files.
- **Mypy**: Keep config in `mypy.ini`/pyproject and point with `mypy.configFile` if needed. Prefer `mypy.runUsingActiveInterpreter=true`. Use "Mypy: Restart Daemon and Recheck Workspace" when stale.
- **Ruff**: Set `editor.defaultFormatter=charliermarsh.ruff`, `editor.formatOnSave=true`, and `editor.codeActionsOnSave` with `source.fixAll.ruff` and `source.organizeImports.ruff`.
- **GitLens**: Enabled by default; inline blame and CodeLens active; use "GitLens: Compare" for file diffs.
- **Error Lens**: Configured via workspace settings; shows errors/warnings inline; CSpell excluded.
- **TODO Tree**: Scans workspace for tags; check sidebar panel for tag overview.
- **Jupyter**: Kernel auto-selects Poetry venv; use for data exploration notebooks.
- **MCP (Optional)**: If `.mcp.json` is absent or MCP servers are unavailable, continue with local tools and GitHub extensions without blocking tasks.

---

## ✅ VS Code Tooling Checklist (Required)

- [ ] Active Python interpreter is the Poetry venv used by `poetry run`.
- [ ] Ruff is the only Python formatter (disable Black/Pylint/Flake8 formatters).
- [ ] Mypy config is centralized (mypy.ini/pyproject) and editor uses the same config.
- [ ] Only `matangover.mypy` installed (NOT `ms-python.mypy-type-checker`).
- [ ] YAML and Markdown linters are enabled for config/docs quality.
- [ ] Error Lens shows errors/warnings only (not hints/info); CSpell excluded.
- [ ] TODO Tree excludes build artifacts and archive folders.
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
