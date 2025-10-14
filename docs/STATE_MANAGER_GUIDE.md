# StateManager Developer Guide

## Quick Reference

The `StateManager` is ZebTrack-AI's centralized state management system that provides a single source of truth for application state with observable pattern support and thread safety.

## When to Use StateManager

### ✅ DO Use StateManager For:

- **Application state that multiple components need to access**
  - Recording status, detector initialization, processing progress
  - Project path and configuration
  
- **State changes that should trigger UI updates**
  - Subscribe GUI components to state changes for reactive updates
  
- **State that needs debugging/auditing**
  - All mutations are tracked with source and timestamp
  
- **Concurrent access from multiple threads**
  - Thread-safe operations built-in

### ❌ DON'T Use StateManager For:

- **Local component state** (temporary variables, UI-only state)
- **High-frequency updates** (pixel coordinates during mouse drag)
- **State that doesn't need to be shared** (private implementation details)

## Basic Usage

### 1. Accessing StateManager

In `MainViewModel` (controller):
```python
# Already initialized in MainViewModel.__init__
self.state_manager  # Access the StateManager instance
```

### 2. Reading State

Use category-specific getter methods:

```python
# Get individual state categories
recording_state = self.state_manager.get_recording_state()
if recording_state.is_recording:
    print(f"Recording to: {recording_state.output_path}")

detector_state = self.state_manager.get_detector_state()
if detector_state.detector_initialized:
    print(f"Using weights: {detector_state.active_weight_name}")

processing_state = self.state_manager.get_processing_state()
progress = processing_state.current_frame / processing_state.total_frames * 100

project_state = self.state_manager.get_project_state()
if project_state.project_path:
    print(f"Active project: {project_state.project_path}")

# Get complete state snapshot (immutable)
snapshot = self.state_manager.get_snapshot()
print(f"Recording: {snapshot.recording.is_recording}")
print(f"Processing: {snapshot.processing.is_processing}")
```

### 3. Updating State

Always provide a `source` parameter for debugging:

```python
# Update recording state
self.state_manager.update_recording_state(
    source="controller.start_recording",
    is_recording=True,
    output_path="/path/to/output.mp4",
)

# Update detector state
self.state_manager.update_detector_state(
    source="controller.setup_detector",
    detector_initialized=True,
    active_weight_name="best_seg.pt",
    use_openvino=False,
)

# Update processing state (progress)
self.state_manager.update_processing_state(
    source="controller.on_progress",
    current_frame=500,
    total_frames=1000,
)

# Update project state
self.state_manager.update_project_state(
    source="controller.open_project",
    project_path=Path("/path/to/project"),
    project_data={"videos": ["v1.mp4", "v2.mp4"]},
)
```

**Important:** Only changed fields need to be provided. Unchanged fields retain their current values.

### 4. Subscribing to State Changes (Observer Pattern)

Subscribe callbacks to be notified when state changes:

```python
from zebtrack.core.state_manager import StateCategory

def on_recording_state_changed(category, key, old_value, new_value):
    """Called whenever recording state changes."""
    print(f"Recording state changed: {key} = {old_value} -> {new_value}")
    
    if key == "is_recording":
        if new_value:
            # Update UI: disable start button, enable stop button
            pass
        else:
            # Update UI: enable start button, disable stop button
            pass

# Subscribe to all recording state changes
self.state_manager.subscribe(StateCategory.RECORDING, on_recording_state_changed)

# Subscribe to all state changes across all categories
self.state_manager.subscribe(None, on_any_state_changed)

# Unsubscribe when no longer needed
self.state_manager.unsubscribe(StateCategory.RECORDING, on_recording_state_changed)
```

**Callback signature:**
```python
def callback(category: StateCategory, key: str, old_value: Any, new_value: Any) -> None:
    """
    Args:
        category: The state category that changed
        key: The specific state field that changed
        old_value: Previous value
        new_value: New value
    """
```

## State Categories

### ProjectState
```python
@dataclass(slots=True)
class ProjectState:
    project_path: Path | None = None
    project_data: dict = field(default_factory=dict)
    active_zone_video: str | None = None
```

**Use for:** Project file paths, configuration, active video for zone editing

### DetectorState
```python
@dataclass(slots=True)
class DetectorState:
    detector_initialized: bool = False
    active_weight_name: str | None = None
    use_openvino: bool = False
    detector_type: str | None = None  # "det" or "seg"
```

**Use for:** Detector initialization status, model selection, inference backend

### RecordingState
```python
@dataclass(slots=True)
class RecordingState:
    is_recording: bool = False
    output_path: str | None = None
    recording_start_time: datetime | None = None
```

**Use for:** Recording session status, output file path, start timestamp

### ProcessingState
```python
@dataclass(slots=True)
class ProcessingState:
    is_processing: bool = False
    current_video: str | None = None
    current_frame: int = 0
    total_frames: int = 0
    processing_start_time: datetime | None = None
    cancel_requested: bool = False
```

**Use for:** Analysis progress, current video being processed, cancellation state

