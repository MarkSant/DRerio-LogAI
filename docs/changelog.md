# Changelog

## 2025-10-09

### Added
- Introduced the UI event bus infrastructure (`ui/event_bus.py`) behind the `settings.ui_features.enable_event_queue` feature flag.
- Application controller now publishes UI work through the event bus when enabled, and the main Tkinter view drains the queue using `root.after`.
- Added automated regression coverage ensuring event bus publishing is wired in `AppController`.

### Changed
- `ApplicationGUI` accepts an optional `event_bus` and schedules polling hooks, logging dispatch metrics via `structlog`.
- Updated architecture guide to reference the opt-in event bus deployment path.

### Testing
- Extended `tests/test_controller.py` with event bus flow checks.
- Existing CI lint/test workflow already asserts `poetry run ruff check` and full pytest; no pipeline changes required.
