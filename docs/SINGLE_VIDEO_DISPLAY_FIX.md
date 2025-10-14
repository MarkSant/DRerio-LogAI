# Fix: Single Video Analysis Display Issue

## Problem

When analyzing a single video (not part of a project), the following issues occurred:

1. **Main Control Tab (Resumo do Projeto)**: 
   - The analyzed video appeared but WITHOUT proper flags (has_arena, has_rois, has_trajectory)
   - Status indicators were incorrect or missing
2. **Reports Tab (Relatórios)**: 
   - NO reports were displayed at all, before or after analysis
   - The tree remained empty even after successful processing

## Root Cause Analysis

After deeper investigation, multiple issues were identified:

### Initial Problems (First Fix Attempt)
1. The video was never registered with the `ProjectManager`
2. The `_register_project_outputs()` method was only called for project-based workflows
3. The GUI's `refresh_project_views()` relied on `project_manager.get_all_videos()`, which returned an empty list

### Additional Problems (Revealed by User Testing)
4. **Zone flags not set**: When registering the single video, `has_arena` and `has_rois` flags were not being passed
5. **Zone data not saved**: The zone data used during processing was not persisted to the video entry
6. **Reports tree early return**: `update_reports_tree()` had an early return when `project_path` was None, preventing ANY display
7. **Missing metadata**: Single videos had no group/day/subject metadata, preventing proper hierarchical display
8. **Flags not updated post-processing**: Even after successful analysis, the zone flags remained unset

## Solution

The fix involves three key changes to ensure single video results are tracked and displayed:

### 1. Register Single Videos in ProjectManager (controller.py)

**Location**: `src/zebtrack/core/controller.py` - `start_single_video_processing()` method

**Change**: Added code to register the single video in the project_manager's in-memory structure before processing begins:

```python
# Register the single video in project_manager for display in UI
# This allows the video to appear in Main Control and Reports tabs
video_entry = self.project_manager.find_video_entry(path=video_path)
if not video_entry:
    log.info("workflow.single_video.registering_video", video=video_path)
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    self.project_manager.add_video_batch(
        [{"path": video_path, "status": "processing"}],
        save_project=False  # Don't save to disk for single video workflow
    )
```

### 2. Always Register Processing Outputs (controller.py)

**Location**: `src/zebtrack/core/controller.py` - `_run_analysis_pipeline()` method

**Change**: Removed the conditional check that prevented single videos from having their outputs registered:

**Before**:
```python
if not single_video_config:
    self._register_project_outputs(...)
```

**After**:
```python
# Register outputs for both project and single video workflows
# This ensures the video and reports appear in the UI tabs
self._register_project_outputs(...)
```

### 3. Auto-Add Videos During Output Registration (project_manager.py)

**Location**: `src/zebtrack/core/project_manager.py` - `register_processing_outputs()` method

**Changes**:

a) If a video is not found, automatically add it instead of failing:
```python
video_entry = self.find_video_entry(path=video_path)
if not video_entry:
    log.info("project.outputs.adding_missing_video", video_path=video_path)
    # Add the video to the in-memory project data
    self.add_video_batch(
        [{"path": video_path, "status": "processing"}],
        save_project=False
    )
    video_entry = self.find_video_entry(path=video_path)
```

b) Only save to disk when there's an actual project file:
```python
if changed:
    # Only save to disk if there's a project path
    # For single video workflows, keep in memory only
    if self.project_path:
        self.save_project()
```

### 4. Include Zone Flags in Registration (controller.py)

**Location**: `src/zebtrack/core/controller.py` - `start_single_video_processing()` method

**Change**: Updated video registration to include zone flags and metadata:

```python
# Include zone information in the video entry
video_data = {
    "path": video_path,
    "status": "processing",
    "has_arena": bool(zone_data and zone_data.polygon),
    "has_rois": bool(zone_data and zone_data.roi_polygons),
}
if metadata:
    video_data["metadata"] = metadata

self.project_manager.add_video_batch([video_data], save_project=False)

# Save the zone data for this video so it can be retrieved later
if zone_data and (zone_data.polygon or zone_data.roi_polygons):
    self.project_manager.save_zone_data(zone_data, video_path)
```

### 5. Add Default Metadata for Single Videos (controller.py)

**Location**: `src/zebtrack/core/controller.py` - `start_single_video_processing()` method

**Change**: Ensure single videos have default metadata for proper tree display:

```python
# Set defaults for missing metadata to ensure proper tree display
if "group" not in metadata:
    metadata["group"] = "single_video"
if "group_display_name" not in metadata:
    metadata["group_display_name"] = "Vídeo Único"
if "day" not in metadata:
    metadata["day"] = "1"
if "subject" not in metadata:
    metadata["subject"] = "1"
```

