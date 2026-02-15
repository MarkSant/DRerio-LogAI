# Dependency Injection Pattern - Implementation Guide

**Status:** Canonical Reference
**Last Updated:** February 2, 2026
**Category:** Explanation (Diátaxis)

## 1. Overview

ZebTrack-AI uses **constructor injection** throughout the codebase. The Composition Root pattern is implemented in `src/zebtrack/__main__.py`, where all core services and coordinators are instantiated and wired.

## 2. Settings Injection Strategy

All services receive configuration via the `settings_obj` parameter. This prevents the "Global Configuration" anti-pattern and allows for easy testing with mocked settings.

### 2.1. Critical Services (Strict Injection)

Services that **cannot function** without settings raise `RuntimeError`:

**`io/video_source.py`**

```python
def __init__(self, settings_obj: Settings):
    if settings_obj is None:
        raise RuntimeError("VideoSource: Settings not injected.")
    self.settings = settings_obj
```

**Reason**: Video capture requires specific hardware IDs and resolution profiles defined in settings.

### 2.2. Functional Services (Graceful Fallback)

Services that can operate with standard defaults use an optional parameter:

**`plugins/yolo_detector.py`**

```python
def __init__(self, model_path, settings_obj: Settings | None = None):
    self.conf_threshold = settings_obj.yolo.conf if settings_obj else 0.25
```

## 3. The Composition Root

The primary orchestration happens in `src/zebtrack/__main__.py` (roughly lines 100-500).

### 3.1. Infrastructure Phase

1. `load_settings()`
2. `StateManager` initialization.
3. `UIScheduler` (UI thread management) and `EventBusV2`.

### 3.2. Service Phase

1. `WeightManager` and `ModelService`.
2. `ProjectManager` and `AnalysisService`.
3. `DetectorService`.

### 3.3. Coordination Phase

1. **Super Coordinators**:
   - `ProcessingCoordinator`
   - `HardwareCoordinator`
   - `SessionCoordinator`
   - `ProjectLifecycleCoordinator`
2. **UICoordinator** (Mediator for UI component sync).
3. **MainViewModel** (Facade for the GUI).

## 4. UI Component Injection

UI widgets receive their dependencies (Command Handlers, Event Buses) from their parent `ViewManager` or directly from the `MainViewModel` during the "Wiring" phase.

```python
# In main_view_model.py
self.project_vm = ProjectViewModel(dependencies, bootstrap_result, self.ui_event_bus)
```

---

**Best Practice**: Never import `from zebtrack import settings`. If a class needs a configuration value, it must be passed in via the constructor.

```python
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
detector=None, # Lazy-initialized
recorder=recorder,
project_manager=project_manager,
state_manager=state_manager,
ui_coordinator=ui_coordinator,
ui_event_bus=event_bus,
root=root,
view=None, # Set later
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

# Live Camera Batch Coordinator (v2.3.0)

live_batch_coordinator = LiveBatchCoordinator(
project_manager=project_manager,
analysis_service=analysis_service,
state_manager=state_manager,
settings_obj=settings_obj,
event_bus=event_bus if settings_obj.ui_features.enable_event_queue else None,
)

session_coordinator = SessionCoordinator(
project_manager=project_manager,
state_manager=state_manager,
ui_event_bus=event_bus,
settings_obj=settings_obj,
live_batch_coordinator=live_batch_coordinator, # v2.3.0 integration
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
recording_service=None, # Created by MainViewModel
hardware_coordinator=hardware_coordinator, # Phase 2
analysis_coordinator=analysis_coordinator, # Phase 2
video_orchestrator=video_orchestrator, # Phase 2
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

### LiveBatchCoordinator (v2.3.0)

**Location**: `coordinators/live_batch_coordinator.py`

```python
class LiveBatchCoordinator:
    """Coordinates unified batch reporting across live camera sessions."""

    def __init__(
        self,
        project_manager: ProjectManager,
        analysis_service: AnalysisService,
        state_manager: StateManager,
        settings_obj: Settings,
        event_bus: EventBus | None = None,
    ):
        """Initialize with all dependencies via constructor."""
        self.project_manager = project_manager
        self.analysis_service = analysis_service
        self.state_manager = state_manager
        self.settings = settings_obj
        self.event_bus = event_bus

        # Batch tracking state
        self._batches: dict[str, BatchInfo] = {}
        self.logger = get_logger()
