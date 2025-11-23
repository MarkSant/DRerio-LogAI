# Migration Guide v4.0

## Introduction
This guide outlines the steps to migrate existing components from the v3.0 "Facade" pattern (direct `ApplicationGUI` calls) to the v4.0 **Event-Driven Architecture**.

## References
*   **Mapping**: See `docs/EVENT_MAPPING.md` for the complete list of legacy methods mapped to `UIEvents`.
*   **Breaking Changes**: See `docs/BREAKING_CHANGES_V4.md` for a list of deprecated methods.

## Migration Strategy: Dual Mode
To ensure stability during the transition (Phase 2), we use a **Dual Mode** approach. Components must support **both** the old direct calls (if `gui` is present) and the new event publishing (if `event_bus_v2` is present).

### Step 1: Inject EventBusV2
Update your component's `__init__` method to accept `event_bus_v2`.

```python
from zebtrack.ui.event_bus_v2 import EventBusV2

class MyComponent:
    def __init__(self, gui: "ApplicationGUI", event_bus_v2: EventBusV2 | None = None):
        self.gui = gui
        self.event_bus_v2 = event_bus_v2  # Store the reference
```

### Step 2: Implement Dual Mode Publishing
Identify where the component modifies the UI state. Keep the old call, but add the event publication.

**Example: Updating Zones**

```python
from zebtrack.ui.event_bus_v2 import Event, UIEvents

def update_zones(self, zone_data):
    # 1. OLD PATH (v3 - Deprecated)
    # Check if the legacy method exists and we are still coupled to GUI
    if hasattr(self.gui, 'update_zone_listbox'):
        self.gui.update_zone_listbox(zone_data)

    # 2. NEW PATH (v4 - Event Driven)
    if self.event_bus_v2:
        self.event_bus_v2.publish(Event(
            type=UIEvents.ZONES_UPDATED,
            data={'zone_data': zone_data},
            source='MyComponent.update_zones'
        ))
```

### Step 3: Subscribe in Target Component
The component that *receives* the update (e.g., `CanvasManager`) must subscribe to the event.

```python
# In CanvasManager.__init__
if self.event_bus_v2:
    self.event_bus_v2.subscribe(UIEvents.ZONES_UPDATED, self.on_zones_updated)

def on_zones_updated(self, data: dict):
    zone_data = data.get('zone_data')
    # Logic to update the canvas...
    self._redraw_zones(zone_data)
```

## Common Patterns

### Updating Zones
*   **Old:** `gui.update_zone_listbox(zone_data)`
*   **New:** Publish `UIEvents.ZONES_UPDATED`
*   **Payload:** `{'zone_data': ZoneData}`

### Refreshing Video Tree
*   **Old:** `gui._populate_video_selector_tree(filter)`
*   **New:** Publish `UIEvents.VIDEO_TREE_REFRESH_REQUESTED`
*   **Payload:** `{'filter_text': str}`

### Analysis Updates
*   **Old:** `gui.update_processing_stats(...)`
*   **New:** Publish `UIEvents.PROCESSING_STATS_UPDATED`
*   **Payload:** `{'total': int, 'processed': int, ...}`

## Verification
To verify your migration:
1.  Run the application.
2.  Trigger the action (e.g., create a zone).
3.  Check the logs for `event_bus_v2.publishing` messages (enable DEBUG level).
4.  Ensure the UI updates correctly.
