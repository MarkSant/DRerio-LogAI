# God Objects Analysis Report - ZebTrack-AI Codebase

**Analysis Date:** November 5, 2025
**Codebase:** ZebTrack-AI (DRerio LogAI)
**Thoroughness Level:** Very Thorough
**Total Files Analyzed:** 56,160 lines of Python code

---

## Executive Summary

The ZebTrack-AI codebase exhibits **5 critical/high-severity God Objects** that violate the Single Responsibility Principle. These classes have accumulated excessive responsibilities due to feature accumulation and incomplete refactoring efforts. The most severe violations are in the view layer (ApplicationGUI) and the main orchestrator (MainViewModel).

| Severity | Count | Classes |
|----------|-------|---------|
| **CRITICAL** | 2 | ApplicationGUI, MainViewModel |
| **HIGH** | 2 | ProjectManager, VideoProcessingService |
| **MEDIUM-HIGH** | 3 | Reporter, StateManager, ProjectWorkflowService |

---

## 1. CRITICAL: ApplicationGUI (ui/gui.py)

**Severity:** CRITICAL (100/100)

### Metrics
- **File Size:** 9,951 lines
- **Class Methods:** 322 methods (!)
- **Dependencies:** 4 major components (controller, event_bus, settings, root)
- **Cyclomatic Complexity:**
  - `__init__`: ~691 lines with 104 control flow statements (CC ~30)
  - Multiple large drawing/update methods with CC > 10

### Responsible for These Unrelated Concerns

1. **UI Layout Creation (20 methods)**
   - `_create_menu_bar`, `_create_welcome_frame`, `_create_main_control_frame`
   - `_create_main_controls_tab`, `_create_pipeline_processing_tab`
   - `_create_roi_analysis_tab`, `_create_analysis_tab_widget`
   - Complete view hierarchy construction

2. **Event Handling & Dispatching (55 methods)**
   - `_handle_*` event handlers for 50+ different event types
   - `_handle_navigate_to_*`, `_handle_update_*`, `_handle_display_*`
   - Event subscription and binding logic
   - Complete event-to-UI mapping

3. **State Display & Synchronization (41 methods)**
   - `_refresh_*` methods for all UI components
   - `_refresh_project_overview`, `_refresh_zone_indicators`
   - `_refresh_video_selector_tree`, `_refresh_pipeline_video_table`
   - Live synchronization of all state changes to UI

4. **Canvas Drawing & Visualization (29 methods)**
   - `_draw_zones_on_frame`, `_draw_detections_on_frame`
   - `_draw_interactive_polygon`, `_draw_bg_image_to_canvas`
   - Coordinate transformation and annotation logic
   - Complete drawing pipeline

5. **Dialog Management (3+ methods)**
   - Open/close dialogs
   - Template save dialogs
   - Pending videos dialogs

6. **Tree View/Table Management**
   - Video hierarchy building and updates
   - Contextual menus
   - Selection handling

### Problems Identified

1. **Massive Initialization**
   - __init__ is 691 lines long with 104 control statements
   - Creates dozens of UI components inline
   - Initializes 30+ instance variables

2. **Mixed Concerns**
   - UI widget creation mixed with event handling
   - Drawing logic mixed with data transformation
   - State synchronization mixed with visualization

3. **Tight Coupling**
   - Direct reference to controller (MainViewModel)
   - Mixes business logic with display logic
   - Hard to test individual UI components

4. **Code Duplication**
   - Multiple similar update patterns
   - Repeated coordinate transformation code
   - Similar event handler patterns duplicated

### Recommended Splits

```
ApplicationGUI (Main Window Manager - 150 methods, 2000 lines)
├── CanvasManager (Drawing/Visualization - 29 methods, 800 lines)
├── TabManager (Tab Management - 5 methods, 300 lines)
├── EventDispatcher (Event Routing - 55 methods, 1200 lines)
├── StateDisplay (UI Sync/Updates - 41 methods, 1500 lines)
├── LayoutBuilder (UI Creation - 20 methods, 1200 lines)
└── DialogManager (Dialog Coordination - 10 methods, 400 lines)
```

**Estimated Effort:** 20-25 days to refactor properly

---

## 2. CRITICAL: MainViewModel (core/main_view_model.py)

