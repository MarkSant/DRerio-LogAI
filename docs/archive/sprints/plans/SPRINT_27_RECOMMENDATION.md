# Sprint 27: ProjectOrchestrator Extraction - RECOMMENDATION

> Relocated to `docs/sprints/plans/` as the canonical recommendation deck for
> Sprint 27. A concise roll-up lives at
> [`overview/SPRINT_27_SUMMARY.md`](../overview/SPRINT_27_SUMMARY.md).

<!-- markdownlint-disable MD022 MD029 MD032 MD026 MD009 MD031 -->

## Executive Summary

✅ **RECOMMENDATION: PROCEED with extraction of 385 lines (14 methods)**

**Confidence Level**: HIGH for Groups A, C, D (203 lines, 53%)
**Confidence Level**: MEDIUM for Group B (182 lines, 47%)

---

## Quick Decision Matrix

| Factor | Assessment | Notes |
| -------- | ------------ | ------- |
| **Size Target** | ✅ ON TARGET | 385 lines vs. ~400 planned |
| **Risk Level** | ✅ ACCEPTABLE | 53% low-risk, 47% medium-risk |
| **Logical Cohesion** | ✅ STRONG | Clear project lifecycle theme |
| **Test Coverage** | ✅ EXISTING | Most methods already tested |
| **Dependencies** | ⚠️ MODERATE | 9 callbacks needed, but manageable |

---

## What to Extract (Sprint 27)

### ✅ GROUP A: Lifecycle & Workflow (74 lines) - START HERE
**Priority**: HIGHEST - Clean extraction, all delegate to existing components

```python
# These are the easiest wins:
close_project(self)                              # 14 lines
create_project_workflow(self, **kwargs)          # 21 lines
open_project_workflow(self, project_path)        # 18 lines
start_project_processing_workflow(self)          # 8 lines
process_pending_project_videos(self, videos)     # 13 lines
```

**Why extract first**:
- All delegate to existing orchestrators/adapters
- Minimal internal state
- Clear input/output contracts

---

### ✅ GROUP C: Asset Management (81 lines) - EXTRACT SECOND
**Priority**: HIGH - Simple delegation pattern

```python
can_remove_project_asset(self, video_path, asset)      # 18 lines
delete_project_asset(self, video_path, asset, delete)  # 35 lines
_register_project_outputs(self, video_path, ...)       # 28 lines
```

**Why extract second**:
- Simple delegates to project_manager
- Clear error handling
- Low risk

---

### ✅ GROUP D: Supporting Methods (48 lines) - EXTRACT THIRD
**Priority**: MEDIUM - Context manager needs care

```python
_setup_zones_from_project(self)                  # 10 lines
project_calibration_session(self)                # 19 lines (context manager)
```

**Why extract third**:
- Small footprint
- Context manager needs careful testing
- Supports other groups

---

### ✅ GROUP B: Model Overrides (182 lines) - EXTRACT LAST
**Priority**: MEDIUM - Highest complexity but manageable

```python
# State checks (low risk - 34 lines)
are_project_overrides_active(self)               # 8 lines
has_project_override_settings(self)              # 11 lines
_get_project_data_dict(self)                     # 7 lines
_ensure_project_overrides_record(self)           # 8 lines

# Settings operations (medium risk - 148 lines)
_persist_project_model_settings(self, w, ov)     # 26 lines
copy_global_model_settings_to_project(self)      # 28 lines
save_current_calibration_to_project(self)        # 30 lines
resolve_project_model_settings(self, overrides)  # 64 lines ⚠️ LARGEST
```

**Why extract last**:
- Heavy project_data manipulation
- State consistency critical
- Needs comprehensive tests
- **WATCH**: `resolve_project_model_settings` is 64 lines!

---

## What NOT to Extract (Sprint 27)

### ⏸️ DEFER TO SPRINT 28 (149 lines)

```python
# Too complex for Sprint 27:
apply_project_model_overrides(self, overrides)   # 32 lines, complexity: 19
save_project_model_overrides(self, w, ov)        # 30 lines, complexity: 11
apply_project_settings_to_batch(self, videos)    # 87 lines, complexity: 15
```

