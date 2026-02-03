# MainViewModel Class - Comprehensive Structural Analysis

**File**: `/home/user/ZebTrack-AI/src/zebtrack/core/main_view_model.py`
**Total Methods**: ~140 methods (incl. properties, nested functions)
**Size**: 5588 lines

---

## 1. DEPENDENCIES INJECTED IN __init__ (13+ services)

### Core Framework
- **root** - Tkinter root window
- **event_bus** (ui_event_bus) - EventBus for UI events
- **state_manager** - StateManager (centralized state observer)
- **ui_coordinator** - UICoordinator (for scheduling UI updates)
- **settings_obj** - Settings (Pydantic v2 config)

### Service Layer (6 services)
- **project_manager** - ProjectManager (project state, videos, zones)
- **project_workflow_service** - ProjectWorkflowService
- **weight_manager** - WeightManager (model weights)
- **model_service** - ModelService (model metadata)
- **detector_service** - DetectorService (AI detector initialization)
- **video_processing_service** - VideoProcessingService (frame processing)

### Optional Services
- **analysis_service** - AnalysisService (behavioral metrics, created if None)
- **recording_service** - RecordingService (Parquet + MP4 output, initialized later)
- **live_camera_service** - LiveCameraService (live camera analysis sessions)
- **test_sync_event** - threading.Event (test synchronization only)

### Internal Instances
- **project_service** - ProjectService() (created in __init__)
- **recorder** - Recorder (Parquet writer, from settings_obj)
- **arduino** / **arduino_manager** - Arduino/ArduinoManager (optional hardware)

---

## 2. METHOD CATEGORIZATION BY RESPONSIBILITY

### A. STATE MANAGEMENT & LIFECYCLE (7 methods)
**Purpose**: Manage application state changes and lifecycle hooks.

| Line | Method | Purpose |
|------|--------|---------|
| 357 | `run()` | Main event loop |
| 527 | `on_close()` | Application exit with cleanup |
| 537 | `join_threads()` | Wait for all worker threads to finish |
| 430 | `_on_state_change_for_test()` | Test observer for state mutations |
| 459 | `_on_project_state_changed()` | Listen to project state → publish UI events |
| 470 | `_on_detector_state_changed()` | Listen to detector state → publish UI events |
| 484 | `_on_recording_state_changed()` | Listen to recording state → publish UI events |
| 505 | `_on_processing_state_changed()` | Listen to processing state → publish UI events |

---

### B. EVENT BUS & EVENT HANDLING (5 methods)
**Purpose**: Register event handlers and dispatch UI→Controller events.

| Line | Method | Purpose |
|------|--------|---------|
| 361 | `bind_events()` | Subscribe to UI events via EventBus |
| 798 | `_register_event_handlers()` | Register generic event dispatchers for all mapped events |
| 762 | `_create_event_dispatcher(event_name)` | Factory for generic event dispatcher |
| 775 | `dispatcher(data)` | Nested: Actual dispatcher that calls mapped method |
| 825 | `_handle_setup_zone_definition_for_single_video()` | Special handler for single-video zone setup event |

**Note**: Uses `_EVENT_METHOD_MAPPING` dict to eliminate 32+ individual handler methods (Phase 7.1 optimization).

---

### C. PROPERTIES & BASIC ACCESSORS (9 items)
**Purpose**: Expose internal state via properties.

| Line | Method | Purpose |
|------|--------|---------|
| 380 | `is_recording` (property getter) | Read-only access to recording state |
| 385 | `is_recording` (property setter) | Update recording state |
| 393 | `detector` (property getter) | Access detector from detector_service |
| 403 | `detector` (property setter) | Set detector in detector_service |
| 412 | `detector` (property deleter) | Clear detector from service |
| 421 | `detector_initialized` (property getter) | Check if detector is ready |
| 426 | `is_processing` (property getter) | Check if video processing is active |
| 517 | `get_openvino_status()` | Get OpenVINO conversion status text |
| 1570 | `get_calibration_scope_info()` | Get project/global calibration context |

---

### D. HARDWARE SETUP & CONTROL (10 methods)
**Purpose**: Initialize and manage external hardware (detector, camera, Arduino).

