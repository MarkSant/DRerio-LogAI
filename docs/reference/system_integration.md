# DRerio LogAI System Integration Map

**Status:** Living Document
**Last Updated:** Feb 3, 2026 (v4.0)
**Purpose:** This document serves as the "source of truth" for AI Agents regarding system integration, event payloads, and control flows. It defines the strict contracts between the decoupled components of the Phase 4 Architecture (16 specialized coordinators).

---

## 0. Coordinator Architecture

### 0.1. Phase 3 → Phase 4 Evolution

Phase 3 consolidated 7 orchestrators into 4 "super coordinators." Phase 4 further decomposed these into 16 specialized coordinators with a unified base class, improving testability and single-responsibility adherence.

**Phase 3 orchestrators deleted (7 total, ~2,500+ lines removed):**

| Orchestrator                   | Lines | Replacement (Phase 3)         |
| ------------------------------ | ----- | ----------------------------- |
| `AnalysisOrchestrator`         | ~200  | ProcessingCoordinator         |
| `ZoneArenaOrchestrator`        | ~150  | ProjectLifecycleCoordinator   |
| `ProcessingConfigOrchestrator` | ~180  | ProcessingCoordinator         |
| `CalibrationOrchestrator`      | ~220  | ProjectLifecycleCoordinator   |
| `ModelDiagnosticsOrchestrator` | ~250  | HardwareCoordinator           |
| `ProjectOrchestrator`          | ~300  | ProjectLifecycleCoordinator   |
| `RecordingSessionOrchestrator` | ~633  | SessionCoordinator            |

**Phase 3 "super coordinators" decomposed in Phase 4:**

| Phase 3 Super Coordinator | Decomposed Into (Phase 4) |
| --- | --- |
| `ProcessingCoordinator` | `VideoProcessingCoordinator`, `ProgressTrackingCoordinator`, `SequentialProcessingCoordinator` |
| `HardwareCoordinator` | `DetectorSetupCoordinator`, `ModelDiagnosticsCoordinator` |
| `SessionCoordinator` | `RecordingSessionCoordinator`, `LiveCameraSessionCoordinator`, `LiveCalibrationCoordinator` |
| (kept) | `ProjectLifecycleCoordinator` (unchanged from Phase 3) |

### 0.2. Current Coordinator Registry (Phase 4 - 16 Coordinators)

| Coordinator                         | Phase | Responsibility                                        |
| ----------------------------------- | ----- | ----------------------------------------------------- |
| `BaseCoordinator`                   | 4     | Unified base class (logging, error handling, DI)      |
| `DetectorSetupCoordinator`          | 4.9   | Detector and weight configuration                     |
| `DialogCoordinator`                 | 4     | Dialog lifecycle management                           |
| `LiveBatchCoordinator`              | 4     | Live batch recording operations                       |
| `LiveCalibrationCoordinator`        | 4.7   | Camera calibration and zone validation                |
| `LiveCameraSessionCoordinator`      | 4.7   | Live camera analysis sessions                         |
| `ModelDiagnosticsCoordinator`       | 4.9   | Model diagnostic tests                                |
| `MultiAquariumCoordinator`          | 4     | Aquarium detection and zone management                |
| `ProgressTrackingCoordinator`       | 4     | Processing progress and batch context                 |
| `ProjectCoordinator`                | 3     | Project CRUD (Sprint 3)                               |
| `ProjectLifecycleCoordinator`       | 3     | Project lifecycle, calibration, zones, model override |
| `RecordingSessionCoordinator`       | 4.7   | Recording session lifecycle                           |
| `ReportGenerationCoordinator`       | 4     | Report generation workflows                           |
| `SequentialProcessingCoordinator`   | 4     | Sequential multi-aquarium processing                  |
| `UIStateController`                 | 3     | UI state synchronization (17 production calls)        |
| `VideoProcessingCoordinator`        | 4     | Core video processing workflow                        |

**Shared Mixins:**

| Mixin | Purpose |
| --- | --- |
| `_UnifiedReportMixin` | Unified report generation logic (Word/Excel) |
| `_VideoSelectionMixin` | Video selection and filtering helpers |

**Supporting Types:**

| File | Contains |
| --- | --- |
| `_protocols.py` | Coordinator protocol definitions |
| `processing_types.py` | `ProcessingCoordinatorError` and types |

---

## 1. Dual Event Bus Architecture

> **Deprecation Notice (ADR-009):** EventBus v1 is deprecated. New features MUST use
> EventBusV2 (`UIEvents` enum). Migration of existing v1 subscribers is planned but
> not yet started. See [ADR-009](../decisions/ADR-009-event-bus-unification.md).

**CRITICAL:** DRerio LogAI uses **two coexisting event bus systems** by design. Agents must understand which system to use for each use case.

### 1.1. Event Bus Overview

| System            | Module                                | Event Type                        | Primary Use Case                                           |
| ----------------- | ------------------------------------- | --------------------------------- | ---------------------------------------------------------- |
| **EventBus (v1)** | `zebtrack.ui.event_bus.EventBus`      | String constants (`Events` class) | Domain events: recording, project, model, video processing |
| **EventBusV2**    | `zebtrack.ui.event_bus_v2.EventBusV2` | Enum (`UIEvents` enum)            | UI component communication: zones, dialogs, canvas updates |

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

| File                              | Contains                                                 |
| --------------------------------- | -------------------------------------------------------- |
| `src/zebtrack/ui/events.py`       | `Events` class with 90+ string constants                 |
| `src/zebtrack/ui/event_bus.py`    | `EventBus` class (v1 implementation)                     |
| `src/zebtrack/ui/event_bus_v2.py` | `UIEvents` enum + `EventBusV2` class + `Event` dataclass |

---

## 2. Event Bus Registry (EventBus v1 - Domain Events)

This section defines the contract for `EventBus` messages. Agents **MUST** adhere to these payload structures when publishing events.

### 2.1. UI Updates (Backend -> UI)

| Event Name                            | Required Payload Keys                            | Optional Keys                                             | Listener (Component)                     | Action/Effect                                                                                                                                                    |
| :------------------------------------ | :----------------------------------------------- | :-------------------------------------------------------- | :--------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Events.UI_DISPLAY_FRAME`             | `frame` (np.ndarray)                             | `detections` (list), `info` (dict), `experiment_id` (str) | `EventDispatcher` -> `CanvasManager`     | Updates the raw video canvas with the provided image. **NOTE:** Only used by `ProcessingWorker` (recorded video). Live Camera uses `LivePreviewWindow` directly. |
| `Events.UI_DISPLAY_VIDEO_FRAME`       | `video_path` (str)                               | -                                                         | `EventDispatcher` -> `CanvasManager`     | Loads a video file from disk and displays the first frame/ROI frame.                                                                                             |
| `Events.UI_UPDATE_DETECTION_OVERLAY`  | `detections` (list), `report` (ProcessingReport) | -                                                         | `EventDispatcher` -> `ApplicationGUI`    | Draws bounding boxes, IDs, and status text over the canvas.                                                                                                      |
| `Events.UI_NAVIGATE_TO_ANALYSIS_VIEW` | -                                                | -                                                         | `EventDispatcher` -> `ApplicationGUI`    | Switches the notebook tab to the "Analysis" tab.                                                                                                                 |
| `Events.UI_UPDATE_PROCESSING_STATS`   | `stats` (dict)                                   | -                                                         | `EventDispatcher` -> `StateSynchronizer` | Updates FPS, frame counter, and progress bars. `stats` must contain: `fps`, `frame`, `total_frames`.                                                             |
| `Events.UI_SET_STATUS`                | `message` (str)                                  | -                                                         | `EventDispatcher` -> `ApplicationGUI`    | Updates the bottom status bar text.                                                                                                                              |
| `Events.UI_UPDATE_PROCESSING_MODE`    | `report` (ProcessingReport)                      | -                                                         | `EventDispatcher` -> `StateSynchronizer` | Updates UI mode indicators. All publishers use correct format as of v3.1.                                                                                        |

### 2.2. Analysis Control (UI -> Backend)

| Event Name                                | Required Payload Keys               | Optional Keys                | Handler (Coordinator/VM)   | Action/Effect                                                                               |
| :---------------------------------------- | :---------------------------------- | :--------------------------- | :------------------------- | :------------------------------------------------------------------------------------------ |
| `Events.VIDEO_ANALYZE_SINGLE`             | `video_path` (str), `config` (dict) | -                            | `AnalysisControlViewModel` | Triggers the start of the single video analysis workflow.                                   |
| `Events.VIDEO_CANCEL_ANALYSIS`            | -                                   | -                            | `AnalysisControlViewModel` | **Delegates to `ProcessingCoordinator.cancel_processing()`**. Sets flags and stops workers. |
| `Events.ZONE_AUTO_DETECT`                 | `video_path` (str or None)          | `stabilization_frames` (int), `expected_count` (int) | `ProcessingCoordinator`    | Runs `AquariumDetector` to find the tank polygon automatically. See § 2.1.                  |
| `Events.PROCESSING_GENERATE_TRAJECTORIES` | `video_paths` (list, optional)      | -                            | `ProcessingCoordinator`    | Triggers `process_pending_project_videos`. Used by Reports tab to start analysis.           |

### 2.1 Arena auto-detection: one path, two flows, three answers

**Project and single pre-recorded video share the same code.** The zone tab's
button emits `ZONE_AUTO_DETECT_CLICKED` → `SingleVideoWorkflow.on_auto_detect_clicked`
(the name predates the project flow reusing it); `DialogManager._start_arena_detection_for`
publishes `ZONE_AUTO_DETECT` directly. Both reach
`VideoProcessingCoordinator._handle_zone_auto_detect` →
`MultiAquariumCoordinator.run_aquarium_detection` → `AquariumDetector`.

**`expected_count`, when absent, comes from the OPEN PROJECT first**
(`_fallback_expected_aquarium_count`). `settings.analysis_config.num_aquariums` is
a cache resynchronised whenever the project UI is rebuilt, so reading it first let
a two-aquarium project auto-detect in single mode depending on timing.

**Which model and which outline** is decided only by
`core/services/arena_detection_policy.resolve_arena_detection`. **Which detection
in a frame is the arena** is decided only by
`core/detection/arena_candidate_selection` — shared with the live burst path, which
resolves masks by box index and never required a single detection.

**Consensus runs over one population.** Mask outlines and bbox fallbacks are kept
apart: rectangles agree with each other at IoU ~0.99 while real outlines jitter, so
mixing them lets one degraded frame out-vote the preserved shapes.

**The result carries provenance**, readable via
`AquariumDetector.get_last_detection_provenance()`:

| Provenance          | Meaning                                             | User-facing effect                    |
| :------------------ | :-------------------------------------------------- | :------------------------------------ |
| `mask`              | A segmentation outline was kept                     | Silent success                        |
| `bbox`              | Rectangle — no usable mask, or none requested       | `UI_SHOW_WARNING` **only** if the project asked to preserve the shape |
| `synthetic_default` | Frame-sized placeholder, nothing was detected       | `UI_SHOW_WARNING`; arena still saved  |
| `none`              | Nothing detected (the real production outcome)      | `UI_SHOW_WARNING`; no arena set       |

The `synthetic_default` branch is guarded by `hasattr(source, "_cap")` and
`VideoFileSource` exposes `cap`, so it is unreachable with a real video — kept
tagged rather than activated, because a fabricated arena is worse than a reported
failure.

---

## 3. EventBusV2 Registry (UI Component Events)

### 3.1. Zone & ROI Events

| Event (UIEvents)         | Payload Keys               | Publishers                                 | Subscribers                      |
| ------------------------ | -------------------------- | ------------------------------------------ | -------------------------------- |
| `ZONES_UPDATED`          | `zone_data` (optional)     | `DialogManager`, `CanvasManager`, `gui.py` | `UICoordinator`, `CanvasManager` |
| `ZONE_SELECTED`          | `zone_id`                  | (internal)                                 | `UICoordinator`                  |
| `POLYGON_EDIT_REQUESTED` | `polygon` (list of points) | `CanvasManager`                            | `UICoordinator`, `CanvasManager` |

### 3.2. Video & Project View Events

| Event (UIEvents)                     | Payload Keys                            | Publishers                            | Subscribers     |
| ------------------------------------ | --------------------------------------- | ------------------------------------- | --------------- |
| `VIDEO_LOADED`                       | `video_path`                            | (internal)                            | `UICoordinator` |
| `VIDEO_TREE_REFRESH_REQUESTED`       | `filter_text` (optional)                | `DialogManager`, `ZoneControlBuilder` | `UICoordinator` |
| `PROJECT_VIEWS_REFRESH_REQUESTED`    | `reason`, `append_summary`, `immediate` | `DialogManager`, `CanvasManager`      | `UICoordinator` |
| `VIDEO_HIERARCHY_SNAPSHOT_REQUESTED` | -                                       | (internal)                            | `UICoordinator` |
| `VIDEO_HIERARCHY_SNAPSHOT_UPDATED`   | `snapshot` (dict)                       | `gui.py`                              | (consumers)     |
| `READINESS_SNAPSHOT_UPDATED`         | `snapshot` (dict)                       | `DialogManager`                       | `UICoordinator` |

### 3.3. Zone Management Events (New - Dec 2025)

| Event (Events class)  | Payload Keys       | Publishers     | Subscribers                                                   |
| --------------------- | ------------------ | -------------- | ------------------------------------------------------------- |
| `ZONE_COPY_ZONES`     | `video_path` (str) | `ZoneControls` | `EventDispatcher` → `CanvasManager.copy_zones_from_video()`   |
| `ZONE_PASTE_ZONES`    | `video_path` (str) | `ZoneControls` | `EventDispatcher` → `CanvasManager.paste_zones_to_video()`    |
| `ZONE_DELETE_ZONES`   | `video_path` (str) | `ZoneControls` | `EventDispatcher` → `CanvasManager.delete_zones_from_video()` |
| `ZONE_FINISH_DRAWING` | -                  | `ZoneControls` | `EventDispatcher` → `CanvasManager.finish_current_polygon()`  |
| `ZONE_CONCLUDE_VIDEO` | -                  | `ZoneControls` | `EventDispatcher` → `ZoneControlBuilder._on_conclude_video()` |

> **`ZONE_CONCLUDE_VIDEO` (atualizado):** além de salvar o projeto e commitar uma edição
> interativa em andamento (apenas quando há edição ativa), `_on_conclude_video` publica
> `LIVE_RECORDING_RESUME_REQUESTED`. Assim, no fluxo de câmera ao vivo, clicar em "✅ Concluir"
> retoma a sessão pendente (paridade com o banner "▶️ Iniciar Gravação"). É um no-op seguro
> fora de projetos live (sem contexto pendente em `LiveCameraSessionCoordinator`).
>
> **Overlay live (correção):** durante a sessão ao vivo, `FrameProcessingMixin._processing_loop`
> chama `detector.draw_overlay(frame, [])` (apenas zonas). As caixas de detecção são desenhadas
> uma única vez pelo consumidor do frame — `VideoFrameManager.update_video_frame` (canvas
> integrado) ou `LivePreviewWindow.update_frame` (janela externa) — evitando bbox duplicado.

### 3.4. Multi-Aquarium Events (Dec 2025)

| Event (Events class)                   | Payload Keys                                            | Publishers                                 | Subscribers                                                     |
| -------------------------------------- | ------------------------------------------------------- | ------------------------------------------ | --------------------------------------------------------------- |
| `ZONE_MULTI_AUTO_DETECT`               | `video_path`, `stabilization_frames`, `expected_count`  | `ZoneControls`                             | `ProcessingCoordinator._handle_multi_auto_detect()`             |
| `ZONE_MULTI_AUTO_DETECT_SUCCESS`       | `video_path`, `polygons` (list)                         | `ProcessingCoordinator`                    | `ZoneControls`, `CanvasManager`                                 |
| `ZONE_MULTI_AUTO_DETECT_FAILED`        | `video_path`, `reason` (str)                            | `ProcessingCoordinator`                    | `ZoneControls`                                                  |
| `ZONE_AQUARIUM_SELECTED`               | `aquarium_id` (int)                                     | `ZoneControls`, `AquariumAssignmentDialog` | `EventDispatcher` → `CanvasManager.update_zone_listbox()`       |
| `ZONE_MULTI_DETECT_COMPLETED`          | `count` (int), `aquariums` (list)                       | `AquariumDetector`                         | `ZoneControlBuilder`, `MultiAquariumConfirmDialog`              |
| `ZONE_AQUARIUM_CONFIG_CONFIRMED`       | `configs` (list[AquariumConfig])                        | `AquariumAssignmentDialog`                 | `ProjectManager`, `CanvasManager`                               |
| `ZONE_AQUARIUM_CONFIG_UPDATED`         | `aquarium_id`, `config`, `video_path`                   | `AquariumAssignmentDialog`                 | `ProjectLifecycleCoordinator._handle_aquarium_config_updated()` |
| `ZONE_AQUARIUM_COUNT_CONFIRMED`        | `count` (int)                                           | `MultiAquariumConfirmDialog`               | `ZoneControlBuilder`                                            |
| `ZONE_AQUARIUM_ASSIGNMENT_COMPLETED`   | `configs` (list[AquariumConfig]), `apply_to_all` (bool) | `AquariumAssignmentDialog`                 | `ProjectManager`, `WizardService`                               |
| `ZONE_SHOW_AQUARIUM_COUNT_DIALOG`      | -                                                       | `ZoneControls`                             | `DialogManager` → `MultiAquariumConfirmDialog`                  |
| `ZONE_SHOW_AQUARIUM_ASSIGNMENT_DIALOG` | -                                                       | `ZoneControls`                             | `DialogManager` → `AquariumAssignmentDialog`                    |

**Track ID Convention**: Global ID = `aquarium_id * 1000 + local_track_id`. Aquarium 0 tracks: 0-999; Aquarium 1 tracks: 1000-1999; Aquarium 2 tracks: 2000-2999.

**Multi-Aquarium Detection Features (Phase 1-5)**:

- **ROI Cropping**: `Detector._crop_aquarium_region()` extracts per-aquarium frames
- **Parallel Detection**: `Detector.detect_partitioned_parallel()` uses ThreadPoolExecutor
- **Batch Inference**: `Detector.detect_batch()` for offline multi-frame processing
- **Tracker Selection**: Toggle between ByteTrack (Kalman Filter) and Simple Tracker (Hybrid IoU/Dist)
- **Advanced Tuning**: Exposed `track_buffer`, `max_center_distance`, and `iou_threshold` in UI
- **Uncertainty Tracking**: `uncertainty` and `bbox_iou` columns in Parquet
- **Error Recovery**: Failed aquarium detection doesn't crash others
- **Validation**: `TrajectoryQualityValidator` checks ID bounds, gaps per aquarium
- **Interval Persistence**: `analysis_interval_frames` and `display_interval_frames` are persisted in `project_data` during project creation and single-video analysis. The `display_interval` is now a first-class citizen in the `Settings` model.

**Output Structure** (per video with multi-aquarium):

```text
<video>_aquarium_1/
  1_ArenaROI_<video>.parquet
  3_CoordMovimento_<video>.parquet
  ...
