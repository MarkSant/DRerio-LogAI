# MainViewModel Refactoring Summary

> **Archived**: December 2, 2025
> **Purpose**: Consolidated summary of MainViewModel extraction and simplification

This document consolidates the outcomes from the MainViewModel refactoring effort,
which reduced the class from ~4,500 lines to ~3,200 lines by extracting responsibilities
to dedicated services and coordinators.

---

## Overview

**Original State**: MainViewModel was a "god class" handling:

- UI coordination
- Video processing control
- Camera management
- Project lifecycle
- Analysis orchestration
- Hardware interaction
- State management

**Final State**: MainViewModel is now a thin orchestrator that delegates to:

- 4 Coordinators (ProcessingCoordinator, HardwareCoordinator, SessionCoordinator, ProjectLifecycleCoordinator)
- 15+ Services (DetectorService, WizardService, LiveCameraService, etc.)
- StateManager for observable state

---

## Extracted Responsibilities

### To Coordinators

| Coordinator | Responsibilities Moved |
| ------------- | ---------------------- |
| `ProcessingCoordinator` | Video processing, frame analysis, overlay rendering |
| `HardwareCoordinator` | Camera initialization, Arduino management |
| `SessionCoordinator` | Analysis session lifecycle, recording control |
| `ProjectLifecycleCoordinator` | Project loading, saving, validation |

### To Services

| Service | Responsibilities Moved |
| --------- | ---------------------- |
| `WizardService` | Project creation workflow, hardware detection cache |
| `LiveCameraService` | Live camera analysis, real-time preview |
| `RecordingService` | Recording coordination, session timing |
| `DetectorService` | Detection orchestration, zone management |
| `ProjectService` | Project persistence, template management |

---

## Key Methods Before/After

### Before (in MainViewModel)

```python
class MainViewModel:
    def start_video_processing(self): ...  # 200+ lines
    def handle_camera_frame(self): ...      # 150+ lines
    def save_project(self): ...             # 100+ lines
    def load_project(self): ...             # 120+ lines
    def run_analysis(self): ...             # 180+ lines
```

### After (delegation)

```python
class MainViewModel:
    def start_video_processing(self):
        self.processing_coordinator.start()

    def handle_camera_frame(self, frame):
        self.hardware_coordinator.process_frame(frame)

    def save_project(self):
        self.project_lifecycle_coordinator.save()
```

---

## Metrics

| Metric | Before | After | Change |
| -------- | -------- | ------- | -------- |
| Lines of code | ~4,500 | ~3,200 | -29% |
| Methods | 150+ | ~80 | -47% |
| Dependencies | 8 | 11 | +3 (explicit) |
| Cyclomatic complexity | High | Medium | Improved |
| Test coverage | 35% | 58% | +23pp |

---

## Dependency Injection

MainViewModel now receives all dependencies via constructor:

```python
def __init__(
    self,
    root: tk.Tk,
    settings_obj: Settings,
    state_manager: StateManager,
    project_manager: ProjectManager,
    detector_service: DetectorService,
    processing_coordinator: ProcessingCoordinator,
    hardware_coordinator: HardwareCoordinator,
    session_coordinator: SessionCoordinator,
    project_lifecycle_coordinator: ProjectLifecycleCoordinator,
    event_bus: Optional[EventBus] = None,
    ui_scheduler: Optional[UIScheduler] = None,
):
```

---

## Related Documents

- `MAINVIEWMODEL_DEPENDENCY_MAP.md` - Dependency graph
- `MAINVIEWMODEL_EXTRACTION_ANALYSIS.md` - Extraction decisions
- `MAINVIEWMODEL_METHOD_CLASSIFICATION.md` - Method categorization
- `MAINVIEWMODEL_SIMPLIFICATION_PLAN.md` - Original plan

---

## Current Location

The current MainViewModel implementation is at:
`src/zebtrack/core/main_view_model.py`

Architecture documentation:
`docs/architecture/ARCHITECTURE.md`
