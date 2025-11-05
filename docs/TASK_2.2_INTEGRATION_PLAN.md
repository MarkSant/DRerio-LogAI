# Task 2.2 Integration Plan - MainViewModel Refactoring

**Date**: 2025-11-05
**Task**: REFACTOR-VIEWMODEL-001
**Status**: In Progress (Part 3/4)

---

## Progress Summary

### ✅ Completed
1. **HardwareCoordinator** (~350 lines)
   - Location: `src/zebtrack/core/hardware_coordinator.py`
   - Methods: 10 (detector setup, Arduino management, events)
   - Commit: c296254

2. **VideoOrchestrator** (~700 lines)
   - Location: `src/zebtrack/core/video_orchestrator.py`
   - Methods: Batch processing, video selection, validation
   - Commit: 0a907cd

3. **AnalysisCoordinator** (~350 lines)
   - Location: `src/zebtrack/core/analysis_coordinator.py`
   - Methods: Report generation, summaries, analysis pipeline
   - Commit: 0a907cd

**Total Extracted**: ~1400 lines

---

## Next Step: MainViewModel Integration

### Approach: Internal Coordinator Creation

**Rationale**:
- Coordinators are internal to MainViewModel (not external services)
- All required dependencies already available in MainViewModel.__init__
- Avoids increasing __init__ parameter count (already 13+ params)
- Simpler initial integration and testing

### Integration Strategy

#### 1. Create Coordinators in __init__ (after line 265)

```python
# Create coordinators (Task 2.2: REFACTOR-VIEWMODEL-001)
self.hardware_coordinator = HardwareCoordinator(
    state_manager=self.state_manager,
    ui_event_bus=self.ui_event_bus,
    settings_obj=self.settings,
    project_manager=self.project_manager,
    detector_service=self.detector_service,
    arduino_manager_cls=self._arduino_manager_cls,
)

# Video orchestrator - needs view reference (set after view is created)
self._video_orchestrator = None  # Initialized in bind_view()

# Analysis coordinator
self.analysis_coordinator = AnalysisCoordinator(
    view=self.view,  # Set after view created
    ui_event_bus=self.ui_event_bus,
    settings_obj=self.settings,
    project_manager=self.project_manager,
    analysis_service=self.analysis_service,
    video_processing_service=self.video_processing_service,
)
```

**Issue**: `self.view` not available yet at __init__ time
**Solution**: Create coordinators in a separate `_init_coordinators(view)` method called after view is set

#### 2. Add Method to Initialize Coordinators

```python
def _init_coordinators(self, view: ApplicationGUI) -> None:
    """Initialize coordinators after view is available.

    Called from bind_view() or run() after self.view is set.
    """
    # Hardware coordinator (no view dependency)
    self.hardware_coordinator = HardwareCoordinator(
        state_manager=self.state_manager,
        ui_event_bus=self.ui_event_bus,
        settings_obj=self.settings,
        project_manager=self.project_manager,
        detector_service=self.detector_service,
        arduino_manager_cls=self._arduino_manager_cls,
    )

    # Video orchestrator (needs view)
    self.video_orchestrator = VideoOrchestrator(
        root=self.root,
        view=view,
        state_manager=self.state_manager,
        ui_event_bus=self.ui_event_bus,
        settings_obj=self.settings,
        project_manager=self.project_manager,
        video_processing_service=self.video_processing_service,
        analysis_service=self.analysis_service,
        recorder=self.recorder,
    )

    # Analysis coordinator (needs view)
    self.analysis_coordinator = AnalysisCoordinator(
        view=view,
        ui_event_bus=self.ui_event_bus,
        settings_obj=self.settings,
        project_manager=self.project_manager,
        analysis_service=self.analysis_service,
        video_processing_service=self.video_processing_service,
    )

    # Set callbacks for coordinators
    self.video_orchestrator.set_arena_callback(self.set_main_arena_polygon)
    self.video_orchestrator.set_analysis_view_mode_callback(self._activate_analysis_view_mode)
```

#### 3. Delegate Methods to Coordinators

**Hardware Methods** → `self.hardware_coordinator.*`
- `setup_detector()` → `hardware_coordinator.setup_detector()`
- `setup_arduino()` → `hardware_coordinator.setup_arduino()`
- `setup_detector_zones()` → `hardware_coordinator.setup_detector_zones()`
- `on_arduino_*()` → `hardware_coordinator.on_arduino_*()`
- `log_arduino_event()` → `hardware_coordinator.log_arduino_event()`

**Video Processing Methods** → `self.video_orchestrator.*`
- `start_project_processing_workflow()` → `video_orchestrator.start_project_processing_workflow()`
- `process_pending_project_videos()` → `video_orchestrator.process_pending_project_videos()`
- `cancel_current_analysis()` → `video_orchestrator.cancel_current_analysis()`

**Analysis Methods** → `self.analysis_coordinator.*`
- `generate_report()` → `analysis_coordinator.generate_report()`
- `generate_parquet_summaries()` → `analysis_coordinator.generate_parquet_summaries()`
- `_run_analysis_pipeline()` → `analysis_coordinator.run_analysis_pipeline()`

#### 4. Update Arduino Management

Move arduino/arduino_manager initialization to HardwareCoordinator:
- Lines 262-264: Keep references but delegate actual management
- Update shutdown logic to call `hardware_coordinator.shutdown_arduino()`

---

## Testing Strategy

### Phase 1: Verify No Regressions
```bash
poetry run pytest tests/test_main_view_model.py -v
```

### Phase 2: Integration Tests
```bash
poetry run pytest tests/integration/ -v -k view_model
```

### Phase 3: Full Suite
```bash
poetry run pytest -q
```

---

## Rollback Plan

If tests fail critically:
1. Revert MainViewModel changes
2. Keep coordinators (they're standalone)
3. Document issues in this file
4. Create new approach

---

## Files to Modify

1. `src/zebtrack/core/main_view_model.py`
   - Add coordinator initialization
   - Delegate methods to coordinators
   - Update Arduino management
   - Estimated: ~50-100 lines changed, ~1500 lines removed

2. `src/zebtrack/__main__.py` (Composition Root)
   - No changes needed (internal coordinator creation)
   - Future: Could inject coordinators if needed

---

## Expected Impact

### Before
- MainViewModel: 5588 lines
- Dependencies: 13+

### After
- MainViewModel: ~3000-3500 lines (target: ~2500)
- Dependencies: 13+ (same, coordinators created internally)
- New Files: 3 coordinators (~1400 lines)

### Reduction
- ~2000-2500 lines removed from MainViewModel
- Responsibility better distributed
- Easier to test individual coordinators

---

## Next Actions

1. ✅ Document integration plan (this file)
2. ⏳ Implement coordinator initialization in MainViewModel
3. ⏳ Delegate methods to coordinators
4. ⏳ Update Arduino management
5. ⏳ Run tests and fix issues
6. ⏳ Commit and push changes
7. ⏳ Update EXECUTION_PLAN.md status
