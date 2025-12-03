# Sprint 26: Recording Methods Analysis Report

**Date:** 2025-11-14
**Analyst:** Claude
**Current MainViewModel Size:** 4,672 lines
**Sprint Goal:** Extract ~500 lines of recording/session methods

---

## Executive Summary

Identified **16 recording/session-related methods** totaling **763 lines**. Analysis reveals three extraction strategies based on complexity and risk level.

**Recommendation:** Option B (Core + Live Camera Analysis) - **488 lines** extraction with MEDIUM risk.

---

## 1. Method Analysis Table

| Method Name | Line Range | Lines | Complexity | Risk | Extract? |
|------------|------------|-------|------------|------|----------|
| **Core Recording Methods** |
| `start_recording` | 2556-2621 | 66 | Medium | Medium | ✅ Yes |
| `stop_recording` | 2838-2858 | 21 | Low | Low | ✅ Yes |
| `start_live_project_session` | 2860-2922 | 63 | Medium | Medium | ✅ Yes |
| `start_live_camera_analysis` | 2623-2687 | 65 | Medium | Medium | ⚠️ Option |
| `start_live_camera_analysis_from_config` | 2689-2836 | 148 | High | High | ❌ Defer |
| **Helper Methods** |
| `_handle_external_trigger` | 2509-2554 | 46 | Medium | Low | ✅ Yes |
| `trigger_recording` | 1177-1193 | 17 | Low | Low | ✅ Yes |
| `_schedule_recording` | 1195-1218 | 24 | Low | Low | ✅ Yes |
| `_clear_external_trigger_wait` | 1129-1141 | 13 | Low | Low | ✅ Yes |
| `on_arduino_event` | 1155-1175 | 21 | Medium | Medium | ✅ Yes |
| **State/Initialization Methods** |
| `is_recording` (property) | 617-627 | 11 | Low | Low | ✅ Yes |
| `_on_recording_state_changed` | 721-740 | 20 | Low | Low | ✅ Yes |
| `_setup_recording_service_callbacks` | 822-841 | 20 | Low | Low | ✅ Yes |
| `_init_recording_service` | 843-878 | 36 | Low | Low | ✅ Yes |
| **Complex Methods (High Risk)** |
| `_ensure_zones_before_recording` | 2924-3016 | 93 | High | High | ❌ Defer |
| `run_live_calibration` | 2409-2507 | 99 | High | High | ❌ Defer |

**Total Lines Identified:** 763

---

## 2. Complexity Analysis

### High Complexity Methods (>90 lines, multiple dependencies)

#### `start_live_camera_analysis_from_config` (148 lines)
- **Complexity Score:** 9/10
- **Dependencies:**
  - LiveCameraService delegation
  - Default arena creation (opens temp camera)
  - Complex config extraction
  - Math calculations for arena sizing
- **Risks:** Camera resource management, geometry calculations
- **Recommendation:** DEFER to Sprint 27 - needs separate arena creation orchestrator

#### `run_live_calibration` (99 lines)
- **Complexity Score:** 8/10
- **Dependencies:**
  - Direct camera access (`self.view.camera`)
  - Temporary file management
  - OpenCV VideoWriter
  - AquariumDetector
  - Processing mode state management
- **Risks:** Camera capture loop, temp file cleanup, detector initialization
- **Recommendation:** DEFER to Sprint 27 - high hardware integration risk

#### `_ensure_zones_before_recording` (93 lines)
- **Complexity Score:** 8/10
- **Dependencies:**
  - Complex UI dialog flow (3 different dialog paths)
  - Project type detection
  - Zone validation logic
  - Calls `run_live_calibration`
- **Risks:** Dialog sequencing, recursive call to calibration
- **Recommendation:** DEFER to Sprint 27 - complex UI orchestration

### Medium Complexity Methods (40-70 lines)

- `start_recording` (66 lines) - Coordinates detector, Arduino, folder creation
- `start_live_camera_analysis` (65 lines) - Dialog handling + service delegation
- `start_live_project_session` (63 lines) - Project config extraction + service delegation
- `_handle_external_trigger` (46 lines) - External trigger validation + UI feedback

