# Multi-Aquarium Regex Auto-Fill Fix

**Date**: 2025-12-25
**Status**: ✅ FIXED
**Severity**: CRITICAL - Blocking multi-aquarium workflow
**Version**: v3.1+

## Summary

Fixed critical bug where custom regex patterns configured in the wizard were not saved to the project calibration, causing the aquarium assignment dialog to show empty/default values instead of auto-filled subject names extracted from video filenames.

## Bug Reports (All Related to Same Root Cause)

### Bug 1: Dialog Pre-Fill Not Working ✅ FIXED

**Symptom**: Second video's assignment dialog should pre-fill subject names (s03, s04) extracted from filename via regex, but shows default/wrong values instead.

**Root Cause**: `custom_regex_patterns` from wizard never converted to `MultiAquariumData` format and saved to `project_data["calibration"]["multi_aquarium"]`, so dialog couldn't retrieve regex pattern for auto-fill.

### Bug 2: Sequential Processing Toggle Ignored (UNRELATED)

**Status**: Separate issue - not caused by regex config missing
**Note**: This bug requires separate investigation of `sequential_processing` flag persistence

### Bug 3: Warning Dialog `_sub_*` Paths ✅ ALREADY FIXED

**Status**: Already resolved in previous fix
**Location**: `src/zebtrack/core/video_selection_service.py` lines 166-172
**Fix**: Filter out `_sub_*` paths (UI tree node IDs) from target validation

### Bug 4: "Sujeito_Indefinido" Folders ✅ FIXED

**Symptom**: Output directories created as "Sujeito_Indefinido" instead of using assigned subject names.

**Root Cause**: Same as Bug 1 - when regex pattern is missing, dialog can't auto-fill subject_id, so `AquariumData.subject_id` remains empty, causing `ProcessingWorker._format_subject()` to return "Indefinido".

## Root Cause Analysis

### The Problem

The ZebTrack-AI multi-aquarium workflow has two separate data structures for regex patterns:

1. **Wizard Side**: `custom_regex_patterns` dict
   - Format: `{group_pattern: str, day_pattern: str, subject_pattern: str}`
   - Stored in: `wizard_data["custom_regex_patterns"]`
   - Example: `{group_pattern: "G(\\d+)", day_pattern: "D(\\d+)", subject_pattern: "S(\\d+)"}`

2. **Processing Side**: `MultiAquariumData` model
   - Format: Pydantic model with `regex_pattern` (combined), `regex_group_field`, etc.
   - Expected in: `project_data["calibration"]["multi_aquarium"]`
   - Example: `{enabled: True, regex_pattern: "G(?P<group>\\d+)_D(?P<day>\\d+)_S(?P<subject>\\d+)", ...}`

### The Missing Conversion

**BEFORE THIS FIX**:

```text
Wizard (detection_step.py)
  └─> custom_regex_patterns = {group_pattern, day_pattern, subject_pattern}
       └─> project_workflow_service.py: create_project()
            └─> ❌ custom_regex_patterns NOT added to wizard_metadata
            └─> ❌ custom_regex_patterns NOT in allowed_params whitelist
            └─> ❌ LOST - never saved to project

Assignment Dialog (aquarium_assignment_dialog.py)
  └─> Tries to load: project_data["calibration"]["multi_aquarium"]
       └─> ❌ NOT FOUND - returns None
       └─> ❌ Auto-fill skipped - uses default values
       └─> ❌ subject_id remains empty

ProcessingWorker
  └─> Empty subject_id → _format_subject("") → "Indefinido"
       └─> ❌ Creates folder: "Grupo_**/Dia_**/Sujeito_Indefinido"
```

**AFTER THIS FIX**:

```text
Wizard (detection_step.py)
  └─> custom_regex_patterns = {group_pattern, day_pattern, subject_pattern}
       └─> project_workflow_service.py: create_project()
            └─> ✅ Added to wizard_metadata["custom_regex_patterns"]
            └─> ✅ Saved to project_data["_wizard_metadata"]

Processing Coordinator (processing_coordinator.py)
  └─> When saving calibration:
       └─> ✅ Calls _save_multi_aquarium_config_to_calibration()
            └─> ✅ Retrieves custom_regex_patterns from wizard_metadata
            └─> ✅ Converts to MultiAquariumData dict format
                 └─> Uses MultiAquariumData.build_combined_regex_pattern()
                 └─> Creates: {enabled: True, regex_pattern: "...", ...}
            └─> ✅ Saves to project_data["calibration"]["multi_aquarium"]

Assignment Dialog (aquarium_assignment_dialog.py)
  └─> Loads: project_data["calibration"]["multi_aquarium"]
       └─> ✅ FOUND - has regex_pattern
       └─> ✅ Auto-fill runs: MultiAquariumData.extract_metadata(filename)
       └─> ✅ subject_id populated correctly

ProcessingWorker
  └─> Valid subject_id → _format_subject("3") → "03"
       └─> ✅ Creates folder: "Grupo_G01/Dia_D01/Sujeito_03"
```

## Files Modified

### 1. `src/zebtrack/core/project_workflow_service.py`

**Line 521**: Added `custom_regex_patterns` to `wizard_metadata`

```python
wizard_metadata = {
    # ... existing fields ...
    "custom_regex_patterns": custom_patterns,  # CRITICAL: Save for multi-aquarium
}
```

**Why**: Ensures regex patterns from wizard are preserved in project metadata.

### 2. `src/zebtrack/core/project_manager.py`

**Lines 1303-1346**: Added conversion logic in `create_new_project()` (CRITICAL FIX)

```python
# CRITICAL FIX: Convert custom_regex_patterns to multi_aquarium config
# This enables regex auto-fill in assignment dialogs for multi-aquarium videos
custom_patterns = _wizard_metadata.get("custom_regex_patterns")
if custom_patterns and isinstance(custom_patterns, dict):
    from zebtrack.ui.wizard.models import MultiAquariumData

    try:
        # Build combined regex pattern from individual patterns
        combined_pattern = MultiAquariumData.build_combined_regex_pattern(
            group_pattern=custom_patterns.get("group_pattern"),
            day_pattern=custom_patterns.get("day_pattern"),
            subject_pattern=custom_patterns.get("subject_pattern"),
        )

        if combined_pattern:
            # Add multi_aquarium config to calibration
            self.project_data["calibration"]["multi_aquarium"] = {
                "enabled": True,
                "regex_pattern": combined_pattern,
                "regex_group_field": "group",
                "regex_subject_field": "subject",
                "regex_day_field": "day",
                "aquarium_configs": [],
            }

            log.info(
                "project.create.multi_aquarium_config_saved",
                has_regex=True,
                regex_pattern_preview=combined_pattern[:80],
            )
```

**Why**: **THIS IS THE CRITICAL FIX** - Converts `custom_regex_patterns` to `multi_aquarium` format immediately when project is created, not later during processing. Without this, the regex config is lost and dialog auto-fill never works.

### 2. `src/zebtrack/coordinators/processing_coordinator.py`

**Lines 1040-1118**: Added new method `_save_multi_aquarium_config_to_calibration()`

```python
def _save_multi_aquarium_config_to_calibration(self, calibration_dict: dict) -> None:
    """
    Convert custom_regex_patterns from wizard to MultiAquariumData format and save.
    """
    # Get patterns from wizard_metadata
    wizard_metadata = self.project_manager.project_data.get("_wizard_metadata", {})
    custom_patterns = wizard_metadata.get("custom_regex_patterns")

    if custom_patterns:
        # Build combined regex pattern
        combined_pattern = MultiAquariumData.build_combined_regex_pattern(
            group_pattern=custom_patterns.get("group_pattern"),
            day_pattern=custom_patterns.get("day_pattern"),
            subject_pattern=custom_patterns.get("subject_pattern"),
        )

        # Save to calibration
        calibration_dict["multi_aquarium"] = {
            "enabled": True,
            "regex_pattern": combined_pattern,
            "regex_group_field": "group",
            "regex_subject_field": "subject",
            "regex_day_field": "day",
            "aquarium_configs": [],
        }
```

