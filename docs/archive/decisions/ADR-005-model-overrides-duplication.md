# Architectural Decision: Model Overrides Duplication

**Date**: 2025-01-14
**Status**: ✅ DOCUMENTED (Not a bug - intentional design)
**Context**: Sprint 34 discovered apparent "duplication" of `apply_project_model_overrides` in two classes

---

## 🎯 Summary

The `apply_project_model_overrides` method exists in **two locations** with **different signatures** and **purposes**. This is **NOT duplication** - it's an intentional architectural separation between:
1. **Stateless service layer** (ProjectWorkflowService) - uses dependency injection callbacks
2. **Stateful orchestrator layer** (ProjectOrchestrator) - has direct MainViewModel reference

---

## 📍 The Two Implementations

### 1. ProjectWorkflowService.apply_project_model_overrides ⚙️

**Location**: `src/zebtrack/core/project_workflow_service.py:284-340`

**Signature**:
```python
def apply_project_model_overrides(
    self,
    overrides: dict | None = None,
    active_weight_setter: Callable[..., Any] | None = None,  # ← CALLBACK
    use_openvino_setter: Callable[..., Any] | None = None,   # ← CALLBACK
) -> tuple[str | None, bool]:
```

**Purpose**: Stateless service method for project workflows (create/open)

**Key Characteristics**:
- ✅ **Stateless** - no MainViewModel reference
- ✅ **Pure DI** - receives callbacks to apply settings
- ✅ **Used in workflows** - `create_project()` and `open_project()`
- ✅ **Flexible** - caller controls how settings are applied

**Call Sites** (2 internal):
1. `ProjectWorkflowService.create_project()` (line 570)
2. `ProjectWorkflowService.open_project()` (line 676)

**Example Usage**:
```python
# In create_project()
self.apply_project_model_overrides(
    overrides=None,
    active_weight_setter=active_weight_setter,  # Passed from caller
    use_openvino_setter=use_openvino_setter,    # Passed from caller
)
```

---

### 2. ProjectOrchestrator.apply_project_model_overrides 🎭

**Location**: `src/zebtrack/orchestrators/project_orchestrator.py:468-502`

**Signature**:
```python
def apply_project_model_overrides(
    self,
    overrides: dict | None = None,  # ← NO CALLBACKS
) -> tuple[str | None, bool]:
```

**Purpose**: Orchestrator method with direct MainViewModel access

**Key Characteristics**:
- ✅ **Stateful** - has `self.main_view_model` reference
- ✅ **Direct calls** - calls `self._apply_model_settings()` directly
- ✅ **Simpler API** - no callbacks needed
- ✅ **Used by other orchestrators** - CalibrationOrchestrator, etc

**Call Sites** (4 total):
1. `ProjectOrchestrator.save_current_calibration_to_project()` (line 407)
2. `ProjectOrchestrator.save_project_model_overrides()` (line 532)
3. `CalibrationOrchestrator.global_calibration_session()` (line 156 - via project_orchestrator)
4. `MainViewModel.apply_project_model_overrides()` (line 1514 - facade)

**Example Usage**:
```python
# In save_current_calibration_to_project()
self.apply_project_model_overrides(overrides)  # No callbacks needed
```

---

## 🏗️ Architectural Rationale

### Why Two Implementations?

#### **Service Layer (ProjectWorkflowService)** 🔄
- **Role**: Stateless orchestration of complex workflows
- **Constraint**: Cannot depend on MainViewModel directly
- **Solution**: Accept callbacks for applying settings
- **Benefit**: Testable without MainViewModel, reusable in different contexts

#### **Orchestrator Layer (ProjectOrchestrator)** 🎯
- **Role**: Stateful coordination with MainViewModel reference
- **Constraint**: Already has MainViewModel access via `__init__`
- **Solution**: Call MainViewModel methods directly
- **Benefit**: Simpler API, no callback boilerplate

---

## 📊 Comparison Table

| Aspect | ProjectWorkflowService | ProjectOrchestrator |
|--------|------------------------|---------------------|
| **Layer** | Service (stateless) | Orchestrator (stateful) |
| **MainViewModel Reference** | ❌ NO | ✅ YES (via __init__) |
| **Callbacks Required** | ✅ YES (2 callbacks) | ❌ NO |
| **Used In** | Project create/open workflows | Model override save/restore |
| **Call Sites** | 2 (internal) | 4 (internal + external) |
| **Testability** | High (mock callbacks) | Medium (needs MainViewModel) |
| **Flexibility** | High (caller controls) | Lower (fixed behavior) |
| **API Complexity** | Higher (3 params) | Lower (1 param) |