#### Detector Setup
| Line | Method | Purpose |
|------|--------|---------|
| 1226 | `setup_detector()` | Initialize detector (delegates to DetectorService) |
| 1306 | `setup_detector_zones()` | Configure detector with zone polygons from project_manager |

#### Arduino Hardware
| Line | Method | Purpose |
|------|--------|---------|
| 1260 | `setup_arduino()` | Ensure Arduino connection ready (enables/disables based on project_data) |
| 1254 | `_is_arduino_connected()` | Check Arduino connection status |
| 560 | `_get_arduino_manager()` | Create ArduinoManager instance |
| 565 | `_shutdown_arduino_manager()` | Gracefully disconnect Arduino |

#### Arduino Event Handlers
| Line | Method | Purpose |
|------|--------|---------|
| 921 | `on_arduino_status_change()` | Handle Arduino connect/disconnect → update state_manager |
| 927 | `on_arduino_command_sent()` | Log Arduino command success/failure |
| 933 | `on_arduino_event()` | Handle Arduino zone trigger events |
| 917 | `log_arduino_event()` | Log event message |

---

### E. RECORDING & LIVE CAMERA (9 methods)
**Purpose**: Control video recording and live camera analysis sessions.

#### Recording Control
| Line | Method | Purpose |
|------|--------|---------|
| 2459 | `start_recording()` | Begin recording from live camera (called by user/Arduino) |
| 2654 | `stop_recording()` | Stop current recording session |
| 2672 | `_ensure_zones_before_recording()` | Validate arena/ROI zones exist before starting |
| 950 | `trigger_recording()` | Handle Arduino-triggered recording (with optional event code) |
| 963 | `_schedule_recording()` | Schedule recording start with delay/duration |

#### Live Camera Analysis
| Line | Method | Purpose |
|------|--------|---------|
| 2588 | `start_live_camera_analysis()` | Launch live camera analysis dialog + LiveCameraService |
| 583 | `_setup_recording_service_callbacks()` | Wire up callbacks (progress, completion, errors) |
| 604 | `_init_recording_service()` | Initialize RecordingService with settings |

---

### F. WEIGHT & MODEL MANAGEMENT (12 methods)
**Purpose**: Manage detector weights (YOLO, OpenVINO) and model selection.

#### Weight Management
| Line | Method | Purpose |
|------|--------|---------|
| 1341 | `_safe_get_default_weight()` | Safely retrieve default weight name |
| 1360 | `get_all_weight_names()` | List all available weights |
| 1368 | `classify_weight_type()` | Detect weight type (YOLO, PyTorch, OpenVINO) from filename |
| 1372 | `add_new_weight()` | Add new weight file + refresh UI |
| 1393 | `delete_weight()` | Delete weight + refresh UI |
| 1412 | `set_active_weight()` | Activate weight + check OpenVINO conversion |
| 1433 | `manage_weights()` | Publish event to open weight management dialog |
| 1437 | `load_new_weight()` | Request weight file via UI dialog |

#### OpenVINO Management
| Line | Method | Purpose |
|------|--------|---------|
| 1476 | `set_openvino_usage()` | Toggle OpenVINO mode (PyTorch ↔ OpenVINO) |
| 1490 | `convert_active_weight_to_openvino()` | Convert weight + cache OpenVINO model |
| 1532 | `update_openvino_status()` | Update OpenVINO status text in UI |

---

### G. MODEL SETTINGS & OVERRIDES (15 methods)
**Purpose**: Manage global vs. project-specific model settings (weight, OpenVINO, calibration).

#### Global Settings Management
| Line | Method | Purpose |
|------|--------|---------|
| 1543 | `get_global_model_defaults()` | Get global weight + OpenVINO defaults |
| 1868 | `_restore_global_model_defaults()` | Reset to global defaults after project work |

#### Project Overrides Query & Config
| Line | Method | Purpose |
|------|--------|---------|
| 1540 | `are_project_overrides_active()` | Check if project overrides are in use |
| 1564 | `has_project_override_settings()` | Check if project has any override values |
| 1549 | `_get_project_data_dict()` | Safely get project_data dict |
| 1556 | `_ensure_project_overrides_record()` | Ensure model_overrides key exists in project_data |

