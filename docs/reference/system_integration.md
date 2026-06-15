# ZebTrack-AI System Integration Map

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

**CRITICAL:** ZebTrack-AI uses **two coexisting event bus systems** by design. Agents must understand which system to use for each use case.

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
| `Events.ZONE_AUTO_DETECT`                 | `video_path` (str or None)          | `stabilization_frames` (int) | `ProcessingCoordinator`    | Runs `AquariumDetector` to find the tank polygon automatically.                             |
| `Events.PROCESSING_GENERATE_TRAJECTORIES` | `video_paths` (list, optional)      | -                            | `ProcessingCoordinator`    | Triggers `process_pending_project_videos`. Used by Reports tab to start analysis.           |

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

---

## 6. Common Pitfalls for Agents

1. **Missing Event Payloads:** Always check the **Event Registry** above. If you publish `UI_DISPLAY_FRAME` without the `frame` key, the UI will crash or show nothing.
2. **Direct UI Access:** Do not try to access `self.view.canvas` from a Coordinator. Use `self.event_bus.publish(Events.UI_..., data)`.
3. **Worker Isolation:** The `ProcessingWorker` runs in a separate process (multiprocessing). It cannot access global variables or shared objects (like `self.detector`) modified in the main thread _after_ it started. Everything must be passed in `ProcessingContext`.
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
16. **Parquet Export for Compatibility (Fixed Dec 2025):** To ensure multi-aquarium videos are correctly classified as 'Ready for Analysis' (`has_arena=True`), `ProjectManager.save_multi_aquarium_zone_data` automatically exports the zones of Aquarium 0 to a standard parquet file (`1_ProcessingArea...`). This satisfies the legacy file scanner while preserving the full multi-aquarium structure in `project_config.json`. Also, `save_project()` is called strictly _after_ updating the file paths in the video entry to ensure persistence.

17. **Multi-Aquarium Reporting + Reports Tree Contracts (Fixed Dec 2025):**
    - **Reporting MUST use multi-aquarium zone accessor:** In multi-aquarium report generation, always call `ProjectManager.get_multi_aquarium_zone_data()` (not `get_zone_data()`). The single-aquarium accessor returns only Aquarium 0 for backward compatibility and will corrupt Aquarium 1 crop/overlay alignment.
    - **Coordinate Normalization:** When generating reports for a cropped arena, existing `x_cm`/`y_cm` columns MUST be dropped before normalization. This forces `BehavioralAnalyzer` to recompute coordinates relative to the new origin (0,0), preventing trajectory misalignment.
    - **Robust Image Loading:** Background frames (PNG) must be loaded using `cv2.imdecode` to support Windows unicode paths. `calibration` should be set to `None` when using a pre-cropped PNG background to avoid redundant warping.
    - **Quality Appendix:** `AnalysisResult` now contains `validation_warnings` (list) and `validation_stats` (dict). These are used by `Reporter` to append a "Trajectory Validation" section with coverage, frame range, and technical warnings.
    - **Canonical metadata source for UI:** The hierarchy builder may omit `multi_aquarium_outputs`. The Reports tab tree must fall back to `ProjectManager.find_video_entry(video_path)` as the canonical source of truth.
    - **Key normalization:** `multi_aquarium_outputs` keys may be mixed (`0` vs `"0"`). Normalize keys to numeric aquarium IDs and merge duplicates to avoid Treeview iid collisions (symptom: only one aquarium visible).
    - **Persistence after generation (Option B):** After generating per-aquarium summaries/reports, re-register updated `multi_aquarium_outputs` via `ProjectManager.register_multi_aquarium_outputs(...)` so `has_summary` and artifact paths persist and the UI updates reliably.

18. **Simultaneous Multi-Aquarium Completion Logic (Fixed Dec 2025):** In the single video workflow, `video_results_dir` is calculated dynamically and may not be preset in the project manager. The `on_video_completed` callback now robustly detects multi-aquarium outputs (`aquarium_0`, `aquarium_1`) by checking the filesystem, even if `video_results_dir` is None in the video entry. This ensures that `register_multi_aquarium_outputs` is called and reports are generated for simultaneous 2-aquarium analyses. The `is_multi_aquarium` flag is now initialized based on the _presence_ of these output folders, not just the project configuration.

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
- **Coverage gates (CI):** Linux core ≥48%, Linux GUI ≥32%, Windows core ≥28%
- **Local gate:** pytest.ini `--cov-fail-under=48`
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
| Feb 3, 2026 | v4.0 | Phase 4 coordinator decomposition (16 coordinators), ADR-009 deprecation notice, performance architecture (Phase 7), documentation standards (Phase 8), updated dependency container |
| Dec 28, 2025 | v3.2 | Unified report contracts, max speed metric, geotaxis data fixes |
| Dec 2, 2025 | v3.1 | Sequential multi-aquarium processing, dead event cleanup |
| Nov 2025 | v3.0 | Phase 3 orchestrator consolidation, multi-aquarium events |
