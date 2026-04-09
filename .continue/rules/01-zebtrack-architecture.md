---
name: ZebTrack Architecture
alwaysApply: true
description: Core architecture and canonical context sources for the ZebTrack-AI workspace.
---

# ZebTrack-AI Architecture

- This workspace is a Python 3.12+ Tkinter application with MVVM, dependency injection,
  and EventBusV2-driven coordination.
- Treat these files as the primary context sources before making significant changes:
  `AGENTS.md`, `.copilot-context.yaml`, `.copilot-impact-map.yaml`,
  `docs/explanation/architecture.md`, and `docs/tasks/active/ROLLING_TASK_LOG.md`.
- The composition root starts in `src/zebtrack/__main__.py` and delegates wiring to
  `src/zebtrack/core/application_bootstrapper.py`.
- High-value runtime files include `src/zebtrack/core/main_view_model.py`,
  `src/zebtrack/ui/gui.py`, `src/zebtrack/core/project/project_manager.py`, and
  `src/zebtrack/core/services/detector_service.py`.
