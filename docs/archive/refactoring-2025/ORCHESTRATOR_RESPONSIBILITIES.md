<!-- markdownlint-disable MD024 -->

# Orchestrator Responsibilities Guide

**Date**: 2025-01-14
**Context**: Response to PR #298 review - clarify orchestrator boundaries and delegation patterns
**Version**: 1.0

---

## 🎯 Purpose

This document defines clear responsibilities for each orchestrator in the ZebTrack-AI MVVM-S architecture. Use this guide to:

- ✅ Understand what each orchestrator owns
- ✅ Know when to delegate vs implement
- ✅ Decide where to add new features
- ✅ Avoid responsibility overlap

---

## 📊 Quick Reference Matrix

| Orchestrator | Primary Domain | Key Responsibilities | Delegates To |
| -------------- | ---------------- | --------------------- | -------------- |
| **ProjectOrchestrator** | Project Lifecycle | Create, open, close projects; asset management | VideoProcessing, Analysis |
| **VideoProcessingOrchestrator** | Video Processing | Process videos, manage processing workflows | Analysis, Recording |
| **AnalysisOrchestrator** | Analysis Workflows | Generate summaries, create reports | Reporter, AnalysisService |
| **RecordingSessionOrchestrator** | Recording Sessions | Manage recording lifecycle, session state | RecordingService |
| **UIStateController** | UI State | Update UI, manage UI state, theme, status bar | (UI layer only) |
| **ModelDiagnosticsOrchestrator** | Model Diagnostics | Run diagnostics, test models, generate reports | DetectorService |
| **ZoneArenaOrchestrator** | Zone Management | Define zones/arenas, validate geometry | ProjectManager |
| **ProcessingConfigOrchestrator** | Processing Config | Determine processing mode, apply config | (Settings only) |
| **CalibrationOrchestrator** | Calibration | Manage calibration sessions, apply calibration | ProjectManager |

---

## 📋 Detailed Responsibilities

### 1. ProjectOrchestrator 📁

**Primary Domain**: Project lifecycle management

#### Owns

- ✅ Project creation (wizard workflows, project setup)
- ✅ Project opening (load data, restore state)
- ✅ Project closing (save state, cleanup)
- ✅ Project asset management (delete assets, validate outputs)
- ✅ Model override management (project-specific settings)
- ✅ Zone/calibration metadata persistence

#### Delegates To

- → **VideoProcessingOrchestrator**: Video processing within project context
- → **AnalysisOrchestrator**: Analysis/reporting within project context
- → **CalibrationOrchestrator**: Calibration data persistence

#### Does NOT Own

- ❌ Video processing logic (delegates to VideoProcessingOrchestrator)
- ❌ Analysis algorithms (delegates to AnalysisOrchestrator)
- ❌ UI updates (delegates to UIStateController)

#### Key Methods

```python
# Lifecycle
close_project()
create_project_workflow(**kwargs)
open_project_workflow(project_path)

# Asset Management
delete_project_asset(video_path, asset)
validate_and_register_output(video_path, parquet_path)

# Model Overrides
apply_project_model_overrides(overrides)
save_project_model_overrides(weight, use_openvino)
```

#### Delegation Example

```python
def start_project_processing_workflow(self, *, skip_dialog: bool = False):
    """Delegates to VideoProcessingOrchestrator for video processing."""
    return self.video_processing_orchestrator.start_project_processing_workflow(
        skip_dialog=skip_dialog
    )
```

---

### 2. VideoProcessingOrchestrator 🎬

**Primary Domain**: Video processing workflows

#### Owns

- ✅ Single video processing workflows
- ✅ Batch video processing (project context)
- ✅ Processing mode determination
- ✅ Video state management (processed, pending, failed)
- ✅ Processing callbacks and progress tracking

#### Delegates To

- → **AnalysisOrchestrator**: Generate analysis after processing
- → **RecordingSessionOrchestrator**: Coordinate recording workflows

#### Does NOT Own

