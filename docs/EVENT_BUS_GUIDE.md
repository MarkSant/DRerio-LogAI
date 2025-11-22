# Event Bus Guide (v4.0)

This guide provides instructions on using the **Event Bus V2** architecture introduced in v4.0.
The goal is to decouple UI components, replacing direct method calls (Facade pattern) with event publications.

## Core Concepts

### 1. The Event Bus
The `EventBusV2` is a thread-safe singleton (or scoped instance) that manages subscriptions and event publishing.
It uses `threading.RLock` to ensure thread safety during subscription changes.

### 2. Events (`UIEvents`)
All events are strictly typed using the `UIEvents` Enum in `src/zebtrack/ui/event_bus_v2.py`.
This prevents typos ("magic strings") and makes it easy to find all event usages in the codebase.

### 3. Publishing is Synchronous
**Important**: `EventBusV2.publish()` executes all handlers *immediately* on the current thread.
- If you publish from the Main Thread (UI), handlers run on the Main Thread.
- If you publish from a Background Thread, handlers run on that Background Thread.

**Thread Safety Rule**: If your handler modifies the UI (Tkinter widgets), and the event might be published from a background thread, YOU (the subscriber) are responsible for dispatching the update to the main thread (e.g., using `root.after` or a helper).

---

## How to Use

### 1. Defining a New Event
Add a new member to the `UIEvents` Enum in `src/zebtrack/ui/event_bus_v2.py`:

```python
class UIEvents(Enum):
    ...
    MY_NEW_EVENT = auto()
```

### 2. Subscribing to an Event
Components should subscribe in their `__init__` or setup method.

```python
from zebtrack.ui.event_bus_v2 import UIEvents

class MyComponent:
    def __init__(self, event_bus):
        self.event_bus = event_bus
        self.event_bus.subscribe(UIEvents.ZONES_UPDATED, self.on_zones_updated)

    def on_zones_updated(self, data: dict):
        zone_data = data.get('zone_data')
        print(f"Zones updated: {zone_data}")
```

### 3. Publishing an Event
Replace direct method calls with `publish`.

**Before (v3 - Coupled):**
```python
# In DialogManager
self.gui.update_zone_listbox(new_zone_data)
```

**After (v4 - Decoupled):**
```python
from zebtrack.ui.event_bus_v2 import Event, UIEvents

# In DialogManager
self.event_bus.publish(Event(
    type=UIEvents.ZONES_UPDATED,
    data={'zone_data': new_zone_data},
    source='DialogManager'
))
```

---

## Migration Strategy (Dual Mode)

During Phase 2 (Migration), we support "Dual Mode" where components might support both legacy calls and events.

```python
def update_zones(self, zones):
    # 1. Legacy support (if gui is still attached)
    if hasattr(self, 'gui'):
        self.gui.update_zone_listbox(zones)

    # 2. New Event System
    if hasattr(self, 'event_bus'):
        self.event_bus.publish(Event(UIEvents.ZONES_UPDATED, {'zone_data': zones}))
```

## Best Practices

1.  **Keep Handlers Fast**: Since execution is synchronous, slow handlers will block the publisher. Offload heavy work to background threads.
2.  **Payload Type Safety**: Document the expected keys in the `data` dictionary for each event (see `docs/EVENT_MAPPING.md`).
3.  **Error Handling**: The Event Bus catches exceptions in handlers to prevent one failing subscriber from crashing the whole bus. However, you should still wrap risky code in your handlers.
4.  **Avoid Event Loops**: Be careful not to publish an event in a handler that triggers a chain reaction leading back to the original event.

---

**Related Documents**:
- `docs/EVENT_MAPPING.md`: List of standard events and their payloads.
- `src/zebtrack/ui/event_bus_v2.py`: The implementation.