**Severity:** CRITICAL (140/100)

### Metrics
- **File Size:** 5,588 lines
- **Class Methods:** 151 methods
- **Dependencies Injected:** 13 major components
  - `root`, `event_bus`, `state_manager`, `ui_coordinator`
  - `settings_obj`, `project_manager`, `project_workflow_service`
  - `weight_manager`, `model_service`, `detector_service`
  - `video_processing_service`, `analysis_service`, `recording_service`
  - `live_camera_service` (optional)
  - Plus: `test_sync_event`

- **Cyclomatic Complexity:**
  - `bind_events`: 165 lines, ~26 control flow statements (CC ~15)
  - Multiple processing methods: CC > 20

### Responsible for These Unrelated Concerns

1. **Project Management (25 methods)**
   - `create_project_workflow`, `open_project_workflow`
   - `_setup_zones_from_project`, `_apply_wizard_detector_overrides`
   - Project creation, loading, saving
   - Wizard data integration

2. **Video Processing Orchestration (25 methods)**
   - `_classify_candidate_videos`, `_collect_params_from_single_video`
   - `_create_processing_callbacks`, `_create_processing_context`
   - `_determine_processing_mode`, `_run_analysis_pipeline`
   - Complete video processing pipeline management

3. **Detector & Model Setup (25 methods)**
   - `setup_detector`, `_initialize_diagnostic_yolo_model`
   - `_initialize_diagnostic_openvino_model`
   - Weight management, model selection
   - Detector configuration and restoration

4. **Recording Control (9 methods)**
   - `trigger_recording`, `start_recording`, `stop_recording`
   - `_schedule_recording`, `_ensure_zones_before_recording`
   - Recording service initialization and callbacks

5. **Hardware Integration (8 methods)**
   - Arduino setup and control
   - `setup_arduino`, `on_arduino_status_change`
   - `log_arduino_event`, `on_arduino_command_sent`
   - Hardware event handling

6. **Analysis Orchestration (10 methods)**
   - Analysis pipeline coordination
   - Report generation
   - Analysis metadata handling
   - Results registration

7. **Event Handling (3+ methods)**
   - Event dispatcher creation
   - Event handler registration
   - Event binding

8. **General Orchestration (55+ methods)**
   - Thread management, shutdown sequences
   - Diagnostic workflows
   - State restoration
   - Many utility methods

### Problems Identified

1. **Excessive Dependencies (13 parameters)**
   - Constructor is a "service locator anti-pattern"
   - Each dependency represents a distinct responsibility area
   - Makes testing extremely difficult (need to mock all 13)
   - Creates high coupling to the entire application

2. **Multiple Unrelated Domains**
   - UI coordination + Video processing + Hardware + Recording
   - Should be split into separate service layers
   - Clear separation already exists in architecture but not enforced

3. **God Object Orchestrator**
   - Acts as master controller coordinating multiple services
   - Services are properly designed, but VM wraps them all
   - VM adds its own business logic on top

4. **Threading Complexity**
   - Manages multiple worker threads
   - Diagnostics workflow is complex (130+ lines)
   - State synchronization across threads

### Recommendations for Splitting

The CLAUDE.md documentation already identifies this issue. Suggested refactoring:

```
MainViewModel (Core Orchestrator - 60-80 methods, ~1200 lines)
├── ProjectWorkflowCoordinator (20 methods, 400 lines) [EXISTING: ProjectWorkflowService]
├── VideoProcessingCoordinator (25 methods, 600 lines) [EXTRACT from current code]
├── DetectorCoordinator (20 methods, 400 lines) [EXTRACT from current code]
├── RecordingCoordinator (15 methods, 300 lines) [EXTRACT from current code]
└── HardwareCoordinator (10 methods, 200 lines) [EXTRACT from current code]
```

**Key Actions:**
1. Extract video processing logic → VideoProcessingCoordinator
2. Extract detector/model setup → DetectorCoordinator
3. Extract recording control → RecordingCoordinator
4. Extract hardware integration → HardwareCoordinator
5. Reduce MainViewModel to pure orchestration (delegate to coordinators)
6. Reduce constructor dependencies from 13 to 5-6

**Estimated Effort:** 30-35 days

---

## 3. HIGH: ProjectManager (core/project_manager.py)