<video>_aquarium_2/
  1_ArenaROI_<video>.parquet
  3_CoordMovimento_<video>.parquet
  ...
```

### 3.5. Processing & Analysis Events

| Event (UIEvents)               | Payload Keys                   | Publishers         | Subscribers     |
| ------------------------------ | ------------------------------ | ------------------ | --------------- |
| `PROCESSING_STATS_UPDATED`     | `fps`, `frame`, `total_frames` | (via event bridge) | `UICoordinator` |
| `SOCIAL_SUMMARY_UPDATED`       | `summary` (dict)               | (via event bridge) | `UICoordinator` |
| `ANALYSIS_TASK_STATUS_UPDATED` | `status`, `progress`           | (via event bridge) | `UICoordinator` |
| `ANALYSIS_STARTED`             | -                              | (lifecycle)        | (consumers)     |
| `ANALYSIS_COMPLETED`           | -                              | (lifecycle)        | (consumers)     |

### 3.6. Detector & Tracking Events (Dec 2025)

| Event (Domain)                | Payload Keys                                                                                                  | Publishers            | Subscribers                 |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------- | --------------------- | --------------------------- |
| `TRACKING_PARAMETERS_UPDATED` | `track_threshold`, `match_threshold`, `track_buffer`, `use_bytetrack`, `max_center_distance`, `iou_threshold` | `DetectorCoordinator` | UI components, StateManager |

**Notes:**

- All payload values are optional (None if not updated)
- `use_bytetrack: bool` - Toggles between ByteTrack and SingleSubjectTracker
- `track_buffer: int` - Frames to keep lost tracks (default: 300)
- `max_center_distance: float` - Max distance for hybrid matching (pixels)
- `iou_threshold: float` - IoU threshold for hybrid matching [0, 1)

### 3.7. Notification Events

| Event (UIEvents)                  | Payload Keys       | Publishers               | Subscribers      |
| --------------------------------- | ------------------ | ------------------------ | ---------------- |
| `SHOW_ERROR`                      | `title`, `message` | (internal)               | `ApplicationGUI` |
| `SHOW_WARNING`                    | `title`, `message` | (internal)               | `ApplicationGUI` |
| `SHOW_INFO`                       | `title`, `message` | (internal)               | `ApplicationGUI` |
| `ERROR_OCCURRED`                  | `title`, `message` | `VideoProcessingService` | `ApplicationGUI` |
| `EXTERNAL_TRIGGER_NOTICE`         | `context` (dict)   | `SessionCoordinator`     | `UICoordinator`  |
| `EXTERNAL_TRIGGER_NOTICE_CLEARED` | -                  | `SessionCoordinator`     | `UICoordinator`  |

---

## 4. Component Dependencies (The Hierarchy)

Understanding who holds what references prevents "AttributeError" and circular dependency issues.

### 4.1. Dependency Container (`MainViewModelDependencies`)

- **Root Object:** Passed to `MainViewModel` and `ApplicationBootstrapper`.

- **Contains:**
  - `event_bus`: Domain event communication (EventBus v1, deprecated — see ADR-009).
  - `cancel_event`: **Shared** `threading.Event` for global cancellation.
  - `video_processing_coordinator`: Core video processing workflow.
  - `progress_tracking_coordinator`: Processing progress and batch context.
  - `detector_setup_coordinator`: Detector and weight configuration.
  - `model_diagnostics_coordinator`: Model diagnostic tests.
  - `recording_session_coordinator`: Recording session lifecycle.
  - `live_camera_session_coordinator`: Live camera analysis sessions.
  - `live_calibration_coordinator`: Camera calibration and zone validation.
  - `project_lifecycle_coordinator`: Project CRUD, calibration, zones.
  - `multi_aquarium_coordinator`: Aquarium detection and zone management.
  - `sequential_processing_coordinator`: Sequential multi-aquarium processing.
  - `report_generation_coordinator`: Report generation workflows.
  - `dialog_coordinator`: Dialog lifecycle management.
  - `ui_coordinator`: Renamed to `UIScheduler` (`zebtrack.core.ui_scheduler`) to avoid collision with `zebtrack.ui.ui_coordinator` (Mediator).

### 4.2. VideoProcessingCoordinator (replaces Phase 3 ProcessingCoordinator)

- **Owns:**
  - `ProcessingWorker` (The background process).
  - `ProcessingContext` (Config for the worker).

- **Accesses:**
  - `ProjectManager` (Read/Write project data).
  - `DetectorService` (To configure detectors).
  - `EventBus` (To publish updates).
  - `core.UIScheduler` (Directly calls `update_view` - Hybrid Pattern).
- **DOES NOT Access:**
  - `MainViewModel` (Strictly forbidden).
  - `ApplicationGUI` (Directly - uses events or `ui_coordinator` abstraction).

---

## 5. Critical Control Flows (The Recipes)

### 3.8. Behavioral Configuration Events (New - Dec 2025)

| Event (EventBus v1)                     | Payload Keys                | Publishers               | Subscribers          |
| --------------------------------------- | --------------------------- | ------------------------ | -------------------- |
| `behavioral_config.perspective_changed` | `video_path`, `perspective` | `BehavioralConfigWidget` | (Logging/Suppressed) |
| `behavioral_config.values_changed`      | `config` (dict)             | `BehavioralConfigWidget` | (Logging/Suppressed) |

> **Note**: These events are currently used primarily for internal component sync or logging. They are suppressed in `EventBus` to avoid "no handlers" warnings since the `SingleVideoConfigDialog` reads the values directly from the widget.

### 5.1. Single Video Analysis Flow (Enhanced Dec 2025)

1. **User Action:** Clicks "Analyze" in Dialog.
   - **Config Persistence:** Dialog defaults (`aquarium_perspective`, `geotaxis_*`) are saved to `Settings.behavioral_analysis`.
2. **Dispatcher:** Publishes `Events.VIDEO_ANALYZE_SINGLE` with payload `{'video_path': '...', 'config': {...}}`.
3. **ViewModel:** `AnalysisControlViewModel.start_single_video_workflow` is triggered.
   - Validates config.
   - Sets `active_zone_video` in `ProjectManager`.
   - Publishes `ui:setup_zone_definition_for_single_video` to prepare UI.
4. **Coordinator:** `AnalysisControlViewModel.start_single_video_processing` calls `ProcessingCoordinator`.
   - **Context:** Collects `behavioral_config` from project/settings.
   - Validates logic (is project loaded? are zones defined?).
   - Creates `ProcessingContext` and `ProcessingCallbacks`.
   - **Spawns `ProcessingWorker`** in a separate thread/process.
   - Sets `state_manager.is_processing = True`.
5. **Worker Loop:** `ProcessingWorker` reads frames.
   - Detects objects.
   - Sends `result_queue.put({'type': 'frame', 'frame': img, 'detections': [...], 'info': {...}})`.
6. **Completion & Reporting:**
   - `ProcessingCoordinator.on_video_completed` triggers.
   - Calls `generate_project_reports`.
   - **CRITICAL:** `behavioral_config` is explicitly passed to `AnalysisService` to ensure Perspective/Geotaxis settings are respected.
   - `Reporter` uses `DataTransformer.rename_geotaxis_columns` to format labels (e.g., "Fundo (0-5cm)").
7. **UI Update:** `EventDispatcher` receives events -> updates `CanvasManager`.

### 5.2. Cancellation Flow (Hardened)

1. **User Action:** Clicks "Cancel".
2. **Dispatcher:** Publishes `Events.VIDEO_CANCEL_ANALYSIS`.
3. **ViewModel:** `AnalysisControlViewModel` receives event.
   - **CRITICAL:** Calls `self.processing_coordinator.cancel_processing()`.
4. **Coordinator:** `ProcessingCoordinator.cancel_processing()`:
   - Sets `self.cancel_event.set()`.
   - Calls `self.processing_worker.cancel()`.
5. **Worker:** `ProcessingWorker` checks `command_queue` or `cancel_event`.
   - Breaks loop cleanly.
   - Sends `{'type': 'completed', 'cancelled': True}`.
6. **Cleanup:** `monitor_loop` receives completed message -> resets state -> Updates UI to "Ready".

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

### 5.4. Live Zones, Batch Completion & Status Counts (June 2026)

Cross-component contracts introduced by the live-project bug-sextet fix
(branch `fix/live-project-bug-sextet`):

- **Reference-frame zones folder:** zone parquets drawn over
  `live_camera_reference_frame.png` are written to
  `<project>/Zonas_Referencia/` (constants `LIVE_REFERENCE_FRAME_FILENAME` /
  `REFERENCE_ZONES_DIRNAME` in `core/project/output_registration_manager.py`).
  `resolve_results_directory` special-cases the reference frame BEFORE the
  hierarchical group/day/subject resolution. Legacy projects that stored these
  parquets under `Grupo_Sem_Grupo/Dia_Indefinido/Sujeito_Indefinido/` are
  still readable (fallback in `ParquetIOManager._resolve_source_zone_parquets`).
- **Zone reuse lookup chain** (`ParquetIOManager.copy_zone_parquet_files`):
  scan → registered `parquet_files` on the video entry → candidate dirs
  (source parent, resolver dir, legacy path). An empty scan no longer
  short-circuits (PNG sources return empty scans by design). The copy never
  re-creates the `Grupo_Sem_Grupo` hierarchy for targets without group
  metadata.
- **Self-import of zone parquets:**
  `ProjectManager.import_zone_data_from_video_parquets(video_path)` loads
  arena/ROIs from the video's OWN session folder into the zone registry;
  `DialogManager.offer_zone_reuse` calls it before offering reuse from another
  video (live recordings always have their own parquets).
- **Batch completion:** `LiveBatchCoordinator.mark_block_complete(group, day,
  *, unified_excel, session_count)` matches in-memory batches by normalized
  (group, day) — NOT by batch_id — and always persists into
  `project_data["batch_reports"]`, publishing `BATCH_ANALYSIS_COMPLETED`.
  `BlockDetailDialog.mark_batch_complete` runs the partial-report generator in
  a daemon thread and marshals UI feedback via `master.after(0, ...)`.
  The Progress grid (`ProjectWidgetsBuilder.render_progress_grid`) paints a
  cell green when its (group, day) appears in `pm.get_batch_reports()`,
  regardless of session count.
- **Status counts:** `ReportTreeBuilder.get_project_status_counts` derives the
  effective status from data flags (summary → `complete`, trajectory →
  `processed`, none → `pending`); explicit `failed`/`complete` are preserved.
  Live sessions persist raw statuses `recorded`/`processed` — do not add raw
  statuses to the cards without updating the derivation.
- **Global model defaults:** the bootstrapper honours
  `settings.model_selection.use_openvino` (converted model required); the
  global OpenVINO toggle persists via `save_settings()` to
  `config.local.yaml`; `Settings.get_default_det_filename()` is the canonical
  perspective-aware detection-weight resolver (there is NO flat
  `weights.det_filename`). `ModelOverrideService.
  copy_global_model_settings_to_project_path(target_dir, ...)` writes
  overrides into another project's `project_config.json` via `ProjectService`
  (integrity hash preserved) without switching the open project.

### 5.5. Unified Report Folders & Summary Resolution (June 2026)

Both "Relatório para Selecionados" (partial) and "Relatório Unificado (Todos)"
publish `REPORT_GENERATE` with `report_type="unified"` and a `report_scope`
(`"selected"` vs `"all"`); the handler calls
`ReportGenerationCoordinator.generate_unified_report(..., report_scope=...)`.

- **Per-scope subfolders (no collision):** unified artifacts are written to
  `<project>/unified_reports/total/` (scope `all`) or
  `<project>/unified_reports/selecionados/` (scope `selected`). `replace_existing`
  cleanup (`_cleanup_unified_reports`) and the run manifest
  (`latest_unified_run.json`) are scoped to that subfolder, so regenerating the
  total report no longer deletes the selected/partial one. Session/day-group
  reports stay in `<project>/partial_reports/` (`BlockDetailDialog`); live raw
  outputs stay in `<project>/live_analysis_sessions/`.
- **Summary resolution fallback (fixes "sumários não encontrados"):**
  `generate_unified_report` no longer trusts only `entry["parquet_files"]["summary"]`.
  `_ensure_unified_summaries` → `_entry_summary_resolved` repairs stale absolute
  paths (e.g. OneDrive sync between machines) by locating `{exp_id}_summary.parquet`
  on disk via `resolve_results_directory`; if still missing but a trajectory
  exists, it regenerates the summary through `generate_parquet_summaries` (same
  on-disk-trajectory fallback used by `generate_project_reports`). Only videos
  with neither summary nor trajectory are reported as missing, by name.
- **UI access buttons:** `ProcessingReportsWidget._open_latest_unified_file` and
  `_update_button_states` scan `unified_reports/` recursively (both subfolders +
  legacy root); open-latest prefers the newest `latest_unified_run.json` artifact,
  falling back to newest file by mtime.
  `ReportGeneratorActions._resolve_unified_generation_strategy(scope)` checks only
  the subfolder of the scope being generated.

### 5.6. Closed-Loop Latency Logging (July 2026)

Software-only characterization (no photodiode) of the live per-zone Arduino
closed loop, layered on the zone-bindings feature (§ Hardware in `CLAUDE.md`).
It timestamps, per ROI enter/exit trigger, three moments with
`time.perf_counter()` (monotonic) and reuses the firmware's textual ACK line
(`"Red LED 1 ON"`, …) as the "LED actuated" marker.

- **Three marks:** `frame_t0` (frame read from camera, attached as the 3rd
  element of the `frame_queue` tuple `(frame_count, frame, capture_perf)`),
  `t_send` (in `ArduinoManager._writer_loop`, right before `ser.write`), `t_ack`
  (in `ArduinoManager._reader_loop`, right after `readline`).
- **Async correlation (FIFO):** the send is fire-and-forget and the ACK is read
  on a **separate** thread, so `t_ack` cannot be captured at the `t_send` site
  (unlike a synchronous `send_command`). The writer registers a pending
  `(t_send, context)`; the reader matches the next **text** ACK line to the
  oldest pending (`_consume_ack`) — valid because serial is strictly ordered.
  **Numeric** inbound lines stay genuine device events (`_dispatch_event`); this
  firmware only ACKs with text, so the two never collide.
- **Contract additions on `ArduinoManager`:** `enqueue_tracked(token, context)`,
  `set_latency_sink(sink)`, `flush_pending_acks()`. The `_write_queue` now carries
  `(token, context|None)`. `ArduinoEventMapper.update_detailed()` returns
  `RoiTokenEvent(roi, edge, token)` so each token is attributed to its transition.
- **Sink & lifecycle:** `core/services/closed_loop_latency.ClosedLoopLatencyLog`
  is built lazily on the first tracked trigger (needs `recorder.output_folder`)
  in `FrameProcessingMixin._dispatch_arduino_zone_commands`, registered as the
  manager's latency sink, and finalized in `_finalize_closed_loop_log()` at the
  end of `_processing_loop` (after the session-end sweep). Reset per session in
  `_reset_arduino_zone_state`.
- **Output:** `5_ClosedLoop_<base>.csv` (streamed per trigger, crash-resilient)
  and `5_ClosedLoop_<base>.parquet` (session end), alongside
  `3_CoordMovimento_<base>.parquet`. Canonical columns `serial_act_ms`
  (`t_ack-t_send`) and `frame_to_ack_ms` (`t_ack-frame_t0`) keep the exact names
  used by the external `analise_latencia.py`; enrichment adds
  `capture_to_decision_ms`, `decision_to_send_ms`, `sampling_interval_ms` and —
  since § 5.9 — `queue_wait_ms`, `inference_ms`, `dequeue_perf`, and — since
  v6.0.0 — `fps_configured`, `sampling_interval_ms_configured` (appended at the
  end; `CSV_COLUMNS` is append-only and the first columns never move).
- **Queue wait vs inference:** `capture_to_decision_ms` alone is an aggregate
  with no diagnostic value — it mixes the time the frame sat in `frame_queue`
  with the inference itself. `_processing_loop` stamps `dequeue_perf` right
  after `frame_queue.get`, so `queue_wait_ms` (`frame_t0 → dequeue`) and
  `inference_ms` (`dequeue → decision`) split it; their sum is exactly
  `capture_to_decision_ms`, kept for compatibility.
- **Interpretation caveats:** `frame_to_ack_ms` starts at the **analyzed** frame's
  capture (1 in `analysis_interval_frames`, default 10), so the sampling
  quantization (animal crossing during a skipped frame, up to
  `analysis_interval_frames/fps ≈ 333 ms @30 fps`) is a **separate** term logged
  as `sampling_interval_ms`. Any `delay()` in the sketch's `loop()` is added to
  `serial_act_ms` in full — a real actuation delay the method correctly captures.
  See § 5.7 for the firmware rewrite that removed the blocking paths.
- **Measured vs configured `fps` (v6.0.0):** `fps` (and therefore
  `sampling_interval_ms`) is the frame rate **actually achieved**, measured from
  capture timestamps via `FrameLedger.current_fps_measured()` — the same source
  the frame ledger anchor uses for `fps_real_medio` (§ 5.9). It is *not* read
  from settings: a USB camera routinely exceeds its configured rate (41.2/39.1
  fps measured against 30 configured in the sessions that surfaced this), and
  logging the configured value as if it had been achieved silently contradicted
  the frame ledger for the same session. The configured (nominal) value is kept
  separately in `fps_configured` / `sampling_interval_ms_configured`, computed
  in `FrameProcessingMixin._dispatch_arduino_zone_commands` from `_actual_fps`
  (itself the camera driver's reported `CAP_PROP_FPS`, which is a configured
  property, not a measurement). `fps` is blank until the ledger has ≥2
  timestamped frames — effectively never at trigger time, since aquarium
  detection and warmup already consume dozens of frames first.

### 5.7. Per-Zone Command Robustness (August 2026)

Fixes from the audit of the 2026-08-04 live session, where one LED latched on
and the others appeared dead. Root cause was a token mapping error amplified by
two blocking `delay()` calls in the reference sketch.

- **Ambiguous-token detection:** `ArduinoBindingConfig.token_conflicts()` returns
  a `TokenConflict(token, enter_rois, exit_rois)` per integer wired as one ROI's
  `on_enter` **and** another's `on_exit`. Such a mapping cannot be right — a
  single firmware command cannot both set and clear a device state — and it
  breaks `session_end_tokens()`, whose "turn everything off" sweep is built from
  the exit tokens and would then turn a device **on**. The application is a pure
  transport, so it **warns and never rewrites**: `_reset_arduino_zone_state`
  logs `live_camera_service.arduino_zone_commands.token_conflict` at session
  start, and `ArduinoBindingsPanel` shows a red warning under the table
  (`_refresh_conflict_warning`, on load and on every save).
  Canonical 4-zone layout for the reference sketch: `1/2`, `3/4`, `5/6`, `7/8`.
- **ROI exit grace period:** `_dispatch_arduino_zone_commands` used to receive
  empty `detections` on any frame the tracker missed, emptying the occupancy set
  and firing an exit token plus a re-enter on the next hit (device flicker; the
  audited session logged one such pair while the animal never left). Frames with
  zero detections are now absorbed for `arduino.roi_exit_grace_frames`
  (default 2, `0` = legacy) before the occupancy is allowed to go empty; any
  frame **with** detections resets the counter. State lives in
  `_arduino_missed_frames`, reset per session.
- **Reference firmware (`scripts/ard_sketch/Program_Final/Program_Final.ino`):**
  `loop()` is now free of `delay()`. `botaoChoque` was `pinMode(..., INPUT)`
  without a pull-up, so the floating pin read `LOW` on its own and triggered a
  `delay(15000)`; it is now `INPUT_PULLUP` with a `millis()`-timed shock window.
  The flash path's `delay(100)+delay(100)` became a `millis()` toggle. The serial
  drain also skips pending separators before `Serial.parseInt()`, so a leftover
  `"\n"` no longer times out into a phantom `0` → `"Unknown command"` ACK that
  would desynchronize the FIFO command↔ACK correlation of § 5.6.

### 5.8. Binding Verification via Firmware ACK (August 2026)

`token_conflicts()` (§ 5.7) only catches an integer wired as one ROI's `enter`
and another's `exit`. The 2026-08-04 follow-up session used `Z1=1/5, Z2=2/6,
Z3=3/7, Z4=4/8` — a plausible "enters 1-4, exits 5-8" layout with **zero**
conflicts by that definition, but inverted against a sketch that pairs ON/OFF
consecutively. `Z4 enter` answered `"Blue LED OFF"` and no stimulus ever fired.

The fix uses evidence rather than assumption: the firmware's ACK line already
says what the device did, and it is already captured for the closed-loop log.

- **`core/services/arduino_ack_semantics.py`** (pure): `classify_ack(text)` →
  `"on"` / `"off"` / `None`, word-anchored so `ON` does not match inside
  `COMMAND` and `LIGADO` does not match inside `DESLIGADO`. Ambiguous or opaque
  text returns `None`, so a sketch with unreadable ACKs is never flagged.
  `edge_ack_is_inverted(edge, ack)` is True only for enter→off or exit→on.
- **Pre-flight (`ArduinoManager.probe_tokens`)**: sends each token and returns
  `(token, ack_text)` in order. It temporarily owns the latency sink, so it
  raises if a live session already registered one. Blocking — the bindings panel
  calls it from a worker thread and marshals results back via `root.after(0,…)`.
  `ArduinoBindingsPanel.test_bindings()` renders `✓`/`⚠` per binding.
- **Runtime**: `FrameProcessingMixin._on_arduino_latency_sample` is now itself
  the latency sink; it writes the closed-loop row and then warns
  `live_camera_service.arduino_zone_commands.ack_inverted`, deduplicated per
  `(roi, edge)` since a ROI is crossed many times per session.

- **Operator label (`ArduinoBinding.label`)**: the ACK text names the channel
  from the sketch's own point of view (`"Red LED 1 ON"`), which is simply wrong
  whenever that pin drives a shock relay, a pump, or any other module. Only the
  operator knows what is wired, so each binding carries an optional free-text
  label (`"Choque"`, `"Bomba"`), edited in the panel's "Dispositivo" column and
  persisted alongside the tokens. Purely cosmetic — never sent to the device,
  and blank input normalizes to `None`. Probe result lines read
  `Z1 (Choque) entrar → 1 → Red LED 1 ON`, naming both the reality and the
  firmware's own claim. Bindings saved before this field load with `label=None`.

Canonical layout for the reference sketch stays `1/2, 3/4, 5/6, 7/8`. Verified
live on 2026-08-04: 6 clean enter/exit pairs, every enter ACK `ON`, every exit
ACK `OFF`, `serial_act_ms` 17-21 ms (was 3 000-12 700 ms before § 5.7's firmware
rewrite).

### 5.9. Frame Ledger & Timeline Reconstruction (August 2026)

A live session keeps **three independent numberings** and, before this section,
none of them was correlated on disk: `frame_count` (capture thread, 1-based,
only incremented on a *successful* capture — it is the number written to the
`frame` column of `3_CoordMovimento`), `_video_frames_written` (video thread,
the real MP4 index), and the clock. A single lost frame shifted every later
mapping with no trace. `core/recording/frame_ledger.FrameLedger` persists the
map as a sidecar — the `3_CoordMovimento` schema stays **immutable**.

- **Output:** `6_FrameLedger_<base>.csv` (streamed, crash-resilient),
  `6_FrameLedger_<base>.parquet` (session end) and
  `6_FrameLedger_<base>_anchor.json`. Columns: `pipeline_frame`,
  `video_frame_index` (`-1` when the frame is not in the MP4), `t_capture_perf`,
  `t_capture_wall`, `outcome`, `is_analysis_frame`, `queued_for_analysis`.
- **One row per captured frame, two producers, one lock** (same pattern as
  `ClosedLoopLatencyLog`). The CAPTURE thread writes `dropped_queue_full` (it is
  the only thread that knows — the frame never reaches the video thread) and
  `not_recording`; the VIDEO thread writes `written` / `write_failed` with the
  **real** index taken from the write counter. The index comes from the
  *consumer* precisely to eliminate the `index = frame_count − drops` inference,
  which is where the offset is born.
- **Three distinct loss modes, all now recorded:** `queue.Full` on
  `video_queue` (capture thread), `OSError` in `write_video_frame` (video
  thread — the frame was dequeued but `_video_frames_written` does **not**
  advance), and a failed `camera.get_frame()` (never counted at all, so it
  cannot desynchronize anything).
- **Queue item shape:** `video_queue` now carries
  `(frame_count, capture_perf, capture_wall, is_analysis_frame,
  queued_for_analysis, frame)`. `_unpack_video_item` tolerates the legacy bare
  frame (no ledger row is produced for it). `frame_queue` is unchanged:
  `(frame_count, frame, capture_perf)`.
- **Opportunistic queueing is preserved:** `3_CoordMovimento` does **not**
  contain only multiples of `analysis_interval_frames` — frames off-cadence are
  still enqueued when `frame_queue` has room, so the spacing is opportunistic
  and not reproducible between runs. Nothing is dropped to "fix" it; instead
  every row carries `is_analysis_frame`, so analysis can filter and recover the
  deterministic cadence when it needs to.
- **Lifecycle:** created in `_start_threads` (`_reset_frame_ledger`, buffering
  in memory because recording may only start after the aquarium-detection
  phase), bound to the recorder folder by `_maybe_bind_frame_ledger`, finalized
  in `stop_session` **after** the producer threads are joined
  (`_finalize_frame_ledger`). Independent of the Arduino path: a session with
  no bindings and no ACK still gets a full ledger.
- **Hot path:** `FrameLedger.record()` only appends to memory; the CSV flush
  runs on a dedicated daemon thread (`FrameLedgerWriterThread`).

**Session anchor (mandatory, not optional).** `perf_counter()` is monotonic and
**has no epoch**: without the `t0_perf`/`t0_wall` pair there is no way to cross
the ledger with the trajectory parquet (wall clock) or with `5_ClosedLoop_*`.
The anchor JSON carries `t0_perf`, `t0_wall`, `recorder_start_time`,
`fps_nominal`, `fps_real_medio`, `analysis_interval_frames`,
`first_captured_index`, `first_video_index`.

**Reconstruction formula** (helpers: `load_ledger`, `load_anchor`,
`index_by_pipeline_frame`, `perf_to_wall` in `frame_ledger.py`):

```text
3_CoordMovimento.frame  ==  6_FrameLedger.pipeline_frame
    -> t_capture_perf                                  (monotonic capture)
    -> t0_wall + (t_capture_perf - t0_perf)            (wall clock)
    -> video_frame_index                               (real MP4 index, -1 = absent)
