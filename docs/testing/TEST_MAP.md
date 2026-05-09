# Test Map: source → tests

Quick lookup for which tests cover which source area. Use this **before** modifying
production code to know which tests to run / extend.

> Last refreshed: 2026-05-09. Counts may drift; pattern column stays accurate.

## Top-level rule

The test tree mirrors `src/zebtrack/`, with two exceptions:

1. **88 legacy `tests/test_*.py`** at the root — pre-reorganization tests covering
   `core/`, `io/`, `analysis/`, `tracker/`, `state_manager`, `settings`, etc. When
   touching code without an obvious mirror, **also grep `tests/test_*.py`**.
2. **`tests/integration/`** — cross-component E2E tests (wizard, multi-aquarium,
   live camera). Run when changing public flow boundaries.

## Layer mapping

| Source area                           | Files | Test location                                   | Files |
| ------------------------------------- | ----- | ----------------------------------------------- | ----- |
| `src/zebtrack/coordinators/`          | 23    | `tests/coordinators/test_*.py`                  | 13    |
| `src/zebtrack/analysis/`              | 11    | `tests/analysis/test_*.py`                      | 21    |
| `src/zebtrack/analysis/reporters/`    | 7     | `tests/analysis/test_*reporter*.py`             | (in analysis/) |
| `src/zebtrack/core/detection/`        | 8     | `tests/core/test_*detect*.py`, `test_tracker_*` | (mixed) |
| `src/zebtrack/core/project/`          | 14    | `tests/core/test_project_*.py`, `test_*_manager*` | (mixed) |
| `src/zebtrack/core/recording/`        | 7     | `tests/core/test_*recording*`, `test_live_*`    | (mixed) |
| `src/zebtrack/core/services/`         | 7     | `tests/core/test_*service*.py`                  | (mixed) |
| `src/zebtrack/core/video/`            | 13    | `tests/core/test_video_*.py`                    | (mixed) |
| `src/zebtrack/core/viewmodels/`       | 4     | `tests/core/test_*view_model*.py`               | (mixed) |
| `src/zebtrack/io/`                    | 10    | `tests/io/test_*.py` + root `tests/test_io_*.py`| 8 + 3 |
| `src/zebtrack/plugins/`               | 3     | `tests/test_plugins_*.py`                       | (root) |
| `src/zebtrack/tracker/`               | 4     | `tests/test_*tracker*.py`, `test_hybrid_matching` | (root) |
| `src/zebtrack/ui/builders/`           | 7     | `tests/ui/builders/test_*.py`                   | 3     |
| `src/zebtrack/ui/components/`         | 28    | `tests/ui/components/test_*.py`                 | 27    |
| `src/zebtrack/ui/components/canvas/`  | 5     | `tests/ui/components/test_canvas*.py`           | (in components/) |
| `src/zebtrack/ui/components/project_views/` | 6 | `tests/ui/components/test_project_view*`       | (in components/) |
| `src/zebtrack/ui/dialogs/`            | 25    | `tests/ui/dialogs/test_*.py` + `test_dialogs_batch*.py` | 10 |
| `src/zebtrack/ui/wizard/`             | 18    | `tests/ui/wizard/test_*.py`                     | 13    |
| `src/zebtrack/ui/` (root)             | 11    | `tests/ui/test_*.py`                            | 16    |
| `src/zebtrack/utils/`                 | 10    | `tests/utils/test_*.py`                         | 10    |

**Cross-cutting (no source mirror):**

- `tests/integration/` (12) — E2E flows: wizard, multi-aquarium, live camera
- `tests/benchmarks/` (2) — perf checks
- `tests/performance/` (1) — perf regressions
- `tests/orchestrators/` (0 currently — placeholder)

## High-traffic files → quick lookup

When changing one of these, run the listed test files **specifically** before the
broader suite:

| Changed file | Run these tests first |
| --- | --- |
| `coordinators/multi_aquarium_coordinator.py` | `tests/coordinators/test_multi_aquarium*.py`, `tests/integration/test_multi_aquarium_e2e.py` |
| `coordinators/video_processing_coordinator.py` | `tests/coordinators/test_video_processing*.py` |
| `coordinators/sequential_processing_coordinator.py` | `tests/coordinators/test_sequential*.py` |
| `coordinators/report_generation_coordinator.py` | `tests/coordinators/test_*report*.py`, `tests/analysis/test_reporter*.py` |
| `core/recording/live_camera_service.py` | `tests/core/test_live_camera*.py`, `tests/integration/test_live_camera*.py` |
| `core/services/wizard_service.py` | `tests/test_wizard_*.py`, `tests/ui/wizard/`, `tests/integration/test_wizard*` |
| `core/state_manager.py` | `tests/test_state_manager*.py` (4 files) |
| `core/project/project_manager.py` (or any project/ module) | `tests/test_project_manager.py`, `tests/core/test_project_*` |
| `io/recorder.py` | `tests/test_recorder.py` (immutable schema!) |
| `io/camera.py`, `io/live_stream_source.py` | `tests/io/test_camera*.py`, `tests/io/test_live_stream_source.py` |
| `analysis/reporters/*` | `tests/analysis/test_reporter*.py`, `test_*_reporter.py` |
| `analysis/behavior*.py`, `analysis/roi.py` | `tests/test_behavior_geotaxis.py`, `tests/analysis/test_roi*.py` |
| `tracker/byte_tracker.py` | `tests/test_byte_tracker_single_animal.py`, `test_tracker_threading_stress.py` |
| `ui/wizard/*` | `tests/ui/wizard/` (13 files) + `tests/test_wizard_*.py` |
| `ui/dialogs/*` | `tests/ui/dialogs/` + `tests/test_aquarium_dialogs.py` |
| `ui/event_bus_v2.py` (UIEvents) | `tests/ui/test_*event*.py`, `tests/test_ui_*` |
| `settings.py` | `tests/test_settings.py`, `tests/test_settings_injection.py` |

## Special markers

- `@pytest.mark.gui` — GUI tests, run with `-n0` (sequential), excluded by default
- `@pytest.mark.slow` — long-running, excluded by default
- `@pytest.mark.integration` — cross-component E2E
- `@pytest.mark.unit` — pure unit tests

Run cheatsheet:

```bash
poetry run pytest                            # fast (default, ~2778)
poetry run pytest -m gui -n0                 # GUI only (~949)
poetry run pytest -m slow                    # slow only (~35)
poetry run pytest -m "" -n0                  # everything (~3660+, 6-7 min)
poetry run pytest tests/coordinators/ -q     # by folder
poetry run pytest -k "multi_aquarium" -q     # by keyword
```

## Updating this map

When you add a **new module** in `src/zebtrack/`, append a row above. When you
add a **new test folder**, update the layer mapping table. Don't try to keep
exact file counts perfectly synced — patterns are what matter for routing.