**Severity:** HIGH (60/100)

### Metrics
- **File Size:** 2,795 lines
- **Class Methods:** 79 methods
- **Dependencies:** 2 (StateManager, Settings)
- **Cyclomatic Complexity:**
  - `__init__` method for ProjectManager: 1,254 lines (!!!)
  - This is not the constructor but the actual class definition
  - `add_video_batch`: 206 lines, ~60 control flow statements
  - `load_project`: 175 lines, ~45 control flow statements
  - `_save_settings_snapshot`: 162 lines, ~34 control flow statements

### Responsible for These Unrelated Concerns

1. **Project File I/O**
   - `create_new_project`, `load_project`, `save_project`
   - Settings snapshot management
   - Parquet file handling and registration

2. **Video Inventory Management**
   - `add_video_batch`, `get_all_videos`
   - `update_video_status`, `reset_all_video_statuses`
   - Video entry lookup and filtering
   - Metadata resolution

3. **Zone/ROI Management**
   - `save_zone_data`, `load_zone_data`, `clear_zone_data_for_video`
   - Zone template management (save, load, import, list)
   - Zone deduplication and validation
   - 20+ zone-related methods

4. **Analysis Profile Management**
   - `get_analysis_profiles`, `resolve_analysis_profile`
   - Design metadata extraction (subjects, groups, days)
   - Profile matching and resolution

5. **Parquet Import/Export**
   - `import_parquets_from_wizard`
   - Parquet file validation
   - Trajectory data handling

6. **Asset Management**
   - `can_remove_asset`, `remove_asset`
   - `_video_has_asset`, `_remove_*_asset` (4 methods for different asset types)
   - Output path resolution

### Problems Identified

1. **Multiple Domain Models**
   - Projects, Videos, Zones, ROIs, Templates, Assets, Profiles
   - Each domain has 8-15 methods
   - Should be separate classes/modules

2. **Complex Initialization**
   - The apparent "class" definition is actually very large
   - Many internal helper methods
   - Lots of validation and normalization

3. **Zone Management Duplication**
   - Zone entry resolution has multiple path variants
   - Deduplication logic is complex
   - Multiple redundant checks

4. **Missing Abstractions**
   - No ROI Template abstraction (has ROITemplateManager but tightly integrated)
   - No Video Entry abstraction (dicts with unclear schema)
   - No Analysis Profile abstraction

### Recommended Splits

```
ProjectManager (Main - 30 methods, 600 lines) [Facade]
├── ProjectFileManager (15 methods, 400 lines) [I/O only]
├── VideoInventoryManager (15 methods, 500 lines) [Video CRUD]
├── ZoneManager (20 methods, 700 lines) [Zone/ROI/Template]
├── AnalysisProfileResolver (10 methods, 300 lines) [Profile matching]
├── ParquetManager (8 methods, 250 lines) [Parquet import/validation]
└── AssetManager (8 methods, 200 lines) [Asset cleanup]
```

**Estimated Effort:** 15-20 days

---

## 4. HIGH: VideoProcessingService (core/video_processing_service.py)

**Severity:** HIGH (60/100)

### Metrics
- **File Size:** 1,513 lines
- **Class Methods:** 27 methods
- **Dependencies:** 6 major + 4 positional args (root, view, cancel_event, settings_obj)
- **Cyclomatic Complexity:**
  - `_collect_params_from_single_video`: 641 lines, ~100 control flow statements (CC ~40!)
  - This single method is a God Method

### Responsible for These Unrelated Concerns

1. **Frame Display**
   - `display_initial_frame`
   - Initial frame extraction and display

2. **Path Resolution**
   - `resolve_results_path`
   - Output directory logic

3. **Video Frame Loading**
   - `load_trajectory_dataframe`
   - Parquet file loading with error handling

4. **Progress Callback Creation**
   - `create_progress_callback`
   - Progress tracking infrastructure

5. **Detector Integration**
   - Frame detection coordination
   - Detector callback handling

6. **Analysis Parameter Collection (641 lines in one method!)**
   - `_collect_params_from_single_video` is monstrous
   - Handles single video parameter collection
   - Collects from both project and single-video configs
   - Complex metadata resolution

7. **Result Processing**
   - Result path resolution
   - Output validation
   - Analysis metadata scheduling

