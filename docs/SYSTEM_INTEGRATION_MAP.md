# ZebTrack-AI System Integration Map

**Status:** Living Document
**Last Updated:** Dec 2025
**Purpose:** This document serves as the "source of truth" for AI Agents regarding system integration, event payloads, and control flows. It defines the strict contracts between the decoupled components of the Phase 3/4 Architecture.

---

## 0. Phase 3 Orchestrator Consolidation Status

### Completed Orchestrator Removals (7 orchestrators deleted, ~2,500+ lines removed):

| Orchestrator | Lines | Status | Replacement |
|-------------|-------|--------|-------------|
| `AnalysisOrchestrator` | ~200 | ❌ DELETED | ProcessingCoordinator |
| `ZoneArenaOrchestrator` | ~150 | ❌ DELETED | ProjectLifecycleCoordinator |
| `ProcessingConfigOrchestrator` | ~180 | ❌ DELETED | ProcessingCoordinator |
| `CalibrationOrchestrator` | ~220 | ❌ DELETED | ProjectLifecycleCoordinator |
| `ModelDiagnosticsOrchestrator` | ~250 | ❌ DELETED | HardwareCoordinator |
| `ProjectOrchestrator` | ~300 | ❌ DELETED | ProjectLifecycleCoordinator |
| `RecordingSessionOrchestrator` | ~633 | ❌ DELETED | SessionCoordinator |

### Slim Orchestrators (kept for UI orchestration only):

| Orchestrator | Lines | Status | Notes |
|-------------|-------|--------|-------|
| `VideoProcessingOrchestrator` | 140 | ✅ SLIM | Only `start_project_processing_workflow` kept |
| `UIStateController` | 543 | ✅ ACTIVE | 17 production calls, manages weight/zone UI |

### Super Coordinators (Phase 3 replacements):

| Coordinator | Responsibilities |
|-------------|-----------------|
| `ProcessingCoordinator` | Video processing, analysis coordination, frame queues |
| `HardwareCoordinator` | Detector, camera, model service coordination |
| `SessionCoordinator` | Recording sessions, Arduino integration |
| `ProjectLifecycleCoordinator` | Project CRUD, calibration, zones, model overrides |

---

## 1. Event Bus Registry (The Nervous System)

This section defines the contract for `EventBus` messages. Agents **MUST** adhere to these payload structures when publishing events.

### 1.1. UI Updates (Backend -> UI)

| Event Name | Required Payload Keys | Optional Keys | Listener (Component) | Action/Effect |
| :--- | :--- | :--- | :--- | :--- |
| `Events.UI_DISPLAY_FRAME` | `frame` (np.ndarray) | `detections` (list), `info` (dict), `experiment_id` (str) | `EventDispatcher` -> `CanvasManager` | Updates the raw video canvas with the provided image. **NOTE:** Only used by `ProcessingWorker` (recorded video). Live Camera uses `LivePreviewWindow` directly. |
| `Events.UI_DISPLAY_VIDEO_FRAME` | `video_path` (str) | - | `EventDispatcher` -> `CanvasManager` | Loads a video file from disk and displays the first frame/ROI frame. |
| `Events.UI_UPDATE_DETECTION_OVERLAY` | `detections` (list), `report` (ProcessingReport) | - | `EventDispatcher` -> `ApplicationGUI` | Draws bounding boxes, IDs, and status text over the canvas. |
| `Events.UI_NAVIGATE_TO_ANALYSIS_VIEW` | - | - | `EventDispatcher` -> `ApplicationGUI` | Switches the notebook tab to the "Analysis" tab. |
| `Events.UI_UPDATE_PROCESSING_STATS` | `stats` (dict) | - | `EventDispatcher` -> `StateSynchronizer` | Updates FPS, frame counter, and progress bars. `stats` must contain: `fps`, `frame`, `total_frames`. |
| `Events.UI_SET_STATUS` | `message` (str) | - | `EventDispatcher` -> `ApplicationGUI` | Updates the bottom status bar text. |
| `Events.UI_UPDATE_PROCESSING_MODE` | `report` (ProcessingReport) | - | `EventDispatcher` -> `StateSynchronizer` | Updates UI mode indicators. All publishers use correct format as of v3.1. |

### 1.2. Analysis Control (UI -> Backend)

| Event Name | Required Payload Keys | Optional Keys | Handler (Coordinator/VM) | Action/Effect |
| :--- | :--- | :--- | :--- | :--- |
| `Events.VIDEO_ANALYZE_SINGLE` | `video_path` (str), `config` (dict) | - | `AnalysisControlViewModel` | Triggers the start of the single video analysis workflow. |
| `Events.VIDEO_CANCEL_ANALYSIS` | - | - | `AnalysisControlViewModel` | **Delegates to `ProcessingCoordinator.cancel_processing()`**. Sets flags and stops workers. |
| `Events.ZONE_AUTO_DETECT` | `video_path` (str or None) | `stabilization_frames` (int) | `ProcessingCoordinator` | Runs `AquariumDetector` to find the tank polygon automatically. |

---

## 2. Component Dependencies (The Hierarchy)

Understanding who holds what references prevents "AttributeError" and circular dependency issues.

### 2.1. Dependency Container (`MainViewModelDependencies`)
*   **Root Object:** Passed to `MainViewModel` and `ApplicationBootstrapper`.
*   **Contains:**
    *   `event_bus`: The communication channel.
    *   `cancel_event`: **Shared** `threading.Event` for global cancellation.
    *   `processing_coordinator`: Handles video loops.
    *   `hardware_coordinator`: Handles Detector/Camera.
    *   `session_coordinator`: Handles Recording/Arduino.
    *   `project_lifecycle_coordinator`: Handles Project CRUD.
    *   `ui_coordinator`: Renamed to `UIScheduler` (`zebtrack.core.ui_scheduler`) to avoid collision with `zebtrack.ui.ui_coordinator` (Mediator).

