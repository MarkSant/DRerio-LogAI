# Changelog

## 2025-10-09 (Phase 8 & 9)

### Added
- Curated baseline wizard templates (`resources/wizard_templates/*.json`) now ship with the repo and are zipped automatically during CI.
- Introduced Portuguese (`pt_BR`) translation catalog for reporter outputs with automated compilation via `scripts/compile_translations.py`.
- Added manual verification helpers under `tests/manual/` covering wizard flows, analysis profile matrices, and ROI template round-trips.
- Established a pre-release QA checklist documented in the README and referenced across flow guides.

### Changed
- README, project workflow guide, wizard guide, and reference guide refreshed to describe the advanced configuration tab and release automation steps.
- CI workflow now packages wizard templates and compiles gettext catalogs before running lint/tests.

### Testing
- CI executes `poetry run python scripts/build_templates.py`, `poetry run python scripts/compile_translations.py`, `poetry run ruff check`, and full pytest as part of the release gate.

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
