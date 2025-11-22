# Migration Guide v4.0

## Introduction
This guide outlines the steps to migrate existing components to the v4.0 Event-Driven Architecture.

## Migration Strategy: Dual Mode
To ensure stability during the transition, we use a "Dual Mode" approach. Components support both the old direct calls (v3) and the new event publishing (v4).

### Step 1: Inject EventBusV2
Ensure your component accepts `event_bus_v2` in `__init__`.

```python
class MyComponent:
    def __init__(self, gui, event_bus_v2=None):
        self.gui = gui
        self.event_bus_v2 = event_bus_v2
```

### Step 2: Implement Dual Mode Publishing
When a state change occurs that needs UI update, keep the old call and add the event publish.

```python
def update_something(self, data):
    # OLD PATH (v3)
    self.gui.update_ui_method(data)

    # NEW PATH (v4)
    if self.event_bus_v2:
        from zebtrack.ui.event_bus_v2 import Event, UIEvents
        self.event_bus_v2.publish(Event(
            type=UIEvents.SOMETHING_UPDATED,
            data={'data': data},
            source='MyComponent.update_something'
        ))
```

### Step 3: Subscribe in Target Component
The component that updates the UI (e.g., `CanvasManager`, `ProjectViewManager`) should subscribe to the event.

```python
def _setup_event_subscriptions(self):
    self.event_bus_v2.subscribe(UIEvents.SOMETHING_UPDATED, self._on_something_updated)

def _on_something_updated(self, data):
    self.update_ui_method(data['data'])
```

## Common Patterns

### Updating Zones
**Old:** `gui.update_zone_listbox(zone_data)`
**New:** Publish `UIEvents.ZONES_UPDATED`

### Refreshing Video Tree
**Old:** `gui._populate_video_selector_tree(filter)`
**New:** Publish `UIEvents.VIDEO_TREE_REFRESH_REQUESTED`