#### Project Overrides Persistence
| Line | Method | Purpose |
|------|--------|---------|
| 1684 | `_persist_project_model_settings()` | Save weight + OpenVINO to project_data |
| 1710 | `copy_global_model_settings_to_project()` | Copy global defaults to project |
| 1733 | `save_current_calibration_to_project()` | Save current calibration to project |

#### Project Overrides Application
| Line | Method | Purpose |
|------|--------|---------|
| 1758 | `_apply_model_settings()` | Apply settings to detector (internal helper) |
| 1767 | `resolve_project_model_settings()` | Determine which settings to use (project vs. global) |
| 1823 | `apply_project_model_overrides()` | Load + apply project overrides to detector |
| 1847 | `save_project_model_overrides()` | Persist project settings to disk |

#### Detector Parameters
| Line | Method | Purpose |
|------|--------|---------|
| 1622 | `get_current_detector_parameters()` | Read active detector params (thresholds, etc.) |
| 1636 | `get_factory_detector_parameters()` | Get default factory params |
| 1650 | `update_detector_parameters()` | Modify detector params + persist to project |

---

### H. CALIBRATION SESSIONS (4 methods)
**Purpose**: Launch calibration workflows (aquarium detection, arena setup).

| Line | Method | Purpose |
|------|--------|---------|
| 1875 | `global_calibration_session()` | Launch global calibration (applies to all future projects) |
| 1888 | `project_calibration_session()` | Launch project-specific calibration |
| 1899 | `run_aquarium_detection()` | Auto-detect arena from video frame (AquariumDetector) |
| 2359 | `run_live_calibration()` | Live calibration with camera preview |

---

### I. ROI (REGION OF INTEREST) MANAGEMENT (13 methods)
**Purpose**: Manage arena (main polygon) and ROI zones.

#### ROI Templates
| Line | Method | Purpose |
|------|--------|---------|
| 2008 | `apply_roi_template()` | Load + apply pre-saved ROI template |
| 2060 | `save_roi_template()` | Save current zones as new template |
| 2067 | `import_and_apply_roi_template()` | Import external template + apply |

#### ROI Editing
| Line | Method | Purpose |
|------|--------|---------|
| 2074 | `rename_selected_roi()` | Rename active ROI |
| 2081 | `change_roi_color()` | Change ROI color |
| 2088 | `remove_selected_roi()` | Delete selected ROI |
| 2095 | `apply_roi_settings()` | Apply ROI changes |

#### Arena (Main Polygon) Management
| Line | Method | Purpose |
|------|--------|---------|
| 2102 | `set_main_arena_polygon()` | Set arena from points (validation + persistence) |
| 2152 | `save_manual_arena()` | Save user-drawn arena polygon |
| 2162 | `update_main_arena()` | Update existing arena polygon |
| 2180 | `add_roi_polygon()` | Add new ROI polygon with name + color |

#### Asset Management
| Line | Method | Purpose |
|------|--------|---------|
| 2306 | `can_remove_project_asset()` | Check if zone/arena can be deleted |
| 2324 | `delete_project_asset()` | Delete zone or arena from project |

---

### J. PROJECT WORKFLOW MANAGEMENT (7 methods)
**Purpose**: Create, open, close projects; wizard integration.

#### Project Lifecycle
| Line | Method | Purpose |
|------|--------|---------|
| 1001 | `create_project_workflow()` | Launch 5-step project wizard |
| 1154 | `open_project_workflow()` | Load existing project + setup detector/zones |
| 981 | `close_project()` | Close active project + cleanup |

#### Post-Creation Steps
| Line | Method | Purpose |
|------|--------|---------|
| 1058 | `_apply_wizard_detector_overrides()` | Apply detector settings from wizard metadata |
| 1107 | `_show_post_creation_guide()` | Display post-creation instructions |
| 1130 | `_restore_detector_settings()` | Restore detector state after wizard |
| 1141 | `_setup_zones_from_project()` | Load zones from project_manager |