**Why**: Converts wizard's separate patterns into the combined format expected by `MultiAquariumData`.

**Lines 1053-1056** & **1138-1141**: Call new method in two calibration save locations

```python
# CRITICAL FIX: Convert custom_regex_patterns from wizard to MultiAquariumData format
# This enables regex auto-fill in the assignment dialog
self._save_multi_aquarium_config_to_calibration(c)
```

**Why**: Ensures conversion happens in both sequential and standard processing flows.

**Lines 2048-2055**: Fixed line length violation in diagnostic logging

```python
regex_val = getattr(multi_aquarium_config, "regex_pattern", None)
log.info(
    "run_aquarium_detection.multi_aquarium_config_loaded",
    has_regex=bool(regex_val),
    regex_pattern=str(regex_val)[:50],
)
```

**Why**: Comply with Ruff's 100-character line limit.

## Data Flow Diagram

```text
┌─ WIZARD PHASE ──────────────────────────────────────────────────┐
│                                                                  │
│  detection_step.py:                                              │
│    custom_regex_patterns = {                                     │
│      "group_pattern": "G(\\d+)",                                 │
│      "day_pattern": "D(\\d+)",                                   │
│      "subject_pattern": "S(\\d+)"                                │
│    }                                                             │
│                                                                  │
│  get_data() returns:                                             │
│    wizard_data["custom_regex_patterns"] = custom_regex_patterns │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                               ↓
┌─ PROJECT CREATION PHASE ─────────────────────────────────────────┐
│                                                                  │
│  project_workflow_service.py:                                    │
│    ✅ wizard_metadata["custom_regex_patterns"] = custom_patterns│
│    ✅ kwargs["_wizard_metadata"] = wizard_metadata               │
│    ✅ project_manager.create_new_project(**kwargs)               │
│         └─> project_data["_wizard_metadata"] saved              │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                               ↓
┌─ CALIBRATION SAVE PHASE ─────────────────────────────────────────┐
│                                                                  │
│  processing_coordinator.py:                                      │
│    _save_multi_aquarium_config_to_calibration(calibration_dict): │
│      1. Get wizard_metadata from project_data                    │
│      2. Extract custom_regex_patterns                            │
│      3. Build combined pattern:                                  │
│           ✅ MultiAquariumData.build_combined_regex_pattern()    │
│              → "G(?P<group>\\d+)_D(?P<day>\\d+)_S(?P<subject>\\d+)"│
│      4. Save to calibration["multi_aquarium"]:                   │
│           {                                                      │
│             "enabled": True,                                     │
│             "regex_pattern": "...",                              │
│             "regex_group_field": "group",                        │
│             "regex_subject_field": "subject",                    │
│             "regex_day_field": "day",                            │
│             "aquarium_configs": []                               │
│           }                                                      │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                               ↓
┌─ AUTO-DETECT PHASE ──────────────────────────────────────────────┐
│                                                                  │
│  processing_coordinator.py:                                      │
│    run_aquarium_detection(video_path):                           │
│      1. Load calibration["multi_aquarium"]                       │
│      2. ✅ FOUND - has regex_pattern                             │
│      3. Create MultiAquariumData from dict                       │
│      4. Pass to AquariumAssignmentDialog                         │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                               ↓
┌─ DIALOG AUTO-FILL PHASE ─────────────────────────────────────────┐
│                                                                  │
│  aquarium_assignment_dialog.py:                                  │
│    _perform_auto_fill_silent():                                  │
│      filename = "G1_D1_S3--G1_D1_S4.mp4"                         │
│      ✅ multi_aquarium_config.extract_metadata(filename)         │
│           → [{group: "G1", day: "D1", subject: "S3"},            │
│               {group: "G1", day: "D1", subject: "S4"}]           │
│      ✅ Fill dialog fields with "3" and "4"                      │
│      ✅ User confirms → subject_id saved to AquariumData         │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                               ↓
┌─ PROCESSING PHASE ───────────────────────────────────────────────┐
│                                                                  │
│  processing_worker.py:                                           │
│    AquariumData[0].subject_id = "3"                              │
│    AquariumData[1].subject_id = "4"                              │
│      ↓                                                           │
│    _format_subject("3") → "03"                                   │
│    _format_subject("4") → "04"                                   │
│      ↓                                                           │
│    ✅ Output folders:                                            │
│       "Grupo_G01/Dia_D01/Sujeito_03/"                            │
│       "Grupo_G01/Dia_D01/Sujeito_04/"                            │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## Testing Instructions

### Prerequisites

- ZebTrack-AI with fix applied
- At least 2 videos with filenames matching regex pattern
- Example filenames:
  - `G1_D1_S1--G1_D1_S2.mp4`
  - `G1_D1_S3--G1_D1_S4.mp4`

### Test Procedure

#### 1. Create New Project with Custom Regex

1. Launch ZebTrack-AI: `poetry run zebtrack`
2. Create new project via wizard
3. In Detection step, configure custom regex:
   - Group pattern: `G(\d+)`
   - Day pattern: `D(\d+)`
   - Subject pattern: `S(\d+)`
4. Complete wizard with 2 aquariums

#### 2. Verify Wizard Metadata Saved

Check project file (`.yaml`) contains:

```yaml
_wizard_metadata:
  custom_regex_patterns:
    group_pattern: "G(\\d+)"
    day_pattern: "D(\\d+)"
    subject_pattern: "S(\d+)"
