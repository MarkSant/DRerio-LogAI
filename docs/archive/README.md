# Documentation Archive

This directory contains historical documentation that provides context about past refactorings and implementation decisions, but is not needed for day-to-day development.

**Last Updated**: November 2025 (P4-T4 Documentation Curation)

## Contents

### Pre-Refactoring Analyses (Nov 2025)
- **GOD_OBJECTS_ANALYSIS.md** - Initial god object assessment (Nov 5, 2025)
- **MAINVIEWMODEL_ANALYSIS.md** - Pre-refactoring MainViewModel structural analysis
- **EXTRACTION_ANALYSIS_PHASE2.md** - Phase 2 extraction analysis
- **METHOD_INDEX_FOR_EXTRACTION.md** - Method extraction tracking index

### Completed Phases & Tasks (2025 Refactoring)
- **PHASE3_FINAL_STATUS.md** - Phase 3 completion report (goal: reduce gui.py to 4000 lines)
- **PHASE3_SESSION_PROGRESS.md** - Phase 3 session-by-session progress tracking
- **TASK_CONTEXTS.md** - Historical task context tracking (Rounds 1-2)
- **TASK_CONTEXTS_RODADAS_3_4_5.md** - Task contexts for rounds 3-5
- **TASK_2.2_INTEGRATION_PLAN.md** - Task 2.2 integration plan (completed)
- **TRACK_6_COMPLETION_SUMMARY.md** - Track 6 completion summary

### Dialog & Pattern Migrations (Completed)
- **DIALOG_MANAGER_EXTRACTION.md** - Dialog extraction from gui.py (completed in Phase 4)
- **DIALOG_MANAGER_MIGRATION_GUIDE.md** - Migration guide for dialog extraction
- **EXTRACTION_TEMPLATE_PATTERN.md** - Template pattern for extraction (superseded by SERVICE_LAYER_PATTERNS.md)
- **FACADE_PATTERN.md** - Facade pattern documentation (historical)

### Live Analysis Feature Development (Nov 2025)
- **LIVE_PROJECTS_PARALLEL_ANALYSIS.md** - Analysis of live projects vs live camera analysis
- **LIVE_ANALYSIS_REFACTORING_SUMMARY.md** - Summary of live analysis refactoring
- **LIVE_ANALYSIS_IMPLEMENTATION_PLAN.md** - Implementation plan for live analysis feature

### Tool-Specific Documentation (GitHub Copilot)
- **COPILOT_OPTIMIZATION.md** - GitHub Copilot optimization strategies
- **COPILOT_OPTIMIZATION_IMPLEMENTATION.md** - Implementation details for Copilot optimizations
- **COPILOT_QUICK_START.md** - Quick start guide for using Copilot with ZebTrack-AI

### Documentation Updates Log
- **DOCUMENTATION_UPDATE_OCT31_2025.md** - Documentation update log for October 31, 2025

## Purpose

These documents are kept for:
- **Historical reference** - Understanding the evolution of the codebase
- **Architectural decisions** - Context for why certain patterns were chosen or discarded
- **Lessons learned** - Documentation of challenges faced during refactoring
- **Audit trail** - Complete record of major refactorings and migrations
- **Knowledge preservation** - Retaining context for future maintainers

## Archive Policy

Documents are moved to this archive when:
1. The refactoring phase they describe is **completed**
2. The patterns or processes they document are **superseded** by newer approaches
3. The analysis they contain is **pre-refactoring** and no longer reflects current state
4. The task tracking they provide is **historical** and no longer active

## For Current Development

⚠️ **Do not use archived documents for current development!**

Refer to the main documentation:
- **[docs/INDEX.md](../INDEX.md)** - Central documentation index (⭐ START HERE)
- **[CLAUDE.md](../../CLAUDE.md)** - AI assistant guidance
- **[docs/ARCHITECTURE.md](../ARCHITECTURE.md)** - Current architecture
- **[docs/REFERENCE_GUIDE.md](../REFERENCE_GUIDE.md)** - Operational reference
- **[docs/CHEATSHEET.md](../CHEATSHEET.md)** - Quick reference for developers
- **[docs/SERVICE_LAYER_PATTERNS.md](../SERVICE_LAYER_PATTERNS.md)** - Current service patterns

## Restoration

If an archived document becomes relevant again (e.g., for a similar refactoring):
1. Review the document to ensure accuracy
2. Update outdated information
3. Move back to main docs/ directory
4. Update the [INDEX.md](../INDEX.md)

## Maintenance

This archive is maintained as part of the P4-T4 documentation curation task.
**Maintained by**: Agent-15