#### UI Refresh
| Line | Method | Purpose |
|------|--------|---------|
| 880 | `refresh_project_views()` | Refresh all project-related UI views |
| 903 | `_clear_external_trigger_wait()` | Clear Arduino wait state |

---

### K. SINGLE VIDEO WORKFLOW (2 methods)
**Purpose**: Handle single-video processing (non-project context).

| Line | Method | Purpose |
|------|--------|---------|
| 2845 | `start_single_video_workflow()` | Prepare UI for zone definition on single video |
| 2896 | `start_single_video_processing()` | Execute processing after zones defined (registers video in project_manager) |

---

### L. PROCESSING MODE & CONFIGURATION (8 methods)
**Purpose**: Determine and configure processing behavior (single-subject vs. multi-track).

| Line | Method | Purpose |
|------|--------|---------|
| 832 | `_determine_processing_mode()` | Inspect detector/settings → infer ProcessingMode (SINGLE_SUBJECT or MULTI_TRACK) |
| 860 | `_publish_processing_mode()` | Notify GUI when processing mode changes |
| 3631 | `_resolve_single_animal_mode()` | Resolve single-animal setting from config or settings |
| 3667 | `_resolve_single_subject_tracker_preference()` | Determine if single-subject tracker should be used |
| 3722 | `_configure_single_subject_tracker()` | Enable/disable single-subject tracker |
| 3734 | `_determine_processing_intervals()` | Calculate analysis + display intervals |
| 3765 | `_temporary_single_animal_mode()` | Context manager for temporary mode override |
| 3830 | `_activate_analysis_view_mode()` | Switch UI to analysis view (during processing) |

---

### M. BATCH VIDEO PROCESSING (39+ methods)
**Purpose**: Process videos individually or in batch; core analysis pipeline.

#### High-Level Workflows
| Line | Method | Purpose |
|------|--------|---------|
| 3034 | `start_project_processing_workflow()` | Validate project + launch batch processing |
| 3262 | `process_pending_project_videos()` | Main batch processing orchestrator (C901 complexity) |
| 3418 | `generate_parquet_summaries()` | Generate summary Parquet files per video |
| 4954 | `_process_videos()` | Delegate to ProcessingWorker + manage callbacks |

#### Video Selection & Validation
| Line | Method | Purpose |
|------|--------|---------|
| 3900 | `_gather_candidate_entries()` | List all videos in project directory |
| 3984 | `_classify_candidate_videos()` | Determine which videos need processing |
| 4030 | `_select_eligible_videos()` | Filter videos by status + eligibility |
| 4112 | `_scan_and_validate_candidate_paths()` | Validate video files exist + are readable |

#### Per-Video Processing
| Line | Method | Purpose |
|------|--------|---------|
| 4623 | `_process_single_video()` | Execute detection + recording for one video |
| 3540 | `_run_tracking_if_needed()` | Conditionally run detector (based on skip logic) |
| 3567 | `_prepare_zone_data_for_tracking()` | Prepare zone polygons for detector |
| 3598 | `_build_calibration_context()` | Load calibration data (if any) for video |
| 3623 | `_tracking_cancelled()` | Check if processing was cancelled |

#### Parameter Collection
| Line | Method | Purpose |
|------|--------|---------|
| 4469 | `_collect_params_from_single_video()` | Extract config from single-video context |
| 4478 | `_collect_params_from_project()` | Extract config from project context |
| 4489 | `_collect_analysis_parameters()` | Merge all parameters for analysis |
| 4508 | `_prepare_calibration_context()` | Build calibration dict for analysis_service |

#### Analysis Pipeline
| Line | Method | Purpose |
|------|--------|---------|
| 4583 | `_run_analysis_pipeline()` | Execute AnalysisService on detector outputs |
| 4534 | `_generate_reports_for_video()` | Generate Word report + metrics |
| 4555 | `_register_project_outputs()` | Record output paths in state |