### UIState
```python
@dataclass(slots=True)
class UIState:
    current_view: str | None = None
    selected_video: str | None = None
    zoom_level: float = 1.0
```

**Use for:** UI-specific state (active tab, zoom level, selected items)

## Backward-Compatible Properties

The controller provides properties that delegate to StateManager:

```python
# In controller.py

@property
def is_recording(self) -> bool:
    return self.state_manager.get_recording_state().is_recording

@is_recording.setter
def is_recording(self, value: bool) -> None:
    self.state_manager.update_recording_state(
        source="controller.is_recording_setter",
        is_recording=value,
    )

@property
def detector_initialized(self) -> bool:
    return self.state_manager.get_detector_state().detector_initialized

@property
def is_processing(self) -> bool:
    return self.state_manager.get_processing_state().is_processing
```

**Usage:**
```python
# Old code continues to work
if self.is_recording:
    self.stop_recording()

# But now it uses StateManager under the hood
```

## Debugging

### View Current State

```python
# Get human-readable state dump
state_dump = self.state_manager.dump_state()

import json
print(json.dumps(state_dump, indent=2, default=str))
```

**Output:**
```json
{
  "recording": {
    "is_recording": true,
    "output_path": "/path/to/output.mp4",
    "recording_start_time": "2024-01-15T10:30:00"
  },
  "detector": {
    "initialized": true,
    "active_weight": "best_seg.pt",
    "use_openvino": false
  },
  "processing": {
    "is_processing": false,
    "current_video": null,
    "current_frame": 0,
    "total_frames": 0
  },
  "project": {
    "project_path": "/path/to/project",
    "active_zone_video": "video1.mp4"
  }
}
```

### View State History

```python
# Get all state changes
all_history = self.state_manager.get_history()

# Get history for specific category
recording_history = self.state_manager.get_history(
    category=StateCategory.RECORDING
)

# Get history for specific field
recording_status_history = self.state_manager.get_history(
    category=StateCategory.RECORDING,
    key="is_recording"
)

# Print history
for entry in recording_status_history:
    print(f"{entry['timestamp']}: {entry['old_value']} -> {entry['new_value']}")
    print(f"  Source: {entry['source']}")
```

**Example output:**
```
2024-01-15 10:30:00: False -> True
  Source: controller.start_recording
2024-01-15 10:35:00: True -> False
  Source: controller.stop_recording
```

## Common Patterns

### Pattern 1: Recording Session

```python
def start_recording(self):
    """Start a new recording session."""
    output_path = self._generate_output_path()
    
    # Update state
    self.state_manager.update_recording_state(
        source="controller.start_recording",
        is_recording=True,
        output_path=str(output_path),
    )
    
    # Actual recording logic...
    
def stop_recording(self):
    """Stop recording session."""
    # Clean up recording...
    
    # Clear state
    self.state_manager.update_recording_state(
        source="controller.stop_recording",
        is_recording=False,
        output_path=None,
        recording_start_time=None,
    )
```

### Pattern 2: Processing Progress

```python
def start_analysis(self, video_path):
    """Start video analysis."""
    self.state_manager.update_processing_state(
        source="controller.start_analysis",
        is_processing=True,
        current_video=str(video_path),
        total_frames=video.total_frames,
    )

def on_progress(self, stats):
    """Called periodically during analysis."""
    self.state_manager.update_processing_state(
        source="controller.on_progress",
        current_frame=stats["processed_frames"],
    )

def on_completed(self):
    """Called when analysis completes."""
    self.state_manager.update_processing_state(
        source="controller.on_completed",
        is_processing=False,
        current_video=None,
        current_frame=0,
        total_frames=0,
    )
```

### Pattern 3: Reactive UI Updates

```python
class ApplicationGUI:
    def __init__(self, controller):
        self.controller = controller
        
        # Subscribe to state changes
        controller.state_manager.subscribe(
            StateCategory.RECORDING,
            self.on_recording_state_changed
        )
        controller.state_manager.subscribe(
            StateCategory.PROCESSING,
            self.on_processing_state_changed
        )
    
    def on_recording_state_changed(self, category, key, old_val, new_val):
        """Update UI when recording state changes."""
        if key == "is_recording":
            if new_val:
                self.start_button.config(state="disabled")
                self.stop_button.config(state="normal")
                self.status_label.config(text="Recording...")
            else:
                self.start_button.config(state="normal")
                self.stop_button.config(state="disabled")
                self.status_label.config(text="Ready")
    
    def on_processing_state_changed(self, category, key, old_val, new_val):
        """Update progress bar when processing state changes."""
        if key == "current_frame":
            state = self.controller.state_manager.get_processing_state()
            progress = state.current_frame / state.total_frames * 100
            self.progress_bar["value"] = progress
```

## Thread Safety

StateManager is thread-safe by default:

```python
# Safe to call from multiple threads
def worker_thread():
    controller.state_manager.update_processing_state(
        source="worker_thread",
        current_frame=frame_number,
    )

# Safe to read from multiple threads
def ui_thread():
    state = controller.state_manager.get_processing_state()
    print(f"Progress: {state.current_frame}/{state.total_frames}")
```