```

**Key Integration Points**:

1. **Wizard Metadata Collection** (`ui/wizard/live_config_step.py`):

   ```python
   def get_data(self):
       return {
           "experimental_group": self.experimental_group_var.get() or None,
           "experiment_day": self.experiment_day_var.get() or None,
           "subject_id": self.subject_id_var.get() or None,
           "is_batch_last_session": self.is_batch_last_session_var.get(),
       }
   ```

2. **SessionCoordinator Registration** (`coordinators/session_coordinator.py`):

   ```python
   def _register_batch_session(self):
       """Register completed session with LiveBatchCoordinator (v2.3.0)."""
       if not self.live_batch_coordinator or not self._active_wizard_data:
           return

       # Extract batch metadata
       group = self._active_wizard_data.get("experimental_group")
       day = self._active_wizard_data.get("experiment_day")
       subject_id = self._active_wizard_data.get("subject_id")

       # Transform to batch metadata
       metadata = {
           "group": group,  # Wizard field → Batch field
           "day": day,
           "subject_id": subject_id,
           "timestamp": datetime.datetime.now().isoformat(),
       }

       batch_id = self.live_batch_coordinator.register_session(
           experiment_id=self._active_live_session_id or "unknown",
           video_path=video_path,
           metadata=metadata,
       )
   ```

3. **Batch Key Creation** (groups sessions by Group x Day x Subject):

   ```python
   def _create_batch_key(self, group: str | None, day: str | None, subject_id: str | None) -> str:
       """Create unique batch key from metadata."""
       parts = [
           group or "no_group",
           day or "no_day",
           subject_id or "no_subject",
       ]
       return "_".join(parts)
       # Example: "Controle_Dia_1_Peixe_01"
   ```

4. **Batch ID Uniqueness** (prevents collisions):

    ```python
    # Include microseconds for uniqueness when multiple batches created in same second
    batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    # Example: "batch_20260103_143025_123456"
    ```

5. **Event Publishing** (after unified report generation):

   ```python
   if self.event_bus:
       self.event_bus.publish_event(
           "BATCH_ANALYSIS_COMPLETED",
           {
               "batch_id": batch_id,
               "session_count": batch.session_count,
               "report_path": str(unified_excel),
               "group": batch.group,
               "day": batch.day,
               "subject_id": batch.subject_id,
           },
       )
   ```

6. **UICoordinator Event Handler** (`ui/ui_coordinator.py`):

   ```python
   self.event_bus.subscribe(UIEvents.BATCH_ANALYSIS_COMPLETED, self._on_batch_analysis_completed)

   def _on_batch_analysis_completed(self, event_data: dict[str, Any]) -> None:
       """Handle batch analysis completed event (v2.3.0)."""
       batch_id = event_data.get("batch_id", "unknown")
       report_path = event_data.get("report_path")
       session_count = event_data.get("session_count", 0)

       # Show success notification
       messagebox.showinfo(
           title="Análise de Lote Completa",
           message=f"✅ Relatório de Lote Gerado!\n\nLote: {batch_id}\nSessões: {session_count}"
       )

       # Open file explorer to report location
       os.startfile(os.path.dirname(report_path))
   ```

**Multi-Aquarium Support**:

- Each aquarium treated as separate subject_id: `Peixe_01_Aquario_0`, `Peixe_01_Aquario_1`
- Separate batches per aquarium (independent reporting)
- Batch keys: `Controle_Dia_1_Peixe_01_Aquario_0`, `Controle_Dia_1_Peixe_01_Aquario_1`

**Key Points**:

- All dependencies via constructor (no singleton imports)
- Settings injected for analysis parameters
- Event bus optional (graceful degradation if disabled)
- Batch key format ensures session grouping by experimental design
- Microsecond-precision batch IDs prevent collisions

### SessionCoordinator (v2.3.0)

**Location**: `coordinators/session_coordinator.py`

```python
class SessionCoordinator:
    """Coordinates live camera session lifecycle and batch integration."""

    def __init__(
        self,
        project_manager: ProjectManager,
        state_manager: StateManager,
        ui_event_bus: EventBus,
        settings_obj: Settings,
        live_batch_coordinator: "LiveBatchCoordinator | None" = None,  # v2.3.0
    ):
        """Initialize with all dependencies."""
        self.project_manager = project_manager
        self.state_manager = state_manager
        self.ui_event_bus = ui_event_bus
        self.settings = settings_obj
        self.live_batch_coordinator = live_batch_coordinator  # v2.3.0 integration
```

**Key Points**:

- Receives `live_batch_coordinator` as optional dependency
- Calls `_register_batch_session()` after live camera stops
- Transforms wizard field names to batch metadata keys
- Enables unified reporting across live camera sessions

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
        ui_coordinator: UIScheduler,
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
✅ **v2.3.0**: LiveBatchCoordinator activated with wizard integration and unified batch reporting
✅ **Singleton Removed**: No global `settings` object exists
✅ **MainViewModel Status**: Currently ~5442 lines; coordinators/adapters extract complex orchestration responsibilities to dedicated components

## References

- Composition Root: `src/zebtrack/__main__.py:140-404` (includes LiveBatchCoordinator and SessionCoordinator instantiation)
- Settings Model: `src/zebtrack/settings.py`
- Test Migration Guide: `TEST_MIGRATION_TODO.md`
- LiveBatchCoordinator Implementation: `docs/decisions/ADR-006-live-batch-coordinator-future.md` (Status: ✅ Implemented)