### Low Complexity Methods (<30 lines)

All other helper methods and state management methods are low complexity with clear, focused responsibilities.

---

## 3. Recommended Extraction Strategies

### **Option A: Conservative (Core Only)** ✅ SAFEST
**Lines to Extract:** 358 lines
**Risk Level:** LOW
**Reduction:** 7.7% (4,672 → 4,314 lines)

**Methods:**
1. `start_recording` (66)
2. `stop_recording` (21)
3. `start_live_project_session` (63)
4. `_handle_external_trigger` (46)
5. `trigger_recording` (17)
6. `_schedule_recording` (24)
7. `_clear_external_trigger_wait` (13)
8. `on_arduino_event` (21)
9. `is_recording` (property) (11)
10. `_on_recording_state_changed` (20)
11. `_setup_recording_service_callbacks` (20)
12. `_init_recording_service` (36)

**Pros:**
- Lowest risk, highest confidence
- Clean logical grouping
- No complex camera/calibration code

**Cons:**
- Below 500-line sprint goal
- Leaves significant recording code in MainViewModel

---

### **Option B: Core + Live Camera Analysis** ⭐ RECOMMENDED
**Lines to Extract:** 488 lines
**Risk Level:** MEDIUM
**Reduction:** 10.4% (4,672 → 4,184 lines)

**Methods:** All from Option A + these 2:
13. `start_live_camera_analysis` (65)
14. `run_live_calibration` (99)

**Additional Methods:** 164 lines

**Pros:**
- Meets sprint goal (~500 lines)
- Consolidates all recording coordination
- Live camera analysis fully extracted
- Manageable risk (calibration is well-tested)

**Cons:**
- `run_live_calibration` has camera capture loop (needs careful testing)
- Temp file management adds cleanup responsibility

**Risk Mitigation:**
- `run_live_calibration` is already well-encapsulated
- Camera access via `self.view.camera` (no new patterns)
- Temp file cleanup in try/finally (safe)

---

### **Option C: Maximum Extraction** ⚠️ HIGH RISK
**Lines to Extract:** 740 lines
**Risk Level:** HIGH
**Reduction:** 15.8% (4,672 → 3,932 lines)

**Methods:** All from Option B + these 3:
15. `start_live_camera_analysis_from_config` (148)
16. `_ensure_zones_before_recording` (93)

**Additional Methods:** 252 lines

**Pros:**
- Maximum reduction in single sprint
- Removes most recording-related code

**Cons:**
- Very high complexity (arena creation, zone validation)
- `start_live_camera_analysis_from_config` opens temp camera
- `_ensure_zones_before_recording` has complex dialog sequencing
- Requires extracting arena creation logic first
- Higher integration test burden

**Recommendation:** DEFER these 2 methods to Sprint 27

---

## 4. Dependencies Analysis

### Methods These Will Need to Call (Stay in MainViewModel)

1. **Detector Management:**
   - `setup_detector()` - line 1365
   - `setup_detector_zones()` - line 1393

2. **Hardware Management:**
   - `setup_arduino()` - line 1382

3. **UI Coordination:**
   - `_publish_processing_mode()` - line 1088
   - `ui_coordinator.*` methods
   - `ui_event_bus.publish_event()`

4. **State Access:**
   - `state_manager.*` methods
   - `project_manager.*` methods

5. **Services:**
   - `recording_coordinator.start_recording()`
   - `recording_coordinator.stop_recording()`
   - `live_camera_service.start_session()`

### Instance Variables Accessed

- `self._pending_external_trigger` (dict | None) - line 375
- `self._cancel_feedback_displayed` (bool) - line 376
- `self.view` - GUI reference
- `self.root` - Tkinter root
- `self.settings` - Settings object
- `self.detector` - Detector instance
- `self.weight_manager` - Weight manager

---

## 5. Risk Assessment

### Threading Concerns ⚠️

