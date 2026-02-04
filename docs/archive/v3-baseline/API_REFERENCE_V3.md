<!-- markdownlint-disable MD024 -->

# API Reference v3.0 - Current Public Interfaces

**Version:** 3.0 (Pre-Refactoring Baseline)
**Date:** January 2025
**Purpose:** Baseline documentation of public APIs before v4.0 refactoring

## Overview

This document catalogs the current public interfaces of ZebTrack-AI v3.0 that external
code and plugins depend on. These interfaces will be preserved or migrated during the
v4.0 refactoring to maintain backward compatibility.

### Related Documents

- `docs/REFACTOR-MASTER-PLAN-2025.md` - Refactoring strategy
- `docs/ARCHITECTURE.md` - Overall architecture
- `docs/DEPENDENCY_INJECTION_GUIDE.md` - DI patterns

---

## 1. MainViewModel Public Interface

**File:** `src/zebtrack/core/main_view_model.py` (5,652 lines)

### 1.1 Overview

The MainViewModel is the central orchestrator of the application. It coordinates all
business logic and state management.

### Current Issues

- **SRP Violation:** 154 methods, 164 instance variables
- **God Object:** Manages 7+ different concerns
- **Low Testability:** High coupling, difficult to mock

**Refactoring Target:** Extract 5 coordinators (Sprint 3-6)

### 1.2 Constructor

```python
def __init__(
    self,
    state_manager: StateManager,
    project_manager: ProjectManager,
    project_service: ProjectService,
    detector_service: DetectorService,
    wizard_service: WizardService,
    video_processing_service: VideoProcessingService,
    recording_service: RecordingService,
    live_camera_service: LiveCameraService,
    analysis_service: AnalysisService,
    camera: Camera,
    event_bus: EventBus | None = None,
    settings_obj: Settings = None,
):
    """Initialize MainViewModel with injected dependencies."""
```

### Dependencies (11 total)

1. `StateManager` - State management
2. `ProjectManager` - Project data persistence
3. `ProjectService` - Project business logic
4. `DetectorService` - AI detection service
5. `WizardService` - Wizard logic
6. `VideoProcessingService` - Video processing workflows
7. `RecordingService` - Recording coordination
8. `LiveCameraService` - Live camera sessions
9. `AnalysisService` - Behavioral analysis
10. `Camera` - Hardware abstraction
11. `EventBus` - Event notifications (optional)
12. `Settings` - Configuration

### 1.3 Project Management Methods

### PUBLIC API - Do Not Break

```python
def create_project_traditional(
    self,
    project_path: str,
    project_name: str,
    experiment_id: str,
    video_file: str = None,
) -> bool:
    """Create project using traditional flow (deprecated in favor of wizard)."""

def create_project_from_wizard_data(self, wizard_data: dict) -> bool:
    """Create project from wizard data (v1.6+)."""

def load_project(self, project_folder: str) -> bool:
    """Load existing project from folder."""

def get_current_project_name(self) -> str | None:
    """Get name of currently loaded project."""

def get_current_project_path(self) -> str | None:
    """Get path of currently loaded project."""

def validate_project_structure(self, project_folder: str) -> bool:
    """Validate project folder structure."""
```

### Planned Migration (Sprint 3)

- Extract to `ProjectCoordinator`
- Maintain compatibility via delegation

### 1.4 Detector Management Methods

### PUBLIC API - Do Not Break

```python
def initialize_detector(
    self,
    detector_type: str = "yolo11",
    weight_name: str = "yolo11n.pt",
    device: str = None,
) -> bool:
    """Initialize AI detector with specified configuration."""

def set_detector_zones(self, zones: list[dict]) -> bool:
    """Configure detection zones."""

def get_available_weights(self) -> list[str]:
    """Get list of available model weights."""

def get_detector_info(self) -> dict:
    """Get current detector configuration and status."""
```

### Planned Migration (Sprint 4)

- Extract to `DetectorCoordinator`
- Maintain compatibility

### 1.5 Recording Management Methods

### PUBLIC API - Do Not Break

```python
def start_recording(
    self,
    output_path: str,
    experiment_id: str,
    duration: int | None = None,
    zones: list[dict] | None = None,
) -> bool:
    """Start Arduino-coordinated recording session."""

def stop_recording(self) -> bool:
    """Stop current recording session."""

def get_recording_status(self) -> dict:
    """Get current recording session status."""
```

