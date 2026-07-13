# Event-Driven Workflows in DRerio LogAI (v4.1)

This document explains the Event-Driven Architecture (EDA) and Model-View-ViewModel (MVVM) workflows in DRerio LogAI. The system utilizes a dual-bus communication pattern and a coordination layer (Mediators) to ensure high decoupling and testability.

## 1. Core Architectural Layers

### 1.1. View Layer (Tkinter)

The UI is composed of self-contained components (e.g., `CanvasManager`, `ZoneControlsWidget`).

- **Input:** Publishes events to `EventBus` or `EventBusV2`.
- **Output:** Subscribes to UI-level events for visual updates.
- **Rule:** Views must never call business logic services directly.

### 1.2. Coordination Layer (Mediators)

Specialized "Super Coordinators" act as mediators between the UI and backend logic:

- **`ProcessingCoordinator`**: Manages video analysis, loops, and results generation.
- **`HardwareCoordinator`**: Handles model weighting, OpenVINO, and camera diagnostics.
- **`SessionCoordinator`**: Manages active recording sessions and hardware triggers.
- **`ProjectLifecycleCoordinator`**: Coordinates project creation, opening, and calibrations.
- **`UICoordinator`**: Coordinates UI-only changes across disparate view managers.

### 1.3. Service Layer

The foundation where data is actually manipulated:

- **`DetectorService`**: Manages YOLO/OpenVINO plugins.
- **`ProjectManager`**: Handles project-level persistence.
- **`StateManager`**: Thread-safe source of truth for app state.

---

## 2. Event Systems

### 2.1. EventBus (Domain Events)

Uses string constants (found in `zebtrack.ui.events.Events`) for heavyweight domain operations.

- **Example:** `Events.VIDEO_ANALYZE_SINGLE` trigger's the analysis workflow.
- **Payloads:** Objects or dicts containing essential context (e.g., `video_path`, `config`).

### 2.2. EventBusV2 (UI Events)

Uses Enum constants (`UIEvents`) for lightweight UI synchronization.

- **Example:** `UIEvents.ZONES_UPDATED` tells the canvas to redraw polygons.
- **Scope:** Primarily used within the UI layer and its immediate coordinators.

---

## 3. Workflow: Video Analysis Initialization

This workflow illustrates how a user request traverses the layers:

1. **User Action:** User clicks "Analyze" in `ProjectView`.
2. **View Action:** `ProjectView` publishes `Events.VIDEO_ANALYZE_SINGLE`.
3. **Dispatch:** `MainViewModel` (Root) receives the event and identifies the handler.
4. **Coordination:** `ProcessingCoordinator` receives the metadata and:
   - Sets the state to `BUSY`.
   - Prepares the `ProcessingWorker`.
   - Spawns the worker thread.
5. **Logic:** `DetectorService` loads the necessary model weights.
6. **Iteration:** The worker sends frames back via `UI_DISPLAY_FRAME` for live preview.
7. **Completion:** Upon finish, `ProcessingCoordinator` triggers result generation.

## 4. Best Practices for Developers

1. **Never use singletons:** Always inject `settings_obj` and services via constructors.
2. **Handle UI on main thread:** Always use `root.after(0, callback)` when updating widgets from a coordinator or service.
3. **Immutable State:** Update the `StateManager` instead of modifying instance variables directly to ensure UI reactivity.
4. **Event Payloads:** Keep payloads serializable and minimal. Use IDs instead of full object instances when possible.

---

**Status:** Stable API (v4.1)
**Category:** Guide (Diátaxis)
**Last Updated:** February 2, 2026

        # 2. Coordinate with services
        output_dir = self.project_service.create_output_directory()

        # 3. Update state
        self.state_manager.set("recording.is_recording", True)
        self.state_manager.set("recording.output_dir", output_dir)

        # 4. Start background worker
        self.recorder.start(output_dir)

### 5. The State Manager (`StateManager`)

**Source of truth** for application state, implementing the **Observable pattern**.

**Responsibilities**:

- Store all application state in 5 categories: `project`, `detector`, `recording`, `processing`, `ui`
- Provide thread-safe read/write access via `RLock`
- Notify observers (UI components) of state changes
- Log all state transitions for debugging

**Integration with ViewModel**:

- ViewModel writes to StateManager (e.g., `state_manager.set("processing.status", "running")`)
- ApplicationGUI observes StateManager and updates UI reactively

**File**: `src/zebtrack/core/state_manager.py`
**Documentation**: [`docs/explanation/state_management.md`](../../explanation/state_management.md)

## General Workflow Pattern

The standard flow for any user-initiated action is as follows:

1. **User Interaction:** The user interacts with a widget in the `ApplicationGUI` (e.g., clicks the "Create Project" button).
2. **Event Publication:** The `ApplicationGUI` collects data from the relevant input fields, creates a payload dictionary, and publishes a specific event (e.g., `Events.PROJECT_CREATE`) to the `EventBus`.
3. **Event Subscription:** The `MainViewModel`, which has already subscribed its handler methods during initialization (via `bind_events()`), receives the notification for that event.
4. **Workflow Orchestration:** The corresponding handler method in the `MainViewModel` (e.g., `create_project_workflow`) is executed. This method orchestrates the necessary actions by calling various services.
5. **UI Update:** The `MainViewModel` updates the UI indirectly by changing the central state or by publishing events that the UI is subscribed to.

---

## Detailed Workflows

Below are descriptions of the main workflows that have been refactored to follow this event-driven pattern.

### 1. Project Creation

- **Trigger:** User fills out the new project wizard and clicks the final "Create" button.
- **Event:** `Events.PROJECT_CREATE`
- **Payload:** A dictionary containing all project configuration details, such as `project_name`, `animal_method`, etc.
- **Handler:** `MainViewModel.create_project_workflow`
- **Orchestration:**
    1. The handler receives the project data from the event payload.
    2. It calls the `ProjectWorkflowService` to perform the business logic of creating the project directory and configuration file.
    3. It then calls `setup_detector()` to initialize the detector with the correct settings for the new project.
    4. Finally, it publishes events to the `UICoordinator` to switch the main window's view from the welcome screen to the main project interface.

### 2. Opening an Existing Project

- **Trigger:** User selects a project file (`.ztp`) via the "Open Project" file dialog.
- **Event:** `Events.PROJECT_OPEN`
- **Payload:** `{"project_path": "/path/to/your/project.ztp"}`
- **Handler:** `MainViewModel.open_project_workflow`
- **Orchestration:**
    1. Receives the project path.
    2. Delegates to `ProjectWorkflowService` to load the project data, validate its contents, and restore detector and model settings from the project configuration.
    3. Calls `setup_detector_zones()` to configure the detection zones based on the loaded project.
    4. Publishes events to update the UI with the loaded project's information and switches to the main project view.

### 3. Single Video Processing

- **Trigger:** After defining zones for a single video, the user clicks the "Start Processing" button.
- **Event:** `Events.VIDEO_START_SINGLE_PROCESSING`
- **Payload:** `{"video_path": "...", "config": {...}, "zone_data": <ZoneData>}`
- **Handler:** `MainViewModel.start_single_video_processing`
- **Orchestration:**
    1. Receives the video path, configuration, and defined zone data.
    2. Updates the `Detector` instance with the provided `zone_data`.
    3. Initializes and starts a `ProcessingWorker` in a separate background thread to handle the computationally intensive video analysis.
    4. The worker uses a callback system to report progress, which the `MainViewModel` then uses to update the UI's progress bar and status messages.
    5. Switches the UI to the analysis view.

### 4. Model & Weight Management

- **Trigger:** User interacts with buttons like "Load New Weight" or "Manage Weights".
- **Events:** `Events.MODEL_LOAD_NEW_WEIGHT`, `Events.MODEL_MANAGE_WEIGHTS`
- **Payload:** Typically empty (`{}`).
- **Handlers:** `MainViewModel.load_new_weight` and `MainViewModel.manage_weights`
- **Orchestration:** These handlers are simpler, primarily responsible for opening the appropriate UI dialogs (`ask_open_filenames` or `ManageWeightsDialog`) which then handle the interaction with the `WeightManager` service.

