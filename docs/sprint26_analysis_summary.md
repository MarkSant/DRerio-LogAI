# Sprint 26 Analysis Summary

**Generated:** 2025-11-14
**Objective:** Analyze recording/session methods for extraction in Sprint 26

---

## Quick Answer

**✅ RECOMMENDATION: Proceed with Option B (Core + Live Camera Analysis)**

- **Extract:** 14 methods, 488 lines
- **Risk:** MEDIUM (acceptable)
- **Result:** 4,672 → 4,184 lines (10.4% reduction)
- **Meets Sprint Goal:** Yes (~500 lines)

---

## What We Analyzed

Identified **16 recording/session-related methods** in MainViewModel totaling **763 lines**:

### Core Recording (363 lines)
- `start_recording` (66)
- `stop_recording` (21)
- `start_live_camera_analysis` (65)
- `start_live_camera_analysis_from_config` (148)
- `start_live_project_session` (63)

### Helpers (194 lines)
- `_handle_external_trigger` (46)
- `_ensure_zones_before_recording` (93)
- `run_live_calibration` (99)
- `_clear_external_trigger_wait` (13)
- `trigger_recording` (17)
- `_schedule_recording` (24)
- `on_arduino_event` (21)

### State Management (87 lines)
- `is_recording` property (11)
- `_on_recording_state_changed` (20)
- `_setup_recording_service_callbacks` (20)
- `_init_recording_service` (36)

---

## Three Options Evaluated

| Option | Lines | Risk | Reduction | Sprint Goal |
|--------|-------|------|-----------|-------------|
| **A: Conservative** | 358 | LOW ✅ | 7.7% | ❌ Below target |
| **B: Recommended** | 488 | MEDIUM ⚠️ | 10.4% | ✅ Meets target |
| **C: Maximum** | 740 | HIGH ❌ | 15.8% | ⚠️ Too risky |

---

## Why Option B (Recommended)

### ✅ Pros
1. Meets sprint goal (~500 lines)
2. Complete recording coordination extracted
3. `run_live_calibration` is well-encapsulated (try/finally, bounded loop)
4. Camera code already tested in production
5. Clean separation from complex arena/zone logic
6. Logical grouping (all recording methods together)

### ⚠️ Cons
1. `run_live_calibration` has 5-second camera capture loop
2. Direct camera access via `self.view.camera`
3. Temp file management (mitigated by try/finally)

### Risk Mitigation
- Camera access is checked with `is_opened()` first
- 5-second capture loop is bounded (not infinite)
- Temp file cleanup guaranteed by try/finally
- Already used in production (stable)
- Comprehensive test coverage exists

---

## What NOT to Extract (Defer to Sprint 27)

### ❌ `start_live_camera_analysis_from_config` (148 lines)
**Why defer:**
- Creates default arena (complex geometry calculations)
- Opens temporary camera to get dimensions
- Math.sqrt calculations for arena sizing
- Should extract arena creation logic first

### ❌ `_ensure_zones_before_recording` (93 lines)
**Why defer:**
- Complex 3-way dialog branching
- Calls `run_live_calibration` (recursive dependency)
- Project type detection with different flows
- Should extract zone validation logic first

**Sprint 27 Prerequisites:**
- Create `ArenaCreationOrchestrator`
- Create `ZoneValidationOrchestrator`
- Then extract these 2 methods (252 lines)

---

## Extraction Plan (5 Phases)

### Phase 1: State Methods (87 lines) - LOW RISK ✅
1. `is_recording` property
2. `_on_recording_state_changed`
3. `_setup_recording_service_callbacks`
4. `_init_recording_service`

### Phase 2: Helpers (37 lines) - LOW RISK ✅
5. `_clear_external_trigger_wait`
6. `_schedule_recording`

### Phase 3: External Trigger (84 lines) - MEDIUM RISK ⚠️
7. `_handle_external_trigger`
8. `trigger_recording`
9. `on_arduino_event`

### Phase 4: Core Recording (150 lines) - MEDIUM RISK ⚠️
10. `start_recording`
11. `stop_recording`
12. `start_live_project_session`

### Phase 5: Live Camera (164 lines) - MEDIUM RISK ⚠️
13. `start_live_camera_analysis`
14. `run_live_calibration`

**Strategy:** Extract incrementally, run tests after each phase.

---

## Key Dependencies

### Methods Extracted Will Call (Stay in MainViewModel)
- `setup_detector()` - Detector initialization
- `setup_detector_zones()` - Zone configuration
- `setup_arduino()` - Arduino initialization
- `_ensure_zones_before_recording()` - Zone validation [deferred]
- `_publish_processing_mode()` - UI mode updates

### Services Used
- `recording_coordinator.start_recording()`
- `recording_coordinator.stop_recording()`
- `live_camera_service.start_session()`

### Hardware Dependencies
- Camera (via `self.view.camera`) - `run_live_calibration` only
- Arduino (optional, graceful degradation)

---

## Expected Results

### Before
- **File:** `/home/user/ZebTrack-AI/src/zebtrack/core/main_view_model.py`
- **Size:** 4,672 lines
- **Recording Methods:** Scattered across file (lines 617-3016)

