# ADR-006: LiveBatchCoordinator - v2.3.0 Implementation

**Status**: ✅ Implemented
**Implementation Date**: January 3, 2026
**Original Decision**: January 2026 (Deferred from v2.2.0)
**Context**: Live Camera v2.2.0 Audit → v2.3.0 Integration

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

## Implementation Summary (v2.3.0)

### Completed January 3, 2026

### What Was Implemented

1. **Composition Root Integration** (`src/zebtrack/__main__.py`)

   ```python
   live_batch_coordinator = LiveBatchCoordinator(
       project_manager=project_manager,
       analysis_service=analysis_service,
       state_manager=state_manager,
       settings_obj=settings_obj,
   )
   ```

2. **Wizard Metadata Collection** (`src/zebtrack/ui/wizard/live_config_step.py`)
   - Added 4 new fields: experimental_group, experiment_day, subject_id, is_batch_last_session
   - Dropdown selection for groups ("Controle", "Tratado", "Veículo", etc.)
   - Day identifier input ("Dia_1", "Dia_2", etc.)
   - Subject ID input ("Peixe_01", "Peixe_02", etc.)
   - "Última sessão do lote" checkbox triggers unified report

3. **Session Registration** (`src/zebtrack/coordinators/session_coordinator.py`)
   - `_register_batch_session()` extracts metadata from wizard
   - Transforms wizard field names: `experimental_group` → `group`, `experiment_day` → `day`
   - Calls `live_batch_coordinator.register_session()` after video recording
   - Batch key format: `{group}_{day}_{subject_id}` (e.g., `Controle_Dia_1_Peixe_01`)

4. **UI Integration** (`src/zebtrack/ui/components/dialog_manager.py`)
   - Enhanced `handle_grid_cell_click()` to use `BlockDetailDialog`
   - Fallback to legacy `SubjectSelectionDialog` if coordinators unavailable
   - Dialog manages session start/stop and batch completion

5. **Multi-Aquarium Support**
   - Each aquarium = separate subject_id: `Peixe_01_Aquario_0`, `Peixe_01_Aquario_1`
   - Batch keys include aquarium suffix: `Controle_Dia_1_Peixe_01_Aquario_0`
   - Independent batch reporting per aquarium

6. **Bug Fixes**
   - Batch ID collision: Added microseconds to timestamp (`%Y%m%d_%H%M%S_%f`)
   - Removed duplicate experiment progress tab (kept existing `widget_factory` implementation)
   - Fixed test batch key assertions to use full format instead of wildcards

### Testing Results

- ✅ 4/4 integration tests passing (`tests/test_live_batch_integration.py`)
- ✅ 2385/2386 fast suite tests passing
- ✅ Wizard live tests: 16/16 passing
- ✅ Batch coordinator E2E tests: 2/2 passing

### User Workflow

1. User creates live project and configures 2-aquarium zones
2. Opens wizard and fills batch metadata fields:
   - Group: "Controle"
   - Day: "Dia_1"
   - Subject: "Peixe_01"
3. Completes 3 recording sessions (same group/day/subject)
4. On 3rd session, checks "Última sessão do lote"
5. LiveBatchCoordinator triggers unified Excel report combining all 3 sessions
6. UICoordinator shows success messagebox and opens file explorer

## References

- Implementation: `src/zebtrack/coordinators/live_batch_coordinator.py`
- Tests: `tests/test_live_batch_integration.py` (4 integration tests)
- E2E Tests: `tests/test_live_camera_workflow_e2e.py` (lines 197-240)
- UI Handler: `src/zebtrack/ui/ui_coordinator.py` (lines 699-740)
- Wizard: `src/zebtrack/ui/wizard/live_config_step.py` (lines 85+ for batch fields)
- Dialog: `src/zebtrack/ui/dialogs/block_detail_dialog.py` (300 lines)
- Audit Finding: "LiveBatchCoordinator exists but never instantiated" → ✅ Resolved