### 6. Update Zone Flags During Output Registration (project_manager.py)

**Location**: `src/zebtrack/core/project_manager.py` - `register_processing_outputs()` method

**Change**: Check and update zone flags if they weren't set during initial registration:

```python
# Update zone flags if they weren't set during registration
zone_data = self.get_zone_data(video_path, fallback_to_global=False)
if zone_data:
    if zone_data.polygon and not video_entry.get("has_arena"):
        video_entry["has_arena"] = True
    if zone_data.roi_polygons and not video_entry.get("has_rois"):
        video_entry["has_rois"] = True
```

### 7. Remove Early Return for Reports Tree (gui.py)

**Location**: `src/zebtrack/ui/gui.py` - `update_reports_tree()` method

**Change**: Removed the check that prevented displaying reports without a project file:

**Before**:
```python
if not pm.project_path:
    return
```

**After**:
```python
# Removed - allow displaying reports even without a project file
# For single video workflows, we still want to show the reports
```

### 8. Allow Display Without Project File (gui.py)

**Location**: `src/zebtrack/ui/gui.py` - `_refresh_project_overview()` method

**Change**: Modified the early-return logic to allow displaying videos even when there's no project file:

```python
# Allow display even when there's no project file
# This enables single video workflow results to be shown
if not all_videos and not pm.project_path:
    # No videos and no project - nothing to show
    return
```

## Implementation Details

### In-Memory vs. Persistent Storage

The solution maintains a clear distinction:

- **Single Video Workflow**: Videos and outputs are tracked in memory only (`save_project=False`)
- **Project Workflow**: Videos and outputs are saved to the project JSON file on disk

This design ensures:
1. Single videos don't create unexpected project files
2. The UI can still display single video results
3. No filesystem side effects for quick single-video analyses

### Backward Compatibility

The changes are fully backward compatible:

- Existing project workflows continue to work exactly as before
- The `save_project` parameter in `add_video_batch()` defaults to `True` for project workflows
- All existing tests pass without modification

## Testing

All 345 tests pass, including:

- `test_single_video_workflow.py`: Verifies single video processing creates output files
- `test_single_video_display_fix.py`: Verifies video registration and output tracking (3 tests)
- `test_single_video_zones_display.py`: Verifies zone flags are properly set and displayed (2 tests)
- `test_controller.py`: Verifies project loading and view refresh
- `test_project_manager.py`: Verifies output registration logic

### New Test Coverage

**test_single_video_display_fix.py**:
1. `test_single_video_appears_in_project_overview`: Verifies video and outputs are registered
2. `test_single_video_does_not_create_project_file`: Ensures no persistent files for single videos
3. `test_register_outputs_auto_adds_missing_video`: Tests auto-registration fallback

**test_single_video_zones_display.py**:
1. `test_single_video_with_zones_shows_all_flags`: Complete workflow with zones, metadata, and all flags
2. `test_zone_flags_updated_during_output_registration`: Verifies retroactive flag updates

## User Impact

After this comprehensive fix, users will see:

### Main Control Tab (Resumo do Projeto)
- ✅ The analyzed video appears in the summary table
- ✅ **Status** shows "processed" after completion
- ✅ **Arena indicator** (🏟) shows green when arena is defined
- ✅ **ROIs indicator** (🎯) shows green when ROIs are defined
- ✅ **Trajectory indicator** (🧭) shows green after analysis
- ✅ **Summary indicator** (Σ) shows green when reports are generated
- ✅ Proper file count and processing state

### Reports Tab (Relatórios)
- ✅ Hierarchical tree structure appears (Group → Day → Subject)
- ✅ Single videos appear under "Vídeo Único" group by default
- ✅ Status ratios show completion (e.g., "✓ 1/1" for arena, ROIs, trajectory, summary)
- ✅ All generated reports are listed:
  - 🐟 Subject entry with all indicators
  - Clickable report files (trajectory Parquet, summary Excel, report Word)
- ✅ Reports are accessible immediately after processing completes

### Consistent UX
- ✅ Single video analysis now provides the **same visibility** as project-based workflows
- ✅ No confusion about whether analysis completed successfully
- ✅ Easy access to all generated output files
- ✅ Proper visual feedback throughout the workflow

## Technical Notes

- The fix leverages the existing `ProjectManager` infrastructure without requiring schema changes
- GUI refresh logic (`refresh_project_views()`) works for both project and non-project contexts
- Logging has been enhanced to track single video registration events
