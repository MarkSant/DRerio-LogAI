# Sprint 27: Project Management Methods - Detailed Analysis

**Current Status**: MainViewModel is 4,305 lines after Sprint 26
**Goal**: Extract project lifecycle/management methods to ProjectOrchestrator
**Target**: ~400 lines reduction

---

## 1. METHOD ANALYSIS TABLE

| Method Name | Lines | Start-End | Complexity | PM Calls | Extract? | Risk |
|------------|-------|-----------|------------|----------|----------|------|
| **Lifecycle & Workflow** |
| close_project | 14 | 1132-1145 | 6 | 1 | ✅ YES | LOW |
| create_project_workflow | 21 | 1146-1166 | 8 | 0 | ✅ YES | LOW |
| open_project_workflow | 18 | 1259-1276 | 9 | 0 | ✅ YES | LOW |
| start_project_processing_workflow | 8 | 3012-3019 | LOW | 0 | ✅ YES | LOW |
| process_pending_project_videos | 13 | 3020-3032 | LOW | 0 | ✅ YES | LOW |
| **Model Settings & Overrides** |
| are_project_overrides_active | 8 | 1560-1567 | 1 | 0 | ✅ YES | LOW |
| has_project_override_settings | 11 | 1594-1604 | 3 | 1 | ✅ YES | LOW |
| _get_project_data_dict | 7 | 1579-1585 | 5 | 1 | ✅ YES | LOW |
| _ensure_project_overrides_record | 8 | 1586-1593 | 5 | 0 | ✅ YES | LOW |
| _persist_project_model_settings | 26 | 1724-1749 | 8 | 3 | ✅ YES | MED |
| copy_global_model_settings_to_project | 28 | 1750-1777 | 6 | 1 | ✅ YES | MED |
| save_current_calibration_to_project | 30 | 1778-1807 | 7 | 1 | ✅ YES | MED |
| resolve_project_model_settings | 64 | 1817-1880 | 8 | 1 | ✅ YES | MED |
| apply_project_model_overrides | 32 | 1881-1912 | 19 | 7 | ⚠️ MAYBE | HIGH |
| save_project_model_overrides | 30 | 1913-1942 | 11 | 4 | ⚠️ MAYBE | HIGH |
| project_calibration_session | 19 | 1971-1989 | MED | 1 | ✅ YES | MED |
| **Asset Management** |
| can_remove_project_asset | 18 | 2268-2285 | 3 | 1 | ✅ YES | LOW |
| delete_project_asset | 35 | 2286-2320 | 5 | 1 | ✅ YES | LOW |
| **Batch & Output** |
| _register_project_outputs | 28 | 3516-3543 | LOW | 0 | ✅ YES | LOW |
| apply_project_settings_to_batch | 87 | 3632-3718 | 15 | 7 | ⚠️ DEFER | HIGH |
| **Supporting Methods** |
| _on_project_state_changed | 11 | 699-709 | LOW | 1 | ❌ NO | LOW |
| refresh_project_views | 22 | 1056-1077 | LOW | 0 | ❌ NO | LOW |
| _setup_zones_from_project | 10 | 1249-1258 | LOW | 0 | ✅ YES | LOW |
| _apply_wizard_detector_overrides | 48 | 1167-1214 | MED | 0 | ❌ NO | MED |
| start_live_project_session | 24 | 2533-2556 | LOW | 0 | ❌ NO | LOW |

**Legend**:
- **Complexity Score**: Count of self/project_manager/settings references
- **PM Calls**: Number of `self.project_manager` calls
- **Extract?**: Recommendation for Sprint 27
- **Risk**: Complexity of extraction (LOW/MED/HIGH)

---

## 2. RECOMMENDED EXTRACTION SET (Sprint 27)

### Group A: Core Lifecycle (74 lines) - **HIGHEST PRIORITY**
**Theme**: Project open/close/workflow orchestration

1. **close_project** (14 lines) - Delegates to adapter, updates project_manager ref
2. **create_project_workflow** (21 lines) - Orchestrates creation with callbacks
3. **open_project_workflow** (18 lines) - Orchestrates loading with callbacks
4. **start_project_processing_workflow** (8 lines) - Delegates to video orchestrator
5. **process_pending_project_videos** (13 lines) - Delegates to video orchestrator

**Risk**: LOW - All delegate to existing adapters/orchestrators
**Dependencies**: project_workflow_adapter, video_processing_orchestrator

---

### Group B: Model Override Management (182 lines) - **HIGH VALUE**
**Theme**: Project-specific model settings and overrides

6. **are_project_overrides_active** (8 lines) - Property check
7. **has_project_override_settings** (11 lines) - Validation check
8. **_get_project_data_dict** (7 lines) - Data accessor
9. **_ensure_project_overrides_record** (8 lines) - Data initialization
10. **_persist_project_model_settings** (26 lines) - Persistence logic
11. **copy_global_model_settings_to_project** (28 lines) - Settings copy
12. **save_current_calibration_to_project** (30 lines) - Calibration save
13. **resolve_project_model_settings** (64 lines) - Override resolution logic

