# ZebTrack-AI System Integration Map

**Status:** Living Document
**Last Updated:** Dec 2, 2025
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

## 1. Dual Event Bus Architecture

**CRITICAL:** ZebTrack-AI uses **two coexisting event bus systems** by design. Agents must understand which system to use for each use case.

### 1.1. Event Bus Overview

| System | Module | Event Type | Primary Use Case |
|--------|--------|-----------|------------------|
| **EventBus (v1)** | `zebtrack.ui.event_bus.EventBus` | String constants (`Events` class) | Domain events: recording, project, model, video processing |
| **EventBusV2** | `zebtrack.ui.event_bus_v2.EventBusV2` | Enum (`UIEvents` enum) | UI component communication: zones, dialogs, canvas updates |

### 1.2. When to Use Each System

**Use `EventBus` (v1) + `Events` class for:**
- Recording lifecycle (`Events.RECORDING_START`, `Events.RECORDING_STOP`)
- Project management (`Events.PROJECT_CREATE`, `Events.PROJECT_OPEN`)
- Video analysis (`Events.VIDEO_ANALYZE_SINGLE`, `Events.VIDEO_CANCEL_ANALYSIS`)
- Model/detector configuration (`Events.MODEL_SET_WEIGHT`, `Events.DETECTOR_SETUP`)
- Backend → UI notifications (`Events.UI_SHOW_ERROR`, `Events.UI_SET_STATUS`)

**Use `EventBusV2` + `UIEvents` enum for:**
- UI component state sync (`UIEvents.ZONES_UPDATED`, `UIEvents.VIDEO_LOADED`)
- Inter-component communication (`UIEvents.POLYGON_EDIT_REQUESTED`)
- View refresh requests (`UIEvents.VIDEO_TREE_REFRESH_REQUESTED`)
- Processing stats display (`UIEvents.PROCESSING_STATS_UPDATED`)

### 1.3. Key Files

| File | Contains |
|------|----------|
| `src/zebtrack/ui/events.py` | `Events` class with 90+ string constants |
| `src/zebtrack/ui/event_bus.py` | `EventBus` class (v1 implementation) |
| `src/zebtrack/ui/event_bus_v2.py` | `UIEvents` enum + `EventBusV2` class + `Event` dataclass |

---

## 2. Event Bus Registry (EventBus v1 - Domain Events)

This section defines the contract for `EventBus` messages. Agents **MUST** adhere to these payload structures when publishing events.

### 2.1. UI Updates (Backend -> UI)

| Event Name | Required Payload Keys | Optional Keys | Listener (Component) | Action/Effect |
| :--- | :--- | :--- | :--- | :--- |
| `Events.UI_DISPLAY_FRAME` | `frame` (np.ndarray) | `detections` (list), `info` (dict), `experiment_id` (str) | `EventDispatcher` -> `CanvasManager` | Updates the raw video canvas with the provided image. **NOTE:** Only used by `ProcessingWorker` (recorded video). Live Camera uses `LivePreviewWindow` directly. |
| `Events.UI_DISPLAY_VIDEO_FRAME` | `video_path` (str) | - | `EventDispatcher` -> `CanvasManager` | Loads a video file from disk and displays the first frame/ROI frame. |
| `Events.UI_UPDATE_DETECTION_OVERLAY` | `detections` (list), `report` (ProcessingReport) | - | `EventDispatcher` -> `ApplicationGUI` | Draws bounding boxes, IDs, and status text over the canvas. |
| `Events.UI_NAVIGATE_TO_ANALYSIS_VIEW` | - | - | `EventDispatcher` -> `ApplicationGUI` | Switches the notebook tab to the "Analysis" tab. |
| `Events.UI_UPDATE_PROCESSING_STATS` | `stats` (dict) | - | `EventDispatcher` -> `StateSynchronizer` | Updates FPS, frame counter, and progress bars. `stats` must contain: `fps`, `frame`, `total_frames`. |
| `Events.UI_SET_STATUS` | `message` (str) | - | `EventDispatcher` -> `ApplicationGUI` | Updates the bottom status bar text. |
| `Events.UI_UPDATE_PROCESSING_MODE` | `report` (ProcessingReport) | - | `EventDispatcher` -> `StateSynchronizer` | Updates UI mode indicators. All publishers use correct format as of v3.1. |

### 2.2. Analysis Control (UI -> Backend)

