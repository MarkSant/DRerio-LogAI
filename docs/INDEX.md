# ZebTrack-AI Documentation Index

**Last Updated**: November 2025
**Version**: 2.1.0
**Maintained by**: Agent-15 (P4-T4)

## 📚 Overview

This index provides centralized navigation for all ZebTrack-AI documentation. ZebTrack-AI (DRerio LogAI) is a Python 3.12+ application for zebrafish behavioral tracking and analysis using YOLO/OpenVINO with MVVM-S architecture and dependency injection.

---

## 👤 For Users

### Getting Started
- **[Installation Guide](../README.md#installation)** - Setup instructions with Poetry
- **[Wizard User Guide](wiki/1_Wizard_User_Guide.md)** - Step-by-step project creation (Portuguese)
- **[Full Tutorial](wiki/2_Full_Tutorial.md)** - Complete workflow walkthrough (Portuguese)
- **[FAQ](wiki/3_FAQ.md)** - Frequently asked questions (Portuguese)

### Features & Usage
- **[Behavioral Metrics](BEHAVIORAL_METRICS.md)** - Available analysis metrics and calculations
- **[Coordinate Systems](COORDINATE_SYSTEMS.md)** - Understanding ROI coordinates and zones
- **[Known Issues](KNOWN_ISSUES.md)** - Current limitations and workarounds
- **[Reference Guide](REFERENCE_GUIDE.md)** - Operational reference for advanced users

### Configuration
- **[Performance Tuning](PERFORMANCE_TUNING.md)** - Optimizing processing speed and resource usage
- **[Settings Reference](../config.yaml)** - Configuration file documentation

---

## 🛠️ For Developers

### Architecture & Design ⭐ START HERE
- **[Architecture Overview](ARCHITECTURE.md)** - System design and MVVM-S pattern
- **[Dependency Injection Guide](DEPENDENCY_INJECTION_GUIDE.md)** - DI patterns and composition root
- **[State Management Guide](STATE_MANAGEMENT_GUIDE.md)** - StateManager usage and thread safety
- **[Service Layer Patterns](SERVICE_LAYER_PATTERNS.md)** - Service design principles
- **[Error Handling](ERROR_HANDLING.md)** - Exception handling patterns

### Development Workflows
- **[Contributing Guide](../CONTRIBUTING.md)** - How to contribute to the project
- **[Developer Cheatsheet](CHEATSHEET.md)** - Quick command reference
- **[Workflows](WORKFLOWS.md)** - Common development flows
- **[Developer Guide - Wizard](DEVELOPER_GUIDE_WIZARD.md)** - Wizard component development
- **[Quick Debug Guide](QUICK_DEBUG_GUIDE.md)** - Debugging tips and common issues

### Testing
- **[Testing Guide](../README_TESTS.md)** - Complete testing guide (root level)
- **[Testing Tkinter Windows](TESTING_TKINTER_WINDOWS.md)** - UI testing patterns
- **[Test Fixes (Nov 2025)](TEST_FIXES_NOV_2025.md)** - Critical pytest hang fixes
- **[Testing Deprecation Warnings](TESTING_DEPRECATION_WARNINGS.md)** - Handling warnings

### API Reference
- **[DetectorService API](detector_service_api.md)** - Detection interface and plugins
- **[Widgets](WIDGETS.md)** - Custom UI components documentation
- **[Sphinx API Docs](api/README.md)** - Auto-generated API documentation

### Performance & Optimization
- **[Performance Tuning](PERFORMANCE_TUNING.md)** - Optimization strategies
- **[Performance Baseline](PERFORMANCE_BASELINE.md)** - Current performance metrics
- **[Benchmark Guide](BENCHMARK_GUIDE.md)** - Benchmarking tools and methodology
- **[State Manager Threading](STATE_MANAGER_THREADING.md)** - Thread safety details

### Migration & Upgrades
- **[Migration Guides](migration/README.md)** - Version upgrade guides
- **[v2.1 → v3.0 Migration](migration/v2.1-to-v3.0.md)** - Major version upgrade
- **[Reporter v3 Migration](migration/reporter-v3-migration.md)** - Reporter API changes

### Recent Major Features (2025)
- **[Wizard & Live Improvements](WIZARD_LIVE_IMPROVEMENTS.md)** - Phase 4-7 enhancements
- **[Changelog](changelog.md)** - Full version history

---

## 📝 Refactoring Documentation (2025)

These documents track the major refactoring effort in 2025:

### Orchestration & Planning
- **[Refactoring Plan Part 1](../PLANO_REFATORACAO_PARALELA_PARTE1.md)** - Phase 1 plan (Portuguese)
- **[Refactoring Plan Part 2](../PLANO_REFATORACAO_PARALELA_PARTE2.md)** - Phases 2-4 plan (Portuguese)
- **[Agent Orchestration Guide](../AGENT_ORCHESTRATION_GUIDE.md)** - Multi-agent execution guide
- **[Refactoring Quick Reference](../REFACTORING_QUICK_REFERENCE.md)** - Summary and status
- **[Execution Plan](../EXECUTION_PLAN.md)** - Detailed execution tracking

### Agent Instructions (Historical)
- [Agent 01 Instructions](../AGENT_INSTRUCTIONS_01_PHASE1_GROUP1.md) - Phase 1 Group 1
- [Agent 02 Instructions](../AGENT_INSTRUCTIONS_02_PHASE1_GROUP2.md) - Phase 1 Group 2
- [Agent 03 Instructions](../AGENT_INSTRUCTIONS_03_PHASE1_GROUP3.md) - Phase 1 Group 3
- [Agent 04 Instructions](../AGENT_INSTRUCTIONS_04_PHASE2_SEQUENTIAL.md) - Phase 2
- [Agent 05 Instructions](../AGENT_INSTRUCTIONS_05_PHASE3_PARALLEL.md) - Phase 3
- [Agent 06 Instructions](../AGENT_INSTRUCTIONS_06_PHASE4_GROUP1.md) - Phase 4 Group 1
- [Agent 07 Instructions](../AGENT_INSTRUCTIONS_07_PHASE4_GROUP2.md) - Phase 4 Group 2

### Phase Progress Tracking (refactoring/ subdirectory)
- **[Final Task 2.1 Summary](refactoring/FINAL_TASK_2.1_SUMMARY.md)**
- **[Task 2.1 Summary](refactoring/TASK_2.1_SUMMARY.md)**
- **[Phase 3 Progress](refactoring/PHASE_3_PROGRESS.md)**
- **[Refactor Summary](refactoring/REFACTOR_SUMMARY.md)**
- **[Metodos GUI Analysis](refactoring/METODOS_GUI_ANALYSIS.md)** (Portuguese)
- **[Project View Manager Analysis](refactoring/PROJECT_VIEW_MANAGER_ANALYSIS.md)**

---

## 🗂️ Archive (Historical Reference Only)

**⚠️ These documents are kept for historical context but may be outdated:**

### Pre-Refactoring Analyses
- **[archive/GOD_OBJECTS_ANALYSIS.md](archive/GOD_OBJECTS_ANALYSIS.md)** - Initial god object assessment
- **[archive/MAINVIEWMODEL_ANALYSIS.md](archive/MAINVIEWMODEL_ANALYSIS.md)** - Pre-refactoring MainViewModel analysis
- **[archive/EXTRACTION_ANALYSIS_PHASE2.md](archive/EXTRACTION_ANALYSIS_PHASE2.md)** - Phase 2 extraction analysis
- **[archive/METHOD_INDEX_FOR_EXTRACTION.md](archive/METHOD_INDEX_FOR_EXTRACTION.md)** - Extraction tracking

### Completed Phases & Tasks
- **[archive/PHASE3_FINAL_STATUS.md](archive/PHASE3_FINAL_STATUS.md)** - Phase 3 completion report
- **[archive/PHASE3_SESSION_PROGRESS.md](archive/PHASE3_SESSION_PROGRESS.md)** - Phase 3 session tracking
- **[archive/TASK_CONTEXTS.md](archive/TASK_CONTEXTS.md)** - Old task context tracking
- **[archive/TASK_CONTEXTS_RODADAS_3_4_5.md](archive/TASK_CONTEXTS_RODADAS_3_4_5.md)** - Additional task contexts
- **[archive/TASK_2.2_INTEGRATION_PLAN.md](archive/TASK_2.2_INTEGRATION_PLAN.md)** - Completed integration task
- **[archive/TRACK_6_COMPLETION_SUMMARY.md](archive/TRACK_6_COMPLETION_SUMMARY.md)** - Track 6 summary

### Dialog & Pattern Migrations
- **[archive/DIALOG_MANAGER_EXTRACTION.md](archive/DIALOG_MANAGER_EXTRACTION.md)** - Dialog extraction completed
- **[archive/DIALOG_MANAGER_MIGRATION_GUIDE.md](archive/DIALOG_MANAGER_MIGRATION_GUIDE.md)** - Migration completed
- **[archive/EXTRACTION_TEMPLATE_PATTERN.md](archive/EXTRACTION_TEMPLATE_PATTERN.md)** - Superseded by SERVICE_LAYER_PATTERNS.md
- **[archive/FACADE_PATTERN.md](archive/FACADE_PATTERN.md)** - Historical pattern documentation

### Live Analysis Feature Development
- **[archive/LIVE_ANALYSIS_IMPLEMENTATION_PLAN.md](archive/LIVE_ANALYSIS_IMPLEMENTATION_PLAN.md)** - Original plan
- **[archive/LIVE_ANALYSIS_REFACTORING_SUMMARY.md](archive/LIVE_ANALYSIS_REFACTORING_SUMMARY.md)** - Implementation summary
- **[archive/LIVE_PROJECTS_PARALLEL_ANALYSIS.md](archive/LIVE_PROJECTS_PARALLEL_ANALYSIS.md)** - Parallel analysis design

### Tool-Specific Documentation
- **[archive/COPILOT_OPTIMIZATION.md](archive/COPILOT_OPTIMIZATION.md)** - GitHub Copilot optimizations
- **[archive/COPILOT_OPTIMIZATION_IMPLEMENTATION.md](archive/COPILOT_OPTIMIZATION_IMPLEMENTATION.md)** - Implementation details
- **[archive/COPILOT_QUICK_START.md](archive/COPILOT_QUICK_START.md)** - Quick start guide

### Documentation Updates Log
- **[archive/DOCUMENTATION_UPDATE_OCT31_2025.md](archive/DOCUMENTATION_UPDATE_OCT31_2025.md)** - October 31 update log

---

## 📋 Quick Navigation

### By Role
- **New User** → Start with [Wizard User Guide](wiki/1_Wizard_User_Guide.md) (Portuguese)
- **New Developer** → Start with [Architecture](ARCHITECTURE.md) + [Contributing](../CONTRIBUTING.md)
- **Debugger** → See [Quick Debug Guide](QUICK_DEBUG_GUIDE.md)
- **Performance Engineer** → See [Performance Tuning](PERFORMANCE_TUNING.md) + [Benchmark Guide](BENCHMARK_GUIDE.md)
- **UI Developer** → See [Widgets](WIDGETS.md) + [State Management](STATE_MANAGEMENT_GUIDE.md)
- **Testing Engineer** → See [Testing Guide](../README_TESTS.md) + [Test Fixes](TEST_FIXES_NOV_2025.md)

### By Task
- **Implementing new feature** → [Workflows](WORKFLOWS.md) + [Service Patterns](SERVICE_LAYER_PATTERNS.md)
- **Fixing bug** → [Error Handling](ERROR_HANDLING.md) + [Quick Debug Guide](QUICK_DEBUG_GUIDE.md)
- **Adding detector plugin** → [DetectorService API](detector_service_api.md)
- **UI changes** → [Widgets](WIDGETS.md) + [State Management](STATE_MANAGEMENT_GUIDE.md)
- **Performance optimization** → [Performance Tuning](PERFORMANCE_TUNING.md) + [Benchmark Guide](BENCHMARK_GUIDE.md)
- **Writing tests** → [Testing Guide](../README_TESTS.md) + [Testing Tkinter](TESTING_TKINTER_WINDOWS.md)
- **Understanding architecture** → [Architecture](ARCHITECTURE.md) + [DI Guide](DEPENDENCY_INJECTION_GUIDE.md)

### By Feature Area
- **Wizard** → [Developer Guide - Wizard](DEVELOPER_GUIDE_WIZARD.md) + [Wizard User Guide](wiki/1_Wizard_User_Guide.md)
- **Live Camera Analysis** → [Wizard Live Improvements](WIZARD_LIVE_IMPROVEMENTS.md)
- **ROI & Zones** → [Coordinate Systems](COORDINATE_SYSTEMS.md) + [Behavioral Metrics](BEHAVIORAL_METRICS.md)
- **Video Processing** → [Reference Guide](REFERENCE_GUIDE.md) + [Performance Tuning](PERFORMANCE_TUNING.md)
- **Analysis & Reports** → [Behavioral Metrics](BEHAVIORAL_METRICS.md) + [Reporter Migration](migration/reporter-v3-migration.md)

---

## 📦 Special Directories

### `/docs/api/`
Auto-generated Sphinx documentation. See [api/README.md](api/README.md) for build instructions.

### `/docs/migration/`
Version migration guides. See [migration/README.md](migration/README.md) for available guides.

### `/docs/refactoring/`
Phase-by-phase refactoring progress tracking (2025 refactoring effort).

### `/docs/archive/`
Historical documents from completed phases, pre-refactoring analyses, and superseded patterns.

### `/docs/wiki/`
User-facing guides in Portuguese (installation, tutorials, FAQ).

### `/test_scenarios/`
Test scenario documentation. See [test_scenarios/README.md](../test_scenarios/README.md).

### `/tests/fixtures/`
Test fixture documentation. See [tests/fixtures/README.md](../tests/fixtures/README.md).

---

## 🔄 Maintenance

### Updating This Index
This index should be updated when:
- New major features are added
- Documentation structure changes
- Files are moved to archive
- New documentation files are created
- Major refactoring phases complete

### Documentation Standards
- **Language**: Portuguese for user docs, English for technical/developer docs
- **Format**: Markdown (.md)
- **Line Length**: 100 characters (Ruff standard)
- **Links**: Use relative paths within repository

### Missing Documentation?
If you notice missing or outdated documentation:
1. Check the [Issue Tracker](https://github.com/MarkSant/ZebTrack-AI/issues)
2. Review existing documentation
3. [Open a new issue](https://github.com/MarkSant/ZebTrack-AI/issues/new) with label `documentation`

---

## 📊 Documentation Statistics

**Total Markdown Files**: ~87
**Active Documentation**: ~60 files
**Archived Documentation**: ~17 files
**User Guides**: 3 (wiki/)
**Developer Guides**: 20+
**API Documentation**: Auto-generated (Sphinx)

**Coverage Areas**:
- ✅ Architecture & Design
- ✅ Testing & Quality
- ✅ Performance & Optimization
- ✅ User Guides (Portuguese)
- ✅ Migration Guides
- ✅ API Reference
- ✅ Refactoring History

---

## 📄 License

This documentation is part of the ZebTrack-AI project and is licensed under the MIT License.

---

**Navigation**: [Main README](../README.md) | [Contributing](../CONTRIBUTING.md) | [Changelog](changelog.md) | [CLAUDE.md](../CLAUDE.md)
