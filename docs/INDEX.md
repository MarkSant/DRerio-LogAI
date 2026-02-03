# ZebTrack-AI Documentation Index

**Last Updated:** February 2, 2026
**Version:** 4.1.0 (Diátaxis Corrected)

---

## 🏗️ Documentation Structure

```text
docs/
├── tutorials/       # Learning-oriented (Step-by-step for beginners)
├── guides/          # Goal-oriented (How-to guides for specific tasks)
├── explanation/     # Understanding-oriented (Deep dives into architecture)
├── reference/       # Information-oriented (API, metrics, technical specs)
├── tasks/           # Active intervention logs and technical debt
├── wiki/            # Portuguese translations and end-user manuals
└── archive/         # Legacy and historical documentation
```

---

## 🧠 Explanation (Understanding-Oriented)

- **[Architecture Overview](explanation/architecture.md)** - The "Source of Truth" for the event-driven system and multi-aquarium logic.
- **[State Management](explanation/state_management.md)** - Ensuring thread-safe UI updates and how the Observer pattern works.
- **[Performance Architecture](explanation/performance.md)** - Baselines, thread models, and storage efficiency.
- **[Dependency Injection](explanation/dependency_injection.md)** - Patterns for modular services.

## 📋 Reference (Information-Oriented)

- **[Event Contracts](reference/events.md)** - Registry of all system events (v1 and v2) and payloads.
- **[Data Schema](reference/data_schema.md)** - Tracking data (Parquet) structure and project hierarchy.
- **[Metrics Guide](reference/metrics.md)** - Definitions of all locomotor and spatial metrics.
- **[Operational Reference](reference/operational_reference.md)** - Runtime behavior, config, and defaults.

## 🛠️ How-To Guides (Goal-Oriented)

### For Developers
- **[Performance Tuning](guides/developer/performance-tuning.md)** - Troubleshooting bottlenecks and configuring parallel plots.
- **[Getting Started](guides/developer/getting_started.md)** - Setting up the development environment.
- **[Debugging Guide](guides/developer/debugging.md)** - Troubleshooting common tracking issues.
- **[GUI Testing (Windows)](guides/developer/testing_gui_windows.md)** - Running Tkinter tests safely.

## 🎓 Tutorials (Learning-Oriented)

- **[First Tracking Run](tutorials/first_tracking_run.md)** - Get from video to results in 5 minutes.
- **[Wizard Workflow](guides/developer/wizard.md)** - Wizard details and processing modes.

---

## 🚀 Meta & Governance

- **[AGENTS.md](../AGENTS.md)** - Mandatory instructions for AI coding agents.
- **[Rolling Task Log](tasks/active/ROLLING_TASK_LOG.md)** - Active technical debt and project progress.
- **[Changelog](../CHANGELOG.md)** - Version history and release notes.

---
**Looking for Portuguese?** Visit the **[Wiki (Português)](wiki/)** for user-facing documentation in Brazilian Portuguese.