### After
- **MainViewModel:** ~4,184 lines (-488, -10.4%)
- **RecordingSessionOrchestrator:** ~550 lines (new file)
- **Total Code:** Same (no net change, just reorganized)

### Cumulative Progress
```
Sprint 24: 5,224 → 4,949 lines (-275, -5.3%) VideoProcessingOrchestrator
Sprint 25: 4,949 → 4,674 lines (-275, -5.6%) AnalysisOrchestrator
Sprint 26: 4,674 → 4,184 lines (-488, -10.4%) RecordingSessionOrchestrator
───────────────────────────────────────────────────────────────────────
TOTAL:     5,224 → 4,184 lines (-1,040, -19.9%)
```

**Target:** Get below 3,000 lines
**Remaining:** 1,184 lines to extract (28.3% more)

---

## Risk Assessment

| Risk Category | Level | Details |
|--------------|-------|---------|
| **Threading** | LOW ✅ | No direct thread creation, delegates to services |
| **Hardware** | MEDIUM ⚠️ | Camera access in `run_live_calibration` (bounded, checked) |
| **State** | LOW ✅ | All via StateManager (thread-safe) |
| **UI** | MEDIUM ⚠️ | Dialog handling, status updates |
| **Integration** | MEDIUM ⚠️ | Need E2E tests for full flow |
| **Overall** | MEDIUM ⚠️ | **Acceptable for sprint** |

---

## Testing Requirements

### Existing Tests to Update
- `tests/test_main_view_model.py` - Recording tests
- `tests/test_recording_service.py` - May need updates
- `tests/test_live_camera_service.py` - Verify delegation

### New Tests Needed
- `tests/test_recording_session_orchestrator.py` (~800-1000 lines)
  - Unit tests for all 14 methods
  - Mock all dependencies
  - Test external trigger flow
  - Test Arduino events
  - Test calibration workflow

### Test Commands
```bash
# Fast tests (excludes GUI/slow)
poetry run pytest -v

# All tests
poetry run pytest -m "" -n0 -v

# Coverage
poetry run pytest --cov=src/zebtrack/core --cov-report=term-missing
```

---

## Manual Smoke Tests

After extraction, test manually:

**Recording Flow:**
- [ ] Start live project recording (with/without Arduino)
- [ ] External trigger recording (Arduino start)
- [ ] Stop recording (manual and Arduino)

**Live Camera:**
- [ ] Live camera analysis (dialog)
- [ ] Live project session start
- [ ] Live calibration (aquarium detection)

**Edge Cases:**
- [ ] Cancel during external trigger wait
- [ ] Recording with no zones (validation)
- [ ] Live camera with no zones (default arena)

---

## Success Criteria

Sprint 26 is complete when:

1. ✅ `RecordingSessionOrchestrator` created with 14 methods
2. ✅ MainViewModel reduced to ~4,184 lines
3. ✅ All 2568 tests pass
4. ✅ Coverage maintained (>70%)
5. ✅ Manual smoke tests pass
6. ✅ Documentation updated
7. ✅ No functional regressions

---

## Documents Created

1. **`sprint26_recording_methods_analysis.md`** (detailed)
   - Complete method analysis table
   - Complexity assessment
   - Three extraction options
   - Risk breakdown
   - Dependencies analysis

2. **`sprint26_extraction_checklist.md`** (actionable)
   - Phase-by-phase extraction steps
   - Exact line numbers for each method
   - Test checkpoints after each phase
   - Orchestrator constructor signature
   - Manual testing checklist

3. **`sprint26_analysis_summary.md`** (this file)
   - Quick recommendation
   - Key findings
   - Expected results
   - Success criteria

---

## Next Steps

1. **Review this analysis** with team/stakeholders
2. **Confirm Option B** as the extraction plan
3. **Read existing tests** for recording methods
4. **Create RecordingSessionOrchestrator** skeleton
5. **Extract Phase 1** (state methods, 87 lines)
6. **Run tests** after Phase 1
7. **Continue phases 2-5** incrementally
8. **Full test suite** after all phases
9. **Manual smoke tests**
10. **Update documentation**
11. **Commit with Sprint 26 message**

---

## Questions/Concerns?

**Q: Is `run_live_calibration` safe to extract?**
A: Yes. It has a bounded 5-second loop, checks camera availability, uses try/finally for cleanup, and is already tested in production.

**Q: What about `_ensure_zones_before_recording`?**
A: Defer to Sprint 27. It has complex 3-way dialog branching and recursive calibration calls. Better to extract zone validation logic first.

**Q: What about `start_live_camera_analysis_from_config`?**
A: Defer to Sprint 27. It creates default arenas with complex geometry. Better to extract arena creation logic first.

**Q: Why not Option A (Conservative)?**
A: It's too conservative (358 lines, below sprint goal). Option B adds only 2 methods (130 lines) but achieves the sprint goal with acceptable risk.

**Q: Why not Option C (Maximum)?**
A: Too risky. The 2 additional methods have complex arena creation and zone validation logic that should be extracted separately in Sprint 27.

---

## Approval

**Status:** ⏳ Awaiting confirmation
**Recommended:** ✅ Option B (488 lines)
**Risk:** ⚠️ MEDIUM (acceptable)

Once approved, proceed with `sprint26_extraction_checklist.md` for implementation.
