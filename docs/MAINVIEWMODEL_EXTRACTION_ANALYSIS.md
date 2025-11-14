# MainViewModel Extraction Analysis Report
**Date**: 2025-11-14
**Current Size**: 3,709 lines
**Previous Extractions**: Sprints 24-28 (VideoProcessingOrchestrator, AnalysisOrchestrator, RecordingSessionOrchestrator, ProjectOrchestrator, UIStateController)

---

## Executive Summary

After analyzing MainViewModel post-Sprint 28, we have:
- **141 total methods**
- **62 facade methods** (771 lines) - simple delegation to orchestrators
- **79 real methods** (2,812 lines) - actual implementation logic
- **126 lines** overhead (imports, class definition, etc.)

The 79 real methods are grouped into **13 logical domains**, with 7 high-value extraction candidates identified.

---

## 1. Summary Statistics

### Method Breakdown
| Category | Count | Lines | Percentage |
|----------|-------|-------|------------|
| **Facade Methods** | 62 | 771 | 21% |
| **Real Methods** | 79 | 2,812 | 76% |
| **Overhead** | N/A | 126 | 3% |
| **TOTAL** | 141 | 3,709 | 100% |

### Real Method Size Distribution
| Size Category | Count | Total Lines |
|---------------|-------|-------------|
| Large (>50 lines) | 17 | 1,398 lines |
| Medium (20-50 lines) | 24 | 758 lines |
| Small (<20 lines) | 38 | 656 lines |

---

## 2. Top 20 Largest Real Methods (Non-Facades)

| Rank | Method | Lines | Range | Description | Complexity |
|------|--------|-------|-------|-------------|------------|
| 1 | `__init__` | 280 | 127-406 | Dependency injection setup | **HIGH** |
| 2 | `_init_coordinators` | 178 | 420-597 | Initialize all coordinators | **MEDIUM** |
| 3 | `start_live_camera_analysis_from_config` | 149 | 1970-2118 | Configure and start live camera analysis | **HIGH** |
| 4 | `add_roi_polygon` | 126 | 1770-1895 | Add ROI with overlap validation | **HIGH** |
| 5 | `_format_diagnostic_report` | 107 | 3603-3709 | Format diagnostic results into text | **LOW** |
| 6 | `run_model_diagnostic` | 103 | 3184-3286 | Prepare and launch diagnostic test | **MEDIUM** |
| 7 | `_ensure_zones_before_recording` | 96 | 2150-2245 | Validate zones before recording | **HIGH** |
| 8 | `_run_diagnostic_frame_loop` | 88 | 3477-3564 | Process frames for diagnostics | **MEDIUM** |
| 9 | `apply_project_settings_to_batch` | 87 | 3031-3117 | Apply project settings to multiple videos | **MEDIUM** |
| 10 | `_initialize_diagnostic_openvino_model` | 73 | 3404-3476 | Setup OpenVINO for diagnostics | **MEDIUM** |
| 11 | `_temporary_single_animal_mode` | 65 | 2695-2759 | Context manager for single animal mode | **LOW** |
| 12 | `get_calibration_scope_info` | 57 | 1409-1465 | Get calibration display info | **LOW** |
| 13 | `_resolve_single_subject_tracker_preference` | 55 | 2597-2651 | Resolve tracker preference logic | **MEDIUM** |
| 14 | `cancel_current_analysis` | 54 | 2246-2299 | Request cancellation of analysis | **MEDIUM** |
| 15 | `_handle_mixed_data_scenario` | 54 | 2358-2411 | Handle partial data scenario | **MEDIUM** |
| 16 | `_diagnostic_processing_thread` | 53 | 3287-3339 | Run diagnostic in background thread | **MEDIUM** |
| 17 | `start_single_video_workflow` | 51 | 2307-2357 | Prepare UI for single video | **MEDIUM** |
| 18 | `set_main_arena_polygon` | 50 | 1703-1752 | Save arena polygon with validation | **MEDIUM** |
| 19 | `_apply_wizard_detector_overrides` | 48 | 1151-1198 | Apply detector params from wizard | **LOW** |
| 20 | `_process_single_video` | 48 | 2983-3030 | Delegate to VideoProcessingService | **LOW** |

