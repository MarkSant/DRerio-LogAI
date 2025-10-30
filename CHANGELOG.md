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
- **Pydantic Data Models**: Type-safe validation for wizard data
  - `LiveConfigData`, `ExperimentalDesignData`, `CalibrationData`
  - Cross-field validations (e.g., external trigger requires Arduino)
  - Auto-generated error messages
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

- Model selection now available for live projects
- Configurable analysis/display intervals per project
- Automatic camera/Arduino detection with status feedback
- Intelligent suggestions (e.g., analysis interval based on FPS)
- Validation moved from UI to service layer (better testability)
- Removed legacy `LiveConfigDialog` (replaced by wizard `LiveConfigStep`)

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

- All 688 tests passing (0 regressions)
- Service layer fully unit tested
- Wizard steps validated with integration tests
- Code coverage maintained at 70%+

### 🐛 Bug Fixes

- Fixed line length violations in `project_manager.py`
- Reduced cyclomatic complexity in `gui.py` (_VideoPathResolverContext helper class)
- Removed unused imports

### 🔄 Refactoring

- Extracted wizard validation logic to `WizardService`
- Moved hardware detection to service layer
- Created Pydantic models for type safety
- Simplified wizard step `validate()` methods (delegate to service)

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