### 5. Automatic Aquarium Detection

- **Trigger:** User clicks the "Auto-Detect Aquarium" button in the zone definition tab.
- **Event:** `Events.ZONE_AUTO_DETECT`
- **Payload:** `{"video_path": "...", "stabilization_frames": 10}`
- **Handler:** `MainViewModel.run_aquarium_detection`
- **Orchestration:**
    1. The handler instantiates an `AquariumDetector`.
    2. It runs the detection model on the specified video.
    3. If a polygon is successfully detected, it publishes a `UI_SETUP_INTERACTIVE_POLYGON` event, which the `ApplicationGUI` listens for to draw the suggested polygon on the screen for the user to confirm or edit.

---

## Event Registry (Fase 3.2 - Consolidação)

Esta seção documenta todos os eventos suportados após a consolidação do EventBus, agrupados por domínio.

### Recording Events

| Event Name | Payload | Handler | Description |
| --- | --- | --- | --- |
| `recording.start_requested` | `{}` | `MainViewModel.start_recording_workflow` | Usuário solicita início de gravação |
| `recording.stop_requested` | `{}` | `MainViewModel.stop_recording_workflow` | Usuário solicita parada de gravação |
| `recording.pause_requested` | `{}` | `MainViewModel.pause_recording` | Usuário solicita pausa |
| `recording.resume_requested` | `{}` | `MainViewModel.resume_recording` | Usuário solicita retomada |

### Zone Events

| Event Name | Payload | Handler | Description |
| --- | --- | --- | --- |
| `zone.draw_roi` | `{"mode": "arena" \| "roi"}` | `MainViewModel.start_zone_drawing` | Usuário inicia desenho de arena/ROI |
| `zone.save` | `{"polygon": list, "roi_data": dict}` | `MainViewModel.save_zone_data` | Salva zona definida |
| `zone.auto_detect` | `{"video_path": str}` | `MainViewModel.run_aquarium_detection` | Detecção automática de arena |
| `zone.clear_all` | `{}` | `MainViewModel.clear_all_zones` | Limpa todas as zonas |
| `zone.load_template` | `{"template_name": str}` | `MainViewModel.load_zone_template` | Carrega template salvo |

### Project Events

| Event Name | Payload | Handler | Description |
| --- | --- | --- | --- |
| `project.create` | `{project_name, type, calibration, ...}` | `MainViewModel.create_project_workflow` | Wizard criou novo projeto |
| `project.open` | `{"project_path": str}` | `MainViewModel.open_project_workflow` | Usuário abriu projeto existente |
| `project.save` | `{}` | `MainViewModel.save_project` | Salva estado atual do projeto |
| `project.close` | `{}` | `MainViewModel.close_project` | Fecha projeto ativo |

### Processing Events

| Event Name | Payload | Handler | Description |
| --- | --- | --- | --- |
| `processing.start_single` | `{video_path, config, zone_data}` | `MainViewModel.start_single_video_processing` | Processa vídeo único |
| `processing.start_batch` | `{videos: list, config}` | `MainViewModel.start_batch_processing` | Processa lote de vídeos |
| `processing.cancel` | `{}` | `MainViewModel.cancel_processing` | Cancela processamento |
| `processing.retry_failed` | `{failed_videos: list}` | `MainViewModel.retry_failed_videos` | Reprocessa vídeos que falharam |

### Detector Events

| Event Name | Payload | Handler | Description |
| --- | --- | --- | --- |
| `detector.configure` | `{plugin, confidence, nms}` | `MainViewModel.configure_detector` | Atualiza configuração do detector |
| `detector.load_weight` | `{weight_path: str}` | `MainViewModel.load_detector_weight` | Carrega novo peso YOLO |
| `detector.toggle_openvino` | `{enabled: bool}` | `MainViewModel.toggle_openvino` | Ativa/desativa OpenVINO |

### UI Events