**Complexity Assessment:**
- **HIGH**: Complex business logic, multiple state changes, error handling
- **MEDIUM**: Moderate logic, some branching, 2-3 dependencies
- **LOW**: Simple delegation, formatting, or straightforward logic

---

## 3. Logical Groupings (Extraction Candidates)

### GROUP 1: Model Diagnostics Orchestrator ⭐ **HIGH PRIORITY**
**Total: 7 methods, 499 lines**

| Method | Lines | Complexity |
|--------|-------|------------|
| `_format_diagnostic_report` | 107 | LOW |
| `run_model_diagnostic` | 103 | MEDIUM |
| `_run_diagnostic_frame_loop` | 88 | MEDIUM |
| `_initialize_diagnostic_openvino_model` | 73 | MEDIUM |
| `_diagnostic_processing_thread` | 53 | MEDIUM |
| `_finish_diagnostic_and_save_report` | 38 | LOW |
| `_initialize_diagnostic_yolo_model` | 37 | MEDIUM |

**Rationale:**
- Self-contained domain (model diagnostics)
- No dependencies on other MainViewModel state
- All methods work together as a cohesive workflow
- Clear single responsibility
- Easy to test in isolation

**Dependencies:**
- `settings`, `weight_manager`, `ui_coordinator`
- `YOLO`, `cv2`, `openvino` (external)

**Extraction Difficulty**: ⭐ **EASY** (low coupling, clear boundaries)

---

### GROUP 2: Zone & Arena Orchestrator ⭐⭐ **HIGH PRIORITY**
**Total: 3 methods, 186 lines**

| Method | Lines | Complexity |
|--------|-------|------------|
| `add_roi_polygon` | 126 | HIGH |
| `set_main_arena_polygon` | 50 | MEDIUM |
| `save_manual_arena` | 10 | LOW |

**Rationale:**
- Clear domain boundary (zone/arena management)
- High complexity reduction (126-line method is largest real method)
- Validation logic can be isolated
- Related to detector zones (potential future extraction)

**Dependencies:**
- `project_manager`, `detector_service`, `state_manager`
- `ui_coordinator` (for UI callbacks)

**Extraction Difficulty**: ⭐⭐ **MEDIUM** (moderate coupling to detector)

---

### GROUP 3: Live Camera Orchestrator ⭐⭐⭐ **MEDIUM PRIORITY**
**Total: 2 methods, 245 lines**

| Method | Lines | Complexity |
|--------|-------|------------|
| `start_live_camera_analysis_from_config` | 149 | HIGH |
| `_ensure_zones_before_recording` | 96 | HIGH |

**Rationale:**
- Highly complex methods (149 and 96 lines)
- Related to live camera workflows
- Could merge with existing `LiveCameraCoordinator`

**Dependencies:**
- `live_camera_service`, `recording_service`
- `detector_service`, `project_manager`
- Many state dependencies

**Extraction Difficulty**: ⭐⭐⭐ **HARD** (high coupling, many dependencies)

**Note**: Might be better to enhance existing `LiveCameraCoordinator` rather than extract

---

### GROUP 4: Processing Configuration Orchestrator ⭐⭐ **MEDIUM PRIORITY**
**Total: 7 methods, 245 lines**

| Method | Lines | Complexity |
|--------|-------|------------|
| `_temporary_single_animal_mode` | 65 | LOW |
| `_resolve_single_subject_tracker_preference` | 55 | MEDIUM |
| `_resolve_single_animal_mode` | 36 | MEDIUM |
| `_determine_processing_intervals` | 31 | LOW |
| `_determine_processing_mode` | 27 | MEDIUM |
| `_publish_processing_mode` | 19 | LOW |
| `_configure_single_subject_tracker` | 12 | LOW |

**Rationale:**
- All methods related to processing configuration
- Handles single-animal mode logic
- Processing interval determination

**Dependencies:**
- `state_manager`, `ui_event_bus`
- `project_manager` (for project settings)

