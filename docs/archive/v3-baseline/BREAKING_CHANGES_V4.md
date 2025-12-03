# Breaking Changes v4.0

## Overview
Version 4.0 introduces an **Event-Driven Architecture** to decouple the GUI from business logic and components. This results in several breaking changes, primarily the removal of direct GUI manipulation methods in favor of event publishing via `EventBusV2`.

## Deprecated/Removed Methods

### GUI Methods
The following methods in `ApplicationGUI` (`src/zebtrack/ui/gui.py`) are **deprecated** and will be removed in v4.0. Components must not call these directly.

| Deprecated Method | Replacement Event (`UIEvents`) | Payload |
|-------------------|-------------------|---------|
| `update_zone_listbox(zone_data)` | `ZONES_UPDATED` | `{'zone_data': zone_data}` |
| `setup_interactive_polygon(polygon)` | `POLYGON_EDIT_REQUESTED` | `{'polygon': polygon}` |
| `refresh_project_views(...)` | `PROJECT_VIEWS_REFRESH_REQUESTED` | `{'reason': str, 'append_summary': bool}` |
| `_populate_video_selector_tree(filter)` | `VIDEO_TREE_REFRESH_REQUESTED` | `{'filter_text': filter}` |
| `apply_pending_readiness_snapshot(...)` | `READINESS_SNAPSHOT_UPDATED` | `{'snapshot': {...}}` |
| `update_processing_stats(...)` | `PROCESSING_STATS_UPDATED` | `{'total_frames': int, ...}` |
| `update_social_summary(...)` | `SOCIAL_SUMMARY_UPDATED` | `{'stats': dict, ...}` |
| `update_analysis_task_status(...)` | `ANALYSIS_TASK_STATUS_UPDATED` | `{'index': int, 'total': int, ...}` |

### Component Requirements

1.  **EventBusV2 Injection**
    *   All UI components (e.g., `DialogManager`, `CanvasManager`, `ProjectViewManager`) now require `EventBusV2` to be injected during initialization.
    *   **Action**: Update `__init__` methods to accept `event_bus_v2: EventBusV2`.

2.  **UICoordinator**
    *   A new `UICoordinator` class now handles cross-component coordination.
    *   **Action**: Components should not directly access other components (e.g., `self.gui.canvas_manager`) to trigger side effects. Instead, publish an event (e.g., `ZONES_UPDATED`), and the `UICoordinator` (or specific subscribers) will handle the response.

3.  **Strict Event Typing**
    *   Events are strictly typed using the `UIEvents` Enum in `src/zebtrack/ui/event_bus_v2.py`. String-based events are not supported on the new bus.

## Migration Support
*   Refer to `docs/MIGRATION_GUIDE_V4.md` for step-by-step migration instructions.
*   Refer to `docs/EVENT_MAPPING.md` for a detailed mapping of old calls to new events.
