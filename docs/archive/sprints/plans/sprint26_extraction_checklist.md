# Sprint 26: RecordingSessionOrchestrator Extraction Checklist

**Option Selected:** Option B (Core + Live Camera Analysis)
**Total Lines:** 488 lines
**Risk Level:** MEDIUM
**Expected Result:** 4,672 → 4,184 lines (10.4% reduction)

---

## Phase 1: State Management Methods (87 lines)

### ✅ Step 1.1: is_recording Property (11 lines)
**Location:** Lines 617-627
```python
@property
def is_recording(self) -> bool:
    """Get recording status from StateManager."""
    return self.state_manager.get_recording_state().is_recording

@is_recording.setter
def is_recording(self, value: bool) -> None:
    """Update recording status in StateManager."""
    self.state_manager.update_recording_state(
        source="controller.is_recording_setter",
        is_recording=value,
    )
```
**Dependencies:** StateManager
**Risk:** LOW
**Tests:** test_main_view_model.py (recording state tests)

---

### ✅ Step 1.2: _on_recording_state_changed (20 lines)
**Location:** Lines 721-740
**Purpose:** UI event publisher for recording state changes
**Dependencies:** ui_event_bus, state_manager
**Risk:** LOW
**Tests:** test_main_view_model.py (state change callbacks)

---

### ✅ Step 1.3: _setup_recording_service_callbacks (20 lines)
**Location:** Lines 822-841
**Purpose:** Inject UI callbacks into RecordingService
**Dependencies:** recording_service, ui_event_bus
**Risk:** LOW
**Tests:** test_main_view_model.py (initialization tests)

---

### ✅ Step 1.4: _init_recording_service (36 lines)
**Location:** Lines 843-878
**Purpose:** Initialize RecordingService and LiveCameraService
**Dependencies:** RecordingService, LiveCameraService
**Risk:** LOW
**Tests:** test_main_view_model.py (initialization tests)

**Phase 1 Checkpoint:**
- [ ] All 4 methods extracted
- [ ] Run: `poetry run pytest tests/test_main_view_model.py -k "recording" -v`
- [ ] All tests pass

---

## Phase 2: Helper Methods (37 lines)

### ✅ Step 2.1: _clear_external_trigger_wait (13 lines)
**Location:** Lines 1129-1141
**Purpose:** Clear pending external trigger state
**Dependencies:** ui_event_bus, _pending_external_trigger
**Risk:** LOW
**Tests:** test_main_view_model.py (external trigger tests)

---

### ✅ Step 2.2: _schedule_recording (24 lines)
**Location:** Lines 1195-1218
**Purpose:** Schedule recording via RecordingCoordinator
**Dependencies:** recording_coordinator, view.camera (for dimensions)
**Risk:** LOW
**Tests:** test_main_view_model.py (recording flow tests)

**Phase 2 Checkpoint:**
- [ ] All 2 methods extracted
- [ ] Run: `poetry run pytest tests/test_main_view_model.py -k "trigger or schedule" -v`
- [ ] All tests pass

---

## Phase 3: External Trigger Methods (84 lines)

### ✅ Step 3.1: _handle_external_trigger (46 lines)
**Location:** Lines 2509-2554
**Purpose:** Handle external trigger setup for recording
**Dependencies:** project_manager, ui_event_bus, _pending_external_trigger
**Risk:** MEDIUM (Arduino interaction)
**Tests:** test_main_view_model.py (external trigger flow)

---

### ✅ Step 3.2: trigger_recording (17 lines)
**Location:** Lines 1177-1193
**Purpose:** Trigger pending recording from Arduino event
**Dependencies:** _pending_external_trigger, _schedule_recording
**Risk:** MEDIUM (Arduino interaction)
**Tests:** test_main_view_model.py (trigger tests)

---

### ✅ Step 3.3: on_arduino_event (21 lines)
**Location:** Lines 1155-1175
**Purpose:** Handle Arduino event signals (start/stop)
**Dependencies:** trigger_recording, stop_recording, is_recording
**Risk:** MEDIUM (Hardware events)
**Tests:** test_main_view_model.py (Arduino event handling)

**Phase 3 Checkpoint:**
- [ ] All 3 methods extracted
- [ ] Run: `poetry run pytest tests/test_main_view_model.py -k "arduino" -v`
- [ ] All tests pass

---

## Phase 4: Core Recording Methods (150 lines)

### ✅ Step 4.1: start_recording (66 lines)
**Location:** Lines 2556-2621
**Purpose:** Start recording session (live mode)
**Dependencies:**
- project_manager.set_active_zone_video()
- _clear_external_trigger_wait()
- _ensure_zones_before_recording() [⚠️ NOT EXTRACTED - stays in MainViewModel]
- setup_detector() [stays in MainViewModel]
- setup_detector_zones() [stays in MainViewModel]
- setup_arduino() [stays in MainViewModel]
- view.ask_recording_details_unified()
- _handle_external_trigger()
- _schedule_recording()
**Risk:** MEDIUM (Complex coordination)
**Tests:** test_main_view_model.py (start recording tests)