### Planned Migration (Sprint 5)

- Extract to `RecordingCoordinator`
- Maintain compatibility

### 1.6 Live Camera Methods

### PUBLIC API - Do Not Break

```python
def start_live_camera_analysis(
    self,
    camera_index: int = 0,
    duration: int | None = None,
    output_path: str | None = None,
    zones: list[dict] | None = None,
    analysis_interval: int = 10,
    display_interval: int = 10,
    save_video: bool = True,
) -> bool:
    """Start live camera analysis session (v2.0+)."""

def stop_live_camera_analysis(self) -> bool:
    """Stop live camera analysis session."""

def get_live_camera_status(self) -> dict:
    """Get current live camera session status."""
```

### Planned Migration (Sprint 6)

- Extract to `LiveCameraCoordinator`
- Maintain compatibility

### 1.7 Video Processing Methods

### PUBLIC API - Do Not Break

```python
def process_single_video(
    self,
    video_path: str,
    zones: list[dict],
    analysis_interval: int = 10,
    display_interval: int = 10,
    output_folder: str | None = None,
) -> bool:
    """Process a single video file with detection and analysis."""

def process_multiple_videos(
    self,
    video_paths: list[str],
    zones: list[dict],
    analysis_interval: int = 10,
    display_interval: int = 10,
    output_folder: str | None = None,
) -> bool:
    """Process multiple videos in parallel."""

def get_processing_progress(self) -> dict:
    """Get current processing progress."""
```

### Planned Migration (Sprint 7)

- Extract to `ProcessingCoordinator`
- Maintain compatibility

### 1.8 State Access Methods

### PUBLIC API - Do Not Break

```python
def get_project_state(self) -> ProjectState:
    """Get current project state."""

def get_detector_state(self) -> DetectorState:
    """Get current detector state."""

def get_recording_state(self) -> RecordingState:
    """Get current recording state."""

def get_processing_state(self) -> ProcessingState:
    """Get current processing state."""

def subscribe_to_state(
    self,
    category: StateCategory,
    observer: callable,
) -> None:
    """Subscribe to state changes (Observer pattern)."""
```

### Planned Changes

- These will delegate to StateManager (already does)
- No compatibility concerns

---

## 2. ApplicationGUI Public Interface

**File:** `src/zebtrack/ui/gui.py` (3,737 lines)

### 2.1 Overview

The ApplicationGUI is the main Tkinter window that manages all UI components.

### Current Issues

- **SRP Violation:** 232 methods, 7 UI responsibilities
- **Monolithic:** All UI in one class
- **Low Testability:** Difficult to test in isolation

**Refactoring Target:** Extract 12 UI components (Sprint 8-10)

### 2.2 Constructor

```python
def __init__(
    self,
    controller: MainViewModel,
    event_bus: EventBus,
    settings_obj: Settings,
):
    """Initialize main GUI window with injected dependencies."""
```

### Dependencies

1. `MainViewModel` - Application controller
2. `EventBus` - Event notifications
3. `Settings` - Configuration

### 2.3 Window Management

### PUBLIC API - Do Not Break

```python
def show(self) -> None:
    """Show the main window."""

def hide(self) -> None:
    """Hide the main window."""

def close(self) -> None:
    """Close the application."""

def get_root(self) -> tk.Tk:
    """Get the root Tkinter window."""
```

### 2.4 Menu Management

### PUBLIC API - Do Not Break

```python
def create_menu_bar(self) -> None:
    """Create application menu bar."""

def update_menu_states(self) -> None:
    """Update menu item states based on application state."""
```

### Planned Migration (Sprint 8)

- Extract to `MenuManager` component
- Maintain compatibility

### 2.5 Project View Management

### PUBLIC API - Do Not Break

```python
def show_project_overview(self) -> None:
    """Show project overview panel."""

def show_video_display(self) -> None:
    """Show video display panel."""

def show_analysis_display(self) -> None:
    """Show analysis results panel."""

def refresh_project_view(self) -> None:
    """Refresh current project view."""
```

### Planned Migration (Sprint 9)

- Extract to `ProjectViewManager` component
- Maintain compatibility

### 2.6 Dialog Management

### PUBLIC API - Do Not Break

```python
def show_settings_dialog(self) -> None:
    """Show settings configuration dialog."""

def show_about_dialog(self) -> None:
    """Show about dialog."""

def show_error_dialog(self, title: str, message: str) -> None:
    """Show error message dialog."""

def show_confirm_dialog(
    self,
    title: str,
    message: str,
) -> bool:
    """Show confirmation dialog, return True if confirmed."""
```

