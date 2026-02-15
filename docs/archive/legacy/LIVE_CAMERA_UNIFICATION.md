# Live Camera Unification - Technical Documentation

## Overview

ZebTrack-AI v2.1+ unified all live camera workflows under a single service architecture,
eliminating code duplication and fixing critical bugs in camera selection and configuration.

## Architecture

### Before (v2.0)
- **Context 1** (Single video analysis): LiveCameraService ✅
- **Context 2** (Live projects): Legacy threads in gui.py ❌
- Result: Duplicated code, conflicting hardware access, bugs

### After (v2.1+)
- **Both contexts**: LiveCameraService ✅
- Result: Unified, performant, maintainable

## Problems Solved

### Bug #1: 🔴 CRITICAL - Projects ignore `camera_index` from wizard
**Location:** `src/zebtrack/ui/gui.py:2839`

**Problem:**
```python
# BEFORE: Always opened camera 0
self.controller.camera = Camera()  # Uses settings.camera.index = 0
```

**Solution:**
```python
# AFTER: Respects project_data
camera_index = pm.project_data.get("camera_index", 0)
temp_settings = self.controller.settings.model_copy(deep=True)
temp_settings.camera.index = camera_index
self.controller.camera = Camera(settings_obj=temp_settings)
```

---

### Bug #2: 🔴 CRITICAL - Analysis intervals ignored
**Location:** `src/zebtrack/ui/components/event_dispatcher.py:523`

**Problem:**
```python
# BEFORE: Only passed camera_index
camera_index = dialog.result.get("camera_index", 0)
self.gui.controller.start_live_camera_analysis(camera_index=camera_index)
```

**Solution:**
```python
# AFTER: Pass complete configuration
config = dialog.result  # Includes intervals!
self.gui.controller.start_live_camera_analysis_from_config(config)
```

---

### Bug #6: 🔴 CRITICAL - LiveCameraService coupled to RecordingService
**Location:** `src/zebtrack/core/live_camera_service.py:209`

**Problem:**
- LiveCameraService called RecordingService (designed for projects)
- RecordingService assumed project context, accessed global state
- Caused: multiple cameras, wrong camera, preview delays

**Solution:**
- LiveCameraService manages its own lightweight recording
- Direct `recorder.start_recording()` call
- Own session timer (`_setup_session_timer()`)
- No global state pollution

**Code Change:**
```python
# BEFORE:
self.recording_service.start_session(context, project_data, ...)

# AFTER:
# Direct recorder management
self.controller.recorder.start_recording(
    folder_name=str(output_dir),
    video_filename=video_filename,
    parquet_filename=parquet_filename,
    width=self.camera.actual_width,
    height=self.camera.actual_height,
    fps=self.camera.actual_fps,
)
self._setup_session_timer(duration_s, output_dir)
```

---

### Bugs #3-4: LiveStreamSource and FrameSourceFactory ignore `camera_index`
**Locations:**
- `src/zebtrack/io/live_stream_source.py:61`
- `src/zebtrack/io/frame_source_factory.py:104`

**Problem:**
```python
# BEFORE: Stored but didn't use camera_index
self.camera_index = camera_index  # Stored
self.camera = Camera(settings_obj=settings_obj)  # Ignored!
```

**Solution:**
```python
# AFTER: Modify settings before creating Camera
temp_settings = settings_obj.model_copy(deep=True)
temp_settings.camera.index = camera_index
self.camera = Camera(settings_obj=temp_settings)
```

---

## New Methods

### `MainViewModel.start_live_camera_analysis_from_config(config: dict)`
**Location:** `src/zebtrack/core/main_view_model.py:2703`

**Purpose:** Start live camera analysis with full configuration from SingleVideoConfigDialog

**Key Features:**
- Extracts `camera_index`, `analysis_interval_frames`, `display_interval_frames`
- Delegates to LiveCameraService with complete parameters
- Provides detailed UI feedback

**Usage:**
```python
config = single_video_dialog.result
controller.start_live_camera_analysis_from_config(config)
```

---

### `MainViewModel.start_live_project_session(day, group, subject, duration_s)`
**Location:** `src/zebtrack/core/main_view_model.py:2796`

**Purpose:** Start a live recording session for Live projects

**Key Features:**
- Validates project type
- Extracts configuration from `project_data`
- Respects `camera_index`, intervals from project
- Delegates to LiveCameraService

**Usage:**
```python
success = controller.start_live_project_session(
    day=1,
    group="control",
    subject="fish01"
)
```

---

### `LiveCameraService._setup_session_timer(duration_s, output_dir)`
**Location:** `src/zebtrack/core/live_camera_service.py:473`