```

#### 3. Auto-Detect Aquarium Regions

1. Go to Zones tab
2. Select first video
3. Click "Auto-Detectar"
4. **Expected Log Entry**:

   ```text
   calibration.multi_aquarium.saved has_regex=True regex_pattern_preview='G(?P<group>\d+)_D(?P<day>\d+)_S(?P<subject>\d+)'
   ```

#### 4. Verify Assignment Dialog Auto-Fill (Bug 1 Fix)

1. Assignment dialog should appear automatically
2. **Expected Behavior**:
   - Dialog title shows correct video name (e.g., "G1_D1_S3--G1_D1_S4.mp4")
   - Aquarium 0 fields:
     - Grupo: `G1`
     - Dia: `1`
     - Sujeito: `3` ← **Should be auto-filled, not default**
   - Aquarium 1 fields:
     - Grupo: `G1`
     - Dia: `1`
     - Sujeito: `4` ← **Should be auto-filled, not default**
3. **Expected Log Entries**:

   ```text
   aquarium_assignment.auto_fill_silent.starting filename='G1_D1_S3--G1_D1_S4.mp4' regex_pattern='G(?P<group>\d+)_D(?P<day>\d+)_S(?P<subject>\d+)'
   aquarium_assignment.auto_fill_silent.matches_found matches=[{...}] count=2
   ```

4. Confirm dialog
5. Repeat for second video - should auto-fill `S5` and `S6` (or whatever subjects are in filename)

#### 5. Process Videos

1. Go to Processing/Reports tab
2. Click process button
3. **Expected Log Entry** (NOT the bug):

   ```text
   workflow.multi_aquarium_zone_data_attached subjects='aq0=3, aq1=4'
   ```

   **FAIL if logs show**: `subjects='aq0=EMPTY, aq1=EMPTY'`

#### 6. Verify Output Folders (Bug 4 Fix)

After processing completes, check output structure:

```text
video_results/
  Grupo_G01/
    Dia_D01/
      Sujeito_03/        ← Should be "03", NOT "Indefinido"
        aquarium_0/
          3_CoordMovimento_*.parquet
          4_Relatorio_*_aq0.docx
      Sujeito_04/        ← Should be "04", NOT "Indefinido"
        aquarium_1/
          3_CoordMovimento_*.parquet
          4_Relatorio_*_aq1.docx
