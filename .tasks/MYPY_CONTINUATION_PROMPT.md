# 🎯 MYPY CLEANUP - CONTINUATION DIRECTIVE

## ⚠️ MANDATORY MISSION PARAMETERS

**This is a CRITICAL task that MUST be completed in full, without interruption.**

### 🔴 NON-NEGOTIABLE REQUIREMENTS

1. **COMPLETE ALL FIXES** - This task is NOT optional. Every single mypy error MUST be resolved.
2. **NO INTERRUPTIONS** - Do NOT stop work until the error count reaches ZERO (0).
3. **NO SUMMARIES UNTIL COMPLETE** - Do not provide interim summaries or ask for approval. Work continuously.
4. **SYSTEMATIC APPROACH** - Follow the priority order defined in `.tasks/mypy_cleanup_task.md`
5. **UPDATE TRACKING** - Update `.tasks/mypy_cleanup_task.md` after every batch of 10+ files fixed

---

## 📊 CURRENT STATUS

**Date**: 2026-01-28 19:10 UTC-3
**Repository**: ZebTrack-AI (Zebrafish tracking application)
**Initial Error Count**: 1,952 mypy errors
**Current Error Count**: 1,852 mypy errors
**Progress**: 100 errors fixed (5% complete)
**Remaining Work**: 1,852 errors (95% remaining)

### ✅ What Has Been Completed

**29 files fixed** across:
- UI dialogs and wizards (8 files)
- Core services (5 files)
- Analysis/reporting (2 files)
- Utils and plugins (6 files)
- Scripts (4 files)
- Type stubs installed (types-PyYAML, types-polib)

**See `.tasks/mypy_cleanup_task.md` for complete list.**

---

## 🎯 YOUR MISSION

### Primary Objective
**Fix ALL remaining 1,852 mypy errors across ~226 files.**

### Execution Strategy

#### Phase 1: High-Impact Files (Priority)
Target files with the most errors first:
1. `processing_coordinator.py` (~50 errors) - Critical for video processing
2. `state_manager.py` (~15 errors) - Core state management
3. `project_manager.py` (~20 errors) - Project lifecycle
4. UI dialogs with multiple errors (~65 errors total)
5. Coordinators (`hardware_coordinator.py`, `session_coordinator.py`, etc.)

#### Phase 2: Moderate-Impact Files
6. Analysis services and data transformers
7. Recording and live camera services
8. UI components and widgets
9. Remaining wizards and dialogs

#### Phase 3: Low-Impact Files
10. Test files (if needed)
11. Utility scripts
12. Documentation scripts

---

## 🔧 TECHNICAL GUIDELINES

### Common Error Types & Fixes

**1. Missing Type Annotations (`no-untyped-def`, `var-annotated`)**
```python
# ❌ Before
def process_data(items):
    results = []

# ✅ After
def process_data(items: list[str]) -> list[dict]:
    results: list[dict] = []
```

**2. Incorrect Type Usage (`any` vs `Any`)**
```python
# ❌ Before
def handler(data: dict[str, any]) -> None:

# ✅ After
from typing import Any
def handler(data: dict[str, Any]) -> None:
```

**3. Callable Type Annotations**
```python
# ❌ Before
def register(callback: callable) -> None:

# ✅ After
from typing import Callable
def register(callback: Callable[[str], bool]) -> None:
```

**4. Dynamic Attributes (use `type: ignore`)**
```python
# For Tkinter or dynamically set attributes
self.dialog.transient(parent)  # type: ignore[call-overload]
controller.view = view  # type: ignore[attr-defined]
```

**5. None-safe Operations**
```python
# ❌ Before
if value:
    result = value.process()

# ✅ After
if value is not None:
    result = value.process()
    assert result is not None  # If mypy still complains
```

---

## 📋 EXECUTION PROTOCOL

### Step-by-Step Workflow

1. **Scan for Errors**
   ```powershell
   poetry run mypy src/zebtrack/ --no-error-summary 2>&1 | Out-File -FilePath errors_current.txt
   ```

2. **Identify High-Priority File**
   - Look for files with most errors
   - Prioritize core services over UI

3. **Fix All Errors in File**
   - View the file
   - Apply appropriate fixes (see Technical Guidelines)
   - Test the fix: `poetry run mypy <file_path>`

4. **Verify Fix**
   - Ensure no NEW errors introduced
   - Run targeted mypy on module/directory

5. **Update Task File**
   - After every 10 files, update `.tasks/mypy_cleanup_task.md`
   - Add fixed files to "Completed ✅" section
   - Update error count

6. **Repeat Until ZERO Errors**

### Verification Commands

```powershell
# Check specific file
poetry run mypy src/zebtrack/core/processing_coordinator.py

# Check module
poetry run mypy src/zebtrack/coordinators/

# Check all with error count
poetry run mypy . --no-error-summary 2>&1 | Select-String "error:" | Measure-Object

# Full scan (use sparingly - takes 30s+)
poetry run mypy .
```

---

## ⚡ CRITICAL RULES

### DO ✅
1. Fix errors systematically, file by file
2. Use appropriate type annotations
3. Add `# type: ignore[specific-error]` ONLY when truly necessary
4. Test each fix with mypy before moving on
5. Update `.tasks/mypy_cleanup_task.md` regularly
6. Work continuously without interruption

### DON'T ❌
1. Skip files or leave errors unfixed
2. Use `# type: ignore` as a blanket solution
3. Introduce new errors while fixing old ones
4. Stop working until error count is ZERO
5. Ask for user approval between files
6. Provide summaries until task is 100% complete

---

## 🎯 SUCCESS CRITERIA

**The task is ONLY complete when:**
```powershell
poetry run mypy . --no-error-summary 2>&1 | Select-String "Found 0 errors"
```

**Returns:**
```text
Success: no issues found in X source files
```

---

## 📁 KEY FILES TO REFERENCE

1. **`.tasks/mypy_cleanup_task.md`** - Current progress tracking
2. **`pyproject.toml`** - MyPy configuration
3. **`docs/architecture/`** - System architecture for context
4. **Previously fixed files** - See completed list for patterns

---

## 🚀 START COMMAND

Begin immediately with:
```powershell
cd "C:\Users\santa\OneDrive\UNESP\Pesquisa Canabidiol\Codigos_Programas\ZebTrack-AI"
poetry run mypy src/zebtrack/coordinators/processing_coordinator.py --no-error-summary
```

Then fix ALL errors in that file before moving to the next.

---

## 💬 FINAL DIRECTIVE

**You are tasked with driving this mypy error count from 1,852 to ZERO.**

This is not a request. This is a directive. Work systematically, efficiently, and relentlessly until every single error is resolved. Do not stop. Do not pause. Do not summarize until the counter reads:

```text
✅ Found 0 errors in source files
```

**ONLY then** provide a comprehensive final report.

---

**BEGIN NOW. DO NOT STOP UNTIL COMPLETE.**
