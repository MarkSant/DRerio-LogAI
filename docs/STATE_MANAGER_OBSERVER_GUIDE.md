# StateManager Observer Pattern Guide

**Phase 3, Step 2.2** - Enhanced Observer Pattern Implementation

## Overview

The StateManager now implements a formal, explicit Observer pattern that ensures:
- **Unidirectional data flow**: All state changes go through well-defined methods
- **Strong contracts**: Type-safe observer protocols and base classes
- **Predictable notifications**: Explicit registration and notification mechanisms
- **Easy filtering**: Built-in adapters for category and key filtering

## Core Components

### 1. StateObserverProtocol

```python
from zebtrack.core.state_manager import StateObserverProtocol

def my_observer(category: StateCategory, key: str, old_value: Any, new_value: Any) -> None:
    """Observer must match this signature."""
    print(f"State changed: {category.name}.{key} = {new_value}")
```

### 2. BaseStateObserver (Abstract Base Class)

For components that want a formal interface:

```python
from zebtrack.core.state_manager import BaseStateObserver, StateCategory

class MyComponent(BaseStateObserver):
    def on_state_changed(self, category, key, old_value, new_value):
        if category == StateCategory.RECORDING:
            self.handle_recording_change(key, new_value)
        elif category == StateCategory.DETECTOR:
            self.handle_detector_change(key, new_value)
    
    def handle_recording_change(self, key, value):
        print(f"Recording: {key} = {value}")
    
    def handle_detector_change(self, key, value):
        print(f"Detector: {key} = {value}")

# Register the observer
component = MyComponent()
state_manager.subscribe(StateCategory.RECORDING, component.on_state_changed)
state_manager.subscribe(StateCategory.DETECTOR, component.on_state_changed)
```

### 3. ObserverAdapter (Filtering Helper)

Simplifies observer implementation with built-in filtering:

```python
from zebtrack.core.state_manager import ObserverAdapter, StateCategory

def handle_recording_status(category, key, old_value, new_value):
    print(f"Recording status changed: {new_value}")

# Create adapter that only notifies for specific keys
adapter = ObserverAdapter(
    callback=handle_recording_status,
    categories={StateCategory.RECORDING},
    keys={"is_recording", "output_path"}
)

# Register the filtered adapter
state_manager.subscribe(StateCategory.RECORDING, adapter)

# Now only changes to is_recording or output_path will trigger the callback
state_manager.update_recording_state(source="app", is_recording=True)  # ✓ Notified
state_manager.update_recording_state(source="app", arduino_connected=True)  # ✗ Not notified
```

## Registration Methods

### Explicit Registration (Preferred)

```python
# Category-specific observer
state_manager.register_observer(StateCategory.RECORDING, my_observer)

# Global observer (all categories)
state_manager.register_global_observer(my_global_observer)
```

### Legacy Methods (Still Supported)

```python
# These are aliases for backward compatibility
state_manager.subscribe(StateCategory.RECORDING, my_observer)
state_manager.subscribe_all(my_global_observer)
```

## Unsubscribing

```python
# Remove category-specific observer
state_manager.unsubscribe(StateCategory.RECORDING, my_observer)

# Remove global observer
state_manager.unsubscribe_all(my_global_observer)
```

## Observer Management Utilities

### Count Observers

```python
# Count observers for specific category
recording_count = state_manager.get_observer_count(StateCategory.RECORDING)

# Count all observers (category + global)
total_count = state_manager.get_observer_count()
```

### Verify State Integrity

```python
integrity = state_manager.verify_state_integrity()

print(integrity)
# {
#     "state_valid": True,
#     "project": {"has_path": True, "has_data": True, ...},
#     "detector": {"initialized": True, ...},
#     "recording": {"is_recording": False, ...},
#     "processing": {"is_processing": False, ...},
#     "observers": {
#         "total": 5,
#         "by_category": {"RECORDING": 2, "DETECTOR": 1, ...},
#         "global": 2
#     }
# }
```

## Best Practices

### ✅ DO: Use Official Update Methods

```python
# Correct: State change is tracked, locked, and observers are notified
state_manager.update_recording_state(
    source="controller.start_recording",
    is_recording=True,
    output_path=Path("/output/data.parquet")
)
```

### ❌ DON'T: Modify State Directly

```python
# WRONG: Bypasses locking, validation, and observer notifications
state_manager._state.recording.is_recording = True  # Anti-pattern!
```

### ✅ DO: Filter Observers When Possible

```python
# Efficient: Only notified for relevant changes
adapter = ObserverAdapter(
    callback=my_callback,
    categories={StateCategory.RECORDING},
    keys={"is_recording"}
)
state_manager.subscribe(StateCategory.RECORDING, adapter)
```

### ❌ DON'T: Create Unfiltered Global Observers for Specific Needs