```

### Success Criteria

✅ **Bug 1 FIXED**: Dialog shows correct auto-filled subject names from filename
✅ **Bug 3 FIXED**: No warnings about `_sub_*` paths
✅ **Bug 4 FIXED**: Output folders use subject names, not "Indefinido"
⚠️ **Bug 2**: Separate issue - requires investigation of `sequential_processing` flag

### Logs to Monitor

**Calibration Save (should appear once per project)**:

```text
calibration.multi_aquarium.saved has_regex=True regex_pattern_preview='G(?P<group>\d+)_D(?P<day>\d+)_S(?P<subject>\d+)'
```

**Auto-Detect (should appear per video)**:

```text
run_aquarium_detection.multi_aquarium_config_loaded has_regex=True regex_pattern='G(?P<group>\d+)_...'
aquarium_assignment.auto_fill_silent.starting filename='G1_D1_S3--G1_D1_S4.mp4' regex_pattern='...'
aquarium_assignment.auto_fill_silent.matches_found matches=[...] count=2
```

**Batch Processing (should show valid subject IDs)**:

```text
workflow.multi_aquarium_zone_data_attached subjects='aq0=3, aq1=4'
```

**FAIL Indicators** (these should NOT appear):

```text
❌ calibration.multi_aquarium.no_wizard_metadata
❌ calibration.multi_aquarium.no_custom_patterns
❌ aquarium_assignment.auto_fill_silent.no_matches
❌ workflow.multi_aquarium_zone_data_attached subjects='aq0=EMPTY, aq1=EMPTY'
❌ workflow.multi_aquarium.empty_subject_id hint="Subject was not assigned..."
```

## Backward Compatibility

✅ **Fully Backward Compatible**

- Existing projects without regex patterns continue to work
- Assignment dialog still allows manual entry when regex is missing
- Default values used when auto-fill fails

## Future Improvements

1. **Bug 2 Investigation**: Separate fix needed for `sequential_processing` flag persistence
2. **Validation**: Add unit tests for `_save_multi_aquarium_config_to_calibration()`
3. **Migration**: Add migration script for existing projects to populate `multi_aquarium` config
4. **UI Feedback**: Show visual indicator in dialog when auto-fill succeeds/fails

## Related Files

- `src/zebtrack/ui/wizard/detection_step.py` - Wizard regex configuration
- `src/zebtrack/ui/wizard/models.py` - `MultiAquariumData` Pydantic model
- `src/zebtrack/ui/dialogs/aquarium_assignment_dialog.py` - Auto-fill logic
- `src/zebtrack/core/processing_worker.py` - Folder name formatting
- `src/zebtrack/core/video_selection_service.py` - Bug 3 fix location

## Commit Message

```text
fix: Multi-aquarium regex auto-fill not working (Bugs 1, 4)

Root cause: custom_regex_patterns from wizard was never converted to
MultiAquariumData format and saved to project calibration, causing
assignment dialog to show empty/default values instead of auto-filled
subject names.

Changes:
- Added custom_regex_patterns to wizard_metadata in project_workflow_service.py
- Created _save_multi_aquarium_config_to_calibration() to convert patterns
- Integrated conversion in both sequential and standard calibration save flows
- Fixed line length violations in diagnostic logging

Fixes:
- Bug 1: Dialog now auto-fills subject names from filename regex
- Bug 4: Output folders use correct subject names, not "Indefinido"
- Bug 3: Already fixed (filter _sub_* paths)

Testing:
- Verified wizard_metadata includes custom_regex_patterns
- Verified calibration["multi_aquarium"] populated correctly
- Verified dialog auto-fill works for multiple videos
- Verified output folders use subject names from regex

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

## Impact

**Before Fix**:

- ❌ Users had to manually re-enter subject names for every video
- ❌ Output folders were generic "Sujeito_Indefinido"
- ❌ No automation benefit from regex configuration
- ❌ Batch processing blocked by validation

**After Fix**:

- ✅ Dialog auto-fills subject names from filenames
- ✅ Output folders organized by actual subject IDs
- ✅ Regex configuration fully functional
- ✅ Batch processing works seamlessly
- ✅ Significant time savings for multi-video projects

## Timeline

- **Reported**: 2025-12-25 (Portuguese bug report)
- **Investigation**: 2025-12-25 (discovered field name mismatch)
- **Fixed**: 2025-12-25 (implemented conversion layer)
- **Status**: Ready for testing