**Reasons**:
1. `apply_project_model_overrides`: 7 project_manager calls, complex state updates
2. `save_project_model_overrides`: Tightly coupled to above
3. `apply_project_settings_to_batch`: 87 lines, multiple concerns

**Strategy**: Extract in Sprint 28 after Groups A-D stabilize

---

### ❌ KEEP IN MAINVIEWMODEL (86 lines)

```python
# Not project lifecycle:
_on_project_state_changed(...)      # 11 lines - MVVM observer
refresh_project_views(...)           # 22 lines - UI coordinator
start_live_project_session(...)      # 24 lines - Recording domain
_apply_wizard_detector_overrides(...) # 48 lines - Wizard/Detector domain
```

**Reasons**: Different domains, core ViewModel responsibilities

---

## Implementation Strategy

### Phase 1: Setup (1-2 hours)
1. Create `src/zebtrack/core/orchestrators/project_orchestrator.py`
2. Define class skeleton with all 14 method signatures
3. Add constructor with 9 callback parameters
4. Add type hints and docstrings

### Phase 2: Extract Groups in Order (4-6 hours)
**Order matters! Follow this sequence:**

1. **Group A first** (1 hour)
   - Extract lifecycle methods
   - Create MainViewModel facades
   - Run tests

2. **Group C second** (1 hour)
   - Extract asset management
   - Test asset removal workflows

3. **Group D third** (1 hour)
   - Extract zones setup
   - **CAREFUL**: Test context manager thoroughly

4. **Group B last** (2-3 hours)
   - Extract helpers first (34 lines)
   - Extract settings ops (148 lines)
   - **CRITICAL**: Test model override state consistency
   - **WATCH**: `resolve_project_model_settings` (64 lines!)

### Phase 3: Integration (2-3 hours)
1. Wire orchestrator in `__main__.py` composition root
2. Update all MainViewModel methods to delegate
3. Run full test suite
4. Fix any state synchronization issues

### Phase 4: Testing (2-3 hours)
1. Run existing tests: `poetry run pytest`
2. Add integration tests for:
   - Project open/close cycle
   - Model override workflows
   - Asset management
3. Test edge cases:
   - Missing project_data
   - Invalid overrides
   - Concurrent access (if applicable)

**Total Estimated Time**: 9-14 hours

---

## Risk Mitigation Plan

### Risk 1: State Consistency (Model Overrides)
**Problem**: `_using_project_overrides` flag in ViewModel vs. orchestrator state

**Mitigation**:
1. Keep flag in ViewModel for now
2. Pass flag value to orchestrator methods
3. Orchestrator returns updated flag value
4. ViewModel updates flag after orchestrator call
5. **Sprint 28**: Consider moving to StateManager

**Example**:
```python
# MainViewModel facade
def apply_project_model_overrides(self, overrides=None):
    resolved_weight, resolved_openvino = self.project_orchestrator.apply_project_model_overrides(
        overrides=overrides,
        using_project_overrides=self._using_project_overrides,
        active_weight_name=self.active_weight_name,
        use_openvino=self.use_openvino,
    )
    self._using_project_overrides = True  # Update flag
    return resolved_weight, resolved_openvino
```

---

### Risk 2: Callback Hell (9 Callbacks)
**Problem**: Constructor has 9 callback parameters

**Mitigation**:
1. Group callbacks into protocol classes:
   ```python
   class DetectorCallbacks(Protocol):
       setup_detector: Callable
       set_active_weight: Callable
       set_openvino_usage: Callable
       update_openvino_status: Callable
       setup_detector_zones: Callable
       restore_detector_settings: Callable

   class ProjectCallbacks(Protocol):
       refresh_project_views: Callable
       get_global_model_defaults: Callable
       apply_model_settings: Callable
   ```
2. Pass protocol instances instead of individual callbacks
3. Reduces constructor parameters from 14 to 7

---

### Risk 3: Context Manager State (`project_calibration_session`)
**Problem**: Context manager manipulates `_using_project_overrides` flag

**Mitigation**:
1. Make context manager a generator that yields and accepts flag updates
2. MainViewModel manages flag, orchestrator provides logic
3. Add comprehensive tests for:
   - Normal exit
   - Exception exit
   - Nested contexts (should this be allowed?)