| Event Name | Required Payload Keys | Optional Keys | Handler (Coordinator/VM) | Action/Effect |
| :--- | :--- | :--- | :--- | :--- |
| `Events.VIDEO_ANALYZE_SINGLE` | `video_path` (str), `config` (dict) | - | `AnalysisControlViewModel` | Triggers the start of the single video analysis workflow. |
| `Events.VIDEO_CANCEL_ANALYSIS` | - | - | `AnalysisControlViewModel` | **Delegates to `ProcessingCoordinator.cancel_processing()`**. Sets flags and stops workers. |
| `Events.ZONE_AUTO_DETECT` | `video_path` (str or None) | `stabilization_frames` (int) | `ProcessingCoordinator` | Runs `AquariumDetector` to find the tank polygon automatically. |

---

## 3. EventBusV2 Registry (UI Component Events)

### 3.1. Zone & ROI Events

| Event (UIEvents) | Payload Keys | Publishers | Subscribers |
|-----------------|--------------|------------|-------------|
| `ZONES_UPDATED` | `zone_data` (optional) | `DialogManager`, `CanvasManager`, `gui.py` | `UICoordinator`, `CanvasManager` |
| `ZONE_SELECTED` | `zone_id` | (internal) | `UICoordinator` |
| `POLYGON_EDIT_REQUESTED` | `polygon` (list of points) | `CanvasManager` | `UICoordinator`, `CanvasManager` |

### 3.2. Video & Project View Events

| Event (UIEvents) | Payload Keys | Publishers | Subscribers |
|-----------------|--------------|------------|-------------|
| `VIDEO_LOADED` | `video_path` | (internal) | `UICoordinator` |
| `VIDEO_TREE_REFRESH_REQUESTED` | `filter_text` (optional) | `DialogManager`, `ZoneControlBuilder` | `UICoordinator` |
| `PROJECT_VIEWS_REFRESH_REQUESTED` | `reason`, `append_summary`, `immediate` | `DialogManager`, `CanvasManager` | `UICoordinator` |
| `VIDEO_HIERARCHY_SNAPSHOT_REQUESTED` | - | (internal) | `UICoordinator` |
| `VIDEO_HIERARCHY_SNAPSHOT_UPDATED` | `snapshot` (dict) | `gui.py` | (consumers) |
| `READINESS_SNAPSHOT_UPDATED` | `snapshot` (dict) | `DialogManager` | `UICoordinator` |

### 3.3. Processing & Analysis Events

| Event (UIEvents) | Payload Keys | Publishers | Subscribers |
|-----------------|--------------|------------|-------------|
| `PROCESSING_STATS_UPDATED` | `fps`, `frame`, `total_frames` | (via event bridge) | `UICoordinator` |
| `SOCIAL_SUMMARY_UPDATED` | `summary` (dict) | (via event bridge) | `UICoordinator` |
| `ANALYSIS_TASK_STATUS_UPDATED` | `status`, `progress` | (via event bridge) | `UICoordinator` |
| `ANALYSIS_STARTED` | - | (lifecycle) | (consumers) |
| `ANALYSIS_COMPLETED` | - | (lifecycle) | (consumers) |

### 3.4. Notification Events

| Event (UIEvents) | Payload Keys | Publishers | Subscribers |
|-----------------|--------------|------------|-------------|
| `SHOW_ERROR` | `title`, `message` | (internal) | `ApplicationGUI` |
| `SHOW_WARNING` | `title`, `message` | (internal) | `ApplicationGUI` |
| `SHOW_INFO` | `title`, `message` | (internal) | `ApplicationGUI` |
| `ERROR_OCCURRED` | `title`, `message` | `VideoProcessingService` | `ApplicationGUI` |
| `EXTERNAL_TRIGGER_NOTICE` | `context` (dict) | `SessionCoordinator` | `UICoordinator` |
| `EXTERNAL_TRIGGER_NOTICE_CLEARED` | - | `SessionCoordinator` | `UICoordinator` |

---

## 4. Component Dependencies (The Hierarchy)

Understanding who holds what references prevents "AttributeError" and circular dependency issues.

