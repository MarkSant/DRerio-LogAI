# Phase 1: Foundational Refactoring - Event Bus Implementation

## Summary of Changes

This document describes the implementation of Phase 1 of the foundational refactoring: introducing a centralized event bus for UI-Core communication to decouple the GUI from the Controller.

## What Was Implemented

### 1. Enhanced EventBus (src/zebtrack/ui/event_bus.py)

**Added:**
- `NamedEvent` dataclass for publish/subscribe pattern events
- `EventType.NAMED` enum value
- `publish_event()` method for publishing named events with data payloads
- `subscribe()` method for registering event handlers
- `unsubscribe()` method for removing event handlers
- `dispatch_named_event()` method for invoking all subscribers of an event
- `get_subscribers()` method for testing/introspection
- Subscriber registry (`_subscribers` dict mapping event names to handler lists)

**Key Features:**
- Thread-safe event queue
- Named event publish/subscribe pattern
- Backward compatible with existing `CallableEvent` pattern
- Graceful error handling with structured logging

### 2. Event Catalog (src/zebtrack/ui/events.py)

**Created new module** defining all UI→Controller events:

**Event Categories:**
- Recording: `RECORDING_START`, `RECORDING_STOP`, `RECORDING_TRIGGER`
- Project: `PROJECT_CREATE`, `PROJECT_OPEN`, `PROJECT_CLOSE`, `PROJECT_PROCESS_VIDEOS`, etc.
- Video Processing: `VIDEO_ANALYZE_SINGLE`, `VIDEO_CANCEL_ANALYSIS`
- Model & Weights: `MODEL_SET_WEIGHT`, `MODEL_SET_OPENVINO`, `MODEL_RUN_DIAGNOSTIC`, etc.
- Detector & Zones: `DETECTOR_SETUP`, `ZONE_SET_ARENA_POLYGON`, etc.
- Calibration: `CALIBRATION_RUN_LIVE`, `CALIBRATION_COPY_TO_PROJECT`, etc.
- Arduino: `ARDUINO_SETUP`, `ARDUINO_LOG_EVENT`
- Reports: `REPORT_GENERATE`
- Application: `APP_CLOSE`

**Documentation:**
- Complete event payload specifications for each event
- Naming convention: `"domain:action"` pattern (e.g., `"recording:start"`)
- `Events` class with constants for type-safe event names

### 3. Controller Event Subscriptions (src/zebtrack/core/controller.py)

**Added:**
- `_register_event_handlers()` method called during initialization when event bus is enabled
- Event handler methods for all events (e.g., `_handle_recording_start()`, `_handle_project_close()`)
- Each handler adapts event data to existing controller method signatures
- Full logging of subscription registration

**Handler Pattern:**
```python
def _handle_recording_start(self, data: dict) -> None:
    self.start_recording(
        day=data.get("day"),
        group=data.get("group"),
        cobaia=data.get("cobaia"),
    )
```

**Total Events Subscribed:** 30+ UI→Controller events

### 4. GUI Event Publishing (src/zebtrack/ui/gui.py)

**Added:**
- `_handle_named_event()` method to dispatch named events to subscribers
- `publish_event()` helper method for convenient event publishing
- Updated event handler registry to include `EventType.NAMED`
- Imported `Events` catalog
- **Demonstrated pattern** with critical button commands:
  - Start/Stop Recording buttons → `Events.RECORDING_START/STOP`
  - Process Videos button → `Events.PROJECT_PROCESS_VIDEOS`
  - Close Project button → `Events.PROJECT_CLOSE`

**Pattern Example:**
```python
# Before (direct coupling):
command=self.controller.start_recording

# After (event-driven):
command=lambda: self.publish_event(Events.RECORDING_START, {})
```

### 5. Settings Update (src/zebtrack/settings.py)

**Changed:**
- `UIFeatureFlags.enable_event_queue` default value: `False` → `True`
- Updated description to reflect new default behavior
- Event bus is now **enabled by default** for all UI→Controller communication

## Architecture Benefits

### Decoupling Achieved
- **Before:** GUI directly calls `controller.method()` (tight coupling)
- **After:** GUI publishes events; Controller subscribes to events (loose coupling)

### Key Advantages
1. **Testability:** Can mock event bus, verify events published/handled without full integration
2. **Threading Preparation:** Events can be processed on worker threads (future Phase 2)
3. **Maintainability:** Clear event contracts documented in one place (`events.py`)
4. **Extensibility:** Easy to add new event types without modifying existing code
5. **Observability:** All interactions logged with structured logging

## What Still Needs To Be Done

### Remaining GUI Updates (Task #4 - In Progress)

**Scope:** Replace remaining ~45+ direct `self.controller.<method>()` calls with `self.publish_event()` calls

**High-Priority Areas:**
1. **Model/Weight Management:**
   - `set_active_weight()`
   - `set_openvino_usage()`
   - `delete_weight()`
   - `add_new_weight()`

2. **Project Management:**
   - `create_project_workflow()`
   - `open_project_workflow()`
   - `generate_parquet_summaries()`
   - `delete_project_asset()`

3. **Video Analysis:**
   - `start_single_video_workflow()`
   - `cancel_current_analysis()`

4. **Detector Configuration:**
   - `update_detector_parameters()`
   - `setup_detector()`
   - `setup_detector_zones()`

5. **Zone/Calibration:**
   - `set_main_arena_polygon()`
   - `run_live_calibration()`
   - `save_current_calibration_to_project()`