---

## 🔍 Code Flow Comparison

### Flow 1: ProjectWorkflowService (Create Project)
```
User creates project
  → ProjectWorkflowAdapter.create_project_workflow()
    → ProjectWorkflowService.create_project(
        active_weight_setter=lambda name: controller.set_active_weight(name),
        use_openvino_setter=lambda flag: controller.set_openvino_usage(flag)
      )
      → self.apply_project_model_overrides(callbacks...)
        → active_weight_setter(resolved_weight)  # Callback to MainViewModel
        → use_openvino_setter(resolved_openvino) # Callback to MainViewModel
```

### Flow 2: ProjectOrchestrator (Save Calibration)
```
User saves calibration
  → CalibrationDialog.on_save()
    → controller.save_current_calibration_to_project()
      → project_orchestrator.save_current_calibration_to_project()
        → self.apply_project_model_overrides(overrides)
          → self._apply_model_settings(weight, openvino)
            → self.main_view_model.set_active_weight(weight)  # Direct call
            → self.main_view_model.set_openvino_usage(openvino)  # Direct call
```

---

## ✅ Validation: Not True Duplication

### Evidence:
1. ✅ **Different purposes** - workflows vs model override management
2. ✅ **Different coupling** - stateless vs stateful
3. ✅ **Different call sites** - no overlap
4. ✅ **Different constraints** - DI callbacks vs direct access
5. ✅ **Both are used** - 2 call sites vs 4 call sites

### Conclusion:
This is **intentional architectural separation**, not accidental duplication.

---

## 💡 Future Optimization Opportunity (Optional)

While not true duplication, there IS code similarity that could be DRY'd:

### Option A: Extract Common Logic ✨
```python
# In ProjectOrchestrator
def apply_project_model_overrides(self, overrides: dict | None = None):
    """Apply overrides by delegating to ProjectWorkflowService with callbacks."""
    return self.project_workflow_service.apply_project_model_overrides(
        overrides=overrides,
        active_weight_setter=lambda name: self.main_view_model.set_active_weight(name),
        use_openvino_setter=lambda flag: self.main_view_model.set_openvino_usage(flag),
    )
```

**Benefits**:
- ✅ Single source of truth for override logic
- ✅ Eliminates code similarity
- ✅ Maintains separate interfaces

**Risks**:
- ⚠️ Adds slight indirection
- ⚠️ ProjectOrchestrator now depends on ProjectWorkflowService
- ⚠️ Requires careful testing of callback passing

### Option B: Keep As-Is (RECOMMENDED) ✅
```python
# Current state - both implementations remain
```

**Benefits**:
- ✅ Clear separation of concerns
- ✅ No new dependencies
- ✅ Already working correctly
- ✅ Easy to understand

**Trade-off**:
- ⚠️ ~30 lines of similar logic maintained separately
- ✅ Worth it for clarity and independence

---

## 📝 Recommendation

**KEEP AS-IS** ✅

**Rationale**:
1. The duplication is **intentional and justified**
2. The code similarity (~30 lines) is **acceptable** for architectural clarity
3. Consolidation would add **dependency coupling** without significant benefit
4. Both implementations are **stable and tested**
5. Future refactoring could revisit if complexity grows

**Document instead of refactor**: This ADR serves as the documentation ✅

---

## 🧪 Testing Verification

Both implementations are tested independently:

### ProjectWorkflowService Tests
- ✅ `tests/core/test_project_workflow_service.py` - workflow scenarios
- ✅ Callbacks mocked and verified

### ProjectOrchestrator Tests
- ✅ `tests/orchestrators/test_project_orchestrator.py` - override management
- ✅ MainViewModel integration verified

---

## 📚 Related Documentation

- `docs/SPRINT_34_RESULTS.md` - Discovery of this "duplication"
- `docs/ARCHITECTURE.md` - Service vs Orchestrator layer distinction
- `docs/DEPENDENCY_INJECTION_GUIDE.md` - DI patterns and callbacks

---

## ✅ Decision

**Status**: DOCUMENTED AND ACCEPTED ✅

**Action**: NO REFACTOR NEEDED

**Rationale**: This is intentional architectural separation, not duplication. The code similarity is acceptable given the different purposes and constraints of the two layers.

**Date**: 2025-01-14
**Decided By**: Sprint 34 analysis

---

**Version**: 1.0
**Last Updated**: 2025-01-14