#### UI & Callback Management
| Line | Method | Purpose |
|------|--------|---------|
| 3837 | `_prepare_processing_ui()` | Setup progress dialog + UI mode |
| 3846 | `_finalize_processing()` | Update UI after batch complete |
| 4384 | `_notify_task_status_start()` | Emit progress event (task N of M) |
| 4393 | `_make_progress_callback()` | Factory for per-frame progress callback |
| 4800 | `_create_processing_callbacks()` | Create ProcessingCallbacks object with 6 callbacks |
| 4932 | `_create_processing_context()` | Create ProcessingContext for ProcessingWorker |

#### Results Management
| Line | Method | Purpose |
|------|--------|---------|
| 3873 | `_build_metadata_context()` | Build metadata dict for output paths |
| 4161 | `_generate_parquet_summaries_worker()` | Worker thread for summary generation |
| 4225 | `_process_summary_video()` | Create summary Parquet from detector outputs |
| 4377 | `_schedule_analysis_metadata_update()` | Schedule UI refresh after completion |
| 4758 | `_prepare_results_directory()` | Create output directory structure |
| 4765 | `_snapshot_results_dir()` | Record baseline files (for cleanup on cancel) |
| 4772 | `_cleanup_cancelled_results()` | Delete partial results on cancellation |
| 4779 | `_compose_analysis_view_metadata()` | Build metadata for analysis view display |
| 4671 | `apply_project_settings_to_batch()` | Apply global settings to video batch |

---

### N. ANALYSIS & REPORTING (2 methods)
**Purpose**: Generate final reports from processed video data.

| Line | Method | Purpose |
|------|--------|---------|
| 4980 | `generate_report()` | Load summary Parquet files + export to XLSX/CSV/Parquet + DOCX report |
| 2823 | `_show_cancel_feedback()` | Display cancellation message to user |

---

### O. MODEL DIAGNOSTIC (8 methods)
**Purpose**: Test detector on sample frames; verify model functionality.

| Line | Method | Purpose |
|------|--------|---------|
| 5070 | `run_model_diagnostic()` | Launch diagnostic in background thread |
| 5172 | `_diagnostic_processing_thread()` | Worker thread for diagnostic |
| 5246 | `_initialize_diagnostic_yolo_model()` | Load YOLO model for diagnostic |
| 5283 | `_initialize_diagnostic_openvino_model()` | Load OpenVINO model for diagnostic |
| 5356 | `_run_diagnostic_frame_loop()` | Process sample frames + collect results |
| 5224 | `_update_diagnostic_progress()` | Update progress dialog during diagnostic |
| 5241 | `_finish_progress_dialog()` | Close progress dialog |
| 5444 | `_finish_diagnostic_and_save_report()` | Save diagnostic results + display report |
| 5482 | `_format_diagnostic_report()` | Format diagnostic output as text |

---

### P. UTILITY & INTERNAL HELPERS (12+ methods)
**Purpose**: Scheduling, logging, internal operations.

| Line | Method | Purpose |
|------|--------|---------|
| 574 | `_schedule_on_ui()` | Schedule function on Tkinter main thread via root.after(0, ...) |
| 2768 | `cancel_current_analysis()` | Stop video processing + cleanup |
| 2803 | `_await_shutdown()` | Nested: Wait for worker threads to finish |

---

## 3. SUMMARY OF RESPONSIBILITIES

### Currently in MainViewModel (Needs Refactoring)

| Category | Count | Status | Recommendation |
|----------|-------|--------|-----------------|
| **State Management** | 8 | Core | Keep - Essential for observable state |
| **Hardware (Detector, Arduino)** | 10 | High | Extract → **HardwareCoordinator** |
| **Recording/Live Camera** | 9 | High | Extract → **RecordingCoordinator** + **LiveCameraCoordinator** |
| **Weight Management** | 12 | Medium | Extract → **WeightCoordinator** |
| **Model Settings/Overrides** | 15 | Medium | Extract → **ModelSettingsCoordinator** |
| **Calibration** | 4 | Medium | Extract → **CalibrationCoordinator** |
| **ROI/Arena** | 13 | High | Extract → **ArenaCoordinator** |
| **Project Workflow** | 7 | High | Extract → **ProjectCoordinator** |
| **Processing Workflows** | 2 | Core | Keep (with delegation) |
| **Processing Mode/Config** | 8 | Medium | Extract → **ProcessingModeCoordinator** |
| **Batch Processing** | 39+ | Very High | Extract → **BatchProcessingCoordinator** (LARGEST) |
| **Reporting** | 2 | Low | Extract → **ReportingService** (new) |
| **Diagnostic** | 8 | Low | Extract → **DiagnosticCoordinator** |
| **Properties/Basic** | 9 | Core | Keep |
| **Event Handling** | 5 | Core | Keep - Foundation |
| **Lifecycle** | 3 | Core | Keep |