| Event Name | Payload | Handler | Description |
| --- | --- | --- | --- |
| `ui.view_change` | `{view: str}` | `MainViewModel.switch_view` | Troca de tela (welcome/project/analysis) |
| `ui.overlay_toggle` | `{enabled: bool}` | `MainViewModel.toggle_overlay` | Ativa/desativa overlay de detecções |
| `ui.zoom_change` | `{level: float}` | `MainViewModel.update_zoom` | Ajusta zoom do vídeo |

---

## Updated Workflow Diagrams

### Consolidated Event Flow (Post-Fase 3.1 & 3.2)

<!-- markdownlint-disable-next-line MD046 --><!-- justification: mermaid requires fenced code blocks -->
```mermaid
sequenceDiagram
    participant User
    participant Component as UI Component
    participant EB as EventBus (Single Instance)
    participant VM as MainViewModel
    participant SM as StateManager
    participant Service as Service Layer
    participant App as ApplicationGUI

    User->>Component: Clicks "Start Recording"
    Component->>EB: publish("recording.start_requested", {})
    EB->>VM: Call subscribed handler
    VM->>VM: start_recording_workflow(payload)

    Note over VM: Validation & Business Logic
    VM->>Service: create_output_directory()
    Service-->>VM: output_dir_path

    VM->>SM: set("recording.is_recording", True)
    VM->>SM: set("recording.output_dir", output_dir_path)

    SM-->>App: Notify observer: on_recording_state_changed
    App->>App: root.after(0, update_ui)
    App->>Component: Update button state ("Stop Recording")
    Component-->>User: UI reflects new state
```

### Error Handling in Workflows

<!-- markdownlint-disable-next-line MD046 --><!-- justification: mermaid requires fenced code blocks -->
```mermaid
flowchart TD
    Event[Event Published] --> Handler[ViewModel Handler]
    Handler --> Validate{Validate<br/>Preconditions}

    Validate -->|Invalid| ErrorState["set('ui.error_message', msg)"]
    Validate -->|Valid| CallService[Call Service Layer]

    ErrorState --> NotifyUI[StateManager notifies UI]

    CallService --> ServiceResult{Service<br/>Success?}
    ServiceResult -->|Success| UpdateState["set('processing.status', 'running')"]
    ServiceResult -->|Error| LogError["log.error('service.operation.failed')"]

    LogError --> ErrorState
    UpdateState --> NotifyUI

    NotifyUI --> UIUpdate[UI updates via root.after]

    style ErrorState fill:#FF6B6B
    style UpdateState fill:#90EE90
```

---

## Migration Notes (Fase 3.1 & 3.2)

### Changes from Previous Architecture

**Before (Pre-Fase 3)**:

- UI callbacks directly called `MainViewModel` methods
- Multiple EventBus instances or no EventBus at all
- Business logic mixed with UI update code
- Difficult to trace event flow

**After (Post-Fase 3.2)**:

- Single EventBus instance in `ApplicationGUI`
- UI components only emit events, never call ViewModel directly
- Business logic centralized in ViewModel handlers
- Clear separation: View → EventBus → ViewModel → Services → StateManager → View

### Benefits Realized

1. **Testability**: Mock EventBus to test ViewModel in isolation
2. **Decoupling**: Components don't depend on ViewModel structure
3. **Maintainability**: Event names are self-documenting contracts
4. **Extensibility**: Add new handlers without modifying UI code
5. **Debugging**: Single event flow path to trace and log

### Testing Example

    def test_start_recording_workflow(mock_event_bus, mock_state_manager):
        # Given
        view_model = MainViewModel(event_bus=mock_event_bus, state_manager=mock_state_manager)
        view_model.bind_events()

        # When
        mock_event_bus.publish("recording.start_requested", {})

        # Then
        mock_state_manager.set.assert_called_with("recording.is_recording", True)

---

## Related Documentation

- **[Architecture overview](../../explanation/architecture.md)**: Full system architecture and MVVM pattern
- **[Error handling](ERROR_HANDLING.md)**: Error handling strategies and callbacks
- **[State management](../../explanation/state_management.md)**: StateManager API and observer pattern
- **[Operational reference](../../reference/operational_reference.md)**: API reference and runtime behavior
