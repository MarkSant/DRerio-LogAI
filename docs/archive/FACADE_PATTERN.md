# Facade Pattern in ZebTrack-AI

## Overview

This document explains the Facade Pattern implementation in ZebTrack-AI, specifically for isolating complex MainViewModel logic into focused, testable facade classes.

## Purpose

The facade classes were created to address the following goals:
1. **Reduce MainViewModel complexity** - Extract specialized logic into dedicated facades
2. **Improve testability** - Each facade can be tested independently with mocked dependencies
3. **Enhance maintainability** - Changes to specific domains (recording, zones, Arduino) are isolated
4. **Support dependency injection** - Facades receive all dependencies via constructor

## Architecture

### Facade Classes

Three facade classes encapsulate distinct domains of functionality:

#### 1. RecordingFacade (`src/zebtrack/core/recording_facade.py`)

**Responsibilities:**
- Managing recording lifecycle (start/stop)
- Coordinating Recorder with StateManager
- Publishing recording events via EventBus

**Dependencies:**
- `Recorder` - Low-level recording operations
- `StateManager` - State tracking and observation
- `EventBus` - Event publishing for UI updates

**Key Methods:**
- `start_recording(video_path, output_dir, fps, record_video)` - Start recording session
- `stop_recording()` - Stop current recording
- `is_recording()` - Check recording status
- `get_output_files()` - Retrieve output file paths

**Example Usage:**
```python
from zebtrack.core.recording_facade import RecordingFacade

# Initialize with dependencies
facade = RecordingFacade(
    recorder=recorder_instance,
    state_manager=state_manager_instance,
    event_bus=event_bus_instance
)

# Start recording
success = facade.start_recording(
    video_path=Path("/path/to/video.mp4"),
    output_dir=Path("/path/to/output"),
    fps=30.0,
    record_video=True
)

# Check status
if facade.is_recording():
    print("Recording in progress")

# Stop recording
facade.stop_recording()

# Get output files
files = facade.get_output_files()
parquet_file = files.get("parquet")
```

---

#### 2. ZoneManagementFacade (`src/zebtrack/core/zone_management_facade.py`)

**Responsibilities:**
- Drawing and saving arena polygons
- Managing ROI templates (load/apply/list)
- Coordinate validation and scaling
- Integration with ProjectManager for persistence

**Dependencies:**
- `ProjectManager` - Zone and ROI persistence
- `StateManager` - UI state tracking (drawing mode)

**Key Methods:**
- `start_arena_drawing(video_path)` - Initiate arena drawing mode
- `save_arena(polygon, video_path)` - Save arena polygon
- `load_roi_template(template_name)` - Load ROI template from library
- `apply_template_to_video(template_name, video_path, scale_to_arena)` - Apply template
- `get_arena_for_video(video_path)` - Retrieve arena for video
- `get_rois_for_video(video_path)` - Retrieve ROIs for video
- `clear_arena(video_path)` - Remove arena
- `clear_rois(video_path)` - Remove ROIs
- `list_available_templates()` - List available ROI templates

**Example Usage:**
```python
from zebtrack.core.zone_management_facade import ZoneManagementFacade

# Initialize with dependencies
facade = ZoneManagementFacade(
    project_manager=project_manager_instance,
    state_manager=state_manager_instance
)

# Start drawing arena
facade.start_arena_drawing(video_path=Path("/path/to/video.mp4"))

# Save arena polygon
polygon = [(0, 0), (100, 0), (100, 100), (0, 100)]
facade.save_arena(polygon, video_path=Path("/path/to/video.mp4"))

# List available templates
templates = facade.list_available_templates()
print(f"Available templates: {templates}")

# Apply template to video
facade.apply_template_to_video(
    template_name="4zones",
    video_path=Path("/path/to/video.mp4"),
    scale_to_arena=True
)

# Get arena for video
arena = facade.get_arena_for_video(video_path=Path("/path/to/video.mp4"))
```

---

#### 3. ArduinoFacade (`src/zebtrack/core/arduino_facade.py`)

**Responsibilities:**
- Scanning for available Arduino ports
- Managing Arduino connection/disconnection
- Sending commands to Arduino
- Tracking connection status

**Dependencies:**
- `ArduinoManager` - Low-level Arduino communication
- `StateManager` - Connection state tracking

**Key Methods:**
- `scan_ports()` - Scan for available Arduino ports
- `connect(port, baudrate)` - Connect to Arduino
- `disconnect()` - Disconnect from Arduino
- `send_command(command)` - Send command to Arduino
- `is_connected()` - Check connection status
- `get_connected_port()` - Get currently connected port
- `get_status()` - Get connection status dictionary

**Example Usage:**
```python
from zebtrack.core.arduino_facade import ArduinoFacade

# Initialize with dependencies
facade = ArduinoFacade(
    arduino_manager=arduino_manager_instance,
    state_manager=state_manager_instance
)

# Scan for ports
ports = facade.scan_ports()
print(f"Available ports: {ports}")

# Connect to Arduino
if ports:
    success = facade.connect(port=ports[0], baudrate=9600)
    if success:
        print("Connected successfully")

# Send command
if facade.is_connected():
    facade.send_command("LED_ON")

# Check status
status = facade.get_status()
print(f"Connected: {status['connected']}, Port: {status['port']}")

# Disconnect
facade.disconnect()
```