```python
# Inefficient: Receives ALL state changes
def my_callback(category, key, old_value, new_value):
    if category == StateCategory.RECORDING and key == "is_recording":
        # This fires for EVERY state change!
        handle_recording(new_value)

state_manager.subscribe_all(my_callback)  # Don't do this
```

### ✅ DO: Use Immutable Snapshots for State Queries

```python
# Correct: Get a thread-safe snapshot
recording_state = state_manager.get_recording_state()
if recording_state.is_recording:
    print(f"Recording to: {recording_state.output_path}")
```

### ❌ DON'T: Keep References to Mutable State

```python
# WRONG: Direct reference can become stale or cause race conditions
recording_ref = state_manager._state.recording  # Anti-pattern!
```

## Integration Examples

### GUI Observer (Tkinter)

```python
class ApplicationGUI:
    def __init__(self, controller):
        self.controller = controller
        self._register_state_observers()
    
    def _register_state_observers(self):
        # Recording state observer
        adapter = ObserverAdapter(
            callback=self._on_recording_changed,
            categories={StateCategory.RECORDING},
            keys={"is_recording"}
        )
        self.controller.state_manager.register_observer(
            StateCategory.RECORDING,
            adapter
        )
    
    def _on_recording_changed(self, category, key, old_value, new_value):
        # Schedule UI update on main thread
        self.root.after(0, self._update_recording_ui, new_value)
    
    def _update_recording_ui(self, is_recording):
        if is_recording:
            self.record_button.config(text="Stop Recording", bg="red")
        else:
            self.record_button.config(text="Start Recording", bg="green")
```

### Controller Observer

```python
class MainViewModel:
    def __init__(self, root):
        self.root = root
        self.state_manager = StateManager(enable_history=True)
        self._register_state_observers()
    
    def _register_state_observers(self):
        # Observe detector initialization
        self.state_manager.register_observer(
            StateCategory.DETECTOR,
            self._on_detector_state_changed
        )
    
    def _on_detector_state_changed(self, category, key, old_value, new_value):
        if key == "detector_initialized" and new_value is True:
            log.info("detector.initialized", source="observer")
            self._enable_detector_features()
```

## Thread Safety

All observer registration/unregistration and state updates are thread-safe:

```python
import threading

def worker_update():
    state_manager.update_processing_state(
        source="worker",
        current_frame=100
    )

# Multiple threads can safely update state
threads = [threading.Thread(target=worker_update) for _ in range(10)]
for t in threads:
    t.start()
for t in threads:
    t.join()
```

## Testing Observers

```python
from unittest.mock import MagicMock

def test_observer_notified():
    state_mgr = StateManager()
    observer = MagicMock()
    
    state_mgr.register_observer(StateCategory.RECORDING, observer)
    state_mgr.update_recording_state(source="test", is_recording=True)
    
    # Verify observer was called
    observer.assert_called_once()
    call_args = observer.call_args[0]
    assert call_args[0] == StateCategory.RECORDING
    assert call_args[1] == "is_recording"
    assert call_args[3] is True  # new_value
```

## Migration Guide

### Old Pattern (Pre-Phase 3)

```python
# Old: Direct state access
if controller.is_recording:
    do_something()

# Old: Manual notification
controller.is_recording = True
controller._notify_gui()
```

### New Pattern (Phase 3+)

```python
# New: Observer pattern
def on_recording_changed(category, key, old_value, new_value):
    if new_value:
        do_something()

state_manager.register_observer(StateCategory.RECORDING, on_recording_changed)

# New: Update through StateManager
state_manager.update_recording_state(
    source="controller",
    is_recording=True
)
```

## Debugging

### View Change History

```python
# Get recent recording state changes
history = state_manager.get_history(
    category=StateCategory.RECORDING,
    limit=10
)

for change in history:
    print(f"{change.timestamp}: {change.key} = {change.new_value} (source: {change.source})")
```

### Dump Complete State

```python
state_dump = state_manager.dump_state()
print(state_dump)
# Shows current values for all state categories + observer counts
```

### Verify Integrity

```python
integrity = state_manager.verify_state_integrity()
if not integrity["detector"]["initialized"]:
    log.warning("Detector not initialized")
if integrity["observers"]["total"] == 0:
    log.warning("No observers registered")
```

## Architecture Benefits

### Before (Phase 2)

- State scattered across multiple objects
- Implicit notification through method calls
- Hard to track state changes
- Race conditions possible

### After (Phase 3, Step 2.2)

- ✅ Single source of truth (`StateManager._state`)
- ✅ Explicit, type-safe observer protocol
- ✅ All changes tracked and logged
- ✅ Thread-safe by design
- ✅ Easy to test and debug
- ✅ Unidirectional data flow

## See Also

- [STATE_MANAGER_GUIDE.md](STATE_MANAGER_GUIDE.md) - Basic StateManager usage
- [ARCHITECTURE.md](ARCHITECTURE.md) - Overall application architecture
- [PHASE3_STRATEGIC_PLAN.md](PHASE3_STRATEGIC_PLAN.md) - Strategic refactoring plan
