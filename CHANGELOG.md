# Changelog

All notable changes to DRerio LogAI (zebtrack) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- **Integration Tests**: 12 new tests validating ZONES_UPDATED event flow
  - `tests/integration/test_zones_updated_event.py`
  - Tests dual mode compatibility, edge cases, and multiple subscribers

#### Changed
- **GUI.__init__**: Now creates EventBusV2 instance (`self.event_bus_v2`)
- **Dependency Injection**: Event Bus V2 injected into 4 components:
  - `DialogManager(gui, event_bus_v2)`
  - `ROITemplateManager(project_manager, gui, event_bus_v2)`
  - `PolygonDrawingService(event_bus_v2)`
  - `CanvasManager(gui, event_bus_v2)`
- **Dual Mode Enabled**: All 4 publishers execute BOTH paths:
  - OLD PATH: Direct `gui.update_zone_listbox()` call (deprecated)
  - NEW PATH: `event_bus_v2.publish(Event(UIEvents.ZONES_UPDATED, ...))` ✅
  - Ensures backward compatibility during migration

#### Deprecated
- **`GUI.update_zone_listbox()`**: Marked with `@deprecated` decorator
  - Reason: "Use Event Bus V2 instead - migrating to Event-Driven Architecture v4.0"
  - Alternative: `event_bus_v2.publish(Event(UIEvents.ZONES_UPDATED, {'zone_data': zone_data}))`
  - Will be removed in v4.0 final (after dual mode phase)

#### Documentation
- Updated `docs/EVENT_MAPPING.md` with ZONES_UPDATED implementation details
- Updated `docs/API_STABILITY.md` with deprecation notice for `update_zone_listbox()`

#### Next Steps (v4.0 Phase 2 Remaining)
- Migrate `_populate_video_selector_tree()` → `UIEvents.VIDEO_TREE_REFRESH_REQUESTED` (3 publishers)
- Migrate `apply_pending_readiness_snapshot()` → `UIEvents.READINESS_SNAPSHOT_UPDATED` (1 publisher)
- Migrate 2-7 additional methods to events

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