### Planned Migration (Sprint 10)

- Extract to `DialogManager` component
- Maintain compatibility

---

## 3. Service Layer Public Interfaces

### 3.1 DetectorService

**File:** `src/zebtrack/core/detector.py` (677 lines)

```python
class DetectorService:
    """AI detection service with zone tracking."""

    def initialize(
        self,
        detector_type: str = "yolo11",
        weight_name: str = "yolo11n.pt",
        device: str | None = None,
    ) -> bool:
        """Initialize detector with model weights."""

    def set_zones(self, zones: list[dict]) -> None:
        """Configure detection zones."""

    def detect(
        self,
        frame: np.ndarray,
        context: DetectionContext = DetectionContext.TRACKING,
    ) -> list[dict]:
        """Run detection on a frame."""

    def get_available_weights(self) -> list[str]:
        """Get available model weights."""
```

**Stability:** Stable - no planned breaking changes

### 3.2 VideoProcessingService

**File:** `src/zebtrack/core/video_processing_service.py` (1,788 lines)

```python
class VideoProcessingService:
    """Video processing workflow orchestration."""

    def process_video(
        self,
        video_path: str,
        zones: list[dict],
        output_folder: str,
        analysis_interval: int = 10,
        display_interval: int = 10,
        progress_callback: callable | None = None,
    ) -> bool:
        """Process single video with detection and analysis."""

    def process_videos_parallel(
        self,
        video_paths: list[str],
        zones: list[dict],
        output_folder: str,
        max_workers: int = 2,
        progress_callback: callable | None = None,
    ) -> dict[str, bool]:
        """Process multiple videos in parallel."""
```

**Stability:** Stable - no planned breaking changes

### 3.3 LiveCameraService

**File:** `src/zebtrack/core/live_camera_service.py` (899 lines)

```python
class LiveCameraService:
    """Live camera analysis session management."""

    def start_session(
        self,
        camera_index: int = 0,
        duration: int | None = None,
        output_path: str | None = None,
        zones: list[dict] | None = None,
        save_video: bool = True,
        progress_callback: callable | None = None,
    ) -> bool:
        """Start live camera analysis session."""

    def stop_session(self) -> bool:
        """Stop current session."""

    def get_session_status(self) -> dict:
        """Get current session status."""
```

**Stability:** Stable (v2.1 unification complete)

### 3.4 WizardService

**File:** `src/zebtrack/core/wizard_service.py`

```python
class WizardService:
    """Project wizard business logic."""

    def detect_cameras(self) -> list[dict]:
        """Detect available cameras (30s cache)."""

    def detect_arduino_ports(self) -> list[dict]:
        """Detect Arduino ports (30s cache)."""

    def validate_project_name(self, name: str) -> tuple[bool, str]:
        """Validate project name."""

    def validate_experiment_id(self, exp_id: str) -> tuple[bool, str]:
        """Validate experiment ID."""
```

**Stability:** Stable - no planned breaking changes

---

## 4. State Management Public Interface

**File:** `src/zebtrack/core/state_manager.py` (1,184 lines)

### 4.1 StateManager

```python
class StateManager:
    """Centralized state management with Observer pattern."""

    def __init__(self, enable_history: bool = False):
        """Initialize state manager."""

    def update_project_state(self, source: str = None, **kwargs) -> None:
        """Update project state fields."""

    def update_detector_state(self, source: str = None, **kwargs) -> None:
        """Update detector state fields."""

    def update_recording_state(self, source: str = None, **kwargs) -> None:
        """Update recording state fields."""

    def update_processing_state(self, source: str = None, **kwargs) -> None:
        """Update processing state fields."""

    def get_project_state(self) -> ProjectState:
        """Get current project state snapshot."""

    def get_detector_state(self) -> DetectorState:
        """Get current detector state snapshot."""

    def subscribe(
        self,
        category: StateCategory,
        observer: callable,
        observer_id: str | None = None,
    ) -> str:
        """Subscribe to state changes."""

    def unsubscribe(
        self,
        category: StateCategory,
        observer_id: str,
    ) -> bool:
        """Unsubscribe from state changes."""
```

**Stability:** Highly stable - foundational component

---

## 5. Data Models