**Extraction Difficulty**: ⭐⭐ **MEDIUM** (moderate coupling)

---

### GROUP 5: Detector & Model Orchestrator ⭐⭐⭐ **LOW PRIORITY**
**Total: 12 methods, 165 lines**

| Method | Lines | Complexity |
|--------|-------|------------|
| `_apply_wizard_detector_overrides` | 48 | LOW |
| `_safe_get_default_weight` | 19 | LOW |
| `setup_detector` | 17 | MEDIUM |
| `get_current_detector_parameters` | 14 | LOW |
| `get_factory_detector_parameters` | 14 | LOW |
| Others (7 methods) | 53 | LOW |

**Rationale:**
- Many small methods (8-19 lines)
- Low individual complexity
- Shared across many workflows

**Dependencies:**
- `detector_service`, `model_service`, `weight_manager`
- `settings`, `state_manager`

**Extraction Difficulty**: ⭐⭐⭐⭐ **VERY HARD** (high coupling, used everywhere)

**Recommendation**: Keep as-is for now (too coupled to mainViewModel)

---

### GROUP 6: Calibration Orchestrator ⭐⭐ **MEDIUM PRIORITY**
**Total: 4 methods, 129 lines**

| Method | Lines | Complexity |
|--------|-------|------------|
| `get_calibration_scope_info` | 57 | LOW |
| `_prepare_calibration_context` | 26 | LOW |
| `_build_calibration_context` | 25 | LOW |
| `global_calibration_session` | 21 | LOW |

**Rationale:**
- Self-contained calibration logic
- Context manager for calibration sessions
- Low complexity

**Dependencies:**
- `project_manager` (calibration data)
- `detector_service` (zones)

**Extraction Difficulty**: ⭐⭐ **MEDIUM** (moderate coupling)

---

### GROUP 7: Video Processing Workflow Orchestrator ⭐⭐⭐ **LOW PRIORITY**
**Total: 7 methods, 360 lines**

| Method | Lines | Complexity |
|--------|-------|------------|
| `apply_project_settings_to_batch` | 87 | MEDIUM |
| `_handle_mixed_data_scenario` | 54 | MEDIUM |
| `cancel_current_analysis` | 54 | MEDIUM |
| `start_single_video_workflow` | 51 | MEDIUM |
| `_process_single_video` | 48 | LOW |
| `_run_analysis_pipeline` | 40 | MEDIUM |
| `_process_videos` | 26 | LOW |

**Rationale:**
- Already heavily delegated to `VideoProcessingOrchestrator` (Sprint 24)
- Remaining methods are facades or glue code

**Recommendation**: Keep as-is (already extracted in Sprint 24)

---

## 4. Recommended Next 3 Sprints

### **Sprint 29: Model Diagnostics Orchestrator** ⭐ **HIGHEST VALUE**

**Methods to Extract**: 7 methods, 499 lines
- `run_model_diagnostic`
- `_diagnostic_processing_thread`
- `_initialize_diagnostic_yolo_model`
- `_initialize_diagnostic_openvino_model`
- `_run_diagnostic_frame_loop`
- `_finish_diagnostic_and_save_report`
- `_format_diagnostic_report`

**New Class**: `orchestrators/model_diagnostics_orchestrator.py`

**Expected Reduction**: ~500 lines from MainViewModel

**Risk Level**: ⭐ **LOW**
- Self-contained domain
- No complex dependencies on MainViewModel state
- Clear interface boundaries
- Easy to test

**Benefits**:
- Removes largest cohesive block of logic
- Improves testability of diagnostic workflow
- Clear single responsibility

---

### **Sprint 30: Zone & Arena Orchestrator** ⭐⭐ **HIGH VALUE**

**Methods to Extract**: 3 methods, 186 lines
- `add_roi_polygon` (126 lines - largest real method!)
- `set_main_arena_polygon`
- `save_manual_arena`

**New Class**: `orchestrators/zone_arena_orchestrator.py`

**Expected Reduction**: ~190 lines from MainViewModel