**IMPORTANT:** `_ensure_zones_before_recording()` is NOT extracted in Sprint 26.
The orchestrator will need to call back to MainViewModel for this method.

---

### ✅ Step 4.2: stop_recording (21 lines)
**Location:** Lines 2838-2858
**Purpose:** Stop current recording session
**Dependencies:**
- _clear_external_trigger_wait()
- recording_coordinator.stop_recording()
- ui_event_bus (button state updates)
**Risk:** LOW
**Tests:** test_main_view_model.py (stop recording tests)

---

### ✅ Step 4.3: start_live_project_session (63 lines)
**Location:** Lines 2860-2922
**Purpose:** Start live recording session for Live projects
**Dependencies:**
- project_manager (project type, data, camera_index)
- live_camera_service.start_session()
**Risk:** MEDIUM (Live project coordination)
**Tests:** test_main_view_model.py (live project tests)

**Phase 4 Checkpoint:**
- [ ] All 3 methods extracted
- [ ] Run: `poetry run pytest tests/test_main_view_model.py -k "start_recording or stop_recording or live_project" -v`
- [ ] All tests pass

---

## Phase 5: Live Camera Methods (164 lines)

### ✅ Step 5.1: start_live_camera_analysis (65 lines)
**Location:** Lines 2623-2687
**Purpose:** Start live camera analysis with dialog
**Dependencies:**
- settings (live_analysis config)
- LiveAnalysisDialog (UI dialog)
- live_camera_service.start_session()
- ui_event_bus (status updates)
**Risk:** MEDIUM (Dialog handling)
**Tests:** test_main_view_model.py (live camera analysis tests)

---

### ✅ Step 5.2: run_live_calibration (99 lines)
**Location:** Lines 2409-2507
**Purpose:** Record short clip and run aquarium detection
**Dependencies:**
- view.camera (direct camera access) ⚠️
- _publish_processing_mode() [stays in MainViewModel]
- settings (fps)
- weight_manager.get_weight_path_by_method()
- AquariumDetector
- ui_event_bus (status updates)
- tempfile (for temporary video)
- cv2.VideoWriter (OpenCV)
**Risk:** MEDIUM-HIGH (Camera capture loop, temp files)
**Tests:** test_main_view_model.py (calibration tests)

**IMPORTANT:** This method directly accesses `self.view.camera` and runs a 5-second
capture loop. Ensure camera resource management is correct.

**Phase 5 Checkpoint:**
- [ ] All 2 methods extracted
- [ ] Run: `poetry run pytest tests/test_main_view_model.py -k "live_camera or calibration" -v`
- [ ] All tests pass

---

## Final Verification

### ✅ All Phases Complete (488 lines extracted)

**Full Test Suite:**
```bash
# 1. Fast tests (excludes GUI/slow)
poetry run pytest -v

# 2. GUI tests
poetry run pytest -m gui -n0 -v

# 3. All tests
poetry run pytest -m "" -n0 -v

# 4. Coverage check
poetry run pytest --cov=src/zebtrack/core/main_view_model --cov-report=term-missing
```

**Expected Results:**
- [ ] All tests pass (2568 tests)
- [ ] Coverage maintained (>70%)
- [ ] MainViewModel reduced to ~4,184 lines
- [ ] RecordingSessionOrchestrator created (~550 lines with docstrings)

---

## Instance Variables to Move

These instance variables are used by recording methods and should move to orchestrator:

```python
# In MainViewModel.__init__ (lines 375-376):
self._pending_external_trigger: dict | None = None
self._cancel_feedback_displayed = False  # Used by _show_cancel_feedback (not extracted)
```

**Action:**
- [ ] Move `_pending_external_trigger` to RecordingSessionOrchestrator
- [ ] Keep `_cancel_feedback_displayed` in MainViewModel (used by other methods)

---

## Orchestrator Constructor Signature

```python
class RecordingSessionOrchestrator:
    """
    Orchestrates recording sessions and live camera analysis.

    Sprint 26: Extracted from MainViewModel to separate recording coordination
    from UI orchestration.
    """

    def __init__(
        self,
        # Core dependencies
        state_manager: StateManager,
        project_manager: ProjectManager,

        # Services
        recording_coordinator: RecordingCoordinator,
        recording_service: RecordingService,
        live_camera_service: LiveCameraService,

        # UI
        ui_event_bus: EventBus,
        view,  # GUI reference for dialogs and camera
        root,  # Tkinter root

        # Settings & Configuration
        settings_obj: Settings,
        weight_manager: WeightManager,

        # Callbacks to MainViewModel (for methods we didn't extract)
        setup_detector_callback: Callable[[], bool],
        setup_detector_zones_callback: Callable[[], None],
        setup_arduino_callback: Callable[[], bool],
        ensure_zones_before_recording_callback: Callable[[], bool],
        publish_processing_mode_callback: Callable[..., ProcessingReport],
    ):
        ...
```

---

## Methods That Need Callbacks to MainViewModel

These methods are called by extracted recording methods but stay in MainViewModel:

1. **setup_detector()** - line 1365
   - Called by: `start_recording()`
   - Purpose: Initialize detector

2. **setup_detector_zones()** - line 1393
   - Called by: `start_recording()`
   - Purpose: Configure detector zones

3. **setup_arduino()** - line 1382
   - Called by: `start_recording()`
   - Purpose: Initialize Arduino

4. **_ensure_zones_before_recording()** - line 2924 [NOT EXTRACTED]
   - Called by: `start_recording()`
   - Purpose: Validate zones before recording
   - Reason: Complex UI flow, deferred to Sprint 27

5. **_publish_processing_mode()** - line 1088
   - Called by: `run_live_calibration()`
   - Purpose: Update UI processing mode
   - Reason: General UI orchestration method

---

## Event Dispatcher Updates

Update `_EVENT_METHOD_MAPPING` in MainViewModel:

```python
# FROM (old):
Events.RECORDING_START: ("start_recording", ["day", "group", "cobaia"], "kwargs_get"),
Events.RECORDING_STOP: ("stop_recording", [], "no_params"),
Events.RECORDING_TRIGGER: ("trigger_recording", ["event_code"], "kwargs_get"),

# TO (new - delegate to orchestrator):
Events.RECORDING_START: ("recording_session_orchestrator.start_recording", ["day", "group", "cobaia"], "kwargs_get"),
Events.RECORDING_STOP: ("recording_session_orchestrator.stop_recording", [], "no_params"),
Events.RECORDING_TRIGGER: ("recording_session_orchestrator.trigger_recording", ["event_code"], "kwargs_get"),
```

---

## Manual Testing Checklist

After extraction, perform manual smoke tests:

### Recording Flow Tests
- [ ] Start live project recording (with Arduino)
- [ ] Start live project recording (without Arduino)
- [ ] External trigger recording (Arduino event start)
- [ ] Stop recording (manual)
- [ ] Stop recording (Arduino event stop)

### Live Camera Tests
- [ ] Live camera analysis (via dialog)
- [ ] Live camera analysis (from config)
- [ ] Live project session start
- [ ] Live calibration (auto aquarium detection)

### Edge Cases
- [ ] Cancel recording during external trigger wait
- [ ] Start recording with no zones (should validate)
- [ ] Live camera analysis with no zones (creates default arena)
- [ ] Recording with failed detector setup

---

## Rollback Plan

If extraction causes major issues:

```bash
# 1. Stash changes
git stash

# 2. Verify tests pass on main branch
git checkout main
poetry run pytest -m ""

# 3. Return to branch
git checkout claude/extract-mainviewmodel-logic-017SK4UUL51U3j6nV8XPKLEQg
git stash pop

# 4. Incremental rollback (phase by phase)
# Revert Phase 5 (live camera) first if that's the issue
# Then Phase 4 (core recording) if needed
# etc.
```

---

## Documentation Updates

After successful extraction:

- [ ] Update `/home/user/ZebTrack-AI/CLAUDE.md`
  - Add Sprint 26 to version history
  - Update architecture section with RecordingSessionOrchestrator
  - Add to Phase history section

- [ ] Update `/home/user/ZebTrack-AI/docs/ARCHITECTURE.md`
  - Add RecordingSessionOrchestrator to core layers
  - Update dependency diagram

- [ ] Create `/home/user/ZebTrack-AI/docs/sprint26_completion_report.md`
  - Before/after metrics
  - Test results
  - Known issues
  - Future work (Sprint 27 deferred items)

---

## Success Criteria ✅

Sprint 26 is complete when:

1. ✅ RecordingSessionOrchestrator created with 14 methods (488 lines)
2. ✅ MainViewModel reduced from 4,672 to ~4,184 lines
3. ✅ All 2568 tests pass
4. ✅ Coverage maintained at >70%
5. ✅ Manual smoke tests pass
6. ✅ Documentation updated
7. ✅ Commit message follows conventions
8. ✅ No regressions in recording functionality

---

## Next Sprint Preview (Sprint 27)

**Deferred Items (252 lines):**
1. `start_live_camera_analysis_from_config` (148 lines)
2. `_ensure_zones_before_recording` (93 lines)

**Prerequisites:**
- Create `ArenaCreationOrchestrator`
- Create `ZoneValidationOrchestrator`

**Expected Reduction:**
- Sprint 27: 4,184 → ~3,932 lines (252 lines, 6.0%)
- Cumulative: 5,224 → 3,932 lines (1,292 lines, 24.7%)

---

## Notes

- **Camera Access:** `run_live_calibration` directly accesses `self.view.camera`.
  This is safe because the method checks `camera.is_opened()` first.

- **Temp Files:** `run_live_calibration` uses `tempfile.NamedTemporaryFile`.
  Cleanup is guaranteed by try/finally block.

- **Threading:** No direct thread creation in extracted methods. All threading
  is delegated to services (RecordingCoordinator, LiveCameraService).

- **State Management:** All recording state is managed via StateManager.
  No direct state mutation in extracted methods.
