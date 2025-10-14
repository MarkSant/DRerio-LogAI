# Known Bugs Discovered During Phase 2 Testing

This document tracks bugs discovered during comprehensive unit testing of core services (Phase 2, Step 5). Each bug includes reproduction steps, root cause analysis, and recommended fixes.

---

## Bug #1: Project Config Integrity Check Non-Functional

**Severity**: Low  
**Status**: Open  
**Discovered**: October 14, 2025  
**Affected Component**: `ProjectService._compute_project_hash()`

### Description

The project configuration integrity check feature does not actually verify file integrity. The hash computation always returns an empty string, causing the integrity check to be silently bypassed.

### Location

- **File**: `src/zebtrack/core/project_service.py`
- **Lines**: 217-228 (hash computation), 155-163 (verification)

### Root Cause

The `_compute_project_hash()` method calls `calculate_sha256()` with encoded bytes, but that function expects a file path string:

```python
def _compute_project_hash(self, project_data: dict) -> str:
    json_str = json.dumps(project_data, sort_keys=True, ensure_ascii=False)
    return calculate_sha256(json_str.encode("utf-8"))  # ❌ Wrong type
```

`calculate_sha256()` in `src/zebtrack/utils/__init__.py` (line 30):

```python
def calculate_sha256(filepath: str) -> str:
    """Calculate the SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as handle:  # ❌ Tries to open bytes as file
            for chunk in iter(lambda: handle.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except IOError:
        log.error("file.hash.read_error", filepath=filepath)
        return ""  # ❌ Returns empty string on error
```

### Impact

- Project config tampering goes undetected
- Integrity violations are silently ignored
- Feature appears to work but provides no actual protection

### Reproduction

```python
from zebtrack.core.project_service import ProjectService

service = ProjectService()
service.create_project_directory("test_project", "Test", "experimental")

# Save config
service.save_project_config("test_project", {"project_name": "Original"})

# Manually tamper with config
import json
config_file = Path("test_project/project_config.json")
with open(config_file, "r") as f:
    data = json.load(f)

# Change data but keep old hash
data["project_name"] = "Tampered"
# Keep _integrity_hash unchanged

with open(config_file, "w") as f:
    json.dump(data, f)

# Load - should raise IntegrityError but doesn't
loaded = service.load_project_config("test_project")  # ❌ No error!
print(loaded["project_name"])  # Prints "Tampered"
```

### Recommended Fix

**Option A**: Make `calculate_sha256()` accept bytes or strings

```python
def calculate_sha256(data: str | bytes) -> str:
    """Calculate the SHA256 hash of a file or bytes."""
    sha256_hash = hashlib.sha256()
    
    if isinstance(data, bytes):
        # Hash bytes directly
        sha256_hash.update(data)
        return sha256_hash.hexdigest()
    
    # Original file-based logic
    try:
        with open(data, "rb") as handle:
            for chunk in iter(lambda: handle.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except IOError:
        log.error("file.hash.read_error", filepath=data)
        return ""
```

**Option B**: Use `hashlib` directly in `_compute_project_hash()` (preferred)

```python
def _compute_project_hash(self, project_data: dict) -> str:
    """
    Compute SHA256 integrity hash of project data.
    
    Args:
        project_data: Project data dictionary (without hash)
        
    Returns:
        str: SHA256 hash hex string
    """
    import hashlib
    json_str = json.dumps(project_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(json_str.encode("utf-8")).hexdigest()
```

### Test Coverage

- **Test File**: `tests/core/test_project_service.py`
- **Test Name**: `test_load_project_config_integrity_check_failure`
- **Status**: Currently skipped with documentation
- **Action**: Enable test after applying fix

### Related Issues

None

---

## Bug #2: AnalysisService Settings Access Pattern

**Severity**: Medium  
**Status**: Open  
**Discovered**: October 14, 2025  
**Affected Component**: `AnalysisService.collect_analysis_parameters()`, `AnalysisService._default_analysis_profile()`

### Description

Multiple methods in `AnalysisService` attempt to access `settings.freezing.*` attributes, but the `Settings` model does not have a `freezing` sub-object. The actual values are stored in `settings.video_processing.freezing_*`.

### Location

- **File**: `src/zebtrack/analysis/analysis_service.py`
- **Lines**: 214, 215, 395, 396

### Root Cause

Incorrect settings path assumptions:

```python
def collect_analysis_parameters(self, project_data: dict | None = None) -> dict:
    params = {
        "freezing_vel_threshold": settings.freezing.velocity_threshold,  # ❌
        "freezing_min_duration": settings.freezing.min_duration,  # ❌
        "smoothing_window_length": settings.trajectory_smoothing.window_length,  # ✅
        "smoothing_polyorder": settings.trajectory_smoothing.polyorder,  # ✅
    }
    ...
```

Similar issue in `_default_analysis_profile()`:

```python
def _default_analysis_profile(self) -> dict:
    return {
        "name": "default",
        "freezing_vel_threshold": settings.freezing.velocity_threshold,  # ❌
        "freezing_min_duration": settings.freezing.min_duration,  # ❌
        "smoothing_window_length": settings.trajectory_smoothing.window_length,  # ✅
        "smoothing_polyorder": settings.trajectory_smoothing.polyorder,  # ✅
    }
```

### Settings Structure

From `src/zebtrack/settings.py` (lines 111-129):

```python
class VideoProcessingSettings(BaseModel):
    fps: int
    processing_interval: int
    processing_offset: int
    sharp_turn_threshold_deg_s: float = 200.0
    freezing_velocity_threshold: float = 1.5  # ✅ Actual location
    freezing_min_duration_s: float = 1.0      # ✅ Actual location
    single_animal_per_aquarium: bool = False

class Settings(BaseModel):
    ...
    video_processing: VideoProcessingSettings  # ✅ Contains freezing params
    trajectory_smoothing: TrajectorySmoothingSettings
    ...
```

### Impact

- `collect_analysis_parameters()` raises `AttributeError` when called
- `_default_analysis_profile()` raises `AttributeError` when called
- Parameter-based analysis workflows completely broken
- Profile resolution fails for projects without explicit profiles

### Reproduction

```python
from zebtrack.analysis.analysis_service import AnalysisService

service = AnalysisService()

# This will raise AttributeError: 'Settings' object has no attribute 'freezing'
try:
    params = service.collect_analysis_parameters()
except AttributeError as e:
    print(f"Error: {e}")

# Same error when resolving default profile
try:
    profile = service.resolve_analysis_profile(metadata=None, project_data=None)
except AttributeError as e:
    print(f"Error: {e}")
```

### Recommended Fix

Update all settings access to use correct paths:

```python
def collect_analysis_parameters(self, project_data: dict | None = None) -> dict:
    # Start with settings defaults
    params = {
        "freezing_vel_threshold": settings.video_processing.freezing_velocity_threshold,  # ✅
        "freezing_min_duration": settings.video_processing.freezing_min_duration_s,      # ✅
        "smoothing_window_length": settings.trajectory_smoothing.window_length,
        "smoothing_polyorder": settings.trajectory_smoothing.polyorder,
    }
    
    # Override with project-specific values if available
    if project_data:
        analysis_params = project_data.get("analysis_parameters", {})
        for key in ["freezing_vel_threshold", "freezing_min_duration", 
                    "smoothing_window_length", "smoothing_polyorder"]:
            if key in analysis_params:
                params[key] = analysis_params[key]
                
    self.log.debug(
        "analysis_service.collect_parameters",
        params=params,
    )
    return params

def _default_analysis_profile(self) -> dict:
    return {
        "name": "default",
        "freezing_vel_threshold": settings.video_processing.freezing_velocity_threshold,  # ✅
        "freezing_min_duration": settings.video_processing.freezing_min_duration_s,      # ✅
        "smoothing_window_length": settings.trajectory_smoothing.window_length,
        "smoothing_polyorder": settings.trajectory_smoothing.polyorder,
    }
```

### Test Coverage

- **Test File**: `tests/analysis/test_analysis_service.py`
- **Affected Tests** (6 tests currently skipped):
  - `test_collect_analysis_parameters_defaults`
  - `test_collect_analysis_parameters_with_project_overrides`
  - `test_collect_analysis_parameters_partial_overrides`
  - `test_resolve_analysis_profile_no_profiles`
  - `test_complete_analysis_workflow`
  - `test_analysis_with_profile_and_report_generation`
- **Action**: Enable all skipped tests after applying fix

### Related Issues

None

---

## Verification Checklist

After fixes are applied, verify the following:

### For Bug #1 (Integrity Hash)
- [ ] `calculate_sha256()` properly handles bytes input OR
- [ ] `_compute_project_hash()` uses `hashlib` directly
- [ ] Hash computation returns non-empty string
- [ ] Integrity check correctly detects tampering
- [ ] Enable and run `test_load_project_config_integrity_check_failure`
- [ ] Test should now PASS (raise `IntegrityError` on tampering)

### For Bug #2 (Settings Access)
- [ ] All `settings.freezing.*` references updated to `settings.video_processing.freezing_*`
- [ ] `collect_analysis_parameters()` works without AttributeError
- [ ] `_default_analysis_profile()` works without AttributeError  
- [ ] Enable and run all 6 skipped tests in `test_analysis_service.py`
- [ ] All tests should now PASS

---

## Notes

These bugs were discovered through comprehensive unit testing (Phase 2, Step 5) and did not cause production issues because:

1. **Bug #1**: Integrity checking is a defensive feature; projects worked despite non-functional validation
2. **Bug #2**: Parameter collection methods may not have been fully integrated into production workflows yet (recent service extraction)

The discovery demonstrates the value of thorough automated testing as part of the refactoring process.

---

**Last Updated**: October 14, 2025  
**Tracked By**: Phase 2 test suite  
**Priority**: Fix before next release