**Purpose:** Setup timer to automatically stop session after duration

**Replaces:** RecordingService's timed recording logic

**Key Features:**
- Uses Tkinter `root.after()` for timer
- Calls `_on_session_complete()` when expired
- Cancellable in `stop_session()`

---

## Updated Grid Click Handler

**Location:** `src/zebtrack/ui/gui.py:2909`

**Change:**
```python
# AFTER: Branch based on project type
if project_type == "live":
    # ✅ NEW: Use LiveCameraService
    success = self.controller.start_live_project_session(
        day=day,
        group=group_name,
        subject=str(subject_id),
    )
else:
    # Legacy path for pre-recorded projects
    self.controller.start_recording(...)
```

---

## Deprecated Code

### Legacy Thread System
**Location:** `src/zebtrack/ui/gui.py:2872-2895`

**Status:** ⚠️ DEPRECATED - Will be removed in v3.0

**Methods:**
- `_live_frame_capture_loop()` (line 2925)
- `_live_processing_loop()` (line 2957)

**Current Behavior:**
- Still active for backward compatibility
- Logs deprecation warning when used
- Docstrings marked with `.. deprecated:: 2.1`

**Migration Path:**
- Replace with `LiveCameraService` via `start_live_project_session()`
- Remove in v3.0 release

---

## Performance Improvements

### Thread Reduction
- **Before:** 4 threads (2 in LiveCameraService + 2 legacy in gui.py)
- **After:** 2 threads (only in LiveCameraService)
- **Result:** 50% reduction

### Memory Reduction
- **Before:** Duplicate frame buffers (2x `frame_queue`, 2x `video_queue`)
- **After:** Single set of buffers
- **Result:** 50% reduction in buffer memory

### Lock Contention
- **Before:** Multiple threads competing for camera hardware
- **After:** Single controlled access path
- **Result:** Eliminated overhead

---

## Migration Guide

### For Users
No action required. Existing projects will continue to work with improved reliability.

### For Developers

#### Using LiveCameraService for Standalone Analysis

```python
# Context 1: Single video analysis
config = single_video_dialog.result
controller.start_live_camera_analysis_from_config(config)
```

#### Using LiveCameraService for Project Sessions

```python
# Context 2: Live project session
controller.start_live_project_session(
    day=1,
    group="control",
    subject="fish01"
)
```

#### Deprecated Code

The following methods are deprecated and will be removed in v3.0:
- `gui._live_frame_capture_loop()`
- `gui._live_processing_loop()`

Use `LiveCameraService` instead.

---

## Testing

### Validation Checklist

**Context 1: Single Video Analysis**
- [x] Camera index respected (not hardcoded 0)
- [x] Analysis intervals respected
- [x] Display intervals respected
- [x] Single camera LED activates
- [x] Preview shows images immediately
- [x] Recording saves to correct location

**Context 2: Live Projects**
- [x] Camera index from wizard respected
- [x] Intervals from project_data respected
- [x] Sessions save to project directory
- [x] Only 2 daemon threads active
- [x] Multiple sessions use correct camera

**Regression**
- [x] Pre-recorded video analysis works
- [x] Pre-recorded projects work
- [x] Zone detection works
- [x] ROI templates load correctly

---

## Integration Tests

All tests updated to use unified architecture. See:
- `tests/integration/test_live_camera_analysis_integration.py`
- `tests/core/test_live_camera_service.py`

---

## Files Modified

| File | Changes | Type |
|------|---------|------|
| `src/zebtrack/ui/components/event_dispatcher.py` | Pass complete config | Bug Fix |
| `src/zebtrack/core/main_view_model.py` | 2 new methods | Feature |
| `src/zebtrack/ui/gui.py` | camera_index fix, deprecation, grid handler | Bug Fix + Deprecation |
| `src/zebtrack/core/live_camera_service.py` | Decoupling, timer, output_base_dir | Refactor |
| `src/zebtrack/io/live_stream_source.py` | Respect camera_index | Bug Fix |
| `src/zebtrack/io/frame_source_factory.py` | Respect camera_index | Bug Fix |

---

## References

- **Action Plan:** `PLANO_CORRECAO_FLUXOS_CAMERA_LIVE.md`
- **CHANGELOG:** `CHANGELOG.md` (Unreleased section)
- **Developer Guide:** `CLAUDE.md` (Phase 8)
- **Historical Context:** `docs/archive/LIVE_*.md`

---

**Version:** 1.0
**Date:** 2025-01-11
**Status:** ✅ Implemented