**LOW RISK (Option A & B):**
- All methods delegate to services (RecordingCoordinator, LiveCameraService)
- No direct thread creation in extracted methods
- State management via thread-safe StateManager

**MEDIUM RISK (if including `run_live_calibration`):**
- 5-second camera capture loop (line 2448)
- Blocking I/O on main thread
- VideoWriter resource management

**Mitigation:**
- Capture loop is short (5s) and bounded
- Already used in production
- Try/finally ensures cleanup

### Hardware Dependencies 🔌

**Methods with hardware access:**
1. `start_recording` - Arduino setup (optional)
2. `on_arduino_event` - Arduino event handling
3. `run_live_calibration` - Direct camera access (`self.view.camera`)
4. `start_live_camera_analysis_from_config` - Temp camera creation

**Mitigation:**
- Arduino is optional (graceful degradation)
- Camera access via existing `self.view.camera` reference
- Services handle hardware lifecycle

### State Management 📊

**All methods properly use StateManager:**
- `is_recording` property wraps StateManager
- `_on_recording_state_changed` subscribes to state changes
- No direct state mutation (all via `state_manager.update_*`)

**LOW RISK** - State management is well-architected.

---

## 6. Extraction Plan (Option B - Recommended)

### Phase 1: Create RecordingSessionOrchestrator

```python
class RecordingSessionOrchestrator:
    """
    Orchestrates recording sessions and live camera analysis.

    Sprint 26: Extracted from MainViewModel to separate recording coordination
    from UI orchestration.

    Responsibilities:
    - Start/stop recording sessions
    - Live project session management
    - Live camera analysis coordination
    - External trigger handling
    - Live calibration workflow
    """

    def __init__(
        self,
        controller,  # Reference to MainViewModel for dependencies
        state_manager: StateManager,
        project_manager: ProjectManager,
        recording_coordinator: RecordingCoordinator,
        live_camera_service: LiveCameraService,
        ui_event_bus: EventBus,
        view,
        root,
        settings_obj,
        weight_manager,
    ):
        ...
```

### Phase 2: Extract Methods (in order)

**Step 1: State Management Methods** (LOW RISK)
1. `is_recording` property (11 lines)
2. `_on_recording_state_changed` (20 lines)
3. `_setup_recording_service_callbacks` (20 lines)
4. `_init_recording_service` (36 lines)

**Step 2: Helper Methods** (LOW RISK)
5. `_clear_external_trigger_wait` (13 lines)
6. `_schedule_recording` (24 lines)

**Step 3: External Trigger Methods** (MEDIUM RISK)
7. `_handle_external_trigger` (46 lines)
8. `trigger_recording` (17 lines)
9. `on_arduino_event` (21 lines)

**Step 4: Core Recording Methods** (MEDIUM RISK)
10. `start_recording` (66 lines)
11. `stop_recording` (21 lines)
12. `start_live_project_session` (63 lines)

**Step 5: Live Camera Methods** (MEDIUM RISK)
13. `start_live_camera_analysis` (65 lines)
14. `run_live_calibration` (99 lines)

### Phase 3: Update MainViewModel

- Add `recording_session_orchestrator` property
- Delegate methods to orchestrator
- Update event dispatcher mappings
- Update tests

---

## 7. Expected Reduction (Option B)

**Current Size:** 4,672 lines
**Lines to Extract:** 488 lines
**Expected New Size:** 4,184 lines
**Reduction:** 10.4%

**Progress Tracking:**
- Sprint 24: 5,224 → 4,949 lines (275 lines, 5.3%)
- Sprint 25: 4,949 → 4,674 lines (275 lines, 5.6%)
- **Sprint 26: 4,674 → 4,184 lines (488 lines, 10.4%)** ⭐
- **Cumulative: 5,224 → 4,184 lines (1,040 lines, 19.9%)**

---

## 8. Test Coverage Requirements

### Existing Tests to Update

1. **test_main_view_model.py**
   - Update `start_recording` tests
   - Update `stop_recording` tests
   - Update external trigger tests
   - Update live camera analysis tests

2. **test_recording_service.py**
   - May need updates if coordination changes

