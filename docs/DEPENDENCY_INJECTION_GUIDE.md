# Dependency Injection Pattern - Implementation Guide

## Overview

ZebTrack-AI uses **constructor injection** throughout the codebase. The Composition Root pattern is implemented in `src/zebtrack/__main__.py`, where all dependencies are created and wired together.

## Settings Injection Strategy

All services receive settings via the `settings_obj` parameter in their constructors.

### Critical Services (RuntimeError on None)

Services that **cannot function** without settings raise `RuntimeError`:

**`io/camera.py`**
```python
def __init__(self, settings_obj: "Settings | None" = None):
    if settings_obj is None:
        raise RuntimeError("Camera: Settings not injected.")
    self.settings = settings_obj
    self._camera_index = self.settings.camera.index  # Required
```

**Reason**: Camera requires specific hardware configuration (index, resolution) and cannot operate with defaults.

**`analysis/analysis_service.py`**
```python
def run_full_analysis(...):
    if self.settings is None:
        raise RuntimeError("AnalysisService: Settings not injected.")
```

**Reason**: Analysis algorithms require precise thresholds (freezing velocity, smoothing windows) for scientific accuracy.

### Optional Services (Graceful Fallback)

Services that **can function** with reasonable defaults use graceful fallback:

**`plugins/openvino_detector.py`** and **`plugins/ultralytics_detector.py`**
```python
def __init__(self, model_path, settings_obj: Any | None = None):
    if settings_obj is not None:
        self.conf_threshold = settings_obj.yolo_model.confidence_threshold
        self.nms_threshold = settings_obj.yolo_model.nms_threshold
    else:
        # Fallback defaults
        self.conf_threshold = 0.25
        self.nms_threshold = 0.45
```

**Reason**: Detection plugins can operate with industry-standard defaults (0.25 confidence, 0.45 NMS).

### UI Components (Graceful Fallback)

UI widgets that display settings-based defaults use fallback to maintain usability:

**`ui/wizard/model_selection_step.py`**
```python
if self.settings and hasattr(self.settings, "yolo_model"):
    default_confidence = self.settings.yolo_model.confidence_threshold
else:
    default_confidence = 0.25  # Hardcoded fallback
```

**Reason**: UI should remain functional even if settings fail to load, using safe defaults.

## Design Principle

**Rule**: Use `RuntimeError` when the service's **core function** depends on settings. Use **graceful fallback** when reasonable defaults exist.

## Lazy Initialization

Some services accept `None` initially and are populated later:

**`core/video_processing_service.py`**
```python
def __init__(self, detector: Detector | None, ...):
    self.detector = detector  # Can be None initially
```

**Reason**: The detector is created lazily via `detector_service.initialize_detector()` when a project is loaded, as different projects may use different detection methods (seg/det) and backends (YOLO/OpenVINO).

## Composition Root

**Primary dependency creation happens in `__main__.py` (lines 197-362):**

```python
# Load settings once
settings_obj = load_settings()

# Core infrastructure
event_bus = EventBus()
state_manager = StateManager(enable_history=True, max_history_size=100)
ui_coordinator = UICoordinator(root=root, event_bus=event_bus)

# Model and weight management
weight_manager = WeightManager(settings_obj=settings_obj)
model_service = ModelService(weight_manager)

# Project management
project_manager = ProjectManager(state_manager=state_manager, settings_obj=settings_obj)
project_workflow_service = ProjectWorkflowService(
    project_manager=project_manager,
    model_service=model_service,
    state_manager=state_manager,
    ui_coordinator=ui_coordinator,
    settings_obj=settings_obj,
)

# Detector service
detector_service = DetectorService(
    state_manager=state_manager,
    project_manager=project_manager,
    weight_manager=weight_manager,
    model_service=model_service,
    settings_obj=settings_obj,
)

# Video processing and analysis services
recorder = Recorder(settings_obj=settings_obj)
video_processing_service = VideoProcessingService(
    detector=None,  # Lazy-initialized
    recorder=recorder,
    project_manager=project_manager,
    state_manager=state_manager,
    ui_coordinator=ui_coordinator,
    ui_event_bus=event_bus,
    root=root,
    view=None,  # Set later
    cancel_event=cancel_event,
    settings_obj=settings_obj,
)
analysis_service = AnalysisService(settings_obj=settings_obj)

# ===== COORDINATORS (Phase 2 Refactoring) =====
hardware_coordinator = HardwareCoordinator(
    state_manager=state_manager,
    ui_event_bus=event_bus,
    settings_obj=settings_obj,
    project_manager=project_manager,
    detector_service=detector_service,
)

analysis_coordinator = AnalysisCoordinator(
    root=root,
    ui_event_bus=event_bus,
    ui_coordinator=ui_coordinator,
    settings_obj=settings_obj,
    project_manager=project_manager,
    analysis_service=analysis_service,
    video_processing_service=video_processing_service,
)

video_orchestrator = VideoOrchestrator(
    root=root,
    state_manager=state_manager,
    ui_event_bus=event_bus,
    ui_coordinator=ui_coordinator,
    settings_obj=settings_obj,
    project_manager=project_manager,
    video_processing_service=video_processing_service,
    analysis_service=analysis_service,
    recorder=recorder,
)

# Wire all dependencies into MainViewModel
controller = MainViewModel(
    root=root,
    event_bus=event_bus,
    state_manager=state_manager,
    ui_coordinator=ui_coordinator,
    settings_obj=settings_obj,
    project_manager=project_manager,
    project_workflow_service=project_workflow_service,
    weight_manager=weight_manager,
    model_service=model_service,
    detector_service=detector_service,
    video_processing_service=video_processing_service,
    analysis_service=analysis_service,
    recording_service=None,  # Created by MainViewModel
    hardware_coordinator=hardware_coordinator,  # Phase 2
    analysis_coordinator=analysis_coordinator,  # Phase 2
    video_orchestrator=video_orchestrator,  # Phase 2
)
```

