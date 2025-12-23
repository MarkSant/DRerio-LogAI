# Changelog

All notable changes to DRerio LogAI (zebtrack) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### 🟢 New Features

#### Multi-Aquarium v2 Improvements (Phase 1-5)

##### Phase 1: Foundation Enhancements
- **ROI Cropping**: `_crop_aquarium_region()` for per-aquarium frame extraction
- **Uncertainty Metrics**: Added `uncertainty` and `bbox_iou` columns to Parquet output
- **Export Formats**: New `export_feather()`, `export_r_script()`, `export_python_script()` in Reporter
- **Thigmotaxis**: Added thigmotaxis metrics calculation in DataTransformer

##### Phase 2: Performance Optimizations
- **Parallel Detection**: `detect_partitioned_parallel()` with ThreadPoolExecutor (~30-40% speedup)
- **Batch Inference**: `detect_batch()` for offline multi-frame batch processing
- **Metrics Cache**: Verified MetricsCache for analysis result caching

##### Phase 3: UI/UX Improvements
- **Side-by-Side Preview**: `create_side_by_side_preview()` in CanvasManager for aquarium comparison
- **Enhanced Validation**: `validate_multi_aquarium_config()` now returns warnings (polygon overlap, small areas)

##### Phase 4: Robustness
- **Tracking Validation**: Multi-aquarium track ID validation (ID bounds, large jumps)
- **Gap Detection**: Per-aquarium frame coverage analysis with gap statistics
- **Error Recovery**: Graceful handling when one aquarium fails in parallel detection

##### Phase 5: Event System
- **New Events**: `ZONE_MULTI_AUTO_DETECT_SUCCESS`, `ZONE_MULTI_AUTO_DETECT_FAILED`, `ZONE_AQUARIUM_CONFIG_UPDATED`
- **Multi-Auto-Detect Handler**: `ProcessingCoordinator._handle_multi_auto_detect()`
- **Config Update Handler**: `ProjectLifecycleCoordinator._handle_aquarium_config_updated()`

#### Zone Copy/Paste/Delete Context Menu
- **NEW**: Right-click context menu on video tree in Zone Configuration tab
- Copy zones from one video and paste to others (arena + all ROIs)
- Delete zones option to clear all zones from a video
- Automatic video tree status update after paste/delete operations
- Uses EventBusV2 `VIDEO_TREE_REFRESH_REQUESTED` for consistent UI updates

#### Finish Drawing Button
- **NEW**: Added "✓ Finalizar Desenho" button for completing polygons
- Alternative to double-click for users who prefer button interaction
- Visible in interactive buttons frame during polygon drawing mode

