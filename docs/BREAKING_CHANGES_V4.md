# Breaking Changes v4.0

## Overview
Version 4.0 introduces an Event-Driven Architecture to decouple the GUI from business logic and components. This results in several breaking changes, primarily the removal of direct GUI manipulation methods in favor of event publishing.

## Deprecated/Removed Methods

### GUI Methods
The following methods in `ApplicationGUI` are deprecated and will be removed in v4.0. Components should no longer call these directly.

| Deprecated Method | Replacement Event | Payload |
|-------------------|-------------------|---------|
| `update_zone_listbox(zone_data)` | `UIEvents.ZONES_UPDATED` | `{'zone_data': zone_data}` |
| `_populate_video_selector_tree(filter)` | `UIEvents.VIDEO_TREE_REFRESH_REQUESTED` | `{'filter_text': filter}` |
| `apply_pending_readiness_snapshot(...)` | `UIEvents.READINESS_SNAPSHOT_UPDATED` | `{'ready_with_trajectory': ..., ...}` |
| `setup_interactive_polygon(polygon)` | `UIEvents.POLYGON_EDIT_REQUESTED` | `{'polygon': polygon}` |

### Component Requirements
- **EventBusV2 Injection**: All UI components (`DialogManager`, `CanvasManager`, etc.) now require `EventBusV2` to be injected during initialization.
- **UICoordinator**: A new `UICoordinator` class now handles cross-component coordination. Components should not directly access other components for side effects.