**Note**: `ProjectWorkflowAdapter` is created inside `MainViewModel.__init__()` (line 457) rather than in `__main__.py`, as it has tight coupling with ViewModel-level callbacks:

```python
# Inside MainViewModel.__init__()
self.project_workflow_adapter = ProjectWorkflowAdapter(
    project_workflow_service=self.project_workflow_service,
    project_manager=self.project_manager,
    detector_service=self.detector_service,
    state_manager=self.state_manager,
    ui_event_bus=self.ui_event_bus,
)
```

This is acceptable because:
1. The adapter requires ViewModel-level callbacks (`setup_detector_callback`, etc.)
2. All injected services come from MainViewModel's own dependencies
3. No new service creation - pure orchestration layer

## Testing

Tests must inject settings or handle RuntimeError:

```python
@pytest.fixture
def test_settings():
    from zebtrack.settings import load_settings
    return load_settings()

def test_camera_requires_settings(test_settings):
    camera = Camera(settings_obj=test_settings)  # OK

def test_camera_fails_without_settings():
    with pytest.raises(RuntimeError, match="Settings not injected"):
        Camera(settings_obj=None)
```

## New Service Examples (Post-Phase 2 Refactoring)

### ProjectWorkflowAdapter

**Location**: `ui/project_workflow_adapter.py`

```python
class ProjectWorkflowAdapter:
    """Adapter for project workflow orchestration with UI coordination."""

    def __init__(
        self,
        project_workflow_service: ProjectWorkflowService,
        project_manager: ProjectManager,
        detector_service: DetectorService,
        state_manager: StateManager,
        ui_event_bus: EventBus,
    ):
        """All dependencies injected via constructor."""
        self.project_workflow_service = project_workflow_service
        self.project_manager = project_manager
        self.detector_service = detector_service
        self.state_manager = state_manager
        self.ui_event_bus = ui_event_bus
```

**Key Points**:
- No `settings_obj` parameter (relies on services that already have settings)
- All service dependencies injected
- Pure orchestration layer - delegates business logic to `ProjectWorkflowService`

### AnalysisCoordinator

**Location**: `core/analysis_coordinator.py`

```python
class AnalysisCoordinator:
    """Coordinates analysis and reporting workflows."""

    def __init__(
        self,
        root,
        ui_event_bus: EventBus,
        ui_coordinator: UICoordinator,
        settings_obj: Settings,
        project_manager: ProjectManager,
        analysis_service: AnalysisService,
        video_processing_service: VideoProcessingService,
        view: ApplicationGUI | None = None,
    ):
        """Initialize with settings and service dependencies."""
        self.root = root
        self.view = view
        self.ui_event_bus = ui_event_bus
        self.ui_coordinator = ui_coordinator
        self.settings = settings_obj  # Required for analysis parameters
        self.project_manager = project_manager
        self.analysis_service = analysis_service
        self.video_processing_service = video_processing_service
```

**Key Points**:
- Requires `settings_obj` for analysis parameters (freezing threshold, smoothing windows)
- View can be set later via `set_view()` for delayed initialization
- Uses `ThreadPoolExecutor` for background analysis tasks

### DialogManager

**Location**: `ui/components/dialog_manager.py`

```python
class DialogManager:
    """Manages dialogs and user interactions for ApplicationGUI."""

    def __init__(self, gui):
        """Initialize DialogManager.

        Args:
            gui: Reference to ApplicationGUI instance
        """
        self.gui = gui
```

**Key Points**:
- Minimal dependencies (only GUI reference)
- No `settings_obj` needed (dialogs are purely UI-driven)
- Extracted from ApplicationGUI to reduce God Object (~811 lines)

## Migration Status

✅ **Phase 1**: Core services (WeightManager, DetectorService, ProjectManager)
✅ **Phase 2**: Analysis & IO layers (AnalysisService, Camera, Recorder, Plugins)
✅ **Phase 3**: UI layer (ApplicationGUI, WizardDialog, all dialogs)
✅ **Phase 2+ Refactoring**: Coordinators/Adapters (ProjectWorkflowAdapter, AnalysisCoordinator, DialogManager)
✅ **Singleton Removed**: No global `settings` object exists
✅ **MainViewModel Reduction**: ~5383 → ~3400 lines (-37%) via coordinator extraction

## References

- Composition Root: `src/zebtrack/__main__.py:140-280`
- Settings Model: `src/zebtrack/settings.py`
- Test Migration Guide: `TEST_MIGRATION_TODO.md`