**Risk**: MEDIUM - Heavy project_data manipulation, needs careful state handling
**Dependencies**: project_manager.project_data, settings, ui_event_bus

---

### Group C: Asset Management (81 lines) - **CLEAN EXTRACTION**
**Theme**: Project asset lifecycle (arena, ROIs, trajectories, summaries)

14. **can_remove_project_asset** (18 lines) - Validation delegate
15. **delete_project_asset** (35 lines) - Asset removal delegate
16. **_register_project_outputs** (28 lines) - Output registration + refresh

**Risk**: LOW - Mostly delegates to project_manager
**Dependencies**: project_manager, refresh_project_views

---

### Group D: Supporting Methods (48 lines) - **SUPPORTING**
**Theme**: Zones and calibration context

17. **_setup_zones_from_project** (10 lines) - Zones setup delegate
18. **project_calibration_session** (19 lines) - Context manager for calibration
19. ~~**_apply_wizard_detector_overrides** (48 lines)~~ - **DEFER to Wizard Orchestrator**

**Risk**: LOW-MEDIUM
**Dependencies**: project_workflow_adapter, setup_detector_zones

---

### **TOTAL FOR SPRINT 27: 385 lines (14 methods)**

---

## 3. METHODS TO DEFER

### Defer to Sprint 28 (Higher Risk)
These have high complexity or cross-cutting concerns:

1. **apply_project_model_overrides** (32 lines, complexity 19)
   - Reason: Heavy internal dependencies, 7 project_manager calls
   - Better after Groups A-C stabilize

2. **save_project_model_overrides** (30 lines, complexity 11)
   - Reason: Tightly coupled with apply_project_model_overrides
   - Extract together in Sprint 28

3. **apply_project_settings_to_batch** (87 lines, complexity 15)
   - Reason: Large, complex, multiple concerns (settings + zones)
   - Consider BatchProjectOrchestrator in future sprint

### Keep in MainViewModel (Not Project Lifecycle)
These belong to other domains or are too coupled to MainViewModel:

1. **_on_project_state_changed** (11 lines) - State observer, stays with MVVM
2. **refresh_project_views** (22 lines) - UI refresh coordinator, stays with ViewModel
3. **start_live_project_session** (24 lines) - Recording concern, not project lifecycle
4. **_apply_wizard_detector_overrides** (48 lines) - Wizard/Detector concern

---

## 4. EXPECTED REDUCTION

| Metric | Value |
|--------|-------|
| **Current MainViewModel Size** | 4,305 lines |
| **Lines to Extract** | 385 lines |
| **Expected After Sprint 27** | ~3,920 lines |
| **Reduction Percentage** | 8.9% |
| **Cumulative Reduction (Sprints 24-27)** | ~16.3% from peak |

**Note**: This is conservative extraction focusing on LOW-MEDIUM risk methods. Sprint 28 can tackle the remaining high-risk methods.

---

## 5. RISK ASSESSMENT

### Low Risk (Groups A, C, D) - 203 lines
- **close_project, create_project_workflow, open_project_workflow**: All delegate to `project_workflow_adapter`
- **start_project_processing_workflow, process_pending_project_videos**: Delegate to `video_processing_orchestrator`
- **can_remove_project_asset, delete_project_asset**: Delegate to `project_manager`
- **_setup_zones_from_project**: Simple delegation
- **_register_project_outputs**: Delegates then refreshes

**Mitigation**: Create facade methods in MainViewModel that call orchestrator

### Medium Risk (Group B) - 182 lines
- **Model override methods**: Heavy `project_data` manipulation
- **Concerns**:
  - State consistency between project_manager.project_data and orchestrator
  - UI event publishing after state changes
  - Interaction with global_model_defaults