```

**`3_CoordMovimento.timestamp` is a PROCESSING clock**, computed in the
processing thread *after* the queue wait and the inference
(`time.time() - recorder.start_time`). Use it to order, never to date an event
or to measure latency — the capture instant lives in the ledger.

**Honest caveats (this will end up in a publication):**

- `frame_t0`/`t_capture_perf` is stamped in the **capture** thread, right after
  `camera.get_frame()` and before any `put` — verified. So queue wait is
  attributed to `queue_wait_ms` and never smuggled into inference time.
- But `perf_counter()` after `camera.get_frame()` measures when the frame became
  available **to Python**, not when the sensor exposed it. Driver/UVC buffering
  (typically 1–3 frames) is invisible and enters `frame_to_ack_ms` in full as if
  it were pipeline latency. It is not correctable in software without reference
  hardware — declare the limit, do not omit it.
- `cv2.VideoWriter.write()` returns `None` and does not report encoder failure.
  An `outcome='written'` row means "Python handed the frame to the writer
  without raising", not "the encoder confirmed the frame".
- The MP4 FPS is **nominal** (`recorder._fps` fixed at `VideoWriter` open) while
  real capture is `sleep(1/(fps*1.5))` + camera latency, and the pipeline still
  adjusts FPS dynamically. Use `fps_real_medio` from the anchor (or the
  per-frame timestamps) for any time axis, never the MP4 frame rate.
- Full-rate analysis is a **configuration** question, not a code one:
  `analysis_interval_frames = 1`. Measure `_dropped_frames_processing` before
  recommending it — detecting at 30 fps can saturate and degrade the very
  measurement.

### 5.10. Canonical ROI Inclusion Rule (August 2026)

"Is the animal inside this ROI?" is decided in four places, and they used to
disagree. `core/services/roi_rule_resolver.py` is now the single source:

```python
resolve_roi_rule(project_data, settings_obj) -> RoiRuleConfig  # frozen
```

Precedence is `project_data["roi_settings"]` > `settings_obj` > default. The
function is pure (no I/O, no singleton) and never raises: an unknown rule, an
unparseable string, a non-finite float (NaN **and** ±inf — `inf` would otherwise
sail past the range check on `roi_buffer_radius_value`, which has no maximum) or
an out-of-range value falls back to the previous precedence level and logs
`roi_rule.resolve.invalid_value`. The **rule is resolved first**, because it
decides the bounds: the exclusive minimum applies only to the parameter that
rule actually uses, mirroring `Settings`' cross-field validator. A zero buffer
under `bbox_intersects` is irrelevant and legitimate (shipped configs look like
that) and is preserved without noise; a zero buffer under
`centroid_in_on_buffered_roi` dilates nothing and falls back with a log.
Recognized keys are exactly
`roi_inclusion_rule`, `roi_buffer_radius_value`, `roi_min_bbox_overlap_ratio`,
`roi_bbox_overlap_basis` — the same ones the settings editor writes.

#### 5.10.1. Overlap semantics (August 2026)

The **single source** of every ROI default is the Pydantic field in
`settings.py`. The shipped `config.yaml` no longer re-declares
`roi_min_bbox_overlap_ratio` (it used to say `0.05` while the model said `0.10`,
so the Zones tab displayed one number and the analysis used another); the key is
present only as a commented-out line documenting the default. UI StringVars are
seeded from the resolved rule, never from literals.

`roi_min_bbox_overlap_ratio` is the fraction of a **reference area** that must
lie inside the ROI, and `roi_bbox_overlap_basis` picks that reference:

| Basis | Ratio | Notes |
| ----- | ----- | ----- |
| `bbox` (default) | `inter / bbox_area` | Historical. A bbox 4× the ROI area covering **100%** of the ROI still scores 0.25 — wrong regime for small stimulus/reward zones. |
| `roi` | `inter / roi_area` | Coverage of the zone. |
| `max` | `max(both)` | Recommended for ROIs of arbitrary size. |

`bbox` is the default, so nothing changes for anyone who does not configure it —
`tests/analysis/test_roi_analyzer.py::TestBboxOverlapBasis` pins the historical
numbers.

`roi_min_bbox_overlap_ratio = 0.0` is legal **only** for `bbox_intersects`,
where it means the predicate the rule name has always promised: any overlap of
non-zero area counts, with no minimum fraction. It is evaluated with the DE-9IM
pattern `T********` ("interiors intersect"), **not** `shapely.intersects` —
`intersects` returns True for tangency (boundary-only contact), which is not
overlap — and not an `area > 0` comparison, which is noisy near tangency.
`seg_overlap` still requires `> 0`: it has no pure-predicate path implemented
(`roi.py` raises for it), so accepting 0 there would promise a semantics nothing
executes. Both `Settings._validate_advanced_constraints` and
`ValidationManager.apply_roi_settings` enforce exactly this split.

The flag that selects the topological path is
`RoiRuleConfig.overlap_any == (rule is bbox_intersects and ratio == 0.0)` —
deliberately *not* `ratio <= 0`. A **negative** threshold is invalid and
dangerous in both directions: routed into the topological path it masks bad
input, and left on the ratio path `ratio >= negative` matches boxes that do not
even touch the ROI. `RoiRuleConfig.__post_init__` therefore normalizes **every**
construction path (not just `resolve_roi_rule`), replacing out-of-range values
with the canonical default and logging `roi_rule.config.sanitized`; it never
raises, because this runs in the live loop. `ROIAnalyzer` takes raw floats, so it
routes them through the same config — but keeps `inclusion_rule` **raw**, so an
unknown rule still raises in the dispatcher instead of silently becoming the
default.

The four consumers:

| Path | Consumer | Was |
| ---- | -------- | --- |
| Pre-recorded report | `VideoSelectionMixin._create_project_settings_snapshot` | honored the project |
| Report regeneration | `ReportGenerationCoordinator._create_project_settings_snapshot` | duplicated snapshot, ROI keys never copied → regenerating changed the numbers |
| Live post-processing | `LiveAnalysisPostProcessorMixin._build_post_analysis_service` | raw global `Settings` |
| Live Arduino trigger | `FrameProcessingMixin._build_arduino_evaluator` | rule hardcoded to centroid-in-polygon |

- **`AnalysisService(settings_obj=…, roi_rule=…)`**: the optional `roi_rule`
  wins; without it the rule is resolved from the service's own `Settings` — so
  callers that already inject a project snapshot keep working unchanged.
- **`ArduinoRoiEvaluator`** now takes the `RoiRuleConfig` and evaluates with
  **shapely**, the same predicates as `ROIAnalyzer` (`contains` for the centroid
  rules, intersection-area ratio for `bbox_intersects`) instead of
  `cv2.pointPolygonTest`. Buffered ROIs are dilated **once** in the constructor;
  `px_per_cm` must be `sqrt(pixelcm_x*pixelcm_y)` to match the analyzer's radius
  conversion. `_dispatch_arduino_zone_commands` now forwards raw bboxes — it
  used to reduce them to centroids, which makes `bbox_intersects` impossible.
  `seg_overlap` (unimplemented, `roi.py` raises) degrades to `centroid_in` with
  `arduino_roi_evaluator.seg_overlap_unsupported_fallback` rather than killing
  the live loop.
- **Applying to `Settings`**: `apply_roi_rule_to_settings` writes the rule and
  its two numeric parameters in an order that never passes through a state the
  cross-field validator rejects (`validate_assignment=True`). `RoiRuleConfig` is
  normalized on construction (`buffer > 0` where required, ratio in range for
  the target rule) precisely so that ordering exists — do not hand-assign these
  fields. `roi_bbox_overlap_basis` is outside that dance (no cross-field
  invariant) and is written first, always.
- **UI**: the Zones tab "Aplicar" button emits `ZONE_APPLY_ROI_SETTINGS`
  (`RoiSettingsApplyPayload`) → `EventDispatcher._on_persist_roi_settings`,
  which writes `project_data["roi_settings"]` + `save_project()` guarded by
  `project_path`. It used to emit `DETECTOR_UPDATE_PARAMETERS`, whose handler
  drops `rule`/`buffer_radius`/`overlap_ratio` (they are in no valid-parameter
  list), returned `True` and logged success — a silent no-op. With no project
  open the rule is applied to the session `Settings` instead.
  The payload carries the **raw** `StringVar` text (`float | str | None`): a
  `float()` inside a Tk callback raises on bad input and kills the click, so
  parsing happens once, in the resolver, which logs whatever it discards. Blank
  fields are dropped as "not informed" before resolving, and the confirmation
  dialog shows the **effective** parameter — that is what makes a discarded
  value visible to the operator.

Note: the two settings snapshots still differ outside ROI —
`VideoSelectionMixin` also applies offset/smoothing/behavioral overrides that
`ReportGenerationCoordinator` does not, and vice-versa for the interval keys.

#### 5.10.2. Presence debounce, duration filters and gap capping (August 2026)

`RoiRuleConfig` no longer carries only the geometric rule. It also decides
**when** a raw presence reading becomes a visit, because the report and the
Arduino trigger must share those parameters for the same reason they share the
rule. Five keys, same precedence, same `roi_settings` dict:

| Key | Default | Meaning |
| --- | ------- | ------- |
| `roi_flutter_enter_frames` | 2 | consecutive frames inside to confirm an entry |
| `roi_flutter_exit_frames` | 3 | consecutive frames outside to confirm an exit |
| `roi_min_visit_s` | 0.2 | visits shorter than this are discarded |
| `roi_min_gap_s` | 0.0 (off) | gaps shorter than this merge adjacent visits |
| `roi_max_gap_s` | `null` (auto) | cap on the `dt` credited to an ROI |

**Order of operations, and it is not commutative:**

```text
raw presence -> debounce (backdated) -> duration filters -> stable series -> metrics
```

Running the duration filter *before* the debounce measures events the debounce
is about to remove or move, and produces different — wrong — numbers.

**Backdating is what made the filter usable.** The old `_apply_flutter_filter`
used `rolling(N, min_periods=1)`, a *trailing* window: a transition was both
confirmed **and recorded** `N-1` frames after it happened, biasing
`latencia_primeira_entrada` and `tempo_gasto_por_roi` in proportion to N. That
is why production hardcoded `flutter_n_frames=1` — the only way to remove the
bias was to remove the filter. The rewrite detects runs and backdates the
confirmed transition to the **first frame of the run**, so N can be raised
without any timestamp cost. `min_periods=1` is gone too: the state starts
outside and only a full run moves it, instead of frame 0 setting the state with
no confirmation at all.

The windows are **asymmetric** (enter 2 / exit 3) for the same behavioural
reason `arduino.roi_exit_grace_frames` exists: a one-frame dropout mid-visit is
not an exit, but an entry should not need much evidence.

**Durations are in seconds, not frames.** A frame count is not invariant —
changing `analysis_interval_frames` from 10 to 5 doubles the series rate and
silently changes what an N-frame filter does. A duration does not move.

**Gap capping fixes the largest of the four defects.** The trajectory DataFrame
only has rows where a detection happened, so the `dt` of the first row after a
tracking gap is the **whole gap**, and it used to be credited in full to
whichever ROI the animal reappeared in — losing the animal for 5 s added 5 s of
"time spent" to that ROI. `roi_max_gap_s` caps it; the discarded excess is
summed into `ROIAnalyzer.unobserved_time_s` and published as
`report["analise_roi"]["tempo_nao_observado_s"]`, so the researcher can see how
much of the session the per-ROI numbers do not cover. `null` means automatic
(`3 ×` the median observed interval); `.inf` disables the cap and restores the
historical attribution.

A visit's duration is the time **credited to the visit's own frames** — the
same sum `get_time_spent_in_rois` reports — read off an *exclusive* prefix-sum
clock (`_clock_s`, length `n+1`). So `roi_min_visit_s` means literally
"discard visits that would be credited less than N seconds". Measuring the
span to the first frame *outside* instead (`t[end] - t[start]`) embeds that
frame's `dt`, and when it is the reappearance after a gap the gap inflates the
**preceding** visit — the exact defect the cap exists to prevent. (Caught in
review of #455; regression pinned by
`test_roi_time_attribution.py::TestGapDoesNotInflateThePrecedingVisit`.)

`roi_max_gap_s` is the one key where `None` is a **value** ("automatic"), not
an absence, so the resolver distinguishes the two with a `_MISSING` sentinel
rather than plain `.get(key)`. Without it a project could never override a
numeric global back to automatic — and since `to_roi_settings()` always writes
the key, persisting an automatic project against a numeric global would
silently resurrect the global's number on the next resolve.

**Neutral mode is bit-identical.** `flutter_enter_frames=1`,
`flutter_exit_frames=1`, `min_visit_s=0.0`, `min_gap_s=0.0`,
`max_gap_s=math.inf` reproduces the old output exactly — the `dt` column is not
even rewritten unless the cap actually binds, so no `Timedelta → seconds →
Timedelta` rounding creeps in. `tests/analysis/test_roi_flutter.py::
TestNeutralModeIsBitIdentical` pins it; that test is what makes the change
opt-in rather than a silent renumbering.

Gotchas:

- `flutter_n_frames` stays accepted as the **legacy** symmetric input and maps
  to both windows; an explicit window always wins.
- `analyze_center_vs_periphery` now builds its temporary analyzer with
  **keyword** arguments. It used to pass the debounce as the third positional,
  so inserting any parameter before it would have swapped the argument silently.
- `ArduinoRoiEvaluator` deliberately does **not** apply these filters: it is a
  per-frame geometry evaluator, and the live loop has no time series. Parity
  tests between the two must neutralize the temporal layer
  (`tests/core/test_arduino_roi_evaluator.py`).
- The five keys are **not** editable from the UI yet — they live in
  `config.yaml` / `config.local.yaml` / `project_data["roi_settings"]`, like
  `arduino.roi_exit_grace_frames`.

### 5.10.3 Multi-animal ROI semantics (per-animal + `any_track`)

**The defect.** With more than one animal in the same trajectory, the pipeline
measured an animal that does not exist. `BehavioralAnalyzer._preprocess_data`
consolidated duplicate timestamps with `groupby(df.index).agg({... "mean"})`.
That aggregation exists for duplicates the *tracker* emits for the **same**
animal, but the key also caught **different** animals seen at the same instant:
two fish became a ghost centroid at their midpoint, labelled with one of their
`track_id`s. Downstream, `ROIAnalyzer` compounded it — presence, entries and
exits all ran `.diff()` over interleaved rows, so a transition could be one
animal followed by another. The common single-fish-per-aquarium setup has one
track, which is why it went unnoticed.

Multi-aquarium is a **different axis** and does not solve this:
`global_id = aquarium_id * 1000 + local_id` separates animals *between* tanks,
each analysed on its own. Two animals in the *same* tank still collapsed.

**The fix, in two layers.**

1. `_preprocess_data` groups by `(timestamp, track_id)` when the column exists.
   Same-track duplicates are still averaged (original intent); distinct animals
   are never merged. Without a `track_id` column there is no way to tell
   subjects apart, so the historical per-timestamp average remains.
2. Everything order-dependent became track-aware. `BehavioralAnalyzer` carries a
   positional `track_labels` array (positional, because with several animals the
   index has repeated timestamps and any label-based grouping mixes subjects)
   and exposes `diff_by_track()`. Savitzky-Golay smoothing, distance, velocity,
   angular velocity, tortuosity and freezing/inactivity episode blocking all run
   per subject. In `ROIAnalyzer`, `dt`, the observed clock, the debounce and the
   duration filter are all per animal.

**Two published semantics.** See `DOMAIN_GLOSSARY.md` for the full contract:

- `report["analise_roi"]["por_animal"][track_id]` — the primary calculation.
- The top-level keys — `any_track` occupancy (the ROI is occupied while *any*
  animal is inside), which is the aggregation of the above **and** the reading
  `ArduinoEventMapper` already uses live, so report and hardware agree again.
- `semantica` and `n_animais` record which is which; a multi-animal trajectory
  also appends a validation warning (`unique_tracks` was already computed by
  `trajectory_validator` and printed as a neutral statistic — it is now a
  warning).

Gotchas:

- **Single track is bit-identical.** `ROIAnalyzer._view` *is* `_trajectory` when
  there is one subject, so the group metrics run the identical code path.
  `tests/analysis/test_multi_track_roi.py::TestSingleTrackRegression` pins it.
- **The track axis is validated, not presumed.** `_resolve_track_axis` accepts
  it only when `is_multi_track is True` *and* the labels are an `ndarray` of the
  trajectory's length. A `MagicMock` analyzer returns a truthy object for every
  attribute, and trusting it would enter the multi-animal path with a
  wrong-sized grouper.
- **Group `dt` is not the sum of per-animal `dt`.** Per-row `dt` is that
  animal's interval; summing it over N fish gives N × the session. The group
  numbers come from `_build_group_view()`, one row per instant.
- **There is one observed clock per animal (`_track_clocks`), not one sliced
  array.** Each is the exclusive prefix sum of § 5.10.2, with its own zero and
  one position more than the frames it describes — so a slice of a global clock
  would be both off by an origin and the wrong length. With a single subject the
  list is `[_clock_s]` and the code path is unchanged.
- **`distancia_por_roi` at group level *is* a sum** across animals — there is no
  path of a group. Tortuosity is the **mean** of individual tortuosities.
- **`calculate_sharp_turns` is still pooled.** Its cooldown loop walks turn
  timestamps globally, so turns by different animals within the cooldown
  collapse into one — it under-counts. Flagged in the validation warning;
  fixing it is separate scope.
- **`analyze_center_vs_periphery` now propagates `inclusion_rule`** (and the
  overlap parameters) to its temporary analyzer. It never did: Center/Periphery
  always ran with the default `bbox_intersects`, even in a project configured
  for `centroid_in` — two numbers in one report answering different criteria.

### 5.10.4 `seg_overlap`: mask sidecar and declared degradation (August 2026)

`seg_overlap` was selectable in the UI, the wizard and `config.yaml` since the
rule set existed, and it **always failed** — `_calculate_seg_overlap` raised
unconditionally. The chain was cut in four places at once: the model default is
`det` (no masks exist), the tracking path disabled mask decoding for
performance, the immutable `3_CoordMovimento` schema has nowhere to put a mask,
and the consumer raised.

**The sidecar.** Masks live in `3b_Mascaras_<base>.parquet`, next to the
trajectory, with schema `frame:int64, track_id:int64, mask_wkb:binary` — the
contour serialised as WKB (~200–400 B per detection). It is a *separate file* by
contract: `3_CoordMovimento`'s column order is immutable (CLAUDE.md), and the
join at consumption time is `(frame, track_id)`, the same shape of relationship
`6_FrameLedger` has with `frame` (§ 5.9). It is written by the **same flush
thread** as the main Parquet, right after it, so a second non-thread-safe writer
never sees concurrent calls and the recording loop never blocks on disk.

**Three conditions gate the capture**, and they live in exactly one place —
`core/services/mask_capture.should_capture_masks()`:

1. `recorder.persist_masks` (default `False`) — the operator asked.
2. `model_selection.animal_method == "seg"` — a model capable of masks exists.
3. The effective ROI rule (project overrides global) is `seg_overlap` — someone
   will read the result.

None of the three alone is enough. With the flag off, **nothing is decoded and
no file is created** — that is the zero-cost promise, pinned by
`tests/core/detection/test_mask_capture.py`.

**Coordinates.** Masks come out of the plugin in ORIGINAL frame pixels, and the
plugin only ever saw the *cropped* frame — so `SingleDetector` applies the same
crop offset that `offset_detections` applies to boxes, and `Recorder` applies
`calibration.transform_points` exactly as `write_detection_data` applies
`transform_bbox`. Skipping either step would intersect mask and ROI in different
coordinate spaces: a number would come out, and it would be wrong.

**How a mask keeps its identity.** Masks are indexed by the detection's bbox,
not by list position: crop offset, polygon filter, class-mismatch correction and
ByteTrack all preserve the detection's coordinates (the tracker re-emits the
ORIGINAL bbox, not the Kalman one), while a parallel list would desynchronise at
the first filter. `SingleDetector.pop_track_masks(detections)` then re-keys by
`track_id` and consumes the index — masks are valid for ONE frame, and handing
them out twice would file a stale contour under another frame's `track_id`.

**Degradation is declared, never an exception.** No sidecar (old data, `det`
model, flag off), unreadable file, wrong columns, or zero rows matching
`(frame, track_id)` → the rule falls back to `bbox_intersects`, logs
`roi.seg_overlap.fallback` with the reason, and records it in
`ROIAnalyzer.degradation_warnings`. `AnalysisService` merges that into
`validation_warnings` **before** `_generate_reports_for_video` — the same
constraint as § 5.10.3's multi-track warning, since `validation_warnings` and
`report["validacao"]["avisos"]` are the same object. The fallback output is
**bit-identical** to running `bbox_intersects` outright, not merely similar.

**The threshold is its own field.** `roi_min_seg_overlap_ratio` (default `0.3`),
never `roi_min_bbox_overlap_ratio` (`0.10`). The denominators differ — the mask
*is* the animal, while a bbox drags the empty corners along — so the two
fractions are not comparable and neither can default to the other. A row with no
mask counts as OUTSIDE rather than silently falling back to its bbox: mixing the
two rules row by row would produce a series matching no criterion at all.

**Not covered:** multi-aquarium recording (detections pass through a partitioner
that re-emits tuples, so the bbox index does not survive) and batch inference
(`detect_batch` clears the one-frame mask buffer rather than risk misattributing
it). Both degrade with the warning above.

### 5.11. External Trigger Reaches the Progress Grid (August 2026)

Two code paths start a live recording, and only one of them used to honour
`external_trigger_mode`:

| Path | Entry point | Folder layout |
| ---- | ----------- | ------------- |
| Legacy | Control-panel "Iniciar Gravação" → `RecordingSessionCoordinator.start_recording` | `D{day}_G{group}_S{subject}/` at project root |
| Current | Progress-grid subject → `BlockDetailDialog.start_session` → `LiveCameraSessionCoordinator.start_live_project_session` | `Grupo_X/Dia_Y/Sujeito_Z/live_{ts}/` |

Ticking "Modo de Gatilho Externo" in the wizard and then recording from the grid
did nothing: the session started immediately, ignoring the Arduino. The rule now
lives in `core/services/external_trigger_gate.py` and both paths consult it:

```python
decide_external_trigger(project_data, arduino_manager=None) -> ExternalTriggerDecision
# PROCEED | ARM_AND_WAIT | REJECT_NO_ARDUINO | REJECT_ARDUINO_OFFLINE
```

The function is pure (no I/O, no events) — each coordinator translates the
decision into its own pending state and UI events. `use_arduino` is the source of
truth for *intent*; a saved `arduino_port` with `use_arduino` false means the
user disabled the hardware, not that hardware exists.

Both rejections **refuse the session** rather than recording blind. The protocol
was designed around synchronisation with an external event; a recording started
at the wrong instant is useless data that only surfaces at analysis time.

The two rejections are distinct because the user's next action differs:

| Decision | Condition | User must |
| -------- | --------- | --------- |
| `REJECT_NO_ARDUINO` | trigger on, `use_arduino` off | configure the Arduino, or turn the trigger off |
| `REJECT_ARDUINO_OFFLINE` | trigger on, `use_arduino` on, port **not open** | check the cable / free the port, reopen the project |

The offline check matters because `initialize_live_components` warns "executando
em modo offline" when `connect` fails and then **opens the project anyway** with
`use_arduino=True`. Checking intent alone would arm a session that waits forever
for a signal with no way to arrive — the worst outcome, because it looks like it
is working. Pass `arduino_manager` to enable the check; without it the gate
degrades to the config-only decision, and a probe that raises never blocks a
recording.

Gate order in `start_live_project_session` is **zones first, trigger second**. The
polygon is operator work and must be finished before we sit waiting for a signal,
otherwise the Arduino can fire into a session with no arena. The two use separate
slots (`_pending_live_context` for zones, `_pending_trigger_context` for the
trigger) because a session can legitimately need both.

`MainViewModel.on_arduino_event` routes to whichever coordinator actually has an
armed session (probed on the reader thread, before the `root.after(0, ...)`
marshalling), falling back to the legacy coordinator so unexpected start codes
still get logged.

**Consequence for callers:** `start_live_project_session` returns `False` for
three different reasons — genuine failure, awaiting zone confirmation, and armed
awaiting the trigger. Anything that shows an error on `False` must probe
`live_calibration_coordinator.pending_zone_confirmation` **and**
`has_pending_external_trigger()` first, or it will lie to the user.

### 5.12. Per-Subject Recording Duration (August 2026)

The wizard sets one duration for the whole project. Real protocols need
exceptions — a shorter habituation day, an animal that needed longer — and the
only previous escape was recreating the project.

`core/services/session_duration_resolver.py` is the single source:

```python
resolve_session_duration(project_data, day, group, subject) -> float  # seconds
```

Precedence: subject override > block (day × group) default >
`project_data["recording_duration_s"]` > 300 s. Overrides live in
`project_data["session_duration_overrides"]` keyed by `duration_override_key()`,
which normalises the three day formats the codebase carries (`1`, `"1"`,
`"Dia_1"`) — never hand-build the key string.

Values are edited in `BlockDetailDialog` (block default beside the camera row;
per-subject button on each pending row), stored in seconds, and shown in minutes.
Setting a subject back to the block default **removes** the override rather than
storing a duplicate, so the UI never claims "própria" for an inherited value.
A corrupt override degrades to the next precedence level with a log — a zero
duration would lose the recording as silently as an exception would.

**Report impact.** Nothing breaks: `duracao_video_s` was already recorded per
session and exported as `video_duration_s`, and no reporter divides by duration
(`sharp_turns_per_minute` is the only time-normalised metric). But the partial
and batch reports aggregate with `groupby("animal").mean()`, and **absolute**
metrics — total distance, entry counts, time in ROI — scale with recording
length. Mixed durations inside a block make those means non-comparable. The app
therefore (a) forces `video_duration_s` into the aggregated columns, (b) asks for
confirmation before generating a report over a heterogeneous block, and (c)
stamps the caveat inside the `.docx`. It deliberately does **not** normalise
automatically: changing the semantics of existing metrics would break
comparability with already-published data, and that call belongs to the
researcher.

### 5.13. Error Boundaries: One Hierarchy, Two Kinds of Failure (August 2026)

**The problem.** Clicking "Apply" in the detector settings panel with an
out-of-range value produced nothing: no dialog, no status line. The panel caught
**pydantic's** `ValidationError`; `DetectorSetupCoordinator` raised
`DetectorSetupCoordinatorError`, at the time a bare `Exception` subclass. Two
unrelated types, so the `except` never matched — and nothing else caught it
either. A census of `coordinators/` found **31 raise sites and zero handlers in
`src/`**. Every one of them escaped into Tk's default
`report_callback_exception`, which writes a traceback to a stderr the packaged
app does not have.

**One hierarchy.** `CoordinatorError` now derives from `ZebTrackError`, and
`DetectorSetupCoordinatorError` from `CoordinatorError` (it was the one
coordinator error still deriving straight from `Exception`). `except
ZebTrackError` at a UI boundary therefore catches any application failure,
coordinator failures included.

**One `ValidationError`.** `zebtrack/exceptions.py` used to *redefine* the whole
hierarchy that `zebtrack/core/exceptions.py` already declared — including a
second `ValidationError` class. Two same-named classes mean `except` on one
silently misses the other, which is the very bug above in miniature.
`zebtrack.exceptions` is now a re-export shim; `zebtrack.core.exceptions` is
canonical.

**Two kinds of failure, two types.** This is the part to preserve when adding
boundaries elsewhere:

| Failure                                  | Type                             | Message is for | UI shows                                       |
| ---------------------------------------- | -------------------------------- | -------------- | ---------------------------------------------- |
| The user typed a value out of range      | `ValidationError` (`UIError`)    | the researcher | `str(exc)` verbatim — and so it is wrapped in `_()` |
| A service raised, a plugin failed to load | `DetectorSetupCoordinatorError`  | the log        | a generic message; the detail goes to structlog |

Collapsing them into one type is what made the panel unable to answer either.
Because `ValidationError` text is now rendered verbatim, it counts as interface
text and needs `_()` plus a pt_BR pair — the technical tail
(`conf_threshold must be between 0.0 and 1.0`) deliberately stays English: it
names the key as it appears in `config.yaml`.

**Three call sites, three boundaries.** `hardware_vm.update_detector_parameters`
is reached from `ui/components/model_diagnostics_panel.py`,
`ui/components/event_dispatcher.py` (the `DETECTOR_UPDATE_PARAMETERS`
subscriber, which answers with `UI_SHOW_ERROR`) and `ui/gui.py`. All three carry
the same two-clause boundary.

**The net.** `ui/tk_exception_handler.install_tk_exception_handler()` replaces
Tk's `report_callback_exception` with one that logs `ui.callback.unhandled`
through structlog and shows a dialog. It is installed in `app_runner.run_app()`
immediately after the root window is created, before anything is drawn. Treat
any `ui.callback.unhandled` entry as a bug report against a call site: the net
cannot know what the user was doing, so it cannot say anything more useful than
"this failed".

**A handler that cannot fire is worse than no handler.**
`UIStateController.update_detector_parameters` wrapped the coordinator in
`except ValueError` → `UI_SHOW_ERROR`. Nothing in `src/` called it, and the
coordinator consumed the `ValueError` before it could propagate, so it was
unreachable twice over — while making the flow look covered in a grep. It was
deleted rather than repaired. `project_model_configuration_panel` had a milder
version of the same (catching pydantic in a chain that validates no pydantic
model) and now catches `ZebTrackError`.

**Out of scope, still open:** `track_buffer` has three disagreeing bounds —
`settings.py` (`ge=10, le=1000`), `DetectorSetupCoordinator` (`>= 0`) and
`DetectorService` (`>= 1`). Picking one is a domain decision; the bounds were
left untouched.

### 5.14. Ad-hoc Live Session: Scale, Stop Intent and Output (August 2026)

The "Analyze Live Camera" button on the main window starts a live session with
**no project behind it** (`LiveAnalysisDialog` → `start_session_from_config`).
That flow shares almost every component with the live-project flow, and the
places where it silently diverged were where the data was lost.

**1. The scale (px→cm).** `_resolve_post_analysis_scale()` is the single
resolver, in this order:

1. `project_data["calibration"]["pixelcm_*"]` — a live PROJECT is calibrated by
   the wizard and that value is authoritative.
2. `aquarium_width_cm` / `aquarium_height_cm` from `analysis_config`, against
   the confirmed arena polygon, via
   `core/services/live_calibration_scale.resolve_live_pixel_per_cm()`. This is
   the AD-HOC path — only the dialog knows the real size.
3. `1.0`, plus a **validation warning appended before**
   `ReporterContext.from_analysis`, so the `.docx` states that the "cm" are
   pixels.

Only the ad-hoc call site puts the cm keys into `analysis_config`; adding them
on the project paths would make `_define_arena_from_detections` overwrite the
wizard's calibration. Never use `Calibration.pixel_per_cm_ratio` here: it is
computed in the rectified 600 px image and is only comparable when the frames
were warped by its homography.

**2. Stopping ≠ discarding.** `stop_session` takes an explicit intent:

| Call | Meaning | On disk |
| ---- | ------- | ------- |
| `stop_session()` | unknown (timer, automatic stop) | 50 % heuristic decides |
| `stop_session(cancelled=True)` | user pressed "Cancel" | folder deleted |
| `stop_session(keep_data=True)` | "Finish and Save", external trigger stop | preserved + post-analysis |

`keep_data` beats `cancelled`: under contradictory instructions, preserving is
the only reversible error. `LiveCameraSessionCoordinator.stop_live_session()`
keeps `discard=True` as its default (the Cancel button), and
`finish_session_early()` routes the keep path through the SAME
`_on_session_complete` the timer uses. The Arduino "stop" code (`0`) now calls
`discard=False` — a firmware stop is end-of-protocol, not a cancellation.

**3. The Analysis tab owns the live controls.** `UIEvents.LIVE_SESSION_FINISH_REQUESTED`
(payload `EmptyPayload`) is published by `AnalysisDisplayWidget`'s "⏹ Finish and
Save" and handled by `AnalysisWidgetsBuilder.handle_live_finish_requested`.
`ANALYSIS_CANCEL_REQUESTED` now asks for confirmation **only** when a live
session is active. `_set_live_analysis_ui_state(live_controls=...)` shows the
pair on confirmed start and removes it on finalize. Before this, an ad-hoc
session had no stop control at all: the cancel button is only enabled by
`start_analysis_view_mode` (the pre-recorded entry point) and "Stop Recording"
is built only for live projects.

**4. Frames are drawn on the Tk thread.** `EventBusV2.publish` is synchronous on
the caller's thread, and `UI_UPDATE_LIVE_FRAME` is published by the processing
worker. `CanvasManager._on_live_frame_update` therefore stashes the frame and
schedules `_render_pending_live_frame` via `root.after(0, ...)`, **drop-latest**
(a newer frame replaces an undrawn one; only one redraw is ever queued).

**5. Output folder.** With no project and no chosen folder, the session lands in
`core/recording/live_output_paths.default_live_sessions_dir()`
(`~/ZebTrack/live_analysis_sessions`) — never in the CWD-relative
`live_analysis_sessions/` it used before, which depended on how the app was
launched. `_cleanup_existing_session_folders` now matches the exact
`{experiment_id}_YYYYMMDD_HHMMSS` pattern and **only deletes folders with no
video and no trajectory** (or an explicit `.cancelled` marker): a longitudinal
protocol reuses experiment ids, and the prefix glob used to destroy the previous
day's recording at the start of the next one.

**6. One aquarium.** Live analysis without a project is single-arena end to end
(`get_zone_data()` is the legacy shim and always returns a plain `ZoneData`), so
the dialog's aquarium count is disabled with an on-screen note. Multi-aquarium
requires a live project.

**7. Ad-hoc inside an external-trigger project.** `external_trigger_gate`
governs the two PROJECT recording paths. An ad-hoc session is different in kind
— no subject, no block, nothing to resume into — so it is not armed; but it is
no longer started in silence either:
`_confirm_adhoc_under_external_trigger()` asks for confirmation when the open
project declares `external_trigger_mode`, and is a no-op otherwise (including
with no project at all).

### 5.15. Project Switch: `PROJECT_MANAGER_REPLACED` and `PROJECT_OPENED` (August 2026)

`close_project` does not clear the current `ProjectManager` — it constructs a
**brand new one** (`project_workflow_adapter.close_project`) and publishes
`PROJECT_MANAGER_REPLACED`. The old instance stays a perfectly valid object
holding the PREVIOUS session's `project_data`, so anything that snapshotted the
manager in its constructor keeps answering from the closed project. Nothing
about that looks like an error, which is what made it survive so long.

**Propagation is a tree, not a list.** `MainViewModelRuntime.handle_project_manager_replaced`
walks `services_to_update`; two of those entries are *owners* that forward to
what they constructed:

| Owner | Forwards to |
| --- | --- |
| `ProjectLifecycleCoordinator` | `CalibrationCoordinator`, `ModelOverrideService` |
| `VideoProcessingCoordinator` | multi-aquarium, sequential, report, progress sub-coordinators, `ui_coordinator`, `dialog_coordinator` |
| `ApplicationGUI` (own subscription) | `gui.project_manager`, `ZoneContextService`, `TabBuilder`, `ROITemplateManager`, and every panel exposing `on_project_manager_replaced` |

A component that holds `project_manager` and is reachable from none of those is
a bug waiting to happen. Two concrete ones this replaced:

- `ZoneContextService` (built once in `ApplicationGUI.__init__`) fed the canvas,
  the zone editor and the zone list. After an ad-hoc single-video run — which
  writes its arena and ROIs into the then-current manager's `project_data`
  (`project.zone_data.save.in_memory`) — opening a project drew the SINGLE
  VIDEO's arena over the project's own, while the detector had the right zones.
- `CalibrationCoordinator` computes `project_loaded = bool(pm.project_path)`.
  Off the closed manager that is `False`, so the **AI Model Config** tab
  reported "Open a project…" with a project fully loaded.

The GUI handler bounces onto the Tk main thread via `root.after(0, ...)` —
`EventBusV2` publishes synchronously on the publisher's thread — and finishes by
republishing `UI_REDRAW_ZONES` + `UI_UPDATE_ZONE_LIST` so the canvas repaints
from the new manager.

**`PROJECT_OPENED` is mandatory.** Its emission was once deleted from
`ProjectLifecycleCoordinator.open_project` as "no handlers exist", while two live
subscribers stayed wired to it and simply stopped running:
`ZoneContextPanel._on_project_opened` and
`MultiAquariumCoordinator.reset_multi_aquarium_state` (so `_auto_assign_aquariums`,
`_last_assignment_configs` and `_assigned_videos` leaked across a project
switch). Anything that must FORGET the previous project belongs on this event.

**Opening a project resets, it does not merely load.** Three steps that used to
be missing:

1. `ProjectManager.load_project` calls `zone_manager.reset_active_context()`.
   `_active_zone_video` / `_last_zone_source_video` are instance state and
   survived the swap, so the new project inherited the previous run's video
   pointer — and `ProjectLifecycleCoordinator` fed THAT video's zones to
   `DetectorService.configure_zones`.
2. `ProjectWorkflowService.open_project` runs `setup_zones_callback`
   **unconditionally**. It used to be gated on the project already having zones,
   with no `else`, so a project without an arena kept the previous session's.
3. `ProjectInitializer.load_project_view` clears `pending_single_video_path`,
   the single-video buttons and the interactive drawing state.

### 5.16. Project vs Session Scope: the settings snapshot (August 2026)

**The ad-hoc dialogs write into the SHARED `Settings` and never restore it.**
`SingleVideoConfigDialog.apply()` and `LiveAnalysisDialog.apply()` push their
per-run choices — `freezing_velocity_threshold`, `freezing_min_duration_s`,
`sharp_turn_threshold_deg_s`, `trajectory_smoothing.window_length` and
`.polyorder` — onto the injected settings object so the other UI tabs stay
consistent. Nothing puts them back.

That is only safe because **no project path reads the live object for those
values**. Project analysis goes through
`core/services/project_settings_snapshot.build_project_settings_snapshot`, which
resolves **project > session baseline > schema default** and returns a deep
copy. The baseline is a pristine `Settings` captured in `ContainerContext`
before any dialog exists; it is what protects projects that carry no
`analysis_parameters` of their own — including every project created before this
existed.

Reading any of those five off `self.settings` in a project flow reintroduces the
bug: run an ad-hoc single video, then analyse a project, and the project's
report silently uses the ad-hoc thresholds. `analysis_pipeline_runner
._collect_params_from_project` did exactly that.

**One snapshot builder, not two.** `_create_project_settings_snapshot` existed
on both `VideoSelectionMixin` and `ReportGenerationCoordinator` and applied
DIFFERENT project keys, so regenerating a report produced different numbers than
processing the video. Both are now one-line delegations. Adding a project key
means adding it in the builder — never in a caller.

**`analysis_parameters` is the per-project home** for the five thresholds, using
the key names the readers already expect (`freezing_vel_threshold`,
`freezing_min_duration`, `sharp_turn_threshold`, `smoothing_window_length`,
`smoothing_polyorder`) — NOT the `Settings` field names. It is written by
`analysis_widgets._update_current_project_settings` (saving config with a
project open) and normalized to a dict by the project migration. The migration
deliberately stamps **no values**: inventing them from session settings would
freeze the leak it exists to close.

Two traps the builder handles, and a caller must not re-derive:

- **Pydantic writes the field before running the model validator.** A rejected
  assignment still leaves the invalid value in place, so the exception is not a
  rollback — the builder restores the previous sub-model via `__dict__`.
  Without it a bad `processing_offset` surfaced later as a ROI-rule failure.
- **Cross-field invariants span sub-models.** `processing_offset` is validated
  against `processing_interval` on `Settings` itself, and
  `trajectory_smoothing.polyorder` against `window_length`. Sub-models are
  therefore replaced whole, and the smoothing pair is never applied key by key:
  a valid pair can be rejected purely on the order the halves are written.

**Two more project-scoped things released on `PROJECT_MANAGER_REPLACED`:**
`LiveCameraSessionCoordinator` restores the `model_selection` it overwrote when
a live session started, and `HardwareStatusViewModel` disconnects the Arduino —
the port is opened from `project_data["arduino_port"]`, so it belongs to the
project, not the session. Use `disconnect()`, never
`_shutdown_arduino_manager()`: the latter drops the manager reference and the
next project would never reconnect.

---

## 6. Common Pitfalls for Agents

1. **Missing Event Payloads:** Always check the **Event Registry** above. If you publish `UI_DISPLAY_FRAME` without the `frame` key, the UI will crash or show nothing.
2. **Direct UI Access:** Do not try to access `self.view.canvas` from a Coordinator. Use `self.event_bus.publish(Events.UI_..., data)`.
3. **Worker Isolation:** The `ProcessingWorker` runs in a separate process (multiprocessing). It cannot access global variables or shared objects (like `self.detector`) modified in the main thread *after* it started. Everything must be passed in `ProcessingContext`.
4. **Legacy vs. New:**
   - **Legacy:** `VideoProcessingOrchestrator`, `AnalysisOrchestrator` (Avoid modifying if possible).
   - **New (Phase 3):** `ProcessingCoordinator` (Preferred location for logic).
5. **UIScheduler (Resolved Naming Conflict):** Phase 2 renamed `zebtrack.core.ui_coordinator.UICoordinator` to `UIScheduler`.
   - `zebtrack.core.ui_scheduler.UIScheduler`: A scheduler/facade for `root.after`. Used by `ProcessingCoordinator`.
   - `zebtrack.ui.ui_coordinator.UICoordinator`: A Mediator for EventBus events. Used by `EventDispatcher`.
   - **Reason:** Eliminated name collision that caused type confusion and import errors.
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
11. **Coordinator Callbacks Must Have Defaults (Fixed Dec 2025):** When calling Coordinator methods that accept callbacks (e.g., `create_project`, `open_project`), the Coordinator MUST provide safe default implementations using its injected dependencies (`state_manager`, `detector_service`). If callbacks are passed as `None` to adapters that require them, it will cause `TypeError: 'NoneType' object is not callable`. This was fixed by adding `detector_service` as an optional dependency to `ProjectLifecycleCoordinator` and implementing default callback factories in `create_project()` and `open_project()`.
12. **Batch Processing Per-Video Results (Fixed Dec 2025):** In batch processing mode, the `ProcessingWorker` now creates a per-video results directory: `{experiment_id}_results/` next to each video file. Previously, all results went to the project root. The fix is in `processing_worker.py:_process_single_video()` which calculates `results_dir = os.path.join(video_dir, f"{experiment_id}_results")` for non-single-video mode.
13. **Batch Processing Zone Data (Fixed Dec 2025):** When processing multiple videos in batch, each video has its own zone data. The `_load_zones_for_eligible_videos()` method now serializes zone data into each `video_info["zone_data"]` dict, and the worker uses `_get_zone_data_for_video(video_metadata)` to retrieve per-video zones instead of a global default.
14. **ProcessingCallbacks.on_progress Signature (Updated Dec 2025):** The `on_progress` callback now has signature: `(index: int, total: int, experiment_id: str, fraction: float, message: str, stats: dict | None)`. The worker's `monitor_loop` passes all these fields, and `create_processing_callbacks` now publishes `UI_UPDATE_ANALYSIS_TASK_STATUS` with full video progress info.
15. **Multi-Aquarium Zone Serialization (Fixed Dec 2025):** When processing multi-aquarium videos, `ProcessingCoordinator` serializes `MultiAquariumZoneData` using `ZoneManager.multi_aquarium_zone_data_to_dict`. The `ProcessingWorker` deserializes this using `ZoneManager.multi_aquarium_zone_data_from_dict`. This ensures the worker receives the complete configuration (aquariums list) instead of just a flattened/partial `ZoneData`.
16. **Parquet Export for Compatibility (Fixed Dec 2025):** To ensure multi-aquarium videos are correctly classified as 'Ready for Analysis' (`has_arena=True`), `ProjectManager.save_multi_aquarium_zone_data` automatically exports the zones of Aquarium 0 to a standard parquet file (`1_ProcessingArea...`). This satisfies the legacy file scanner while preserving the full multi-aquarium structure in `project_config.json`. Also, `save_project()` is called strictly *after* updating the file paths in the video entry to ensure persistence.

17. **Multi-Aquarium Reporting + Reports Tree Contracts (Fixed Dec 2025):**
    - **Reporting MUST use multi-aquarium zone accessor:** In multi-aquarium report generation, always call `ProjectManager.get_multi_aquarium_zone_data()` (not `get_zone_data()`). The single-aquarium accessor returns only Aquarium 0 for backward compatibility and will corrupt Aquarium 1 crop/overlay alignment.
    - **Coordinate Normalization:** When generating reports for a cropped arena, existing `x_cm`/`y_cm` columns MUST be dropped before normalization. This forces `BehavioralAnalyzer` to recompute coordinates relative to the new origin (0,0), preventing trajectory misalignment.
    - **Robust Image Loading:** Background frames (PNG) must be loaded using `cv2.imdecode` to support Windows unicode paths. `calibration` should be set to `None` when using a pre-cropped PNG background to avoid redundant warping.
    - **Quality Appendix:** `AnalysisResult` now contains `validation_warnings` (list) and `validation_stats` (dict). These are used by `Reporter` to append a "Trajectory Validation" section with coverage, frame range, and technical warnings.
    - **Canonical metadata source for UI:** The hierarchy builder may omit `multi_aquarium_outputs`. The Reports tab tree must fall back to `ProjectManager.find_video_entry(video_path)` as the canonical source of truth.
    - **Key normalization:** `multi_aquarium_outputs` keys may be mixed (`0` vs `"0"`). Normalize keys to numeric aquarium IDs and merge duplicates to avoid Treeview iid collisions (symptom: only one aquarium visible).
    - **Persistence after generation (Option B):** After generating per-aquarium summaries/reports, re-register updated `multi_aquarium_outputs` via `ProjectManager.register_multi_aquarium_outputs(...)` so `has_summary` and artifact paths persist and the UI updates reliably.

18. **Simultaneous Multi-Aquarium Completion Logic (Fixed Dec 2025):** In the single video workflow, `video_results_dir` is calculated dynamically and may not be preset in the project manager. The `on_video_completed` callback now robustly detects multi-aquarium outputs (`aquarium_0`, `aquarium_1`) by checking the filesystem, even if `video_results_dir` is None in the video entry. This ensures that `register_multi_aquarium_outputs` is called and reports are generated for simultaneous 2-aquarium analyses. The `is_multi_aquarium` flag is now initialized based on the *presence* of these output folders, not just the project configuration.

19. **Unified Report & Analysis Contracts (Fixed Dec 28, 2025 - v3.2):**
    - **Reporter behavioral_config Storage:** The `Reporter` legacy constructor MUST store `self.behavioral_config = behavioral_config if behavioral_config else {}` BEFORE creating `tidy_data`. Previously, the conditional `if not hasattr(self, "behavioral_config")` always triggered because the parameter was never stored, causing geotaxis data to be empty.
    - **Unified Report Metadata Enrichment:** `_enrich_unified_report_metadata()` MUST always add identification columns (group, subject, day, experiment_id) even when values are empty (use "N/A" fallback). This ensures every row in unified reports is identifiable.
    - **Unified Report Column Ordering:** `_align_and_concatenate_unified_dfs()` MUST place priority columns first: `["group", "subject", "day", "experiment_id", "aquarium_id", "is_multi_aquarium"]`. Other columns follow alphabetically.
    - **Word Report Column Display:** Summary tables MUST use `DISPLAY_COLUMN_MAPPING` for metric names (e.g., "Max Speed (cm/s)" not "Max Speed Cm S"). Fall back to `.title()` only for unmapped columns.
    - **Geotaxis Zone Naming:** Zone columns MUST display 1-indexed names for users ("Zona 1 - Fundo" for zone_0). Fallback logic in `reporter.py` and `data_transformer.py` handles cases where height_cm/num_zones metadata is unavailable.
    - **Batch Processing Dialogs:** `_finalize_report_generation()` MUST check `_is_batch_processing()` before showing dialogs. Individual dialogs are suppressed during batch; only a consolidated dialog appears at batch end.

---

## 7. Removed Events (Changelog)

### Dec 2, 2025 - Dead Event Cleanup

The following events were removed during the integration audit as they had **no subscribers**:

| Event                     | Previous Location                                                  | Reason for Removal                                                                                                                                            |
| ------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `PROCESSING_MODE_CHANGED` | `session_coordinator.py:1050`, `hardware_coordinator.py:1091`      | No subscribers found. Processing mode is handled via `ProcessingCoordinator._publish_processing_mode()` which calls `view.update_processing_mode()` directly. |
| `PROCESSING_MODE_RESTORE` | `session_coordinator.py:1139`, `hardware_coordinator.py:1163,1490` | No subscribers found. Same as above - orphaned event from earlier refactoring.                                                                                |

**Impact:** None. These events were never handled by any component.

---

## 8. Legacy Patterns (Known Technical Debt)

The following patterns remain in the codebase and should be addressed in future refactoring:

### 8.1. Direct View Access in Coordinators

Some coordinators still access `self.view` directly instead of publishing events:

| Coordinator                    | Pattern                                                | Recommended Fix                                               |
| ------------------------------ | ------------------------------------------------------ | ------------------------------------------------------------- |
| `RecordingSessionCoordinator`  | `self.view.camera.get_frame()`                         | Inject camera service; publish frame events                   |
| `VideoProcessingCoordinator`   | `self.view.update_processing_mode()` via `UIScheduler` | Migrate to `EventBusV2` → `UIEvents.PROCESSING_STATS_UPDATED` |

### 8.2. Hybrid Patterns (Acceptable)

These patterns are intentional trade-offs documented in ADRs:

| Pattern | Location | ADR Reference |
| --- | --- | --- |
| Live Camera direct display | `LiveCameraSessionCoordinator` → `LivePreviewWindow` | ADR-004 |
| `UIScheduler.update_view()` direct calls | `VideoProcessingCoordinator` | ADR-003 (Phase 2) |

### 8.3. EventBus v1 Deprecation (Planned)

EventBus v1 (string-based `Events` class) is deprecated per ADR-009. All 90+ domain
events should be migrated to `EventBusV2` (`UIEvents` enum) in a future phase.
Migration has not started; coordinator decomposition (Phase 4) was prioritized first.

---

## 9. Performance Architecture (Phase 7)

### 9.1. RecorderFactory (Lazy Loading)

- **File:** `io/recorder_factory.py`
- **Pattern:** Lazy-loads `Recorder` (pandas/pyarrow) only when first analysis starts
- **Thread Safety:** Double-checked locking prevents duplicate initialization
- **Impact:** Saves ~2.9s startup time + 150 MB memory by deferring heavy dependency imports
- **API:** Delegates via `__getattr__` + context manager support (transparent proxy)

### 9.2. Splash Screen

- **File:** `ui/splash_screen.py`
- **Pattern:** Professional loading UI displayed during app initialization
- **Platform:** Segoe UI on Windows, Helvetica elsewhere; configurable duration via `SPLASH_DISPLAY_DURATION_MS`
- **Integration:** Wired in `__main__.py` Composition Root

### 9.3. Lazy Import Strategy

Heavy imports (pandas, pyarrow, openpyxl) are deferred in:

| Module                 | Deferred Imports                | Loaded When              |
| ---------------------- | ------------------------------- | ------------------------ |
| `project_manager.py`   | pandas                          | Accessing project data   |
| `zone_manager.py`      | pandas                          | Reading zone parquets    |
| `project_service.py`   | pandas                          | Processing project files |
| `recorder_factory.py`  | pandas, pyarrow                 | First analysis start     |

**Total Impact:** Startup time reduced from ~6.0s to ~2.0s (-67%).

### 9.4. Detection Performance

- **Partitioned Parallel Detection:** `detect_partitioned_parallel()` uses ThreadPoolExecutor (~30-40% speedup)
- **Batch Inference:** `detect_batch()` for offline multi-frame processing
- **Mask-Based Containment:** `_build_single_mask()` for per-aquarium region extraction

---

## 10. Documentation & Quality Standards (Phase 8)

### 10.1. Language Policy

- **Code comments and docstrings:** English (translated from Portuguese in Phase 8.1)
- **User-facing strings:** Portuguese (PT-BR) — dialog titles, status messages, error messages
- **Technical documentation:** English
- **Wiki (`docs/wiki/`):** Portuguese

### 10.2. Testing Standards

- **Property-based testing:** Hypothesis (6 test files, 83+ tests) covering settings, detection types, recorder, zone scaler, behavior, and calibration
- **Coverage gates (CI):** Linux core ≥50%, Linux GUI ≥32%, Windows core ≥44%
- **Local gate:** pytest.ini `--cov-fail-under=50`
- **Roadmap:** Target OpenSSF Silver (80% stmt)

### 10.3. Architecture Decision Records

| ADR | Title | Status |
| --- | ----- | ------ |
| [ADR-001](../decisions/ADR-001-multi-aquarium-support.md) | Multi-Aquarium Support | Accepted |
| [ADR-004](../decisions/ADR-004-live-camera-divergence.md) | Live Camera Architecture Divergence | Accepted |
| [ADR-009](../decisions/ADR-009-event-bus-unification.md) | Event Bus Unification | Accepted (migration pending) |

---

## 11. Document Changelog

| Date | Version | Changes |
| ---- | ------- | ------- |
| Aug 23, 2026 | v5.2 | § 5.14 ad-hoc live session — `live_calibration_scale` px→cm resolver (dialog dimensions were dropped, reports read pixels as cm), `stop_session(keep_data=...)` + `stop_live_session(discard=...)` + `finish_session_early()`, new `LIVE_SESSION_FINISH_REQUESTED` event and the "⏹ Finish and Save" / confirmed-Cancel pair, live frames marshalled to the Tk thread (drop-latest), `live_output_paths.default_live_sessions_dir()`, non-destructive session-folder cleanup |
| Aug 15, 2026 | v5.1 | § 5.6 closed-loop `fps` corrected to the rate measured from capture timestamps (`FrameLedger.current_fps_measured()`), replacing the configured value that had been logged as achieved; configured value kept in new `fps_configured` / `sampling_interval_ms_configured` columns (release v6.0.0 archival snapshot) |
| Aug 8, 2026 | v5.0 | § 5.11 external trigger reaches the Progress grid (`external_trigger_gate`, two coordinators unified, `on_arduino_event` routing); § 5.12 per-subject recording duration (`session_duration_resolver`, `session_duration_overrides`, heterogeneity warning in partial/batch reports) |
| Aug 7, 2026 | v4.9 | § 5.10.4 `seg_overlap` made real — `3b_Mascaras_<base>.parquet` sidecar (WKB, same flush thread), opt-in mask decode gated by `should_capture_masks()`, calibration applied to mask points, dedicated `roi_min_seg_overlap_ratio`, declared degradation to `bbox_intersects` instead of the old unconditional raise |
| Aug 6, 2026 | v4.8 | § 5.10.3 multi-animal ROI — `(timestamp, track_id)` aggregation ends the ghost centroid, track-aware diffs/smoothing/episodes, `analise_roi.por_animal` + `any_track` group semantics, multi-track validation warning |
| Aug 6, 2026 | v4.7 | § 5.10.2 ROI presence timing — backdated asymmetric debounce (production no longer hardcodes `flutter_n_frames=1`), duration filters in seconds, `roi_max_gap_s` + `analise_roi.tempo_nao_observado_s` |
| Aug 6, 2026 | v4.6 | § 5.10.1 overlap semantics — single-source defaults (config.yaml no longer overrides `roi_min_bbox_overlap_ratio` with 0.05), `roi_bbox_overlap_basis` (`bbox`/`roi`/`max`), threshold `0` = any non-zero overlap area for `bbox_intersects` |
| Aug 6, 2026 | v4.5 | § 5.10 canonical ROI inclusion rule — `roi_rule_resolver`, four consumers unified, shapely-based `ArduinoRoiEvaluator`, `ZONE_APPLY_ROI_SETTINGS` persists the rule |
| Aug 5, 2026 | v4.4 | § 5.9 frame ledger & timeline reconstruction — `6_FrameLedger_<base>.{csv,parquet}` + session anchor JSON, `video_queue` item carries capture metadata, `queue_wait_ms`/`inference_ms` appended to `5_ClosedLoop_*` |
| Aug 4, 2026 | v4.3 | § 5.8 binding verification via firmware ACK — `arduino_ack_semantics`, `ArduinoManager.probe_tokens`, panel "test commands" button, runtime `ack_inverted` warning |
| Aug 4, 2026 | v4.2 | § 5.7 per-zone command robustness — ambiguous-token detection (`token_conflicts()`), ROI exit grace period (`arduino.roi_exit_grace_frames`), non-blocking reference firmware |
| Jul 23, 2026 | v4.1 | § 5.6 closed-loop latency logging (software-only, ACK-based) — `ArduinoManager` tracked path + FIFO ACK correlation, `5_ClosedLoop_<base>.{csv,parquet}` |
| Feb 3, 2026 | v4.0 | Phase 4 coordinator decomposition (16 coordinators), ADR-009 deprecation notice, performance architecture (Phase 7), documentation standards (Phase 8), updated dependency container |
| Dec 28, 2025 | v3.2 | Unified report contracts, max speed metric, geotaxis data fixes |
| Dec 2, 2025 | v3.1 | Sequential multi-aquarium processing, dead event cleanup |
| Nov 2025 | v3.0 | Phase 3 orchestrator consolidation, multi-aquarium events |