#### Improved Zone Drawing Colors
- **UI**: Changed zone drawing colors for better visibility on video backgrounds
- Cyan (#00FFFF) → Dark Teal (#008B8B) for arena outlines
- Yellow (#FFFF00) → Goldenrod (#DAA520) for interactive polygons/elastic lines
- Better contrast and readability on light-colored videos

#### Drawing Flickering Fix
- **UI**: Added 16ms debounce (~60fps) to `on_canvas_motion()` in event_handler.py
- Reduces visual flickering during polygon drawing
- Smoother elastic line animation while moving mouse

#### Improved Word Reports (Quality & Robustness)
- **NEW**: Added "Appendix: Trajectory Validation" section to Word reports.
- Includes technical summary table: Total Frames, Frame Range, Temporal Coverage (%), Unique Track IDs, and Gap counts.
- Displays detailed validation warnings (teleportation, gaps, arena violations) directly in the document.
- **UI**: Removed redundant blank pages between trajectory and heatmap figures for a more compact layout.

### 🔴 Bug Fixes

#### Simultaneous Multi-Aquarium Report Generation Fix
- **CRITICAL**: Fixed issue where simultaneous 2-aquarium analysis in single-video mode would stop after tracking without generating Word/Excel reports.
- `ProcessingCoordinator.on_video_completed` now robustly detects output folders (`aquarium_0`, `aquarium_1`) even when the results directory is calculated dynamically.
- Ensures all analysis artifacts (Parquet summaries, Word reports, Excel tables) are generated for both aquariums upon completion.

#### Multi-Aquarium Reporting Fix
- **CRITICAL**: Fixed regression where Aquarium 1 would erroneously use Aquarium 0's zones and background in reports.
- `ProcessingCoordinator` now correctly prioritizes `MultiAquariumZoneData` for per-aquarium report generation.

#### Background Image "Gray Screen" Fix (Windows)
- **CRITICAL**: Fixed background images not displaying in reports on Windows when paths contained spaces or special characters.
- Switched to robust `cv2.imdecode` method for reading background frames.
- Standardized single-aquarium flow to extract cropped background PNGs, consistent with multi-aquarium logic.

#### Trajectory Alignment Fix
- **HIGH**: Fixed trajectory misalignment in cropped reports.
- Normalization logic now drops existing CM columns to force recalculation relative to the aquarium crop origin (0,0).
- Prevents trajectories from "floating" outside the visible aquarium area in Word reports.

#### Batch Processing Video Frame Display Fix
- **CRITICAL**: Fixed frames not displaying during batch processing
- Added missing `update_processing_state(is_processing=True)` call in `process_pending_project_videos()`
- This triggers `UI_NAVIGATE_TO_ANALYSIS_VIEW` event to set `analysis_active = True`
- Frames now correctly display in the Analysis tab during batch video processing

#### Batch Processing Per-Video Zone Data Fix
- **CRITICAL**: Fixed zones/ROIs not being loaded for each video in batch processing
- Modified `_load_zones_for_eligible_videos()` to serialize zone data into each `video_info` dict
- Added `_get_zone_data_for_video()` method in ProcessingWorker for per-video zone lookup
- Worker now uses video-specific zones instead of global default zones
- Zones and ROIs now display correctly during batch processing with proper tracking

#### Batch Processing Results Directory Fix
- **CRITICAL**: Fixed results (parquet, reports) saving to wrong directory in batch processing
- Worker now creates per-video results directory: `{video_name}_results/` next to each video
- Trajectory parquet, arena/ROI parquets, and reports now save in correct location
- `_generate_summaries_impl` can now find the trajectory files correctly

#### Batch Processing Task Status Display Fix
- **HIGH**: Fixed Analysis tab not showing video progress (X de Y), group, day, subject info
- Updated `ProcessingCallbacks.on_progress` signature to include `index`, `total`, `experiment_id`
- Worker `monitor_loop` now passes all progress fields to callback
- `on_progress` callback now publishes `UI_UPDATE_ANALYSIS_TASK_STATUS` event
- Analysis tab displays: "Vídeo X de Y — ExperimentID • Etapa"

#### Batch Processing Selected Videos Fix
- **HIGH**: Fixed batch processing ignoring pre-selected videos from context menu
- Removed duplicate `PROJECT_PROCESS_VIDEOS` handler from `MainViewModel`
- `ProcessingCoordinator` now sole handler, correctly receives `video_paths` parameter
- "Processar Vídeos Selecionados" context menu action now works correctly

### 🟠 Visualization & Report Fixes

#### Trajectory Plot Coordinate System Fix
- **CRITICAL**: Fixed Y-axis inversion in trajectory plots (`visualization_generator.py`)
- Frame now vertically flipped with `cv2.flip(frame_rgb, 0)` for Cartesian alignment
- Changed matplotlib `origin` from "upper" to "lower" for correct coordinate display
- Fixed `extent` calculation using `video_height_for_transform` from BehavioralAnalyzer
- Y-coordinates now display correctly (0 at bottom, height at top)

#### ROI Color Consistency Fix
- **HIGH**: Fixed BGR→RGB color conversion for ROI colors in visualizations
- `analysis_control_view_model.py` now converts BGR tuples to RGB for matplotlib
- Colors in trajectory plots and heatmaps match actual ROI colors defined in zones

#### Word Report Layout Improvements
- **MEDIUM**: Increased image sizes from 3.2" to 5.5" for better readability
- Added page breaks before "Heatmap" and "Cumulative Distance" figures
- Ensures 2 figures per page layout with titles always adjacent to images
- Fixed "Chart" → "Figure" translation in Portuguese reports

#### Zone List Color Display Enhancement
- **UI**: Zone list now displays color names in Portuguese instead of hex codes
- Colors shown with colored text styling (Treeview tags)
- Arena principal also shows "Ciano" with colored text
- Added `_get_color_name_from_bgr()` helper method for color name mapping

### 🟡 Minor Improvements

#### ByteTracker Fallback Log Level
- Changed ByteTracker fallback message from WARNING to DEBUG
- Reduces log noise when simple tracker is used as expected fallback

#### Summary Parquet Generation
- Added summary parquet file creation in analysis workflow
- Trajectory registration now includes results_dir and experiment_id in hierarchy

---

## [2.2.0] - 2025-12-XX

### 🔴 Critical Fixes

#### Fixed Camera Thread Deadlock (Atomic Shutdown Pattern)
- **CRITICAL**: Eliminated camera thread deadlocks during shutdown in `io/camera.py`
- Implemented single ownership pattern: only `_reader_thread` calls `cap.release()` in finally block
- `release()` method now only signals `_shutdown_requested` Event and joins thread with 3s timeout
- Prevents race condition where main thread and reader thread both accessed VideoCapture object
- Shutdown now completes cleanly in <3 seconds with no zombie threads

#### VideoProcessingService UI Decoupling
- **CRITICAL**: Decoupled `VideoProcessingService` from tkinter and ApplicationGUI dependencies
- Removed `view` and `root` parameters from constructor (10 params → 8 params)
- Error handling now publishes `UIEvents.ERROR_OCCURRED` instead of calling `view.show_error()` directly
- ApplicationGUI subscribes to error events and schedules UI updates via `root.after()`
- Enables headless testing and better separation of concerns

#### Graceful Shutdown (Removed Hard Exit)
- **MEDIUM**: Removed `sys.exit(70)` forced termination when camera thread fails to shut down
- Publishes `UIEvents.ERROR_OCCURRED` with fatal error message for user notification
- Allows natural shutdown flow via `root.destroy()` instead of process kill
- Better cleanup and resource management during abnormal shutdown

### 🟢 Performance & Optimization

#### EventBus Performance Monitoring (100ms Fixed Threshold)
- **HIGH**: Added performance monitoring to `event_bus_v2.py` to identify UI-blocking handlers
- Measures handler execution time with `time.perf_counter()`
- Logs warning when handler exceeds 100ms fixed threshold (not configurable)
- Creates healthy pressure to move I/O operations to background threads instead of hiding with config
- Warnings include event name, handler name, elapsed time, and tech debt message

#### Dynamic Frame Skip Calibration
- **PERFORMANCE**: Implemented warm-up + 1 seek calibration in `video_processing_service.py`
- Measures single seek to frame 100 during `_create_video_context()`
- Calculates optimal skip threshold: 120 (<10ms), 80 (<50ms), or 60 (≥50ms) based on storage speed
- Added `_seek_to_frame()` helper using hybrid grab()/set() strategy
- Adapts to hardware capabilities (fast SSD vs network storage)
- Logged for debugging: `seek_time_ms`, `skip_threshold`

#### Memory Optimization (Column Subset Copy)
- **MEMORY**: Reduced memory usage during trajectory analysis by 40-60%
- Added `REQUIRED_TRAJECTORY_COLUMNS` constant in `analysis/analysis_service.py`
- Only copies 9 required columns instead of full DataFrame (15+ columns)
- Faster DataFrame operations and better cache locality
- Estimated savings: ~24MB per 500K-row trajectory

### 🧪 Testing Infrastructure

#### Wait Condition Helpers
- **NEW**: Created `tests/utils/wait_helpers.py` with robust polling-based wait utilities
- Eliminates flaky tests from `time.sleep()` usage
- Provides `wait_for_condition()`, `wait_for_event()`, `wait_for_thread_exit()`, `assert_condition_met()`
- Polling-based approach works reliably across different CPU speeds

#### Nightly Stress Test Workflow
- **NEW**: Created `.github/workflows/stress-tests.yml` scheduled for 2 AM UTC daily
- Threading stress tests (10x repetition of slow tests)
- Memory leak detection with memray profiling
- Flakiness detection (3x full suite runs)
- Auto-creates GitHub Issues on failure with labels and run links
- Keeps `ci.yml` fast for PR feedback

### Changed
- Updated `VideoContext` dataclass to include `skip_threshold` field (default 60)
- Modified `__main__.py` Composition Root to remove view/root from VideoProcessingService instantiation
- ApplicationGUI now subscribes to `UIEvents.ERROR_OCCURRED` in `__init__()`

### Documentation
- Updated `BUGFIX_SUMMARY.md` with v2.2 architectural improvements
- Added detailed explanations for all 8 major changes

---

## [2.1.0] - 2025-11-XX

### 🔄 Event-Driven Architecture (v4.0 Migration - Phase 2)
**Status**: IN PROGRESS (Dual Mode Compatibility)

#### Added
- **Event Bus V2** (`ui/event_bus_v2.py`): Foundation for Event-Driven Architecture v4.0
  - Type-safe event system with `UIEvents` enum (20+ event types)
  - Thread-safe publish/subscribe pattern with RLock
  - Event payload validation with dataclass `Event`
- **ZONES_UPDATED Event**: Migrated `update_zone_listbox()` from direct calls to events
  - 4 publishers now emit ZONES_UPDATED event:
    - `DialogManager.import_and_apply_template()`
    - `ROITemplateManager.apply_template()`
    - `CanvasRenderer.redraw_zones()`
    - `PolygonDrawingService` (ArenaCompletionStrategy + ROICompletionStrategy)
  - `CanvasManager` subscribes to ZONES_UPDATED and processes updates
- **VIDEO_TREE_REFRESH_REQUESTED Event**: Migrated `_populate_video_selector_tree()` from direct calls to events
  - 3 publishers now emit VIDEO_TREE_REFRESH_REQUESTED event:
    - `ZoneControlBuilder._refresh_video_tree_dual_mode()` (2 call sites: refresh button + initialization)
    - `ProjectViewManager._build_readiness_snapshot()`
  - `ProjectViewManager` subscribes to VIDEO_TREE_REFRESH_REQUESTED and processes updates
- **READINESS_SNAPSHOT_UPDATED Event**: Migrated `apply_pending_readiness_snapshot()` from direct calls to events
  - 1 publisher now emits READINESS_SNAPSHOT_UPDATED event:
    - `DialogManager.ask_reuse_zones()`
  - `ProjectViewManager` subscribes to READINESS_SNAPSHOT_UPDATED and processes updates
- **POLYGON_EDIT_REQUESTED Event**: Migrated `setup_interactive_polygon()` from direct calls to events ✨ **NEW + BUG FIX**
  - **CRITICAL BUG FIX**: Method was calling non-existent `EventDispatcher.setup_interactive_polygon()`, making polygon editing non-functional
  - 2 publishers now emit POLYGON_EDIT_REQUESTED event:
    - `CanvasManager.edit_selected_zone_vertices()` (arena editing)
    - `CanvasManager.edit_selected_zone_vertices()` (ROI editing)
  - `CanvasManager` subscribes to POLYGON_EDIT_REQUESTED and implements the MISSING logic:
    - Populates `gui.edited_polygon_points` from polygon data
    - Calls `renderer.draw_interactive_polygon()` to draw interactive handles
  - **This migration restores broken functionality while modernizing the architecture**
- **Integration Tests**: 46 new tests validating event flows (+15 from previous 31)
  - `tests/integration/test_zones_updated_event.py` (12 tests)
  - `tests/integration/test_video_tree_refresh_event.py` (9 tests)
  - `tests/integration/test_readiness_snapshot_event.py` (10 tests)
  - `tests/integration/test_polygon_edit_requested_event.py` (15 tests) ✨ NEW
  - Tests dual mode compatibility, edge cases, multiple subscribers, empty/missing data, polygon shapes, and coordinate precision

#### Changed
- **GUI.__init__**: Now creates EventBusV2 instance (`self.event_bus_v2`)
- **Dependency Injection**: Event Bus V2 injected into 6 components:
  - `DialogManager(gui, event_bus_v2)`
  - `ROITemplateManager(project_manager, gui, event_bus_v2)`
  - `PolygonDrawingService(event_bus_v2)`
  - `CanvasManager(gui, event_bus_v2)`
  - `ProjectViewManager(gui, event_bus_v2)` ✨ NEW
  - `ZoneControlBuilder(gui, event_bus_v2)` ✨ NEW
- **Dual Mode Enabled**: All 10 publishers execute BOTH paths:
  - ZONES_UPDATED: 4 publishers (OLD + NEW paths)
  - VIDEO_TREE_REFRESH_REQUESTED: 3 publishers (OLD + NEW paths)
  - READINESS_SNAPSHOT_UPDATED: 1 publisher (OLD + NEW paths)
  - POLYGON_EDIT_REQUESTED: 2 publishers (OLD + NEW paths) ✨ NEW
  - Ensures backward compatibility during migration

#### Deprecated
- **`GUI.update_zone_listbox()`**: Marked with `@deprecated` decorator
  - Reason: "Use Event Bus V2 instead - migrating to Event-Driven Architecture v4.0"
  - Alternative: `event_bus_v2.publish(Event(UIEvents.ZONES_UPDATED, {'zone_data': zone_data}))`
  - Will be removed in v4.0 final (after dual mode phase)
- **`GUI._populate_video_selector_tree()`**: Marked with `@deprecated` decorator
  - Reason: "Use Event Bus V2 instead - migrating to Event-Driven Architecture v4.0"
  - Alternative: `event_bus_v2.publish(Event(UIEvents.VIDEO_TREE_REFRESH_REQUESTED, {'filter_text': filter_text}))`
  - Will be removed in v4.0 final (after dual mode phase)
- **`GUI.apply_pending_readiness_snapshot()`**: Marked with `@deprecated` decorator
  - Reason: "Use Event Bus V2 instead - migrating to Event-Driven Architecture v4.0"
  - Alternative: `event_bus_v2.publish(Event(UIEvents.READINESS_SNAPSHOT_UPDATED, {...}))`
  - Will be removed in v4.0 final (after dual mode phase)
- **`GUI.setup_interactive_polygon()`**: Marked with `@deprecated` decorator ✨ **NEW + BUG FIX**
  - Reason: "Use Event Bus V2 instead - migrating to Event-Driven Architecture v4.0"
  - Alternative: `event_bus_v2.publish(Event(UIEvents.POLYGON_EDIT_REQUESTED, {'polygon': polygon}))`
  - **NOTE**: This method was non-functional (calling non-existent EventDispatcher method). Migration restores functionality.
  - Will be removed in v4.0 final (after dual mode phase)

#### Documentation
- Updated `docs/EVENT_MAPPING.md` with implementation details for all 3 events
- Updated `docs/API_STABILITY.md` with deprecation notices

#### Next Steps (v4.0 Phase 2 Remaining)
- ✅ ~~Migrate `update_zone_listbox()` → `UIEvents.ZONES_UPDATED`~~ (COMPLETE - 4 publishers)
- ✅ ~~Migrate `_populate_video_selector_tree()` → `UIEvents.VIDEO_TREE_REFRESH_REQUESTED`~~ (COMPLETE - 3 publishers)
- ✅ ~~Migrate `apply_pending_readiness_snapshot()` → `UIEvents.READINESS_SNAPSHOT_UPDATED`~~ (COMPLETE - 1 publisher)
- ✅ ~~Migrate `setup_interactive_polygon()` → `UIEvents.POLYGON_EDIT_REQUESTED`~~ (COMPLETE - 2 publishers + BUG FIX) ✨ NEW
- Migrate 1-6 additional methods to events
  - Candidates: `_build_video_hierarchy_snapshot()`, `update_processing_stats()`, `update_social_summary()`, `update_analysis_task_status()`

#### Progress
- **4 of 11+** methods migrated to Event Bus V2 (**36% complete**)

## [3.0.0] - 2025-01-11

### 🔴 Breaking Changes
- **REMOVED**: Legacy thread system for Live projects completely removed
  - `_live_frame_capture_loop()` method removed from GUI
  - `_live_processing_loop()` method removed from GUI
  - `capture_thread` cleanup removed from MainViewModel
  - All Live camera functionality now exclusively through LiveCameraService

### 🧹 Code Cleanup
- Removed ~90 lines of deprecated legacy code
- Simplified project loading flow for Live projects
- Cleaner separation between video processing and live camera threads

## [2.1.0] - 2025-01-11

### 🔴 Breaking Changes
- **Live Projects**: Migrated to unified LiveCameraService architecture
  - Legacy thread system (`_live_frame_capture_loop`, `_live_processing_loop`) deprecated
  - Will be removed in v3.0

### ✨ Features
- Unified camera management for both analysis contexts
- Live projects now respect `camera_index` selected in wizard
- Intervals (analysis/display) properly respected in all workflows

### 🐛 Bug Fixes
- **CRITICAL**: Fixed Live projects always opening camera 0 (now uses wizard selection)
- **CRITICAL**: Fixed analysis intervals being ignored in single video workflow
- **CRITICAL**: Decoupled LiveCameraService from RecordingService (eliminated tight coupling)
  - Fixed multiple cameras activating simultaneously
  - Fixed wrong camera opening (respects camera_index correctly)
  - Fixed preview window delays and display issues
  - Eliminated unwanted side effects on global state
- **CRITICAL**: Fixed `TypeError` in LiveCameraService when starting recording
  - `Recorder.start_recording()` was being called with incorrect parameters
  - Changed from `folder_name`, `video_filename`, `parquet_filename`, `width`, `height`, `fps`
  - To correct parameters: `output_folder`, `frame_width`, `frame_height`, `zones`, `is_video_file`, `base_name`
  - Added regression test to prevent future parameter mismatches
- Fixed LiveStreamSource ignoring camera_index parameter
- Fixed FrameSourceFactory ignoring camera_index parameter

### 🚀 Performance
- Reduced thread count by 50% (4 → 2 threads)
- Reduced frame buffer memory by 50%
- Eliminated lock contention overhead

### 📝 Deprecated
- `gui._live_frame_capture_loop()` - Use LiveCameraService
- `gui._live_processing_loop()` - Use LiveCameraService
- Scheduled for removal: v3.0

### 🏗️ Architecture
- Unified `LiveCameraService` for both contexts:
  - Context 1: Single video analysis with camera
  - Context 2: Live projects with multi-session recording

## [Unreleased]

### Fixed
- **🎯 CRITICAL: Ghost Camera Detection**: Fixed wizard detecting "phantom" cameras that report `isOpened=True` but never return frames (e.g., virtual cameras, disconnected devices)
- **🎯 CRITICAL: Black Frame Detection**: Added detection of cameras that return completely black frames (virtual cameras with no input source)
- **🎯 CRITICAL: Camera Detection Hang**: Fixed wizard freezing during camera detection when encountering ghost cameras by adding 2-second timeout to frame capture test
- **🎯 Camera Name Mapping**: Disabled Windows PnP camera names due to unreliable index mapping between PowerShell enumeration and DirectShow device order
- **Live Camera Warmup**: Added 10-frame warmup period after camera initialization to fix preview lag (exposure/white balance adjustment time)
- **Live Camera Performance**: Added forced 1280x720 resolution for all cameras to prevent performance degradation with high-resolution cameras (e.g., 1920x1080)
- **Live Camera Error Handling**: Added user-friendly error dialog when camera fails to open with troubleshooting suggestions
- **Live Camera Recording**: Fixed `Recorder.start_recording()` TypeError by using correct parameter names (`output_folder`, `frame_width`, `frame_height` instead of deprecated `folder_name`, `width`, `height`)
- **Live Camera DirectShow**: Added DirectShow backend (`cv2.CAP_DSHOW`) to Camera class for Windows consistency with wizard detection
- **Detector Empty Polygon**: Fixed ValueError when zone data contains empty polygons in standalone analysis mode

### Changed
- **🎯 Camera Detection Logic**: Wizard now validates each camera can actually capture frames before adding to list (prevents index misalignment)
- **🎯 Camera Descriptions**: Changed from Windows device names to sequential numbering with resolution + brightness hints (e.g., "Câmera #1 [índice 1] - SD (640x480) (iluminação clara)")
- **Live Camera Resolution**: All cameras now forced to 1280x720 regardless of native resolution for consistent performance
- **Camera Detection Reliability**: Added consecutive failure tracking (stops after 3 consecutive ghost cameras to avoid long scans)
- **Camera Detection Range**: Reduced scan range from 0-9 to 0-5 for faster detection

### Removed
- **Live Camera Health Check**: Removed blocking 3-frame capture test that caused program hangs with slow/ghost cameras

## [v2.1.0] - 2025-11-12

### 🚨 **CRITICAL BUG FIX** - Pytest Hang on Windows

**PROBLEM RESOLVED**: Tests completed successfully (100% pass) but pytest hung indefinitely, causing VSCode and system to freeze and require manual restart. This critical issue blocked all development, testing, and coverage measurement.

### Fixed

- **Non-daemon threads blocking Python shutdown** ([#CRITICAL](https://github.com/MarkSant/ZebTrack-AI/commit/2372a4e))
  - Changed 4 worker threads to `daemon=True` in `LiveCameraService` and `GUI`
  - Allows Python to exit even if threads are running
  - Prevents indefinite hangs waiting for threads to terminate

- **Tkinter callbacks persisting after window destruction**
  - Added `pytest_sessionfinish` hook to force cleanup before exit
  - Cancels ALL pending `root.after()` callbacks (30+ locations in code)
  - Enhanced fixture cleanup in `tests/conftest.py`:
    - `tkinter_session_root`: Cancel callbacks before destroy
    - `tkinter_root`: Cancel Toplevel callbacks before destroy
    - `cleanup_threads`: New autouse fixture for thread leak detection

- **Added pytest-timeout plugin**
  - 300s (5 min) timeout per test
  - Thread-based method (safer on Windows)
  - Prevents infinite hangs in future

### Validation

- ✅ **2568 tests pass** (8 skip, 1 xfail) in **6min40s** - no hang
- ✅ **Coverage: 61%** measured successfully
- ✅ Works in terminal and VSCode Test Explorer
- ✅ System remains responsive throughout test execution

### Changed

- **Code quality improvements**
  - Ran `ruff check --fix` and `ruff format` on entire codebase
  - Fixed 37 auto-fixable linting issues
  - Reformatted 35 files for consistency

### Files Modified

- `tests/conftest.py` - Added hooks and enhanced fixtures
- `src/zebtrack/core/live_camera_service.py` - `daemon=True` for 2 threads
- `src/zebtrack/ui/gui.py` - `daemon=True` for 2 threads
- `pyproject.toml` - pytest-timeout configuration
- `poetry.lock` - Added pytest-timeout 2.4.0

---

## [2.0.0] - 2025-10-XX

### ⚠️ Breaking Changes

- Wizard live projects now require experimental design configuration (groups/days/subjects)
- Existing projects may need metadata added for full compatibility with new features

### ✨ New Features

**Architecture & Code Quality**:

- **Wizard Service Layer**: Extracted all wizard business logic to `zebtrack.core.wizard_service`
  - Centralized hardware detection (cameras, Arduino)
  - Reusable validation functions
  - Calculation utilities (experiment metrics, interval suggestions)
  - Fully testable independent of UI
  - **Hardware Detection Caching**: 30-second TTL cache for camera/Arduino detection (~5x faster on repeated calls)
- **Pydantic Data Models**: Type-safe validation for wizard data
  - `LiveConfigData`, `ExperimentalDesignData`, `CalibrationData`
  - Cross-field validations (e.g., external trigger requires Arduino)
  - Auto-generated error messages
- **Dialog Modularization**: Extracted 13 dialog classes from `gui.py` to `zebtrack.ui.dialogs/`
  - Reduced `gui.py` from 13,473 to 10,759 lines (~20% reduction)
  - Improved modularity, testability, and maintainability
  - Dialogs: CalibrationDialog, ManageWeightsDialog, ColorSelectionDialog, etc.
  - Resolved circular dependencies with `ui/format_utils.py`
- **Single-Video Mode Enhancement**: CalibrationDialog now hides "Project Preferences" section when in single-video analysis mode (no project context)

**Wizard Improvements** (from previous phases):

- Express/Advanced wizard modes
- External Trigger Mode for Arduino-based experiments
- Zone-based Arduino command triggers
- ROI inclusion rules (per-project configuration)
- Project template system (save/load wizard configurations)
- Unified preferences dialog with CollapsibleFrame UI

**Hardware Integration**:

- Arduino port detection with handshake validation
- Port descriptions (e.g., "COM3 - Arduino Uno")
- Connection test button with detailed error messages
- Camera detection with DirectShow backend (Windows) and early stopping optimization
- OpenCV log suppression during detection

**UI Enhancements**:

- NumberInput widget for intuitive numeric entry (+/- buttons)
- CollapsibleFrame widget for organized UI sections
- Treeview color harmonization (consistent green/yellow/red indicators)
- Interactive regex examples in CustomRegexDialog
- Improved tooltip coverage (100% of wizard fields)

### 🔧 Improvements

- **Performance**: Hardware detection caching reduces wizard navigation lag
  - Camera detection: ~5x faster on repeated calls (cached for 30 seconds)
  - Arduino port scanning: Instant results when navigating back/forward in wizard
  - Manual cache clearing available via `WizardService.clear_hardware_cache()`
- Model selection now available for live projects
- Configurable analysis/display intervals per project
- Automatic camera/Arduino detection with status feedback
- Intelligent suggestions (e.g., analysis interval based on FPS)
- Validation moved from UI to service layer (better testability)
- Removed legacy `LiveConfigDialog` (replaced by wizard `LiveConfigStep`)
- Code organization: Major cleanup with dialog extraction reducing `gui.py` complexity

### 📝 Documentation

- **NEW**: `docs/DEVELOPER_GUIDE_WIZARD.md` - Comprehensive wizard architecture guide
  - Service layer patterns
  - Pydantic model usage
  - How to add new wizard steps
  - Testing strategies
  - Best practices and anti-patterns
- **UPDATED**: `docs/WIZARD_LIVE_IMPROVEMENTS.md` - Phase 0-4 improvements
- **UPDATED**: `CLAUDE.md` - Project instructions with v2.0 features

### 🧪 Testing

- **712 tests passing** (24 new tests, 0 regressions)
  - 16 E2E tests for WizardService integration (`tests/ui/wizard/test_wizard_live_e2e.py`)
  - 8 hardware caching tests (`tests/test_wizard_service_caching.py`)
- Service layer fully unit tested
- Wizard steps validated with integration tests
- Code coverage maintained at 70%+
- Removed 1 redundant skipped test (architectural rule already enforced by other tests)

### 🐛 Bug Fixes

- Fixed line length violations in `project_manager.py`
- Reduced cyclomatic complexity in `gui.py` (_VideoPathResolverContext helper class)
- Removed unused imports

### 🔄 Refactoring

- **Dialog Extraction**: Moved 13 dialog classes from `gui.py` to `zebtrack.ui.dialogs/`
  - Created AST-based extraction scripts for reliable code extraction
  - Fixed all missing imports and circular dependencies
  - Updated tests to reference new dialog locations
- Extracted wizard validation logic to `WizardService`
- Moved hardware detection to service layer with caching
- Created Pydantic models for type safety
- Simplified wizard step `validate()` methods (delegate to service)
- Created `ui/format_utils.py` to resolve circular dependencies

### 📦 Dependencies

- No new dependencies added
- Pydantic v2 already in use (existing dependency)

---

## [1.6.0] - Previous Release

### Added

- Wizard-based project creation (5-step flow)
- Live project support with camera/Arduino integration
- Experimental design fields (groups, days, subjects)
- Template persistence

### Changed

- Wizard is now the default project creation method
- Legacy dialogs maintained for backward compatibility

---

## How to Upgrade

### From v1.x to v2.0

1. **No action required** for existing projects - they will continue to work
2. **New live projects** must use the wizard and provide experimental design
3. **Developers**: Review `docs/DEVELOPER_GUIDE_WIZARD.md` for new patterns
4. **Tip**: Use `WizardService` for any new validation/hardware logic

### Template Migration

If you have saved wizard templates from v1.6+, they are compatible with v2.0.
New fields (experimental design) will use defaults if not present in old templates.

---

## Support

- Report issues: <https://github.com/anthropics/claude-code/issues>
- Documentation: See `docs/` directory
- Developer Guide: `docs/DEVELOPER_GUIDE_WIZARD.md`
