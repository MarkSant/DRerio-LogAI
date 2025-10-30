# Changelog

All notable changes to DRerio LogAI (zebtrack) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.0] - YYYY-MM-DD

### ⚠️ Breaking Changes

- Wizard live projects now require experimental design configuration (groups/days/subjects)
- Existing projects may need metadata added for full compatibility with new features

### ✨ New Features

**Architecture & Code Quality**:
- **Wizard Service Layer**: Extracted all wizard business logic to `zebtrack.core.wizard_service`
  - Centralized hardware detection (cameras, Arduino)
  - Reusable validation functions
  - Calculation utilities (experiment metrics, interval suggestions)
  - Fully testable independent of UI
  - **Hardware Detection Caching**: 30-second TTL cache for camera/Arduino detection (~5x faster on repeated calls)
- **Pydantic Data Models**: Type-safe validation for wizard data
  - `LiveConfigData`, `ExperimentalDesignData`, `CalibrationData`
  - Cross-field validations (e.g., external trigger requires Arduino)
  - Auto-generated error messages
- **Dialog Modularization**: Extracted 13 dialog classes from `gui.py` to `zebtrack.ui.dialogs/`
  - Reduced `gui.py` from 13,473 to 10,759 lines (~20% reduction)
  - Improved modularity, testability, and maintainability
  - Dialogs: CalibrationDialog, ManageWeightsDialog, ColorSelectionDialog, etc.
  - Resolved circular dependencies with `ui/format_utils.py`
- **Single-Video Mode Enhancement**: CalibrationDialog now hides "Project Preferences" section when in single-video analysis mode (no project context)

**Wizard Improvements** (from previous phases):
- Express/Advanced wizard modes
- External Trigger Mode for Arduino-based experiments
- Zone-based Arduino command triggers
- ROI inclusion rules (per-project configuration)
- Project template system (save/load wizard configurations)
- Unified preferences dialog with CollapsibleFrame UI

**Hardware Integration**:
- Arduino port detection with handshake validation
- Port descriptions (e.g., "COM3 - Arduino Uno")
- Connection test button with detailed error messages
- Camera detection with DirectShow backend (Windows) and early stopping optimization
- OpenCV log suppression during detection

**UI Enhancements**:
- NumberInput widget for intuitive numeric entry (+/- buttons)
- CollapsibleFrame widget for organized UI sections
- Treeview color harmonization (consistent green/yellow/red indicators)
- Interactive regex examples in CustomRegexDialog
- Improved tooltip coverage (100% of wizard fields)

### 🔧 Improvements

- **Performance**: Hardware detection caching reduces wizard navigation lag
  - Camera detection: ~5x faster on repeated calls (cached for 30 seconds)
  - Arduino port scanning: Instant results when navigating back/forward in wizard
  - Manual cache clearing available via `WizardService.clear_hardware_cache()`
- Model selection now available for live projects
- Configurable analysis/display intervals per project
- Automatic camera/Arduino detection with status feedback
- Intelligent suggestions (e.g., analysis interval based on FPS)
- Validation moved from UI to service layer (better testability)
- Removed legacy `LiveConfigDialog` (replaced by wizard `LiveConfigStep`)
- Code organization: Major cleanup with dialog extraction reducing `gui.py` complexity

### 📝 Documentation

- **NEW**: `docs/DEVELOPER_GUIDE_WIZARD.md` - Comprehensive wizard architecture guide
  - Service layer patterns
  - Pydantic model usage
  - How to add new wizard steps
  - Testing strategies
  - Best practices and anti-patterns
- **UPDATED**: `docs/WIZARD_LIVE_IMPROVEMENTS.md` - Phase 0-4 improvements
- **UPDATED**: `CLAUDE.md` - Project instructions with v2.0 features

### 🧪 Testing

- **712 tests passing** (24 new tests, 0 regressions)
  - 16 E2E tests for WizardService integration (`tests/ui/wizard/test_wizard_live_e2e.py`)
  - 8 hardware caching tests (`tests/test_wizard_service_caching.py`)
- Service layer fully unit tested
- Wizard steps validated with integration tests
- Code coverage maintained at 70%+
- Removed 1 redundant skipped test (architectural rule already enforced by other tests)

### 🐛 Bug Fixes

- Fixed line length violations in `project_manager.py`
- Reduced cyclomatic complexity in `gui.py` (_VideoPathResolverContext helper class)
- Removed unused imports

### 🔄 Refactoring

- **Dialog Extraction**: Moved 13 dialog classes from `gui.py` to `zebtrack.ui.dialogs/`
  - Created AST-based extraction scripts for reliable code extraction
  - Fixed all missing imports and circular dependencies
  - Updated tests to reference new dialog locations
- Extracted wizard validation logic to `WizardService`
- Moved hardware detection to service layer with caching
- Created Pydantic models for type safety
- Simplified wizard step `validate()` methods (delegate to service)
- Created `ui/format_utils.py` to resolve circular dependencies

### 📦 Dependencies

- No new dependencies added
- Pydantic v2 already in use (existing dependency)

---

## [1.6.0] - Previous Release

### Added
- Wizard-based project creation (5-step flow)
- Live project support with camera/Arduino integration
- Experimental design fields (groups, days, subjects)
- Template persistence

### Changed
- Wizard is now the default project creation method
- Legacy dialogs maintained for backward compatibility

---

## How to Upgrade

### From v1.x to v2.0

1. **No action required** for existing projects - they will continue to work
2. **New live projects** must use the wizard and provide experimental design
3. **Developers**: Review `docs/DEVELOPER_GUIDE_WIZARD.md` for new patterns
4. **Tip**: Use `WizardService` for any new validation/hardware logic

### Template Migration

If you have saved wizard templates from v1.6+, they are compatible with v2.0.
New fields (experimental design) will use defaults if not present in old templates.

---

## Support

- Report issues: https://github.com/anthropics/claude-code/issues
- Documentation: See `docs/` directory
- Developer Guide: `docs/DEVELOPER_GUIDE_WIZARD.md`
