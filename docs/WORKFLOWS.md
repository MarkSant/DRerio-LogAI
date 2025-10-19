# Event-Driven Workflows in ZebTrack-AI

This document outlines the event-driven architecture adopted in ZebTrack-AI, aligning with the Model-View-ViewModel (MVVM) pattern. This design decouples the user interface (View) from the business logic and orchestration (ViewModel), leading to a more maintainable, testable, and scalable application.

## Core Architectural Components

1.  **The View (`ApplicationGUI`):**
    *   The user interface, built with Tkinter.
    *   Its primary responsibilities are to display data to the user and capture user interactions (e.g., button clicks, form submissions).
    *   It **does not** contain any business logic or orchestration.
    *   When a user performs an action, the View's role is to gather the necessary data from UI elements and publish an event to the `EventBus`.

2.  **The Event Bus (`EventBus`):**
    *   A central messaging system that allows components to communicate without having direct references to each other.
    *   It follows a publish-subscribe pattern. Components can publish events, and other components can subscribe to listen for specific events.

3.  **The Events (`Events` Enum):**
    *   A centralized enumeration that defines all possible events that can be sent through the `EventBus`. This provides a clear, self-documenting contract for communication between the View and ViewModel.

4.  **The ViewModel (`MainViewModel`):**
    *   The orchestrator of the application. It contains all the business logic, state management, and workflow coordination.
    *   It subscribes to events published by the View.
    *   When it receives an event, the corresponding handler method is invoked, which then coordinates with various services (`ProjectWorkflowService`, `DetectorService`, etc.) to execute the required tasks.
    *   It updates the application's state via the `StateManager` and uses the `UICoordinator` to schedule updates back on the UI thread.

## General Workflow Pattern

The standard flow for any user-initiated action is as follows:

1.  **User Interaction:** The user interacts with a widget in the `ApplicationGUI` (e.g., clicks the "Create Project" button).
2.  **Event Publication:** The `ApplicationGUI` collects data from the relevant input fields, creates a payload dictionary, and publishes a specific event (e.g., `Events.PROJECT_CREATE`) to the `EventBus`.
3.  **Event Subscription:** The `MainViewModel`, which has already subscribed its handler methods during initialization (via `bind_events()`), receives the notification for that event.
4.  **Workflow Orchestration:** The corresponding handler method in the `MainViewModel` (e.g., `create_project_workflow`) is executed. This method orchestrates the necessary actions by calling various services.
5.  **UI Update:** The `MainViewModel` updates the UI indirectly by changing the central state or by publishing events that the UI is subscribed to.

---

## Detailed Workflows

Below are descriptions of the main workflows that have been refactored to follow this event-driven pattern.

### 1. Project Creation

*   **Trigger:** User fills out the new project wizard and clicks the final "Create" button.
*   **Event:** `Events.PROJECT_CREATE`
*   **Payload:** A dictionary containing all project configuration details, such as `project_name`, `animal_method`, etc.
*   **Handler:** `MainViewModel.create_project_workflow`
*   **Orchestration:**
    1.  The handler receives the project data from the event payload.
    2.  It calls the `ProjectWorkflowService` to perform the business logic of creating the project directory and configuration file.
    3.  It then calls `setup_detector()` to initialize the detector with the correct settings for the new project.
    4.  Finally, it publishes events to the `UICoordinator` to switch the main window's view from the welcome screen to the main project interface.

### 2. Opening an Existing Project

*   **Trigger:** User selects a project file (`.ztp`) via the "Open Project" file dialog.
*   **Event:** `Events.PROJECT_OPEN`
*   **Payload:** `{"project_path": "/path/to/your/project.ztp"}`
*   **Handler:** `MainViewModel.open_project_workflow`
*   **Orchestration:**
    1.  Receives the project path.
    2.  Delegates to `ProjectWorkflowService` to load the project data, validate its contents, and restore detector and model settings from the project configuration.
    3.  Calls `setup_detector_zones()` to configure the detection zones based on the loaded project.
    4.  Publishes events to update the UI with the loaded project's information and switches to the main project view.

### 3. Single Video Processing

*   **Trigger:** After defining zones for a single video, the user clicks the "Start Processing" button.
*   **Event:** `Events.VIDEO_START_SINGLE_PROCESSING`
*   **Payload:** `{"video_path": "...", "config": {...}, "zone_data": <ZoneData>}`
*   **Handler:** `MainViewModel.start_single_video_processing`
*   **Orchestration:**
    1.  Receives the video path, configuration, and defined zone data.
    2.  Updates the `Detector` instance with the provided `zone_data`.
    3.  Initializes and starts a `ProcessingWorker` in a separate background thread to handle the computationally intensive video analysis.
    4.  The worker uses a callback system to report progress, which the `MainViewModel` then uses to update the UI's progress bar and status messages.
    5.  Switches the UI to the analysis view.

### 4. Model & Weight Management

*   **Trigger:** User interacts with buttons like "Load New Weight" or "Manage Weights".
*   **Events:**
    *   `Events.MODEL_LOAD_NEW_WEIGHT`
    *   `Events.MODEL_MANAGE_WEIGHTS`
*   **Payload:** Typically empty (`{}`).
*   **Handlers:** `MainViewModel.load_new_weight` and `MainViewModel.manage_weights`
*   **Orchestration:** These handlers are simpler, primarily responsible for opening the appropriate UI dialogs (`ask_open_filenames` or `ManageWeightsDialog`) which then handle the interaction with the `WeightManager` service.

### 5. Automatic Aquarium Detection

*   **Trigger:** User clicks the "Auto-Detect Aquarium" button in the zone definition tab.
*   **Event:** `Events.ZONE_AUTO_DETECT`
*   **Payload:** `{"video_path": "...", "stabilization_frames": 10}`
*   **Handler:** `MainViewModel.run_aquarium_detection`
*   **Orchestration:**
    1.  The handler instantiates an `AquariumDetector`.
    2.  It runs the detection model on the specified video.
    3.  If a polygon is successfully detected, it publishes a `UI_SETUP_INTERACTIVE_POLYGON` event, which the `ApplicationGUI` listens for to draw the suggested polygon on the screen for the user to confirm or edit.