---

## 4. PROPOSED REFACTORING: CREATE SPECIALIZED COORDINATORS

### Option 1: 6-Coordinator Architecture (Recommended)

1. **MainViewModel** (Thin Orchestrator)
   - Lifecycle: `run()`, `on_close()`, `join_threads()`
   - State observers: `_on_*_state_changed()` methods
   - Event routing: `bind_events()`, `_register_event_handlers()`
   - Public API: High-level entry points only

2. **HardwareCoordinator**
   - All detector setup + initialization
   - Arduino connection + event handling
   - **Moves**: ~10 methods

3. **ModelCoordinator**
   - Weight management (add, delete, set_active)
   - OpenVINO conversion + usage
   - Detector parameters + global defaults
   - **Moves**: ~20 methods

4. **ArenaCoordinator**
   - ROI template management
   - Arena polygon editing
   - Calibration (aquarium detection, live calibration)
   - **Moves**: ~15 methods

5. **ProcessingCoordinator**
   - Video selection + validation
   - Per-video processing orchestration
   - Callback creation + result management
   - **Moves**: ~40 methods

6. **RecordingCoordinator**
   - Recording start/stop
   - Live camera analysis
   - Arduino trigger integration
   - **Moves**: ~9 methods

### Option 2: 9-Coordinator Architecture (Modular)
More granular separation of concerns:
- HardwareCoordinator
- ModelCoordinator
- WeightCoordinator (separate from ModelCoordinator)
- ArenaCoordinator (with CalibrationCoordinator as sub-service)
- ProcessingModeCoordinator (separate from ProcessingCoordinator)
- BatchProcessingCoordinator
- LiveCameraCoordinator (separate from RecordingCoordinator)
- DiagnosticCoordinator
- ReportingCoordinator

---

## 5. ORCHESTRATION FLOW (Current)

```
MainViewModel (orchestrator)
  ├─ state_manager (observable, thread-safe)
  ├─ ui_event_bus (publish/subscribe)
  ├─ project_manager (project state)
  ├─ detector_service (detector instance)
  ├─ video_processing_service (frame processor)
  ├─ analysis_service (metrics calculation)
  ├─ recording_service (Parquet/MP4 output)
  └─ live_camera_service (live sessions)
```

After refactoring:
```
MainViewModel (thin orchestrator)
  ├─ HardwareCoordinator
  │   ├─ detector_service
  │   ├─ arduino_manager
  │   └─ live_camera_service
  ├─ ModelCoordinator
  │   ├─ weight_manager
  │   ├─ model_service
  │   └─ detector_service
  ├─ ArenaCoordinator
  │   ├─ project_manager (zones)
  │   └─ calibration logic
  ├─ ProcessingCoordinator
  │   ├─ video_processing_service
  │   ├─ analysis_service
  │   ├─ recording_service
  │   └─ state_manager
  └─ RecordingCoordinator
      ├─ recording_service
      └─ arduino_manager
```

---

## 6. EXTRACTION CHECKLIST

**Phase 1**: Extract easiest first (HardwareCoordinator, ArenaCoordinator)
**Phase 2**: Extract complex logic (ProcessingCoordinator, ModelCoordinator)
**Phase 3**: Extract remaining (RecordingCoordinator, DiagnosticCoordinator)
**Phase 4**: Thin down MainViewModel → pure orchestrator

Each coordinator should:
- Have single responsibility
- Accept dependencies via `__init__`
- Publish events to ui_event_bus
- Update state via state_manager (not directly)
- Have comprehensive tests