- ❌ Project lifecycle (delegates to ProjectOrchestrator)
- ❌ Analysis generation (delegates to AnalysisOrchestrator)
- ❌ UI state updates (uses UIStateController)

#### Key Methods

```python
# Single Video
start_single_video_workflow(video_path, config)
start_single_video_processing(video_path, config, zone_data)

# Batch Processing
start_project_processing_workflow(skip_dialog)
process_videos_batch(videos, skip_existing)

# State Management
cancel_current_analysis()
```

#### Decision Tree

```text
Is this about VIDEO PROCESSING logic?
  YES → VideoProcessingOrchestrator
  NO → Is it about project management?
    YES → ProjectOrchestrator
    NO → Is it about analysis?
      YES → AnalysisOrchestrator
```

---

### 3. AnalysisOrchestrator 📊

**Primary Domain**: Analysis and reporting workflows

#### Owns

- ✅ Generate Parquet summaries
- ✅ Generate Word reports
- ✅ ROI analysis coordination
- ✅ Behavioral metric generation

#### Delegates To

- → **Reporter**: Generate .docx reports
- → **AnalysisService**: Run analysis algorithms

#### Does NOT Own

- ❌ Video processing (delegates to VideoProcessingOrchestrator)
- ❌ Data persistence (delegates to Recorder)

#### Key Methods

```python
generate_parquet_summaries(video_paths)
generate_report(videos, report_type)
```

---

### 4. RecordingSessionOrchestrator 🔴

**Primary Domain**: Recording session lifecycle

#### Owns

- ✅ Recording session state (idle, recording, paused)
- ✅ Recording start/stop/pause/resume
- ✅ Session coordination with RecordingService
- ✅ Zone validation before recording
- ✅ Live calibration workflows

#### Delegates To

- → **RecordingService**: Actual recording implementation

#### Does NOT Own

- ❌ Live camera management (handled by LiveCameraCoordinator)
- ❌ Frame capture (handled by Camera)

#### Key Methods

```python
start_recording(day, group, cobaia)
stop_recording()
pause_recording()
resume_recording()
_ensure_zones_before_recording()
run_live_calibration(temp_aquarium_method)
```

---

### 5. UIStateController 🎨

**Primary Domain**: UI state coordination

**Note**: This is a **Controller**, not an Orchestrator - reflects MVC pattern for UI coordination

#### Owns

- ✅ UI theme management (dark mode toggle)
- ✅ Status bar updates
- ✅ Processing mode UI display
- ✅ UI state synchronization
- ✅ Detector parameter UI updates

#### Delegates To

- → (None - this is the UI coordination layer)

#### Does NOT Own

- ❌ Business logic (only UI state)
- ❌ Data persistence
- ❌ Video processing

#### Key Methods

```python
toggle_dark_mode()
set_status(message)
update_detector_parameters(params, reset_overrides, scope)
_schedule_on_ui(callback, *args)  # Threading helper
```

#### Threading Pattern

```python
def _schedule_on_ui(self, callback, *args):
    """All UI updates must use root.after() for thread safety."""
    if self.root:
        self.root.after(0, callback, *args)
```

---

### 6. ModelDiagnosticsOrchestrator 🔍

**Primary Domain**: Model diagnostics and testing

#### Owns

- ✅ Run model diagnostics
- ✅ Test model on sample data
- ✅ Generate diagnostic reports
- ✅ Model performance analysis

#### Delegates To

- → **DetectorService**: Load models, run inference

#### Does NOT Own

- ❌ Model weight management (handled by WeightManager)
- ❌ Model training/fine-tuning

#### Key Methods

```python
run_model_diagnostic(config)
_run_diagnostic_thread(config, progress_dialog)
_finish_diagnostic_and_save_report(config, results)
```

---

### 7. ZoneArenaOrchestrator 📐

**Primary Domain**: Zone and arena geometry management

#### Owns

- ✅ Add/validate ROI polygons
- ✅ Set main arena polygon
- ✅ Validate polygon geometry (contains ROIs)
- ✅ Manual arena saving

#### Delegates To