**Risk Level**: ⭐⭐ **MEDIUM**
- Moderate coupling to detector_service
- Validation logic needs careful extraction
- UI callbacks need to be preserved

**Benefits**:
- Removes the largest single real method (126 lines)
- Isolates complex validation logic
- Clearer zone management responsibility

---

### **Sprint 31: Processing Configuration Orchestrator** ⭐⭐ **MEDIUM VALUE**

**Methods to Extract**: 7 methods, 245 lines
- `_determine_processing_mode`
- `_publish_processing_mode`
- `_resolve_single_animal_mode`
- `_resolve_single_subject_tracker_preference`
- `_configure_single_subject_tracker`
- `_determine_processing_intervals`
- `_temporary_single_animal_mode`

**New Class**: `orchestrators/processing_config_orchestrator.py`

**Expected Reduction**: ~250 lines from MainViewModel

**Risk Level**: ⭐⭐ **MEDIUM**
- Used across multiple workflows
- State management dependencies
- Event bus integration

**Benefits**:
- Isolates processing mode logic
- Clearer configuration responsibility
- Better testability

---

## 5. Additional Opportunities (Sprints 32-35)

### **Sprint 32: Calibration Orchestrator**
- **Methods**: 4 methods, 129 lines
- **Risk**: MEDIUM
- **Value**: MEDIUM (cleaner calibration management)

### **Sprint 33: Live Camera Enhancement**
- **Methods**: Enhance existing `LiveCameraCoordinator` with 2 methods, 245 lines
- **Risk**: HIGH (complex, many dependencies)
- **Value**: HIGH (if successful, removes very complex methods)

### **Sprint 34: Detector & Model Facade Cleanup**
- **Methods**: Consolidate 12 small methods into cleaner facade pattern
- **Risk**: HIGH (used everywhere)
- **Value**: LOW (small individual methods, high coupling)
- **Recommendation**: Skip this - too risky for small gain

### **Sprint 35: Final Cleanup**
- Remove dead code
- Consolidate remaining small methods
- Documentation cleanup
- **Value**: MEDIUM

---

## 6. Projected Final State (After Sprints 29-31)

| Metric | Current | After Sprint 29 | After Sprint 30 | After Sprint 31 |
|--------|---------|-----------------|-----------------|-----------------|
| Total Lines | 3,709 | 3,209 | 3,019 | 2,769 |
| Real Methods | 79 | 72 | 69 | 62 |
| Facade Methods | 62 | 62 | 62 | 62 |
| Real Method Lines | 2,812 | 2,312 | 2,122 | 1,872 |

**Total Reduction**: **940 lines** (25% reduction)
**Final Size**: **~2,769 lines** (manageable, well-organized)

---

## 7. Success Criteria

After completing Sprints 29-31, MainViewModel should:

✅ Be under 3,000 lines
✅ Have <70 real methods (excluding facades)
✅ Have clear orchestrator boundaries
✅ Maintain 100% test coverage on extracted code
✅ No regression in existing functionality

---

## 8. Risk Mitigation Strategy

### For Each Sprint:
1. **Before Extraction**:
   - Read all related tests
   - Document all dependencies
   - Identify all call sites

2. **During Extraction**:
   - Extract methods incrementally
   - Run full test suite after each method
   - Keep MainViewModel facade methods as thin wrappers

3. **After Extraction**:
   - Run full test suite (2568 tests)
   - Run `ruff check`
   - Verify no performance regression
   - Update documentation

---

## 9. Conclusion

MainViewModel has **940 lines of high-value extraction opportunities** across 3 prioritized sprints:

1. **Sprint 29** (Model Diagnostics): 499 lines, LOW risk, EASY extraction
2. **Sprint 30** (Zone & Arena): 186 lines, MEDIUM risk, valuable complexity reduction
3. **Sprint 31** (Processing Config): 245 lines, MEDIUM risk, cleaner architecture

These extractions will reduce MainViewModel by **25%** while maintaining clean facades and testability.

The remaining ~1,872 lines of real implementation will be well-organized, focused, and maintainable.

---

**End of Report**