### 5.1 State Models

**File:** `src/zebtrack/core/state_manager.py`

```python
@dataclass
class ProjectState:
    """Project state data."""
    project_path: str | None = None
    project_name: str | None = None
    experiment_id: str | None = None
    video_file: str | None = None
    is_loaded: bool = False
    # ... additional fields

@dataclass
class DetectorState:
    """Detector state data."""
    detector_initialized: bool = False
    active_weight_name: str | None = None
    device: str | None = None
    zones_configured: bool = False
    # ... additional fields

@dataclass
class RecordingState:
    """Recording state data."""
    is_recording: bool = False
    session_start_time: float | None = None
    session_duration: int | None = None
    # ... additional fields

@dataclass
class ProcessingState:
    """Processing state data."""
    is_processing: bool = False
    current_video: str | None = None
    total_frames: int = 0
    processed_frames: int = 0
    # ... additional fields
```

**Stability:** Stable - fields may be added but not removed

### 5.2 Wizard Models

**File:** `src/zebtrack/ui/wizard/models.py`

```python
class ProjectTypeStep(BaseModel):
    """Project type selection data (Pydantic v2)."""
    project_type: Literal["traditional", "live_arduino"] = "traditional"

class ProjectInfoStep(BaseModel):
    """Project information data."""
    project_name: str = Field(min_length=1, max_length=100)
    experiment_id: str = Field(min_length=1, max_length=50)

class HardwareConfigStep(BaseModel):
    """Hardware configuration data."""
    camera_index: int = Field(ge=0)
    arduino_port: str | None = None
    # ... additional fields
```

**Stability:** Stable - no planned changes

---

## 6. Plugin System

### 6.1 DetectorPlugin Interface

**File:** `src/zebtrack/plugins/base.py`

```python
class DetectorPlugin(ABC):
    """Abstract base for detector plugins."""

    @abstractmethod
    def initialize(self, weight_name: str, device: str | None = None) -> bool:
        """Initialize the detector."""

    @abstractmethod
    def detect(self, frame: np.ndarray) -> list[dict]:
        """Run detection on a frame."""

    @abstractmethod
    def get_available_weights(self) -> list[str]:
        """Get available model weights."""

    @abstractmethod
    def cleanup(self) -> None:
        """Clean up resources."""
```

**Stability:** Stable - well-established interface

### 6.2 Registering Plugins

**File:** `src/zebtrack/plugins/__init__.py`

```python
DETECTOR_PLUGINS = {
    "yolo11": Yolo11Plugin,
    "yolo8": Yolo8Plugin,
    "openvino": OpenVinoPlugin,
}
```

**Stability:** Stable - new plugins can be added

---

## 7. Event System

### 7.1 EventBus

**File:** `src/zebtrack/ui/event_bus.py`

```python
class EventBus:
    """Event bus for loose coupling (Observer pattern)."""

    def subscribe(
        self,
        event_name: str,
        handler: callable,
        subscriber_id: str | None = None,
    ) -> str:
        """Subscribe to an event."""

    def unsubscribe(
        self,
        event_name: str,
        subscriber_id: str,
    ) -> bool:
        """Unsubscribe from an event."""

    def publish_event(
        self,
        event_name: str,
        data: dict,
    ) -> None:
        """Publish an event to all subscribers."""
```

### 7.2 Standard Events

**File:** `src/zebtrack/ui/events.py`

```python
class Events:
    """Standard event names."""

    # Project events
    PROJECT_CREATED = "project.created"
    PROJECT_LOADED = "project.loaded"
    PROJECT_CLOSED = "project.closed"

    # Detector events
    DETECTOR_INITIALIZED = "detector.initialized"
    DETECTION_STARTED = "detection.started"
    DETECTION_COMPLETED = "detection.completed"

    # Recording events
    RECORDING_STARTED = "recording.started"
    RECORDING_STOPPED = "recording.stopped"

    # Processing events
    PROCESSING_STARTED = "processing.started"
    PROCESSING_PROGRESS = "processing.progress"
    PROCESSING_COMPLETED = "processing.completed"

    # UI events
    UI_REFRESH_REQUESTED = "ui.refresh_requested"
```

**Stability:** Stable - new events may be added

---

## 8. Configuration

### 8.1 Settings

**File:** `src/zebtrack/settings.py`