**Note:** Callbacks are executed synchronously in the thread that triggers the state change. Keep callbacks fast to avoid blocking.

## Best Practices

### 1. Always Provide Source

```python
# ✅ Good - clear source for debugging
self.state_manager.update_recording_state(
    source="controller.start_recording_session",
    is_recording=True,
)

# ❌ Bad - no source (won't work, raises error)
self.state_manager.update_recording_state(
    is_recording=True,
)
```

### 2. Use Descriptive Source Names

```python
# ✅ Good - identifies exact location
source="controller.create_project_workflow"
source="gui.on_start_button_clicked"
source="detector.zone_entry_detected"

# ❌ Bad - too vague
source="update"
source="test"
```

### 3. Keep State Minimal

Only store what needs to be shared:

```python
# ✅ Good - shared state
self.state_manager.update_recording_state(
    source="...",
    is_recording=True,  # Multiple components need this
)

# ❌ Bad - local state doesn't belong in StateManager
self.state_manager.update_ui_state(
    source="...",
    mouse_x=event.x,  # Too granular, use local variable
    mouse_y=event.y,
)
```

### 4. Batch Related Updates

```python
# ✅ Good - one update with all related fields
self.state_manager.update_recording_state(
    source="controller.start_recording",
    is_recording=True,
    output_path=str(path),
    recording_start_time=datetime.now(),
)

# ❌ Bad - multiple separate updates (triggers observers multiple times)
self.state_manager.update_recording_state(source="...", is_recording=True)
self.state_manager.update_recording_state(source="...", output_path=str(path))
self.state_manager.update_recording_state(source="...", recording_start_time=datetime.now())
```

### 5. Clear State on Completion

```python
# ✅ Good - reset state after operation completes
self.state_manager.update_processing_state(
    source="controller.on_completed",
    is_processing=False,
    current_video=None,
    current_frame=0,
    total_frames=0,
)

# ❌ Bad - leaves stale state
self.state_manager.update_processing_state(
    source="controller.on_completed",
    is_processing=False,
    # current_video still set to old video!
)
```

## Testing

### Unit Tests

```python
def test_state_update():
    state_manager = StateManager()
    
    state_manager.update_recording_state(
        source="test",
        is_recording=True,
    )
    
    state = state_manager.get_recording_state()
    assert state.is_recording is True

def test_observer_notification():
    state_manager = StateManager()
    changes = []
    
    def observer(category, key, old_val, new_val):
        changes.append((key, old_val, new_val))
    
    state_manager.subscribe(StateCategory.RECORDING, observer)
    
    state_manager.update_recording_state(
        source="test",
        is_recording=True,
    )
    
    assert len(changes) == 1
    assert changes[0] == ("is_recording", False, True)
```

### Integration Tests

```python
def test_controller_integration(controller):
    """Test StateManager integration with controller."""
    # Start recording
    controller.start_recording()
    
    # Verify state updated
    assert controller.state_manager.get_recording_state().is_recording
    assert controller.is_recording  # Property works too
    
    # Stop recording
    controller.stop_recording()
    
    # Verify state cleared
    assert not controller.state_manager.get_recording_state().is_recording
    assert not controller.is_recording
```

## Troubleshooting

### State Not Updating

**Problem:** State change not reflected

**Solutions:**
1. Check that `update_*_state()` was called with correct parameters
2. Verify history: `state_manager.get_history()`
3. Check for exceptions in observer callbacks (they're logged but don't crash)

### Observer Not Called

**Problem:** Subscribed callback not receiving notifications

**Solutions:**
1. Verify subscription: print registered observers `state_manager._observers`
2. Check that you're subscribing to correct category
3. Ensure state actually changed (updates with same value don't notify)

### Performance Issues

**Problem:** StateManager operations slow

**Solutions:**
1. Check history size: `state_manager.history_max_size` (default 100)
2. Disable history if not needed: `StateManager(enable_history=False)`
3. Review observer callbacks - keep them fast (< 1ms)
4. Avoid high-frequency updates (> 60 Hz)

## Migration Checklist

When adding StateManager to a new component:

- [ ] Identify state that needs to be shared
- [ ] Choose appropriate state category (or create new one)
- [ ] Add state updates at mutation points with descriptive `source`
- [ ] Add backward-compatible properties if needed
- [ ] Subscribe observers for reactive behavior
- [ ] Add tests for state updates and observations
- [ ] Document state fields and their meaning
- [ ] Clear state on cleanup/completion

## See Also

- `src/zebtrack/core/state_manager.py` - Implementation
- `tests/test_state_manager.py` - Unit tests (35 tests)
- `tests/test_state_manager_integration.py` - Integration tests (9 tests)
- `docs/STATE_MANAGER_IMPLEMENTATION.md` - Full implementation guide
- `docs/PHASE2_STEP4_STATE_MANAGEMENT_SUMMARY.md` - Implementation summary
