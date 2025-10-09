# Changelog

## 2025-10-09

### Added
- Introduced the UI event bus infrastructure (`ui/event_bus.py`) behind the `settings.ui_features.enable_event_queue` feature flag.
- Application controller now publishes UI work through the event bus when enabled, and the main Tkinter view drains the queue using `root.after`.
- Added automated regression coverage ensuring event bus publishing is wired in `AppController`.
- Reporter now uses gettext-driven translations with docx template support, falling back to the legacy builder when templates are unavailable.
- Declared the `docxtpl` dependency to ship the templated reporting workflow.
- Wizard step 2 now includes an inline folder tree preview with summary counts for quick validation.
- Custom regex dialog ships with a live preview table and inline error feedback while editing patterns.

### Changed
- `ApplicationGUI` accepts an optional `event_bus` and schedules polling hooks, logging dispatch metrics via `structlog`.
- Updated architecture guide to reference the opt-in event bus deployment path.
- Confirmation summary surfaces the folder preview highlights and persists the preview structure in wizard metadata.

### Testing
- Extended `tests/test_controller.py` with event bus flow checks.
- Added focused reporter regression tests to validate the templated export path.
- Existing CI lint/test workflow already asserts `poetry run ruff check` and full pytest; no pipeline changes required.
- Added wizard file selection, adapter, and confirmation tests covering the new preview and live regex flows.