**Search Command to Find Remaining Calls:**
```bash
rg "self\.controller\.((?!project_manager|weight_manager|view|ui_event_bus|root|recorder|detector|arduino)[a-zA-Z_]+)\(" src/zebtrack/ui/gui.py
```

**Pattern to Follow:**
```python
# Direct call:
self.controller.some_method(arg1, arg2)

# Event-driven equivalent:
self.publish_event(Events.SOME_EVENT, {"arg1": arg1, "arg2": arg2})
```

### Test Updates (Task #6 - Not Started)

**Required Changes:**
1. **Mock Event Bus in Tests:**
   ```python
   from unittest.mock import Mock
   
   mock_event_bus = Mock(spec=EventBus)
   controller = AppController(root, event_bus=mock_event_bus)
   
   # Verify event published:
   mock_event_bus.publish_event.assert_called_once_with(
       Events.RECORDING_START, {}
   )
   ```

2. **Update Controller Tests:**
   - Tests that check direct method calls need to verify event handlers instead
   - Example: Instead of calling `controller.start_recording()`, publish `Events.RECORDING_START`

3. **Add Event Bus Integration Tests:**
   - Verify events published by GUI trigger controller actions
   - Verify event payloads correctly passed to handlers

4. **Test Files to Update:**
   - `tests/test_controller.py` (main controller tests)
   - `tests/test_gui*.py` (GUI interaction tests)
   - `tests/test_integration.py` (end-to-end workflows)
   - `tests/test_wizard*.py` (wizard interaction tests)

### Validation (Task #7 - Not Started)

**Test Execution:**
```powershell
# Full test suite:
poetry run pytest -q

# Focused test runs:
poetry run pytest tests/test_controller.py -v
poetry run pytest tests/test_integration.py -v
poetry run pytest tests/test_gui*.py -v
```

**Manual Smoke Tests:**
1. **Recording Workflow (Live Project):**
   - Create live project
   - Click "Iniciar Gravação" → verify recording starts
   - Click "Parar Gravação" → verify recording stops
   - Verify events logged in console

2. **Project Processing (Pre-recorded):**
   - Create/open pre-recorded project
   - Click "Adicionar e Processar Novos Vídeos" → verify dialog opens
   - Process video → verify analysis runs
   - Click "Fechar Projeto" → verify project closes

3. **Model Management:**
   - Change active weight → verify model reloads
   - Toggle OpenVINO → verify status updates
   - Run diagnostic → verify results displayed

4. **Zone Drawing:**
   - Draw arena polygon → verify polygon saved
   - Add ROI zones → verify zones appear in list
   - Apply ROI template → verify zones loaded

## Backward Compatibility

The implementation maintains **full backward compatibility**:

1. **Fallback Path:** `publish_event()` checks if event bus exists; logs warning if not
2. **Direct Calls Still Work:** Existing direct controller calls remain functional
3. **Opt-Out Available:** Set `enable_event_queue=False` in config to disable event bus
4. **Gradual Migration:** Can convert calls incrementally without breaking existing workflows

## Next Steps After Phase 1 Completion

### Phase 2: Move Controller to Worker Thread
Once all direct calls are replaced:
- Controller can run in background thread
- GUI remains responsive during long operations
- Events cross thread boundary safely via queue
- Progress updates via controller→GUI events

### Phase 3: State Management Layer
- Introduce centralized state store
- Controller modifies state, GUI observes changes
- Further decoupling: UI becomes pure view layer

## Testing the Current Implementation

**Quick Verification:**
```python
# In Python REPL or test file:
from zebtrack.ui.event_bus import EventBus
from zebtrack.ui.events import Events

bus = EventBus()

# Subscribe handler:
def handle_start(data):
    print(f"Recording start: {data}")

bus.subscribe(Events.RECORDING_START, handle_start)

# Publish event:
bus.publish_event(Events.RECORDING_START, {"day": 1, "group": "A"})

# Drain and dispatch:
for event in bus.drain():
    if event.type == EventType.NAMED:
        bus.dispatch_named_event(event.payload)
```

**Expected Output:**
```
Recording start: {'day': 1, 'group': 'A'}
```

## Files Modified

1. `src/zebtrack/ui/event_bus.py` - Enhanced with named events
2. `src/zebtrack/ui/events.py` - **NEW** - Event catalog
3. `src/zebtrack/core/controller.py` - Added event subscriptions
4. `src/zebtrack/ui/gui.py` - Added event handling, demonstrated pattern
5. `src/zebtrack/settings.py` - Enabled event bus by default

## Lines of Code Added

- ~200 lines in `event_bus.py` (new methods + subscribers)
- ~120 lines in `events.py` (event catalog)
- ~180 lines in `controller.py` (handler registration + 30 handlers)
- ~30 lines in `gui.py` (event handling + publish helper)

**Total:** ~530 lines of new event-driven architecture code

## Conclusion

**Phase 1 is ~70% complete:**
- ✅ Event bus infrastructure fully implemented
- ✅ Event catalog documented
- ✅ Controller subscriptions wired up
- ✅ Event bus enabled by default
- ✅ Pattern demonstrated with critical controls
- ⚠️ ~45+ GUI calls still need conversion
- ❌ Tests not yet updated
- ❌ Full validation not yet performed

**Estimated Remaining Effort:**
- GUI call conversions: ~2-3 hours (mechanical, repetitive)
- Test updates: ~3-4 hours (requires thought, mocking)
- Validation & smoke tests: ~1-2 hours

**Total Remaining:** ~6-9 hours to complete Phase 1