8. **Analysis Pipeline Orchestration**
   - `run_tracking_if_needed`
   - `process_single_video`
   - `process_frame_source`
   - Complete analysis orchestration

### Problems Identified

1. **Massive God Method**
   - `_collect_params_from_single_video`: 641 lines in a single method
   - ~100 control flow branches (CC ~40)
   - Extremely difficult to test
   - Should be broken into 5-10 smaller methods

2. **Multiple Concerns Mixed**
   - Parameter collection mixed with validation
   - Metadata enrichment mixed with database lookups
   - UI coordination mixed with data collection

3. **Tight UI Coupling**
   - Direct reference to `view` (ApplicationGUI)
   - UI event scheduling in service layer
   - Violates separation of concerns

### Recommended Splits

```
VideoProcessingService (Facade - 8 methods, 250 lines)
├── FrameSourceManager (5 methods, 200 lines)
├── ProcessingParameterBuilder (10 methods, 400 lines) [Break up the 641-line method]
├── AnalysisCoordinator (8 methods, 300 lines)
└── ResultsManager (6 methods, 200 lines)
```

**Focus:** Break down `_collect_params_from_single_video` into:
- `_resolve_video_metadata`
- `_build_detector_params`
- `_build_calibration_params`
- `_build_analysis_params`
- `_build_recording_params`
- `_validate_parameters`

**Estimated Effort:** 10-15 days

---

## 5. MEDIUM-HIGH: Reporter (analysis/reporter.py)

**Severity:** MEDIUM-HIGH (40/100)

### Metrics
- **File Size:** 1,412 lines
- **Class Methods:** 29 methods
- **Cyclomatic Complexity:**
  - `export_summary_data`: 442 lines, ~87 control flow statements
  - `_roi_geometry_to_cm`: 195 lines, ~45 control flow statements
  - `_prepare_report_document`: 183 lines, ~35 control flow statements

### Responsible for These Unrelated Concerns

1. **Data Transformation**
   - `_create_tidy_dataframe`
   - `_standardize_tidy_dataframe`
   - `_collect_roi_metrics`

2. **Trajectory Visualization**
   - `generate_trajectory_plot`
   - `generate_heatmap`
   - `generate_roi_reference_plot`

3. **Behavioral Analysis Plots**
   - `generate_angular_velocity_plot`
   - `generate_position_vs_time_plot`
   - `generate_cumulative_distance_plot`

4. **Report Generation**
   - `export_individual_report`
   - `export_individual_report_step_by_step`
   - `export_project_report`
   - Template handling

5. **Excel/Parquet Export**
   - `export_summary_data`
   - Format handling
   - Data standardization

6. **Geometry Transformations**
   - `_roi_geometry_to_cm`
   - `_warp_trajectory_if_needed`
   - Coordinate system conversions

### Problems Identified

1. **Two Very Large Methods**
   - `export_summary_data`: 442 lines (CC ~50)
   - `_roi_geometry_to_cm`: 195 lines (CC ~20)

2. **Mixed Concerns**
   - Data transformation mixed with visualization
   - Report generation mixed with plotting
   - Geometry transformations mixed with metrics

3. **Threading & Parallel Processing Embedded**
   - `_generate_plots_parallel` with ThreadPoolExecutor
   - Threading logic in service layer

### Recommended Splits

```
Reporter (Facade - 8 methods, 300 lines)
├── TrajectoryCleaner (3 methods, 150 lines) [Warp, coordinate transform]
├── MetricsCollector (8 methods, 350 lines) [Tidy data, ROI metrics]
├── PlotGenerator (8 methods, 500 lines) [All plot generation]
├── ReportBuilder (6 methods, 400 lines) [DOCX report generation]
└── DataExporter (4 methods, 200 lines) [Excel/Parquet export]
```

**Estimated Effort:** 8-10 days

---

## 6. MEDIUM-HIGH: StateManager (core/state_manager.py)

**Severity:** MEDIUM-HIGH (40/100)

### Metrics
- **File Size:** 1,184 lines
- **Main Class Methods:** 26 methods
- **Multiple State Classes:** 9 classes total
  - StateCategory, StateChange, ProjectState, DetectorState
  - RecordingState, ProcessingState, UIState, ApplicationState
  - StateManager

