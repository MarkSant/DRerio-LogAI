# ADR-006: LiveBatchCoordinator - Future Feature v2.3.0+

**Status**: Deferred  
**Date**: January 2026  
**Context**: Live Camera v2.2.0 Audit

## Problem

`LiveBatchCoordinator` (`src/zebtrack/coordinators/live_batch_coordinator.py`) is a 433-line implementation with:
- ✅ Complete batch tracking logic
- ✅ Unified report generation
- ✅ E2E test coverage (`tests/test_live_camera_workflow_e2e.py`)
- ❌ Never instantiated in production code (`__main__.py`)
- ❌ Events published but never triggered (`BATCH_ANALYSIS_COMPLETED`)

`UICoordinator` has a handler (`_on_batch_analysis_completed`) waiting for events that never arrive.

## Decision

**DEFER to v2.3.0** - Do NOT integrate now because:

1. **Incomplete UX Design**: No UI to mark batch completion or trigger unified reports
2. **Unclear User Workflow**: When/how users indicate "last session of batch"?
3. **Metadata Dependency**: Requires `group`, `day`, `subject_id` in wizard (not yet collected)
4. **Scope Creep**: Proper integration requires:
   - Wizard step for batch metadata
   - UI indicator for "same batch" sessions
   - Manual "Generate Batch Report" button
   - Automatic batch detection heuristics

## Consequences

### Immediate (v2.2.0)
- LiveBatchCoordinator remains dormant code
- Tests continue passing
- No production impact (feature unused)

### Future (v2.3.0+)
When integrating:
1. Add batch metadata to LiveConfigStep wizard
2. Instantiate in `__main__.py` Composition Root:
   ```python
   live_batch_coordinator = LiveBatchCoordinator(
       project_manager=project_manager,
       analysis_service=analysis_service,
       state_manager=state_manager,
       event_bus=event_bus,
       settings_obj=settings_obj,
   )
   ```
3. Wire `SessionCoordinator._on_live_session_complete()` to call:
   ```python
   live_batch_coordinator.register_session(experiment_id, metadata)
   ```
4. Add UI button in Reports tab: "Generate Batch Report"
5. Update `UICoordinator._on_batch_analysis_completed` implementation

## Alternatives Considered

1. **Remove code entirely** - Rejected; tests passing, no harm in keeping
2. **Integrate now** - Rejected; missing UX design and wizard metadata
3. **Move to archive** - Rejected; active E2E tests would break

## References

- Implementation: `src/zebtrack/coordinators/live_batch_coordinator.py`
- Tests: `tests/test_live_camera_workflow_e2e.py` (lines 197-240)
- UI Handler: `src/zebtrack/ui/ui_coordinator.py` (lines 699-740)
- Audit Finding: "LiveBatchCoordinator exists but never instantiated"
