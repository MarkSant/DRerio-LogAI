# Dependency Injection Migration - Remaining Work

## ✅ Phase 1: Core Services (COMPLETED)

The following core services have been successfully migrated to use Dependency Injection:

- ✅ `src/zebtrack/core/weight_manager.py` - Accepts `settings_obj` parameter
- ✅ `src/zebtrack/core/detector_service.py` - Accepts `settings_obj` parameter
- ✅ `src/zebtrack/core/project_manager.py` - Accepts `settings_obj` parameter
- ✅ `src/zebtrack/core/main_view_model.py` - Accepts 11 injected dependencies
- ✅ `src/zebtrack/core/detector.py` - Accepts `settings_obj` parameter
- ✅ `src/zebtrack/core/project_service.py` - Removed settings usage (delegated to ProjectManager)
- ⚠️ `src/zebtrack/core/wizard_service.py` - **2 usages** (needs migration - marked with TODO)
- ✅ `src/zebtrack/core/project_workflow_service.py` - Accepts `settings_obj` parameter
- ✅ `src/zebtrack/__main__.py` - Transformed into Composition Root with full DI

## ⚠️ Phase 2: Remaining Files (TODO - Next PR)

The following files **still use the singleton `settings`** and need to be migrated:

### Analysis Layer (19 total usages)
- ❌ `src/zebtrack/analysis/analysis_service.py` - **17 usages** (HIGH PRIORITY - Core service)
  - Needs constructor to accept `settings_obj`
  - Created by MainViewModel - easy to inject
- ❌ `src/zebtrack/analysis/reporter.py` - **0 usages** (import only - LOW PRIORITY)
  - Just remove the unused import

### IO Layer (11 total usages)
- ❌ `src/zebtrack/io/camera.py` - **9 usages** (HIGH PRIORITY - Core infrastructure)
  - Needs constructor to accept `settings_obj`
  - Used by MainViewModel and wizard
- ❌ `src/zebtrack/io/arduino.py` - **1 usage** (MEDIUM PRIORITY)
  - Needs constructor to accept `settings_obj`
  - Used by MainViewModel
- ❌ `src/zebtrack/io/recorder.py` - **1 usage** (MEDIUM PRIORITY)
  - Needs constructor to accept `settings_obj`
  - Created in Composition Root

### Plugins Layer (4 total usages)
- ❌ `src/zebtrack/plugins/openvino_detector.py` - **2 usages** (MEDIUM PRIORITY)
  - Needs constructor to accept `settings_obj`
  - Created by DetectorService (already has settings)
- ❌ `src/zebtrack/plugins/ultralytics_detector.py` - **2 usages** (MEDIUM PRIORITY)
  - Needs constructor to accept `settings_obj`
  - Created by DetectorService (already has settings)

### UI Layer (Unknown usages - needs analysis)
- ❌ `src/zebtrack/ui/gui.py` (LARGE FILE - Complex migration)
  - ApplicationGUI receives controller which has settings
  - May need settings passed explicitly for some operations
- ❌ `src/zebtrack/ui/wizard/wizard_adapter.py`
  - Used in wizard context
- ❌ `src/zebtrack/ui/wizard/model_selection_step.py`
  - Used in wizard step
- ❌ `src/zebtrack/ui/dialogs/single_video_config_dialog.py`
  - Dialog instantiation

### Logging
- ❌ `src/zebtrack/logging_config.py`
  - Used during application startup
  - May need special handling

### Test Files
- ❌ `tests/test_project_manager.py`
- ❌ `tests/analysis/test_analysis_service.py`

## 📋 Migration Strategy for Phase 2

### Priority Order:
1. **HIGH**: `analysis_service.py` (17 usages) - Core service, easy to inject via MainViewModel
2. **HIGH**: `camera.py` (9 usages) - Core infrastructure
3. **MEDIUM**: Plugins (4 usages) - Can be injected from DetectorService
4. **MEDIUM**: IO classes (2 usages) - Small, straightforward
5. **LOW**: UI layer - Complex, needs careful analysis
6. **LOW**: `reporter.py` - Just remove import
7. **LOW**: Tests - Update after implementation files

### Steps for Each File:
1. Add `settings_obj` parameter to `__init__` (with default `None` for backward compat)
2. Replace all `settings.` with `self.settings.`
3. Add null checks where appropriate
4. Update instantiation sites to pass `settings_obj`
5. Update tests to inject mock settings

## 🔧 Current Workaround

A **temporary singleton** has been restored in `settings.py` with:
- Clear deprecation comments
- Warning logs indicating it's temporary
- List of files that need migration
- TODO comments pointing to this document

This allows the application to function while migration continues incrementally.

## 🎯 Goal

Complete removal of the singleton so that:
- All settings are explicitly injected via Composition Root
- No global state
- Full testability with mocked settings
- Clear dependency graph

## 📝 Notes

- The Composition Root (`__main__.py`) is responsible for loading settings once
- All services should receive settings via constructor injection
- Settings should never be imported and used directly in service classes
- Test files should inject mock settings objects
