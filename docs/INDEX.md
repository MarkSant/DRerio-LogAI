# ZebTrack-AI Documentation Index

**Last Updated**: December 2025
**Version**: 3.0.0

## Overview

This index provides centralized navigation for all ZebTrack-AI documentation.

ZebTrack-AI (DRerio LogAI) is a Python 3.12+ application for zebrafish behavioral tracking
and analysis using YOLO/OpenVINO with MVVM-S architecture and dependency injection.

---

## Documentation Structure

```text
docs/
├── INDEX.md                 # This file - central navigation
├── README.md                # Documentation entry point
├── changelog.md             # Version history
├── VULNERABILITY_REPORT.md  # Active security tracking
│
├── architecture/            # System design & patterns
├── guides/                  # Developer & user guides
│   ├── developer/           # Technical development guides
│   └── user/                # End-user documentation
├── reference/               # API & operational reference
├── performance/             # Optimization & benchmarks
├── testing/                 # Testing guides & fixes
├── decisions/               # Architecture Decision Records (ADRs)
├── migration/               # Version upgrade guides
├── wiki/                    # User guides (Portuguese)
├── api/                     # Auto-generated Sphinx docs
└── archive/                 # Historical documentation
```

---

## For Users

### Getting Started

- **[Installation Guide](../README.md#installation)** - Setup instructions with Poetry
- **[Wizard User Guide](wiki/1_Wizard_User_Guide.md)** - Step-by-step project creation (Portuguese)
- **[Full Tutorial](wiki/2_Full_Tutorial.md)** - Complete workflow walkthrough (Portuguese)
- **[FAQ](wiki/3_FAQ.md)** - Frequently asked questions (Portuguese)

### Features & Usage

- **[Behavioral Metrics](reference/BEHAVIORAL_METRICS.md)** - Available analysis metrics
- **[Coordinate Systems](reference/COORDINATE_SYSTEMS.md)** - Understanding ROI coordinates
- **[Known Issues](reference/KNOWN_ISSUES.md)** - Current limitations and workarounds
- **[Reference Guide](reference/REFERENCE_GUIDE.md)** - Operational reference

### Configuration

- **[Performance Tuning](performance/PERFORMANCE_TUNING.md)** - Optimizing processing speed
- **[Settings Reference](../config.yaml)** - Configuration file documentation

---

## For Developers

### Architecture & Design (START HERE)

- **[Architecture Overview](architecture/ARCHITECTURE.md)** - System design and MVVM-S pattern
- **[Architecture v4.0](architecture/ARCHITECTURE_V4.md)** - Event-driven architecture details
- **[Dependency Injection Guide](architecture/DEPENDENCY_INJECTION_GUIDE.md)** - DI patterns
- **[State Management Guide](architecture/STATE_MANAGEMENT_GUIDE.md)** - StateManager usage
- **[Service Layer Patterns](architecture/SERVICE_LAYER_PATTERNS.md)** - Service design
- **[System Integration Map](architecture/SYSTEM_INTEGRATION_MAP.md)** - CRITICAL: Event payloads

### Event System

- **[Event Bus Guide](architecture/EVENT_BUS_GUIDE.md)** - Event bus usage patterns
- **[Event Mapping](architecture/EVENT_MAPPING.md)** - Component-to-event mapping

### Development Workflows

- **[Contributing Guide](../CONTRIBUTING.md)** - How to contribute
- **[Developer Cheatsheet](guides/developer/CHEATSHEET.md)** - Quick command reference
- **[Workflows](guides/developer/WORKFLOWS.md)** - Common development flows
- **[Developer Guide - Wizard](guides/developer/DEVELOPER_GUIDE_WIZARD.md)** - Wizard development
- **[Quick Debug Guide](guides/developer/QUICK_DEBUG_GUIDE.md)** - Debugging tips
- **[Error Handling](guides/developer/ERROR_HANDLING.md)** - Exception handling patterns

### Feature-Specific Guides

- **[Live Camera Unification](guides/developer/LIVE_CAMERA_UNIFICATION.md)** - v2.1 camera architecture
- **[Wizard & Live Improvements](guides/developer/WIZARD_LIVE_IMPROVEMENTS.md)** - Phase 4-7 enhancements

### Testing

- **[Testing Guide](../README_TESTS.md)** - Complete testing guide
- **[Testing Tkinter Windows](testing/TESTING_TKINTER_WINDOWS.md)** - UI testing patterns
- **[Test Fixes (Nov 2025)](testing/TEST_FIXES_NOV_2025.md)** - Critical pytest fixes
- **[Testing Deprecation Warnings](testing/TESTING_DEPRECATION_WARNINGS.md)** - Handling warnings

### API Reference

- **[DetectorService API](reference/detector_service_api.md)** - Detection interface
- **[Widgets](reference/WIDGETS.md)** - Custom UI components
- **[API Stability](reference/API_STABILITY.md)** - API versioning policy
- **[Sphinx API Docs](api/README.md)** - Auto-generated API docs

### Performance & Optimization

- **[Performance Tuning](performance/PERFORMANCE_TUNING.md)** - Optimization strategies
- **[Performance Baseline](performance/PERFORMANCE_BASELINE.md)** - Current metrics
- **[Benchmark Guide](performance/BENCHMARK_GUIDE.md)** - Benchmarking tools
- **[State Manager Threading](performance/STATE_MANAGER_THREADING.md)** - Thread safety

### Migration & Upgrades

- **[Migration Guides](migration/README.md)** - Version upgrade guides
- **[v2.1 to v3.0 Migration](migration/v2.1-to-v3.0.md)** - Major version upgrade
- **[Reporter v3 Migration](migration/reporter-v3-migration.md)** - Reporter API changes

### Architecture Decisions (ADRs)

- **[ADR-004: Live Camera Divergence](decisions/ADR-004-live-camera-divergence.md)**
- **[ADR-005: Model Overrides Duplication](decisions/ADR-005-model-overrides-duplication.md)**

---

## Quick Navigation

### By Role

| Role | Start Here |
|------|------------|
| New User | [Wizard User Guide](wiki/1_Wizard_User_Guide.md) |
| New Developer | [Architecture](architecture/ARCHITECTURE.md) + [Contributing](../CONTRIBUTING.md) |
| Debugger | [Quick Debug Guide](guides/developer/QUICK_DEBUG_GUIDE.md) |
| Performance Engineer | [Performance Tuning](performance/PERFORMANCE_TUNING.md) |
| UI Developer | [Widgets](reference/WIDGETS.md) + [State Management](architecture/STATE_MANAGEMENT_GUIDE.md) |
| Testing Engineer | [Testing Guide](../README_TESTS.md) |

### By Task

| Task | Documents |
|------|-----------|
| Implementing new feature | [Workflows](guides/developer/WORKFLOWS.md) + [Service Patterns](architecture/SERVICE_LAYER_PATTERNS.md) |
| Fixing bug | [Error Handling](guides/developer/ERROR_HANDLING.md) + [Quick Debug](guides/developer/QUICK_DEBUG_GUIDE.md) |
| Adding detector plugin | [DetectorService API](reference/detector_service_api.md) |
| UI changes | [Widgets](reference/WIDGETS.md) + [State Management](architecture/STATE_MANAGEMENT_GUIDE.md) |
| Writing tests | [Testing Guide](../README_TESTS.md) + [Testing Tkinter](testing/TESTING_TKINTER_WINDOWS.md) |

---

## Special Directories

- **architecture/** - Core system design (MVVM-S, DI, State Management, Events)
- **guides/developer/** - Technical guides for contributors
- **guides/user/** - End-user documentation (English)
- **reference/** - API documentation and operational guides
- **performance/** - Performance tuning and benchmarking
- **testing/** - Testing patterns and pytest configuration
- **decisions/** - Architecture Decision Records (ADRs)
- **migration/** - Version upgrade guides
- **wiki/** - User guides in Portuguese
- **api/** - Auto-generated Sphinx docs
- **archive/** - Historical documents (see [archive/README.md](archive/README.md))

---

## Documentation Statistics

| Category | Count |
|----------|-------|
| Total Active Files | ~40 |
| Architecture Docs | 8 |
| Developer Guides | 8 |
| Reference Docs | 8 |
| Performance Docs | 4 |
| Testing Docs | 3 |
| User Guides (wiki/) | 5 |
| Archived Files | 70+ |

---

**Navigation**: [Main README](../README.md) | [Contributing](../CONTRIBUTING.md) | [Changelog](changelog.md)
