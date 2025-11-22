# GUI Public API - Stability Guarantee

**Version**: 3.0+
**Last Updated**: 2025-01-22
**Status**: STABLE

---

## Overview

This document defines the **public API** of the `GUI` class that external components (orchestrators, services, components) depend on. These methods are marked with `@public_api` decorator and have **stability guarantees**.

### Stability Promise

Methods in this document:
- ✅ **MUST NOT be removed** without major version bump
- ✅ **MUST maintain signature compatibility** (parameters, return types)
- ✅ **MAY be deprecated** with at least 1 major version notice
- ✅ **Can delegate internally** to components (implementation detail)

---

## Public API Methods (by Category)

### 1. Project View Management (5 methods)

#### `refresh_project_views()`
**Signature**: `(reason: str | None, *, append_summary: bool, immediate: bool) -> None`
**Called by**: Orchestrators, AnalysisService, ProjectViewManager
**Purpose**: Refresh project overview, pipeline status, and reports panels
**Status**: ✅ STABLE (marked with @public_api)

#### `_request_overview_refresh()`
**Signature**: `(reason: str | None, *, append_summary: bool, immediate: bool) -> None`
**Called by**: GUI (internal), multiple event handlers
**Purpose**: Request deferred project overview refresh
**Status**: 🟡 INTERNAL (used extensively internally)

#### `_update_project_overview_summary()`
**Signature**: `(counts: Counter, total: int, videos: list[dict] | None) -> None`
**Called by**: ProjectViewManager
**Purpose**: Update summary statistics in overview panel
**Status**: 🟡 INTERNAL

#### `_refresh_processing_reports_tab()`
**Signature**: `() -> None`
**Called by**: ProjectViewManager
**Purpose**: Reload processing reports tree
**Status**: 🟡 INTERNAL

#### `_populate_video_selector_tree()`
**Signature**: `(filter_text: str | None) -> None`
**Called by**: ZoneControlBuilder (2x), ProjectViewManager
**Purpose**: Populate video selector tree with filtering
**Status**: 🟡 SEMI-PUBLIC (called from builders)

---

### 2. Zone & ROI Management (3 methods)

#### `update_zone_listbox()`
**Signature**: `(zone_data: ZoneData | None) -> None`
**Called by**: DialogManager, Renderer, PolygonDrawingService, ROITemplateManager, ZoneControlBuilder
**Purpose**: Update zone listbox with current zones
**Status**: ✅ STABLE (marked with @public_api) - **MOST CALLED** (5+ callers)

#### `setup_interactive_polygon()`
**Signature**: `(polygon: np.ndarray) -> None`
**Called by**: CanvasManager
**Purpose**: Enable interactive polygon editing mode
**Status**: ✅ STABLE (marked with @public_api)

#### `apply_pending_readiness_snapshot()`
**Signature**: `(*, ready_with_trajectory, ready_with_zones, arena_only, without_arena) -> None`
**Called by**: DialogManager (after zone reuse)
**Purpose**: Update UI with video readiness status
**Status**: ✅ STABLE (marked with @public_api)

---

### 3. Live Recording / External Triggers (2 methods)

#### `show_external_trigger_notice()`
**Signature**: `(session_label: str, **details) -> None`
**Called by**: RecordingService, LiveCameraService
**Purpose**: Display external Arduino trigger notice
**Status**: ✅ STABLE (marked with @public_api)

#### `clear_external_trigger_notice()`
**Signature**: `() -> None`
**Called by**: RecordingService, LiveCameraService
**Purpose**: Remove external trigger notice
**Status**: ✅ STABLE (marked with @public_api)

---

### 4. Analysis Progress & Statistics (3 methods)

#### `update_processing_stats()`
**Signature**: `(total_frames, processed_frames, detected_frames, start_time, current_frame) -> None`
**Called by**: AnalysisService, VideoProcessingOrchestrator
**Purpose**: Update progress bar and FPS stats
**Status**: ✅ STABLE (marked with @public_api)

#### `update_social_summary()`
**Signature**: `(*, profile: str, stats: dict | None, tracks: list[str] | None) -> None`
**Called by**: AnalysisService
**Purpose**: Display social proximity statistics
**Status**: ✅ STABLE (marked with @public_api)

#### `update_analysis_task_status()`
**Signature**: `(*, index: int, total: int, experiment_id, step) -> None`
**Called by**: AnalysisService, VideoProcessingOrchestrator
**Purpose**: Show current video being analyzed (X of Y)
**Status**: ✅ STABLE (marked with @public_api)

---

### 5. Processing Reports (7 methods)

All these methods delegate to `ProjectViewManager` and are called internally during report generation:

- `handle_processing_reports_item_double_click(event)` - Open report on double-click
- `on_processing_reports_generate_partial()` - Generate partial report
- `_determine_status_tag(complete_count, total_count)` - Compute readiness tag
- `_sort_key_for_reports(value)` - Sort key for reports tree
- `_build_report_hierarchy(all_videos, pm)` - Build report tree structure
- `_populate_reports_tree_from_hierarchy(hierarchy, pm)` - Populate tree widget
- `append_report_artifacts_from_entry(parent_id, entry)` - Add report files to tree

**Status**: 🟡 INTERNAL (complex delegation chain)

---

### 6. Video Hierarchy & Metadata (6 methods)

These provide video metadata and hierarchy for various UI components:

- `_build_video_hierarchy_data(all_videos, search_text)` - Build filtered video hierarchy
- `_build_video_hierarchy_snapshot()` - Capture current video states
- `_format_status_token(has_parquet, symbol_key)` - Format readiness symbol
- `format_subject_for_reports(value)` - Format subject name for display

**Status**: 🟡 INTERNAL (called by ProjectViewManager/ValidationManager)

---

### 7. Dialog Management (1 method)

#### `_maybe_offer_zone_reuse()`
**Signature**: `(video_path: str) -> None`
**Called by**: DialogManager
**Purpose**: Prompt user to reuse zones when loading video without zones
**Status**: 🟡 INTERNAL

---

### 8. Single Video Analysis (2 methods)

#### `setup_zone_definition_for_single_video()`
**Signature**: `(video_path: str, config: dict) -> None`
**Called by**: EventDispatcher
**Purpose**: Prepare zone definition UI for single video workflow
**Status**: 🟡 PUBLIC (entry point for single video mode)

#### `_on_analyze_single_video_clicked()`
**Signature**: `() -> None`
**Called by**: Button command (internal)
**Purpose**: Handle "Analyze Single Video" button
**Status**: 🟡 EVENT HANDLER

---

### 9. Other Public Methods (9 methods)

These are public-facing but have fewer external dependencies:

- `_on_canvas_click(event)` - Event handler for canvas clicks
- `update_weights_dropdown(weights)` - Update weight selection dropdown
- `_edit_selected_zone_vertices()` - Context menu command (MenuManager)
- `handle_report_item_double_click(event)` - Open report file
- `handle_report_video_node(metadata)` - Navigate to video from report
- `_handle_report_file_node(metadata)` - Open report artifact file

**Status**: 🟡 SEMI-PUBLIC (event handlers / menu commands)

---

## API by Caller

### Called by Orchestrators (4 callers)
- `refresh_project_views()` - ProjectOrchestrator, AnalysisOrchestrator, VideoProcessingOrchestrator

### Called by Services (3 callers)
- `update_processing_stats()` - AnalysisService
- `update_social_summary()` - AnalysisService
- `update_analysis_task_status()` - AnalysisService
- `show_external_trigger_notice()` - RecordingService, LiveCameraService
- `clear_external_trigger_notice()` - RecordingService, LiveCameraService

### Called by Components (20+ callers)
- `update_zone_listbox()` - **5 components** (DialogManager, Renderer, PolygonDrawingService, ROITemplateManager, ZoneControlBuilder)
- `setup_interactive_polygon()` - CanvasManager
- `apply_pending_readiness_snapshot()` - DialogManager
- `_populate_video_selector_tree()` - ZoneControlBuilder (2x), ProjectViewManager
- Most ProjectViewManager delegation methods

---

## Breaking Changes Policy

### What Requires Major Version Bump (v3 → v4)
- Removing any `@public_api` method
- Changing signature of `@public_api` method
- Changing return type of `@public_api` method

### What Requires Minor Version Bump (v3.0 → v3.1)
- Adding new `@public_api` method
- Adding optional parameters to existing methods

### What is Safe (Patch)
- Changing internal implementation (delegation target)
- Improving docstrings
- Adding `@public_api` to previously unmarked methods

---

## Deprecation Process

When deprecating a public API method:

1. Add `@deprecated` decorator with reason and alternative
   ```python
   @deprecated(
       reason="Replaced by component-based architecture",
       version="v3.0",
       alternative="Use self.widget_factory.create_frame() directly"
   )
   @public_api
   def old_method(self):
       ...
   ```

2. Document in CHANGELOG.md under "Deprecated" section
3. Keep method for at least 1 major version
4. Remove in next major version with migration guide

---

## Statistics

- **Total Public API Methods**: ~37
- **Marked with @public_api**: 10 (critical paths)
- **Most Called Method**: `update_zone_listbox()` (5+ callers)
- **Most Complex**: Report generation methods (7-method chain)

---

## References

- Decorator implementation: `src/zebtrack/ui/decorators.py`
- GUI source: `src/zebtrack/ui/gui.py`
- Wrapper removal report: `RELATORIO_REMOCAO_WRAPPERS_FINAL.md`

---

**Next Review Date**: 2025-07-22 (6 months)