**Mitigation**:
1. Pass `project_manager` reference to orchestrator (don't copy state)
2. Return values from orchestrator, let ViewModel publish events
3. Keep `_using_project_overrides` flag in ViewModel initially
4. Add comprehensive integration tests for override workflows

---

## 6. DEPENDENCIES TO MAINTAIN

### ProjectOrchestrator will need:
**Constructor Injections**:
- `project_manager: ProjectManager` (reference, not copy)
- `project_workflow_adapter: ProjectWorkflowAdapter`
- `video_processing_orchestrator: VideoProcessingOrchestrator`
- `settings: Settings` (for model defaults)
- `ui_event_bus: UIEventBus` (for status updates)

**MainViewModel Methods to Call** (via callbacks or facade):
- `self.setup_detector()` - For detector initialization
- `self.set_active_weight()` - For weight changes
- `self.set_openvino_usage()` - For OpenVINO toggles
- `self.update_openvino_status()` - For status updates
- `self.setup_detector_zones()` - For zone updates
- `self._restore_detector_settings()` - For detector restoration
- `self.refresh_project_views()` - For UI refresh
- `self.get_global_model_defaults()` - For global settings
- `self._apply_model_settings()` - For model application

**MainViewModel State to Access**:
- `self.active_weight_name` - Current weight
- `self.use_openvino` - OpenVINO state
- `self._using_project_overrides` - Override flag (consider moving to StateManager)
- `self._global_model_defaults` - Global defaults (consider moving to StateManager)

---

## 7. PROPOSED API

```python
class ProjectOrchestrator:
    """Orchestrates project lifecycle and configuration management."""

    def __init__(
        self,
        project_manager: ProjectManager,
        project_workflow_adapter: ProjectWorkflowAdapter,
        video_processing_orchestrator: VideoProcessingOrchestrator,
        settings: Settings,
        ui_event_bus: UIEventBus,
        # Callbacks for MainViewModel methods
        setup_detector_callback: Callable,
        set_active_weight_callback: Callable,
        set_openvino_usage_callback: Callable,
        update_openvino_status_callback: Callable,
        setup_detector_zones_callback: Callable,
        restore_detector_settings_callback: Callable,
        refresh_project_views_callback: Callable,
        get_global_model_defaults_callback: Callable,
        apply_model_settings_callback: Callable,
    ):
        ...

    # Group A: Lifecycle
    def close_project(self) -> ProjectManager: ...
    def create_project_workflow(self, **kwargs): ...
    def open_project_workflow(self, project_path: Path | str): ...
    def start_project_processing_workflow(self): ...
    def process_pending_project_videos(self, video_paths: list[str] | None = None): ...

    # Group B: Model Overrides
    def are_project_overrides_active(self, using_project_overrides: bool) -> bool: ...
    def has_project_override_settings(self) -> bool: ...
    def copy_global_model_settings_to_project(self) -> tuple[str | None, bool] | None: ...
    def save_current_calibration_to_project(
        self, active_weight_name: str | None, use_openvino: bool
    ) -> tuple[str | None, bool] | None: ...
    def resolve_project_model_settings(
        self, overrides: dict | None = None
    ) -> tuple[str | None, bool]: ...

    # Group C: Asset Management
    def can_remove_project_asset(
        self, video_path: Path | str, asset: str
    ) -> tuple[bool, str | None]: ...
    def delete_project_asset(
        self, video_path: Path | str, asset: str, delete_source: bool = True
    ) -> bool: ...
    def register_project_outputs(
        self, video_path: str, results_dir: str, trajectory_path: str,
        summary_parquet: str, summary_excel: str, report_path: str
    ) -> None: ...

    # Group D: Supporting
    def setup_zones_from_project(self) -> None: ...
    @contextmanager
    def project_calibration_session(
        self, using_project_overrides: bool
    ) -> Generator[None, None, None]: ...

    # Internal helpers
    def _get_project_data_dict(self) -> dict: ...
    def _ensure_project_overrides_record(self) -> dict: ...
    def _persist_project_model_settings(
        self, weight: str | None, use_openvino: bool
    ) -> dict: ...
```

---

## 8. NEXT STEPS

### Sprint 27 Implementation Plan:
1. ✅ Create `ProjectOrchestrator` class skeleton
2. ✅ Extract Group A methods (lifecycle - 74 lines)
3. ✅ Extract Group C methods (asset mgmt - 81 lines)
4. ✅ Extract Group D methods (supporting - 48 lines)
5. ✅ Extract Group B methods (overrides - 182 lines) - **CAREFUL**
6. ✅ Create MainViewModel facade methods
7. ✅ Update tests
8. ✅ Verify no regressions

### Sprint 28 (Future):
- Extract `apply_project_model_overrides` (32 lines, high complexity)
- Extract `save_project_model_overrides` (30 lines, high complexity)
- Extract `apply_project_settings_to_batch` (87 lines, very high complexity)
- **Total Sprint 28**: ~150 lines

---

## 9. TEST COVERAGE REQUIREMENTS

### Critical Test Scenarios:
1. **Project Lifecycle**:
   - Open project → verify model overrides applied
   - Close project → verify global defaults restored
   - Create project → verify workflow callbacks executed

2. **Model Overrides**:
   - Copy global settings to project → verify persistence
   - Save calibration to project → verify overrides updated
   - Resolve project settings → verify fallback chain works

3. **Asset Management**:
   - Remove asset → verify validation and deletion
   - Register outputs → verify project_data updated

4. **Integration**:
   - Full workflow: create → configure → close → reopen
   - Verify state consistency across orchestrators

---

## 10. DECISION SUMMARY

### ✅ EXTRACT NOW (Sprint 27): 385 lines
- Groups A, B, C, D
- Low-Medium risk
- Clear boundaries
- High cohesion

### ⏸️ DEFER (Sprint 28+): 149 lines
- apply_project_model_overrides (32)
- save_project_model_overrides (30)
- apply_project_settings_to_batch (87)

### ❌ KEEP IN MAINVIEWMODEL: 86 lines
- _on_project_state_changed (observer)
- refresh_project_views (UI coordinator)
- start_live_project_session (recording)
- _apply_wizard_detector_overrides (wizard/detector)

**Total Project Methods Identified**: 620 lines
**Sprint 27 Extraction**: 385 lines (62% of project methods)
**Remaining for Future**: 235 lines (38% - high complexity or other domains)