```python
class Settings(BaseSettings):
    """Application settings (Pydantic v2)."""

    # Directories
    projects_dir: str = "projects"
    templates_dir: str = "templates"

    # Detector
    default_detector: str = "yolo11"
    default_weight: str = "yolo11n.pt"

    # Performance
    max_parallel_videos: int = 2
    max_parallel_plots: int = 3
    parquet_compression: str = "snappy"

    # UI
    window_width: int = 1150
    window_height: int = 550
    enable_event_queue: bool = False

    # ... additional fields
```

**Stability:** Fields may be added, existing fields preserved

---

## 9. Backward Compatibility Strategy

### 9.1 Coordinator Migration Pattern

When extracting coordinators from MainViewModel:

1. **Create new coordinator** with clean interface
2. **Keep original methods** in MainViewModel
3. **Delegate to coordinator** internally
4. **Deprecation warnings** in v4.0
5. **Remove delegation** in v5.0 (2026)

### Example

```python
# v4.0 - Delegation pattern
class MainViewModel:
    def create_project_from_wizard_data(self, wizard_data: dict) -> bool:
        """Create project from wizard data.

        DEPRECATED: Use ProjectCoordinator.create_project() instead.
        This method will be removed in v5.0.
        """
        warnings.warn(
            "create_project_from_wizard_data is deprecated, "
            "use ProjectCoordinator.create_project()",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._project_coordinator.create_project(wizard_data)
```

### 9.2 Component Migration Pattern

When extracting UI components from ApplicationGUI:

1. **Create new component** class
2. **Keep original methods** as thin wrappers
3. **Delegate to component** internally
4. **Gradual migration** over multiple sprints

---

## 10. API Stability Levels

### 10.1 Stable APIs

### No breaking changes planned

- StateManager interface
- Service layer interfaces (DetectorService, VideoProcessingService, etc.)
- Plugin system
- Event system
- Data models (fields may be added)

### 10.2 Evolving APIs

### Will be refactored with compatibility shim

- MainViewModel public methods → Coordinators (v4.0)
- ApplicationGUI public methods → Components (v4.0)

### 10.3 Internal APIs

### May change without notice

- Private methods (`_method_name`)
- Internal helper functions
- UI widget implementation details

---

## 11. Migration Timeline

| Sprint | Target | Changes | Compatibility |
| -------- | -------- | --------- | --------------- |
| 1-2 | Foundation | BaseCoordinator, BaseUIComponent | N/A (new) |
| 3 | ProjectCoordinator | Extract project methods | Delegation |
| 4 | DetectorCoordinator | Extract detector methods | Delegation |
| 5 | RecordingCoordinator | Extract recording methods | Delegation |
| 6 | LiveCameraCoordinator | Extract live camera methods | Delegation |
| 7 | ProcessingCoordinator | Extract processing methods | Delegation |
| 8-10 | UI Components | Extract UI components | Delegation |
| 11-14 | Integration | Wire coordinators in DI | Transparent |
| 15-16 | Cleanup | Remove legacy code paths | Breaking (v5.0) |

---

## 12. Developer Guidelines

### 12.1 For External Developers

### If you're building on ZebTrack-AI

1. **Use only public APIs** documented here
2. **Avoid private methods** (`_method_name`)
3. **Subscribe to releases** for deprecation notices
4. **Test against v4.0 betas** (Q1 2025)

### 12.2 For Internal Development

### When modifying existing code

1. **Check this document** before changing signatures
2. **Add deprecation warnings** for changed methods
3. **Update this document** when adding public methods
4. **Maintain tests** for all public interfaces

---

## 13. Version History

| Version | Date | Changes |
| --------- | ------ | --------- |
| 3.0 | 2025-01 | Baseline documentation (pre-refactoring) |

---

## Appendix A: Method Count by Category

### MainViewModel (154 methods)

- Project Management: 12 methods
- Detector Management: 8 methods
- Recording Management: 15 methods
- Live Camera: 10 methods
- Video Processing: 18 methods
- Analysis: 14 methods
- State Management: 22 methods
- Event Handling: 25 methods
- Utility/Internal: 30 methods

### ApplicationGUI (232 methods)

- Window Management: 8 methods
- Menu Management: 25 methods
- Project View: 32 methods
- Control Panel: 28 methods
- Video Display: 35 methods
- Analysis Display: 24 methods
- Dialog Management: 18 methods
- Event Handlers: 42 methods
- Widget Creation: 20 methods

---

### End of API Reference v3.0