**Example**:
```python
# ProjectOrchestrator
@contextmanager
def project_calibration_session(self, using_project_overrides: bool):
    """Context manager for project calibration mode."""
    previous_flag = using_project_overrides
    try:
        yield False  # Return new flag value to ViewModel
    finally:
        # Logic to determine final flag state
        if self.has_project_override_settings():
            final_flag = True
        else:
            final_flag = previous_flag
        yield final_flag  # Return final flag to ViewModel
```

---

### Risk 4: Large Method (`resolve_project_model_settings` - 64 lines)
**Problem**: Largest method to extract, complex fallback logic

**Mitigation**:
1. Extract AS-IS first (don't refactor during extraction)
2. Ensure comprehensive test coverage exists
3. Add logging for each fallback step
4. Document fallback chain clearly
5. **Sprint 28**: Consider breaking into smaller helpers

---

## Test Requirements

### Minimum Test Coverage (Before Merging)

1. **Unit Tests** (orchestrator methods in isolation):
   - ✅ All 14 methods have unit tests
   - ✅ Mock all dependencies
   - ✅ Test edge cases (None values, missing data, etc.)

2. **Integration Tests** (ViewModel → Orchestrator):
   - ✅ Project lifecycle: create → open → close
   - ✅ Model overrides: set → save → load → restore
   - ✅ Asset management: register → remove
   - ✅ Context managers: normal + exception paths

3. **Regression Tests** (existing tests must pass):
   - ✅ `poetry run pytest` - all existing tests pass
   - ✅ No new test skips or xfails
   - ✅ Coverage maintained or improved

4. **Critical Workflows** (end-to-end):
   - ✅ Open existing project → verify overrides applied
   - ✅ Close project → verify globals restored
   - ✅ Modify project settings → save → reload → verify persistence
   - ✅ Delete asset → verify cleanup

---

## Success Criteria

### Sprint 27 is complete when:

✅ **Code**:
- [ ] ProjectOrchestrator created with 14 methods
- [ ] MainViewModel facades delegate to orchestrator
- [ ] All extracted methods removed from MainViewModel
- [ ] MainViewModel reduced to ~3,920 lines

✅ **Tests**:
- [ ] All existing tests pass
- [ ] New unit tests for orchestrator (14 methods)
- [ ] Integration tests for critical workflows (4+ tests)
- [ ] Coverage maintained at 70%+

✅ **Documentation**:
- [ ] Orchestrator docstrings complete
- [ ] CLAUDE.md updated with Sprint 27 completion
- [ ] Sprint 27 marked as COMPLETE in tracking doc

✅ **Quality**:
- [ ] `poetry run ruff check .` passes
- [ ] No regressions in existing functionality
- [ ] Code review approved (if applicable)

---

## Post-Sprint Review Questions

After completing Sprint 27, evaluate:

1. **Size**: Did we achieve ~400 line reduction? (Target: 385)
2. **Risk**: Were there any unexpected coupling issues?
3. **Tests**: Did existing tests catch regressions?
4. **Callbacks**: Was the callback pattern manageable?
5. **State**: Did state synchronization work as expected?

**IF YES TO ALL**: Proceed with Sprint 28 (extract deferred methods)
**IF NO**: Investigate issues before continuing refactor

---

## Next Steps (After Sprint 27)

### Sprint 28: High-Complexity Methods (149 lines)
**Only proceed if Sprint 27 was clean!**

Extract the 3 deferred methods:
1. `apply_project_model_overrides` (32 lines, complexity: 19)
2. `save_project_model_overrides` (30 lines, complexity: 11)
3. `apply_project_settings_to_batch` (87 lines, complexity: 15)

**Expected Final Size**: ~3,770 lines (12% total reduction from Sprint 24)

---

## Final Recommendation

✅ **PROCEED WITH SPRINT 27**

**Rationale**:
- Well-scoped extraction (385 lines, 14 methods)
- Clear logical grouping (project lifecycle)
- Manageable risk (53% low, 47% medium)
- Follows proven pattern from Sprints 24-26
- Defers highest-complexity methods to Sprint 28

**Confidence**: 8/10

**Proceed**: YES, but follow the group extraction order (A → C → D → B)

---

**Document**: `/home/user/ZebTrack-AI/SPRINT_27_ANALYSIS.md` (detailed analysis)
**Status**: Ready for implementation
**Last Updated**: 2025-11-14