3. **test_live_camera_service.py**
   - Verify delegation still works

### New Tests Needed

1. **test_recording_session_orchestrator.py**
   - Unit tests for all 14 extracted methods
   - Mock dependencies (state_manager, services, etc.)
   - Test external trigger flow
   - Test Arduino event handling
   - Test calibration workflow

2. **Integration Tests**
   - E2E recording session test
   - E2E live camera analysis test
   - External trigger integration test

**Estimated Test Lines:** ~800-1000 lines

---

## 9. Sprint 27 Deferred Items

**Methods to Extract in Sprint 27** (252 lines):
1. `start_live_camera_analysis_from_config` (148 lines)
2. `_ensure_zones_before_recording` (93 lines)

**Additional Work Required:**
- Create `ArenaCreationOrchestrator` for default arena logic
- Create `ZoneValidationOrchestrator` for zone checks
- These methods have higher complexity and UI dependencies

---

## 10. Final Recommendation

### ⭐ **Proceed with Option B: Core + Live Camera Analysis**

**Rationale:**
1. ✅ Meets sprint goal (~500 lines)
2. ✅ Logical grouping (all recording coordination)
3. ✅ Manageable risk (MEDIUM vs HIGH)
4. ✅ `run_live_calibration` is well-tested and encapsulated
5. ✅ Clean separation from complex arena/zone logic
6. ✅ Achieves 10.4% reduction (strong progress)

**Risk Mitigation:**
- Extract in phases (state → helpers → core → live)
- Comprehensive test coverage
- Manual testing with real camera
- Keep complex methods (`_ensure_zones_before_recording`, `start_live_camera_analysis_from_config`) for Sprint 27

**Success Criteria:**
- ✅ All 488 lines extracted
- ✅ All existing tests pass
- ✅ New orchestrator tests added
- ✅ No regression in recording functionality
- ✅ Manual smoke test with camera + Arduino

---

## 11. Implementation Checklist

### Pre-Extraction
- [ ] Read all test files for recording methods
- [ ] Document current test coverage
- [ ] Create `RecordingSessionOrchestrator` skeleton

### During Extraction
- [ ] Extract Phase 1: State methods (87 lines)
- [ ] Run tests after Phase 1
- [ ] Extract Phase 2: Helper methods (37 lines)
- [ ] Run tests after Phase 2
- [ ] Extract Phase 3: External trigger (84 lines)
- [ ] Run tests after Phase 3
- [ ] Extract Phase 4: Core recording (150 lines)
- [ ] Run tests after Phase 4
- [ ] Extract Phase 5: Live camera (164 lines)
- [ ] Run tests after Phase 5

### Post-Extraction
- [ ] Full test suite passes (`pytest -m ""`)
- [ ] Coverage maintained (>70%)
- [ ] Manual smoke test
- [ ] Update CLAUDE.md
- [ ] Document Sprint 26 completion

---

## Appendix: Method Call Graph

```
MainViewModel
├── start_recording()
│   ├── _ensure_zones_before_recording() [DEFER]
│   │   └── run_live_calibration() [EXTRACT]
│   ├── setup_detector()
│   ├── setup_detector_zones()
│   ├── setup_arduino()
│   └── _handle_external_trigger()
│       └── trigger_recording()
│           └── _schedule_recording()
│
├── stop_recording()
│   ├── _clear_external_trigger_wait()
│   └── recording_coordinator.stop_recording()
│
├── start_live_camera_analysis() [EXTRACT]
│   └── live_camera_service.start_session()
│
├── start_live_camera_analysis_from_config() [DEFER]
│   ├── Camera() [temp]
│   ├── ZoneData() [default arena]
│   └── live_camera_service.start_session()
│
├── start_live_project_session() [EXTRACT]
│   └── live_camera_service.start_session()
│
└── on_arduino_event() [EXTRACT]
    ├── trigger_recording()
    └── stop_recording()
```

**Legend:**
- [EXTRACT] - Include in Sprint 26
- [DEFER] - Postpone to Sprint 27