### Assessment

**Note:** StateManager is actually well-designed for its purpose. The apparent size is inflated by:
1. Multiple purpose-specific state classes (justified)
2. Observer pattern infrastructure (justified)
3. Comprehensive state synchronization (complex but necessary)

**Unlike the other God Objects, StateManager has good cohesion:**
- All methods relate to state management
- Clear separation between state classes
- Each state class manages one domain

**Minor Issues:**
- Could extract observer infrastructure to separate module
- Could reduce notification complexity

**Recommendation:** MONITOR, but not a priority for refactoring

---

## 7. MEDIUM-HIGH: ProjectWorkflowService (core/project_workflow_service.py)

**Severity:** MEDIUM-HIGH (20/100)

### Metrics
- **File Size:** 1,204 lines
- **Class Methods:** 17 methods
- **Dependencies:** 5 (ProjectManager, ModelService, StateManager, UICoordinator, Settings)

### Assessment

This is actually a good refactoring that extracted logic from MainViewModel. The service is well-focused on:
1. Project creation coordination
2. Project opening/restoration
3. Model settings application
4. Parameter validation

**Recommendation:** GOOD example of extraction; use as template for splitting others

---

## Summary Recommendations by Priority

### Phase 1 - CRITICAL (Do First)
1. **Split ApplicationGUI** (~25 days)
   - Extract CanvasManager (drawing logic)
   - Extract EventDispatcher (event routing)
   - Extract StateDisplay (synchronization)
   - Reduce from 322 to ~100 methods

2. **Extract from MainViewModel** (~35 days)
   - Create VideoProcessingCoordinator
   - Create DetectorCoordinator
   - Create RecordingCoordinator
   - Reduce from 151 to ~70 methods
   - Reduce dependencies from 13 to 6

### Phase 2 - HIGH (Do Next)
3. **Refactor ProjectManager** (~20 days)
   - Extract ProjectFileManager
   - Extract VideoInventoryManager
   - Extract ZoneManager
   - Reduce from 79 to ~30 methods

4. **Refactor VideoProcessingService** (~15 days)
   - Break down massive `_collect_params_from_single_video` method
   - Extract ProcessingParameterBuilder
   - Reduce from 27 to ~12 methods

### Phase 3 - MEDIUM (Backlog)
5. **Refactor Reporter** (~10 days)
   - Extract PlotGenerator
   - Extract ReportBuilder
   - Break down large export methods

### Phase 4 - MONITORING
6. **StateManager** - Monitor only, currently well-designed

---

## Detailed Metrics Table

| Class | Lines | Methods | Deps | CC Max | Severity | Days |
|-------|-------|---------|------|--------|----------|------|
| ApplicationGUI | 9,951 | 322 | 4 | ~30 | CRITICAL | 25 |
| MainViewModel | 5,588 | 151 | 13 | ~25 | CRITICAL | 35 |
| ProjectManager | 2,795 | 79 | 2 | ~40 | HIGH | 20 |
| VideoProcessingService | 1,513 | 27 | 6 | ~40 | HIGH | 15 |
| Reporter | 1,412 | 29 | 0 | ~50 | MED-HIGH | 10 |
| StateManager | 1,184 | 26 | 0 | ~10 | MED-HIGH | Monitor |
| ProjectWorkflowService | 1,204 | 17 | 5 | ~12 | MED-HIGH | Good |

**Total Refactoring Effort:** 100-125 days (2.5-3 months)

---

## Root Causes

1. **Incomplete Extraction:** Services exist (ProjectWorkflowService, WizardService) but coordinator logic still lives in MainViewModel
2. **Monolithic GUI:** ApplicationGUI combines layout, events, drawing, and state sync
3. **Feature Accumulation:** Classes grew to accommodate new features without refactoring
4. **Facade Pattern Needed:** Large classes should become facades delegating to focused components

---

## Prevention Strategies

1. **Enforce Method Count Limits:** Flag classes >50 methods in code review
2. **Limit Constructor Parameters:** Maximum 5-7 dependencies (currently violates with 13)
3. **Single Responsibility Checks:** Code reviews focused on concern separation
4. **Extract Services Early:** Refactor at 1000 lines, not 5000+
5. **Component Tests:** Test individual UI components separately from the main window

