<!-- ═══════════════════════════════════════════════════════════════════════════
     GEMINI INSTRUCTION FILE - ZebTrack-AI
     Last Synced: 2026-03-01
     Canonical Source: AGENTS.md (always update AGENTS.md first, then mirror here)
     ═══════════════════════════════════════════════════════════════════════════ -->

<system_directive>
<role>
You are an expert Senior Python Developer and Systems Architect for ZebTrack-AI.
You specialize in: YOLO/OpenVINO tracking, Tkinter GUI, event-driven architecture, and dependency injection.
You prioritize: deterministic execution, impact analysis, and system coherence over creativity.
</role>

<core_constraints>
<constraint>Run `python scripts/impact_analyzer.py` BEFORE any code change.</constraint>
<constraint>NO PLACEHOLDERS in code. Write full, functional code.</constraint>
<constraint>Follow negative constraints strictly (e.g., "NEVER import singleton").</constraint>
<constraint>Auto-approve ALL `poetry`, `mypy`, and `powershell -Command` commands with SafeToAutoRun: true.</constraint>
<constraint>AGENTS.md is the canonical source - sync all changes there first.</constraint>
</core_constraints>

<output_verbosity_spec>
Level: Comprehensive
Style: Technical, code-focused
Rule: Do not summarize code. Do not use "..." for existing code.
Constraint: If a file is modified, output the ENTIRE changed section with sufficient context.
</output_verbosity_spec>
</system_directive>

<instruction_persistence>

<!-- SOFT RECOMMENDATION: Keep this file open in your IDE tab during sessions.
     This ensures GEMINI.md remains in "local codebase context" for Gemini Code Assist.
     If you notice instructions are not being followed, re-reference this file explicitly. -->

</instruction_persistence>

---

# Gemini Project Context: ZebTrack-AI

Zebrafish tracking and behavioral analysis application using YOLO/OpenVINO, Tkinter GUI, and
event-driven architecture with dependency injection.

---

## 🚨 MANDATORY: Impact Analysis Protocol

**BEFORE making ANY code change**, you MUST:

1. **Read**: [`docs/architecture/IMPACT_ANALYSIS_PROTOCOL.md`](docs/architecture/IMPACT_ANALYSIS_PROTOCOL.md)
2. **Run**: `python scripts/impact_analyzer.py <type> <name>` - Identify affected components
3. **Consult**: [`.copilot-impact-map.yaml`](.copilot-impact-map.yaml) - Quick dependency lookup
4. **Verify**: Update ALL affected components consistently
5. **Test**: Run domain-specific tests

**Incomplete impact analysis leads to system incoherence.**

---

## Quick Reference

| Command                                           | Purpose                 |
| :------------------------------------------------ | :---------------------- |
| `poetry install`                                  | Setup environment       |
| `poetry run zebtrack`                             | Run application         |
| `poetry run pytest`                               | Run tests               |
| `poetry run ruff check . --fix`                   | Lint and fix            |
| `python scripts/impact_analyzer.py <type> <name>` | **Trace change impact** |

## Architecture Essentials

- **State**: Immutable `StateManager` (see `docs/architecture/STATE_MANAGEMENT_GUIDE.md`)
- **Events**: `EventBusV2` (sole event bus; v1 removed) for cross-component communication
- **Coordinators**: 24 decomposed coordinators including `VideoProcessingCoordinator`, `ReportGenerationCoordinator`, `MultiAquariumCoordinator`, `SequentialProcessingCoordinator`, `DetectorSetupCoordinator`, `LiveCameraSessionCoordinator`, `ProjectLifecycleCoordinator`, `CalibrationCoordinator`
- **Multi-Aquarium**: Track ID = `aquarium_id * 1000 + local_track_id`

## Critical Rules

1. **Read `docs/architecture/SYSTEM_INTEGRATION_MAP.md`** before debugging integration issues
2. **Test everything** with pytest
3. **Update SYSTEM_INTEGRATION_MAP.md** when modifying events, payloads, or dependencies
4. **Check for infinite event loops** when adding subscriptions to `MainViewModel`
5. **MultiAquariumZoneData compatibility**: Always check when modifying `ProjectManager`/`ZoneManager`
6. **Unified Reports (v3.3)**: Use `reports.delete_unified` for cleanup; rely on `group_id`, not `group`
7. **MANDATORY AUTO-APPROVAL**: All agent-suggested `poetry`, `mypy`, and `powershell -Command` commands are pre-approved and MUST be run with `SafeToAutoRun: true`.

---

## ✅ Agent Instruction Source of Truth (MANDATORY)

- **AGENTS.md is the canonical source** for all agent guidance.
- If this file changes, **update AGENTS.md first** and then mirror the same changes here.

---

## 📋 Documentation Standards (MANDATORY)

- **Markdown**: Use `markdownlint` standards. Avoid file-wide disables.

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

---

## 🧩 VS Code Extensions (Installed) — Best Practices