### 2.2. ProcessingCoordinator
*   **Owns:**
    *   `ProcessingWorker` (The background process).
    *   `ProcessingContext` (Config for the worker).
*   **Accesses:**
    *   `ProjectManager` (Read/Write project data).
    *   `DetectorService` (To configure detectors).
    *   `EventBus` (To publish updates).
    *   `core.UIScheduler` (Directly calls `update_view` - Hybrid Pattern).
*   **DOES NOT Access:**
    *   `MainViewModel` (Strictly forbidden).
    *   `ApplicationGUI` (Directly - uses events or `ui_coordinator` abstraction).

---

## 3. Critical Control Flows (The Recipes)

### 3.1. Single Video Analysis Flow
1.  **User Action:** Clicks "Analyze" in Dialog.
2.  **Dispatcher:** Publishes `Events.VIDEO_ANALYZE_SINGLE` with payload `{'video_path': '...', 'config': {...}}`.
3.  **ViewModel:** `AnalysisControlViewModel.start_single_video_workflow` is triggered.
    *   Validates config.
    *   Sets `active_zone_video` in `ProjectManager`.
    *   Publishes `ui:setup_zone_definition_for_single_video` to prepare UI.
4.  **Coordinator:** `AnalysisControlViewModel.start_single_video_processing` calls `ProcessingCoordinator`.
    *   Validates logic (is project loaded? are zones defined?).
    *   Creates `ProcessingContext` and `ProcessingCallbacks`.
    *   **Spawns `ProcessingWorker`** in a separate thread/process.
    *   Sets `state_manager.is_processing = True`.
5.  **Worker Loop:** `ProcessingWorker` reads frames.
    *   Detects objects.
    *   Sends `result_queue.put({'type': 'frame', 'frame': img, 'detections': [...], 'info': {...}})`.
6.  **Feedback Loop:** `ProcessingCoordinator._monitor_loop` reads queue.
    *   Publishes `Events.UI_DISPLAY_FRAME` (Image).
    *   Publishes `Events.UI_UPDATE_DETECTION_OVERLAY` (Meta).
7.  **UI Update:** `EventDispatcher` receives events -> updates `CanvasManager`.

### 3.2. Cancellation Flow (Hardened)
1.  **User Action:** Clicks "Cancel".
2.  **Dispatcher:** Publishes `Events.VIDEO_CANCEL_ANALYSIS`.
3.  **ViewModel:** `AnalysisControlViewModel` receives event.
    *   **CRITICAL:** Calls `self.processing_coordinator.cancel_processing()`.
4.  **Coordinator:** `ProcessingCoordinator.cancel_processing()`:
    *   Sets `self.cancel_event.set()`.
    *   Calls `self.processing_worker.cancel()`.
5.  **Worker:** `ProcessingWorker` checks `command_queue` or `cancel_event`.
    *   Breaks loop cleanly.
    *   Sends `{'type': 'completed', 'cancelled': True}`.
6.  **Cleanup:** `monitor_loop` receives completed message -> resets state -> Updates UI to "Ready".

### 3.3. Live Camera Flow (Intentional Divergence)

**Decision:** Live camera uses `LivePreviewWindow` dedicated display instead of `CanvasManager`.

**Architecture:**
- **Logic:** Managed by `LiveCameraCoordinator` -> `LiveCameraService`
- **Display:** Creates and manages a dedicated `LivePreviewWindow` (Tkinter Toplevel)
- **Updates:** Calls `self.preview_window.update_frame()` directly from the service thread (via `root.after`)
- **Events:** Does NOT use `Events.UI_DISPLAY_FRAME`

**Justification:**
1. **Different Threading Model:** Live camera requires daemon threads for capture + processing, different from `ProcessingWorker`'s queue-based approach
2. **Different Lifecycle:** Preview window is created/destroyed per camera session, not bound to main canvas
3. **Recent Stabilization:** Unified in Phase 8 (Jan 2025) - working reliably with no user complaints

**Trade-offs:**
- Features built for `CanvasManager` (drawing tools) are NOT available in live preview
- If needed, implement equivalent features directly in `LivePreviewWindow`

**Reference:** See `docs/decisions/ADR-004-live-camera-divergence.md` for full decision record.

---

## 4. Common Pitfalls for Agents

1.  **Missing Event Payloads:** Always check the **Event Registry** above. If you publish `UI_DISPLAY_FRAME` without the `frame` key, the UI will crash or show nothing.
2.  **Direct UI Access:** Do not try to access `self.view.canvas` from a Coordinator. Use `self.event_bus.publish(Events.UI_..., data)`.
3.  **Worker Isolation:** The `ProcessingWorker` runs in a separate process (multiprocessing). It cannot access global variables or shared objects (like `self.detector`) modified in the main thread *after* it started. Everything must be passed in `ProcessingContext`.
4.  **Legacy vs. New:**
    *   **Legacy:** `VideoProcessingOrchestrator`, `AnalysisOrchestrator` (Avoid modifying if possible).
    *   **New (Phase 3):** `ProcessingCoordinator` (Preferred location for logic).
5.  **UIScheduler (Resolved Naming Conflict):** Phase 2 renamed `zebtrack.core.ui_coordinator.UICoordinator` to `UIScheduler`.
    *   `zebtrack.core.ui_scheduler.UIScheduler`: A scheduler/facade for `root.after`. Used by `ProcessingCoordinator`.
    *   `zebtrack.ui.ui_coordinator.UICoordinator`: A Mediator for EventBus events. Used by `EventDispatcher`.
    *   **Reason:** Eliminated name collision that caused type confusion and import errors.