### 4.1. Dependency Container (`MainViewModelDependencies`)
*   **Root Object:** Passed to `MainViewModel` and `ApplicationBootstrapper`.
*   **Contains:**
    *   `event_bus`: The communication channel.
    *   `cancel_event`: **Shared** `threading.Event` for global cancellation.
    *   `processing_coordinator`: Handles video loops.
    *   `hardware_coordinator`: Handles Detector/Camera.
    *   `session_coordinator`: Handles Recording/Arduino.
    *   `project_lifecycle_coordinator`: Handles Project CRUD.
    *   `ui_coordinator`: Renamed to `UIScheduler` (`zebtrack.core.ui_scheduler`) to avoid collision with `zebtrack.ui.ui_coordinator` (Mediator).

### 4.2. ProcessingCoordinator
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

## 5. Critical Control Flows (The Recipes)

### 5.1. Single Video Analysis Flow
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

### 5.2. Cancellation Flow (Hardened)
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

### 5.3. Live Camera Flow (Intentional Divergence)

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

## 6. Common Pitfalls for Agents

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
6. **Dual Event Bus:** Use `Events` class with `EventBus` for domain events; use `UIEvents` enum with `EventBusV2` for UI component communication. **Do NOT mix them.**
7. **ByteTracker Kalman Filter Drift:** The ByteTracker uses a Kalman Filter that can predict track positions OUTSIDE the original polygon boundary. All tracking output MUST be re-filtered by the polygon after `_apply_byte_tracking()`. This was fixed in Dec 2025 - see `detector.py:_apply_byte_tracking()` post-filter logic.
8. **BBox Overlay Tab Check (Updated Jan 2025):** Detection overlays are drawn ONLY by `canvas_manager.update_video_frame()` which checks the current tab. The `processing_worker` does NOT call `detector.draw_overlay()` anymore - it sends the raw frame, and `canvas_manager` decides whether to draw overlays based on `is_on_analysis_tab`. This prevents bboxes from appearing on the zone drawing tab.
9. **Guard ui_event_bus Before Publish:** Always check `if self.ui_event_bus:` before calling `publish_event()` in observer callbacks. The event bus may not be initialized during early startup or in edge cases.
10. **ByteTrack Sparse Frame Tuning (Critical Fix Jan 2025):** When using `processing_interval > 1`:
    - The Kalman Filter `dt` is now automatically set to `processing_interval` in `detector.py`
    - This correctly models motion predictions over larger time steps
    - The `track_buffer` is scaled by `processing_interval` to maintain equivalent temporal window
    - Position/velocity weights scale with `sqrt(dt)` for proper uncertainty propagation
    - Without this fix, track IDs will jump erratically on sparse frames.

---

## 7. Removed Events (Changelog)

### Dec 2, 2025 - Dead Event Cleanup

The following events were removed during the integration audit as they had **no subscribers**:

| Event | Previous Location | Reason for Removal |
|-------|------------------|-------------------|
| `PROCESSING_MODE_CHANGED` | `session_coordinator.py:1050`, `hardware_coordinator.py:1091` | No subscribers found. Processing mode is handled via `ProcessingCoordinator._publish_processing_mode()` which calls `view.update_processing_mode()` directly. |
| `PROCESSING_MODE_RESTORE` | `session_coordinator.py:1139`, `hardware_coordinator.py:1163,1490` | No subscribers found. Same as above - orphaned event from earlier refactoring. |

**Impact:** None. These events were never handled by any component.

---

## 8. Legacy Patterns (Known Technical Debt)

The following patterns remain in the codebase and should be addressed in future refactoring:

### 8.1. Direct View Access in Coordinators

Some coordinators still access `self.view` directly instead of publishing events:

| Coordinator | Pattern | Recommended Fix |
|-------------|---------|-----------------|
| `SessionCoordinator` | `self.view.camera.get_frame()` | Inject camera service; publish frame events |
| `ProcessingCoordinator` | `self.view.update_processing_mode()` via `UIScheduler` | Migrate to `EventBusV2` → `UIEvents.PROCESSING_STATS_UPDATED` |
| `HardwareCoordinator` | Direct `root.after()` calls | Use `UIScheduler` abstraction |

### 8.2. Hybrid Patterns (Acceptable)

These patterns are intentional trade-offs documented in ADRs:

| Pattern | Location | ADR Reference |
|---------|----------|---------------|
| Live Camera direct display | `LiveCameraCoordinator` → `LivePreviewWindow` | ADR-004 |
| `UIScheduler.update_view()` direct calls | `ProcessingCoordinator` | ADR-003 (Phase 2) |