- → **ProjectManager**: Persist zone data

#### Does NOT Own

- ❌ Zone detection algorithms (handled by DetectorService)
- ❌ Coordinate system conversions

#### Key Methods

```python
add_roi_polygon(label, points, buffered_points)
set_main_arena_polygon(points)
save_manual_arena(polygon_points)
```

#### Validation Logic

```python
# Intelligent 3-pixel tolerance adjustment
for point in roi_points:
    dist = cv2.pointPolygonTest(arena_poly, tuple(point), True)
    if -3.0 <= dist < 0:  # Within 3 pixels outside
        # Adjust point toward centroid
        point[0] += (dx / length) * 3.0
        point[1] += (dy / length) * 3.0
```

---

### 8. ProcessingConfigOrchestrator ⚙️

**Primary Domain**: Processing configuration management

#### Owns

- ✅ Determine processing mode (SINGLE_SUBJECT vs MULTI_TRACK)
- ✅ Resolve configuration preferences
- ✅ Apply processing mode to UI
- ✅ Context manager for single-animal mode

#### Delegates To

- → (Settings only - reads configuration)

#### Does NOT Own

- ❌ Video processing execution (handled by VideoProcessingOrchestrator)

#### Key Methods

```python
_determine_processing_mode() -> ProcessingMode
_publish_processing_mode(source, force, mode_override)
_temporary_single_animal_mode(config)  # Context manager
```

---

### 9. CalibrationOrchestrator 📏

**Primary Domain**: Calibration session management

#### Owns

- ✅ Global calibration sessions
- ✅ Calibration context building
- ✅ Save calibration to project
- ✅ Calibration scope info

#### Delegates To

- → **ProjectManager**: Persist calibration data
- → **ProjectOrchestrator**: Apply model overrides

#### Does NOT Own

- ❌ Calibration algorithms (handled by Calibration class)
- ❌ Live camera management

#### Key Methods

```python
global_calibration_session()  # Context manager
get_calibration_scope_info() -> dict
save_current_calibration_to_project()
```

---

## 🔄 Delegation Patterns

### Pattern 1: Cross-Domain Coordination

**When**: Feature spans multiple domains

**Example**: Project processing workflow

```python
# ProjectOrchestrator coordinates video processing within project context
def start_project_processing_workflow(self, skip_dialog: bool):
    # Project-level validation
    if not self.project_manager.project_path:
        self.ui_event_bus.publish_event(Events.UI_SHOW_WARNING, {...})
        return

    # Delegate to VideoProcessingOrchestrator for actual processing
    return self.video_processing_orchestrator.start_project_processing_workflow(
        skip_dialog=skip_dialog
    )
```

### Pattern 2: Service Delegation

**When**: Need specialized service functionality

**Example**: Analysis generation

```python
# AnalysisOrchestrator delegates to Reporter service
def generate_report(self, videos: list, report_type: str):
    # Orchestrator handles workflow, service handles implementation
    self.reporter.generate_report(videos, report_type)
```

### Pattern 3: UI Coordination

**When**: Need to update UI from business logic

**Example**: Status updates

```python
# Any orchestrator can request UI updates via UIStateController
self.ui_state_controller.set_status("Processing complete")
```

---

## 🎯 Decision Tree: Where to Add New Features

### Question 1: What domain does the feature belong to?

```text
Is it about PROJECT management?
  → ProjectOrchestrator

Is it about VIDEO PROCESSING?
  → VideoProcessingOrchestrator

Is it about ANALYSIS/REPORTING?
  → AnalysisOrchestrator

Is it about RECORDING?
  → RecordingSessionOrchestrator

Is it about UI STATE?
  → UIStateController

Is it about MODEL DIAGNOSTICS?
  → ModelDiagnosticsOrchestrator

Is it about ZONES/GEOMETRY?
  → ZoneArenaOrchestrator

Is it about PROCESSING CONFIG?
  → ProcessingConfigOrchestrator

Is it about CALIBRATION?
  → CalibrationOrchestrator
```