---

## Design Principles

### 1. Single Responsibility Principle
Each facade handles one domain:
- Recording operations
- Zone/ROI management
- Arduino communication

### 2. Dependency Injection
All dependencies are passed via constructor:
```python
def __init__(
    self,
    recorder: "Recorder",
    state_manager: "StateManager",
    event_bus: "EventBus",
):
```

This enables:
- Easy testing with mocks
- Flexible composition
- Clear dependency graph

### 3. Error Handling
All public methods:
- Return `bool` for success/failure operations
- Log errors with structured logging
- Never raise exceptions to callers
- Return empty/safe defaults on error

Example:
```python
def start_recording(...) -> bool:
    try:
        # ... operation logic
        return True
    except Exception as e:
        log.error("recording_facade.start.failed", error=str(e), exc_info=True)
        return False
```

### 4. State Coordination
Facades coordinate state updates:
```python
# Update state
self.state_manager.update_recording_state(
    source="recording_facade.start",
    is_recording=True,
    output_path=output_dir
)

# Publish event
self.event_bus.publish_event(
    "recording.started",
    data={"video_path": str(video_path)}
)
```

### 5. Logging
Structured logging with domain.action.result pattern:
```python
log.info("recording_facade.start.success", video=str(video_path))
log.error("recording_facade.start.failed", error=str(e))
log.warning("recording_facade.stop.not_recording")
```

---

## Testing Strategy

Each facade has comprehensive unit tests (see `tests/core/test_*_facade.py`):

### Test Coverage
- **RecordingFacade**: 17 tests
- **ZoneManagementFacade**: 21 tests
- **ArduinoFacade**: 21 tests
- **Total**: 59 tests

### Test Structure
```python
class TestRecordingFacadeInitialization:
    """Test initialization"""
    
class TestRecordingFacadeStartRecording:
    """Test start_recording method"""
    
class TestRecordingFacadeStopRecording:
    """Test stop_recording method"""
```

### Test Patterns
1. **Mock all dependencies** - No real I/O in unit tests
2. **Test success paths** - Verify expected behavior
3. **Test failure paths** - Exception handling, invalid inputs
4. **Test state updates** - Verify StateManager calls
5. **Test event publishing** - Verify EventBus calls

Example test:
```python
def test_start_recording_success(self, recording_facade, tmp_path):
    """Test successful start of recording."""
    video_path = tmp_path / "test_video.mp4"
    video_path.touch()
    output_dir = tmp_path / "output"
    
    result = recording_facade.start_recording(
        video_path=video_path,
        output_dir=output_dir
    )
    
    assert result is True
    assert output_dir.exists()
```

---

## Integration with MainViewModel

The facades are designed to be used by MainViewModel:

```python
class MainViewModel:
    def __init__(
        self,
        recorder: Recorder,
        state_manager: StateManager,
        event_bus: EventBus,
        project_manager: ProjectManager,
        arduino_manager: ArduinoManager,
        # ... other dependencies
    ):
        # Initialize facades
        self.recording_facade = RecordingFacade(
            recorder=recorder,
            state_manager=state_manager,
            event_bus=event_bus
        )
        
        self.zone_facade = ZoneManagementFacade(
            project_manager=project_manager,
            state_manager=state_manager
        )
        
        self.arduino_facade = ArduinoFacade(
            arduino_manager=arduino_manager,
            state_manager=state_manager
        )
    
    def start_recording(self):
        """Delegate to facade"""
        return self.recording_facade.start_recording(...)
```

---

## Benefits

### Before Facades
- MainViewModel had 1000+ lines
- Mixed concerns (recording, zones, Arduino, UI)
- Difficult to test
- High coupling

### After Facades
- Logic extracted to 3 focused classes
- Each facade < 300 lines
- 59 comprehensive tests
- Clear boundaries and responsibilities
- Easy to mock and test

---

## Future Enhancements

Potential improvements:
1. **ROI Scaling Logic** - Implement proper coordinate scaling in `_scale_rois_to_arena`
2. **Validation** - Add more input validation for polygons and coordinates
3. **Events** - Expand event publishing for fine-grained UI updates
4. **Async Operations** - Support async recording operations
5. **Additional Facades** - Extract more domains (e.g., ProcessingFacade, AnalysisFacade)

---

## References

- `src/zebtrack/core/recording_facade.py`
- `src/zebtrack/core/zone_management_facade.py`
- `src/zebtrack/core/arduino_facade.py`
- `tests/core/test_recording_facade.py`
- `tests/core/test_zone_management_facade.py`
- `tests/core/test_arduino_facade.py`
- `docs/ARCHITECTURE.md` - Overall system architecture
- `docs/DEPENDENCY_INJECTION_GUIDE.md` - DI patterns

---

## Contact

For questions or suggestions regarding the facade pattern implementation:
- Review the test files for usage examples
- Check existing facade implementations for patterns
- Consult `docs/ARCHITECTURE.md` for broader context
