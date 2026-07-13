---
name: ZebTrack Workflow
alwaysApply: true
description: Repository workflow, testing, documentation, and performance expectations.
---

# DRerio LogAI Workflow

- Keep `docs/tasks/active/ROLLING_TASK_LOG.md` updated for substantial agent sessions.
- Use Poetry-first commands for app runs, tests, linting, and developer automation.
- When documentation changes, follow Diataxis placement and update `docs/INDEX.md`.
- Respect workspace performance exclusions in `.vscode/settings.json`; avoid scanning heavy
  caches and analysis output directories by default.
- Preferred quick references are `AGENTS.md`, `.copilot-context.yaml`,
  `.copilot-impact-map.yaml`, and `docs/guides/developer/impact_analysis.md`.