### Question 2: Does it span multiple domains?

**YES** → Choose the **primary domain** orchestrator, delegate to others

**Example**: "Export project as ZIP"

- **Primary**: ProjectOrchestrator (project-level feature)
- **Delegates**: VideoProcessingOrchestrator (gather video outputs)

---

## ⚠️ Anti-Patterns to Avoid

### ❌ Anti-Pattern 1: Logic Duplication

**Problem**: Implementing same logic in multiple orchestrators

**Example**:

```python
# BAD: Duplicate zone validation in multiple orchestrators
class ProjectOrchestrator:
    def validate_zones(self):
        # 50 lines of validation logic

class VideoProcessingOrchestrator:
    def validate_zones(self):
        # Same 50 lines duplicated
```

**Solution**: Use **ZoneArenaOrchestrator**

```python
# GOOD: Single source of truth
class ZoneArenaOrchestrator:
    def validate_zones(self):
        # 50 lines of validation logic

# Other orchestrators delegate
self.zone_arena_orchestrator.validate_zones()
```

---

### ❌ Anti-Pattern 2: Circular Delegation

**Problem**: Orchestrator A calls B calls A

**Example**:

```python
# BAD: Circular dependency
class ProjectOrchestrator:
    def process_videos(self):
        self.video_processing_orchestrator.process(self)

class VideoProcessingOrchestrator:
    def process(self, project_orchestrator):
        project_orchestrator.save_project()  # Circular!
```

**Solution**: Use **event bus** or **callbacks**

```python
# GOOD: One-way delegation with callbacks
class ProjectOrchestrator:
    def process_videos(self):
        self.video_processing_orchestrator.process(
            on_complete=self.save_project  # Callback
        )
```

---

### ❌ Anti-Pattern 3: God Orchestrator

**Problem**: One orchestrator does everything

**Solution**: Split responsibilities into multiple orchestrators (already done in Sprints 24-34!)

---

## 📚 Related Documentation

- `docs/ARCHITECTURE.md` - Overall MVVM-S architecture
- `docs/DEPENDENCY_INJECTION_GUIDE.md` - DI patterns and composition root
- `docs/PR_298_REVIEW_ANALYSIS.md` - Analysis of PR #298 recommendations
- `docs/sprints/SPRINT_24_RESULTS.md` through `SPRINT_34_RESULTS.md` - Extraction history

---

## 🔮 Future Evolution

### Sprint 36: Test Coverage

Each orchestrator will get dedicated unit tests, validating responsibilities in isolation.

### Sprint 37+: Decoupling

Orchestrators will transition from receiving `MainViewModel` to explicit dependencies:

```python
# Current (Sprints 24-34)
ProjectOrchestrator(main_view_model)

# Future (Sprint 37+)
ProjectOrchestrator(
    project_manager=project_manager,
    state_manager=state_manager,
    ui_event_bus=ui_event_bus,
)
```

This will make responsibilities even clearer (explicit dependencies = explicit contracts).

---

## ✅ Summary

**10 Orchestrators/Controllers**, each with **clear responsibilities**:

1. **ProjectOrchestrator**: Project lifecycle
2. **VideoProcessingOrchestrator**: Video processing
3. **AnalysisOrchestrator**: Analysis/reporting
4. **RecordingSessionOrchestrator**: Recording sessions
5. **UIStateController**: UI state (note: Controller, not Orchestrator)
6. **ModelDiagnosticsOrchestrator**: Model diagnostics
7. **ZoneArenaOrchestrator**: Zone/geometry management
8. **ProcessingConfigOrchestrator**: Processing configuration
9. **CalibrationOrchestrator**: Calibration sessions

**Delegation patterns**: Orchestrators coordinate, services implement.

**Decision tree**: Primary domain → delegate to others as needed.

**Anti-patterns**: Avoid duplication, circular deps, god orchestrators.

---

**Version**: 1.0
**Last Updated**: 2025-01-14
**Author**: Sprint 34+ refactoring effort
**Status**: ✅ COMPLETE