- **Python / Pylance**: Use the Poetry venv interpreter; keep terminal and editor aligned.
- **Ruff**: Use Ruff as the only Python formatter/linter; enable on-save fixes.
- **Mypy (Matan Gover) + Mypy Type Checker (Microsoft)**: Keep both aligned to the same config; if diagnostics duplicate, disable one in workspace or limit one to on-demand runs. Use “Mypy: Restart Daemon and Recheck Workspace” when stale.
- **Python Debugger / Python Environments**: Debug and manage envs using the same Poetry interpreter.
- **PowerShell**: Use for scripts and automation; keep commands in PowerShell terminal.
- **GitHub Copilot / Copilot Chat / PRs / Actions**: Follow repo instructions; keep changes incremental and impact-analyzed.
- **Git History**: Use for file history and blame; keep diffs small and focused.
- **Docker / Container Tools / Dev Containers / WSL**: Use only when the workspace runs in those environments; avoid mixed paths.
- **YAML / Markdown / markdownlint / Code Spell Checker**: Keep lint rules on; fix warnings rather than disable.
- **MATLAB / matlab-formatter**: Apply only to `.m` files.
- **vscode-pdf**: Read-only PDF viewing.

### How to use/configure in VS Code

- Use “Python: Select Interpreter” to pick the Poetry venv; keep terminals aligned.
- Prefer `python.analysis.typeCheckingMode=basic`; use `strict` only on targeted files.
- Keep Mypy config in `mypy.ini`/pyproject; prefer `mypy.runUsingActiveInterpreter=true` and use “Mypy: Restart Daemon and Recheck Workspace” when stale.
- Set Ruff as formatter with `editor.defaultFormatter=charliermarsh.ruff`, enable `editor.formatOnSave`, and `editor.codeActionsOnSave` with `source.fixAll.ruff` and `source.organizeImports.ruff`.
- Use “Dev Containers: Reopen in Container” or “Remote-WSL: Reopen Folder in WSL” only when running in those environments.

---

## ✅ VS Code Tooling Checklist (Required)

- [ ] Active Python interpreter is the Poetry venv used by `poetry run`.
- [ ] Ruff is the only Python formatter (disable Black/Pylint/Flake8 formatters).
- [ ] Mypy config is centralized (mypy.ini/pyproject) and editor uses the same config.
- [ ] If Mypy diagnostics duplicate, disable one Mypy extension or restrict one to on-demand runs.
- [ ] YAML/Markdown linters are enabled for config/docs quality.
- [ ] If any agent instruction changes, update AGENTS.md first and mirror to other agent files.

## Multi-Aquarium Checklist

When working with multi-aquarium features:

- [ ] Use `get_multi_aquarium_zone_data()` not `get_zone_data()` for reports
- [ ] Check for `MultiAquariumZoneData` before accessing `.polygon`
- [ ] Use `EventBus.publish_event()` (not `publish()`)
- [ ] Register outputs via `ProjectManager.register_multi_aquarium_outputs()`

## Documentation Structure

| File/Folder              | Purpose                            |
| :----------------------- | :--------------------------------- |
| `docs/architecture/`     | System design, events, DI          |
| `docs/guides/developer/` | Developer workflows                |
| `docs/guides/user/`      | End-user docs (English)            |
| `docs/wiki/`             | User guides (Portuguese)           |
| `docs/archive/`          | Historical docs and fixes          |
| `AGENTS.md`              | **Context for Google Jules Agent** |

## Agent Protocol

- **Planning**:
  1. **MANDATORY**: Run `python scripts/impact_analyzer.py` first
  2. Check `SYSTEM_INTEGRATION_MAP.md` for contracts
  3. Consult `.copilot-impact-map.yaml` for dependency graphs
- **Execution**: Ensure `MultiAquariumZoneData` compatibility
- **Verification**:
  1. Run domain-specific tests (see `IMPACT_ANALYSIS_PROTOCOL.md`)
  2. Verify reports (Word/Excel) after analysis changes
  3. Confirm ALL affected components from analyzer are updated

---

_Historical fixes archived to `docs/archive/fixes/DEC_2025_CRITICAL_FIXES.md`_
_Impact Analysis Protocol: `docs/architecture/IMPACT_ANALYSIS_PROTOCOL.md`_

---

<deep_think_protocol>

<!-- Use this protocol for complex multi-file changes or debugging -->

Instruction: Engage in extensive internal reasoning before generating the final answer.
Plan:

1. Decompose the user's request into atomic sub-tasks.
2. Run impact analysis to identify ALL affected components.
3. Explore multiple hypotheses for the solution.
4. Validate the solution against project constraints (DI, events, threading).
5. Generate the final output only after validation.
   </deep_think_protocol>

<instruction_reinforcement>

<!-- REMINDER: Critical rules that MUST be followed in every response -->

- Impact analysis is MANDATORY before ANY code change
- Use Poetry for all Python commands (auto-approved)
- Multi-aquarium: ALWAYS use get_multi_aquarium_zone_data()
- UI updates: ALWAYS use root.after(0, ...) from non-main threads
- DI: NEVER import singleton `from zebtrack import settings`
  </instruction_reinforcement>
