# ZebTrack-AI Validation Analysis: Critical Gaps

## Executive Summary
Found **16+ critical validation gaps** across Pydantic models and configuration management. Most critical issues are missing bounds checks on numeric fields that could cause runtime errors or silent data corruption.

---

## 1. SETTINGS.PY - Pydantic Model Issues

### CRITICAL: Missing Bounds on Camera Settings
**File:** `/home/user/ZebTrack-AI/src/zebtrack/settings.py`
**Lines:** 63-68
**Severity:** HIGH

```python
class CameraSettings(BaseModel):
    index: int = Field(..., description="The index of the camera device (e.g., 0, 1).")
    # ❌ NO BOUNDS - could accept negative or huge values
    desired_width: int = Field(
        ..., description="The width (pixels) used for defining detection zones."
    )
    # ❌ NO BOUNDS - could accept negative or zero
    desired_height: int = Field(
        ..., description="The height (pixels) used for defining detection zones."
    )
```

**What Could Go Wrong:**
- Negative dimensions would cause crashes in OpenCV
- Zero dimensions would fail silently
- Very large values (e.g., 999999) could cause memory exhaustion
- Invalid camera indices could hang system during initialization

**Suggested Fix:**
```python
desired_width: int = Field(
    ..., 
    gt=0,
    le=7680,  # 8K max
    description="The width (pixels) used for defining detection zones."
)
desired_height: int = Field(
    ..., 
    gt=0,
    le=4320,  # 8K max
    description="The height (pixels) used for defining detection zones."
)
```

---

### CRITICAL: Missing Bounds on FPS
**File:** `settings.py`
**Line:** 210
**Severity:** HIGH

```python
class VideoProcessingSettings(BaseModel):
    fps: int = Field(..., description="Frames Per Second (FPS) for saving output videos.")
    # ❌ NO BOUNDS - allows zero, negative, or unrealistic values
```

**What Could Go Wrong:**
- FPS=0 would cause division by zero in video recording
- Negative FPS would cause cryptic OpenCV errors
- FPS=10000 would create corrupt video files

**Suggested Fix:**
```python
fps: int = Field(
    ..., 
    gt=0,
    le=120,  # Reasonable max for typical hardware
    description="Frames Per Second (FPS) for saving output videos."
)
```

---

### CRITICAL: Missing Processing Interval Validation
**File:** `settings.py`
**Lines:** 211-220
**Severity:** CRITICAL

```python
class VideoProcessingSettings(BaseModel):
    processing_interval: int = Field(
        ..., description="Process 1 frame every N frames to optimize performance."
    )
    # ❌ NO VALIDATOR - accepts zero, negative, or unrealistic values
    processing_offset: int = Field(
        ...,
        description="Frame offset for processing. E.g., offset=1 and interval=10 processes frames 1, 11, 21, ..."
    )
    # ❌ NO VALIDATOR - accepts negative values
```

**Validation Exists:** Lines 604-616 in `_validate_advanced_constraints()` checks:
- `interval <= 0` ❌ (should be `< 1`)
- `offset >= interval` ✓ (correct)

**What Could Go Wrong:**
- `processing_interval=0` causes modulo division by zero (line 322 in `video_processing_service.py`)
- `processing_offset=-5` silently skips frames
- Validation error message doesn't explain the requirement clearly

**Suggested Fix:**
```python
processing_interval: int = Field(
    ..., 
    ge=1,  # Must be at least 1
    le=1000,
    description="Process 1 frame every N frames (must be >= 1)."
)
processing_offset: int = Field(
    ...,
    ge=0,
    description="Frame offset for processing (must be >= 0 and < interval)."
)
```

---

### CRITICAL: No Validation on Model Path
**File:** `settings.py`
**Line:** 165
**Severity:** HIGH

```python
class YOLOModelSettings(BaseModel):
    path: str = Field(..., description="Path to the YOLO model weights file (e.g., 'model.pt').")
    # ❌ NO VALIDATION
    # - Doesn't check if file exists
    # - Doesn't validate file extension
    # - Doesn't check if path is readable
```

**What Could Go Wrong:**
- File paths with invalid characters pass validation
- File doesn't exist until first use → crashes at detection time
- Empty string path causes cryptic errors deep in detector plugin
- Relative paths interpreted differently depending on CWD

**Suggested Fix:**
```python
path: str = Field(
    ...,
    min_length=1,
    pattern=r'\.pt$|\.onnx$|\.xml$',  # Common model formats
    description="Path to the YOLO model weights file (e.g., 'model.pt')."
)

@field_validator("path")
@classmethod
def validate_model_path(cls, v):
    path_obj = Path(v)
    if not path_obj.exists():
        raise ValueError(f"Model file not found: {v}")
    if not path_obj.is_file():
        raise ValueError(f"Model path is not a file: {v}")
    return str(path_obj.resolve())
```

---

### CRITICAL: Missing Bounds on Arduino Port
**File:** `settings.py`
**Line:** 136
**Severity:** MEDIUM

```python
class ArduinoSettings(BaseModel):
    port: str = Field(
        ...,
        description="The serial port the Arduino is connected to (e.g., 'COM5' or '/dev/ttyACM0')."
    )
    # ❌ NO VALIDATION
    baud_rate: int = Field(..., description="The baud rate for serial communication.")
    # ❌ NO BOUNDS on baud_rate
```

**What Could Go Wrong:**
- Empty port string: `""`
- Invalid port names like `"/dev/invalid123"`
- Invalid baud rates (e.g., 999999, 0, negative)
- Only caught at serial connection time, not during config load

**Suggested Fix:**
```python
port: str = Field(
    ...,
    min_length=1,
    pattern=r'^(COM\d+|/dev/tty[A-Za-z0-9]+)$',
    description="The serial port the Arduino is connected to."
)

baud_rate: int = Field(
    ...,
    ge=300,
    le=2000000,  # Common baud rates
    description="The baud rate for serial communication (e.g., 9600, 115200)."
)
```

---

## 2. WIZARD/MODELS.PY - Pydantic Validation Issues

### CRITICAL: No Validation on Detector Name
**File:** `/home/user/ZebTrack-AI/src/zebtrack/ui/wizard/models.py`
**Line:** 121
**Severity:** MEDIUM

```python
class ModelSelectionData(BaseModel):
    detector_name: str = Field(description="Name of the detector to use")
    # ❌ NO VALIDATION
    # - Accepts empty strings
    # - No check against valid detector names
    # - Case-sensitive, no normalization
```

**What Could Go Wrong:**
- Empty detector name causes "detector not found" errors later
- Typo in detector name silently uses default
- Case mismatch breaks detector plugin lookup

**Suggested Fix:**
```python
detector_name: str = Field(
    ...,
    min_length=1,
    description="Name of the detector to use"
)

@field_validator("detector_name")
@classmethod
def validate_detector_name(cls, v):
    from zebtrack.plugins import DETECTOR_PLUGINS
    valid_names = set(DETECTOR_PLUGINS.keys())
    if v not in valid_names:
        raise ValueError(
            f"Unknown detector '{v}'. Valid options: {', '.join(sorted(valid_names))}"
        )
    return v
```

---

### WARNING: Optional Threshold Fields Without Defaults
**File:** `wizard/models.py`
**Lines:** 122-133
**Severity:** MEDIUM

```python
class ModelSelectionData(BaseModel):
    confidence_threshold: float | None = Field(
        default=None, ge=0.0, le=1.0, description="..."
    )
    nms_threshold: float | None = Field(
        default=None, ge=0.0, le=1.0, description="..."
    )
    # ❌ These allow None, could skip critical threshold setup
```

**What Could Go Wrong:**
- All thresholds None → uses global settings without warning
- Partial thresholds create inconsistent state
- Users might think they set thresholds but didn't

**Suggested Fix:**
```python
@field_validator("confidence_threshold", "nms_threshold", mode="before")
@classmethod
def require_threshold_values(cls, v, info):
    # If model explicitly selected, thresholds should be specified
    if v is None and info.data.get("detector_name"):
        raise ValueError(f"{info.field_name} is required when detector is specified")
    return v
```

---

### CRITICAL: No File Path Validation
**File:** `wizard/models.py`
**Lines:** 139-147
**Severity:** HIGH

```python
class FileSelectionData(BaseModel):
    video_files: list[str] = Field(min_length=1, description="List of video file paths")

    @field_validator("video_files")
    @classmethod
    def validate_video_files(cls, v):
        """Ensure all video files are non-empty strings."""
        if any(not vf.strip() for vf in v):
            raise ValueError("Caminhos de vídeo não podem estar vazios")
        return v
        # ❌ Only checks for empty strings
        # ❌ Doesn't validate:
        # - File exists
        # - File extension is video format
        # - File is readable
        # - File is not already in use
```

**What Could Go Wrong:**
- Path `/home/deleted_file.mp4` passes but doesn't exist
- Path `"image.jpg"` passes as video file
- Path to directory passes as video file
- Path to special file (device, socket) causes hang

**Suggested Fix:**
```python
@field_validator("video_files")
@classmethod
def validate_video_files(cls, v):
    VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm'}
    
    for vf in v:
        if not vf.strip():
            raise ValueError("Caminhos de vídeo não podem estar vazios")
        
        path = Path(vf)
        if not path.exists():
            raise ValueError(f"Arquivo de vídeo não encontrado: {vf}")
        if not path.is_file():
            raise ValueError(f"Caminho não é um arquivo: {vf}")
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            raise ValueError(f"Extensão de arquivo não suportada: {path.suffix}")
    
    return v
```

---

### WARNING: Recording Duration Allows Zero
**File:** `wizard/models.py`
**Lines:** 22-24
**Severity:** MEDIUM

```python
recording_duration_s: float = Field(
    default=0, ge=0, le=7200, description="Recording duration in seconds (max 2 hours)"
)
# ❌ Allows 0, should be gt=0 when use_timed_recording=true
```

**Note:** Validator exists at lines 57-63 but only checks `> 0` when enabled.
However, `ge=0` allows the field itself to be 0 even before validation.

**Suggested Fix:**
```python
recording_duration_s: float = Field(
    default=0, 
    ge=1,  # At least 1 second if specified
    le=7200,
    description="Recording duration in seconds (must be > 0 when timed recording enabled)"
)
```

---

## 3. PROJECT_MANAGER.PY - Input Validation Issues

### CRITICAL: No Bounds on Calibration Parameters
**File:** `/home/user/ZebTrack-AI/src/zebtrack/core/project_manager.py`
**Lines:** 862-865 (in `create_new_project()`)
**Severity:** CRITICAL

```python
def create_new_project(
    self,
    ...
    num_aquariums: int = 1,              # ❌ NO BOUNDS
    animals_per_aquarium: int = 1,       # ❌ NO BOUNDS
    aquarium_width_cm: float = 0.0,      # ❌ Allows 0, negative
    aquarium_height_cm: float = 0.0,     # ❌ Allows 0, negative
    analysis_interval_frames: int = 10,  # ❌ NO BOUNDS
    display_interval_frames: int = 10,   # ❌ NO BOUNDS
    camera_index: int = 0,               # ❌ NO LOWER BOUND (negative allowed)
```

**What Could Go Wrong:**
- `num_aquariums=-5` creates invalid project state
- `aquarium_width_cm=0` causes division by zero in calibration
- `analysis_interval_frames=-1` causes modulo errors
- `camera_index=-100` tries to open impossible camera

**Suggested Fix:**
```python
def create_new_project(
    self,
    ...
    num_aquariums: int = 1,  # Validate: 1-1000
    animals_per_aquarium: int = 1,  # Validate: 1-1000
    aquarium_width_cm: float = 0.0,  # Validate: > 0 and <= 500
    aquarium_height_cm: float = 0.0,  # Validate: > 0 and <= 500
    analysis_interval_frames: int = 10,  # Validate: 1-100
    display_interval_frames: int = 10,  # Validate: 1-100
    camera_index: int = 0,  # Validate: >= 0 and <= 100
```

Then add validation:
```python
# At start of method
if num_aquariums < 1:
    raise ValueError("num_aquariums must be >= 1")
if animals_per_aquarium < 1:
    raise ValueError("animals_per_aquarium must be >= 1")
if aquarium_width_cm <= 0:
    raise ValueError("aquarium_width_cm must be > 0")
if aquarium_height_cm <= 0:
    raise ValueError("aquarium_height_cm must be > 0")
if analysis_interval_frames < 1:
    raise ValueError("analysis_interval_frames must be >= 1")
if display_interval_frames < 1:
    raise ValueError("display_interval_frames must be >= 1")
if camera_index < 0:
    raise ValueError("camera_index must be >= 0")
```

---

### CRITICAL: No Validation on Video File Existence
**File:** `project_manager.py`
**Line:** 902-903 (in `create_new_project()`)
**Severity:** HIGH

```python
if project_type == "pre-recorded" and not video_files:
    raise ValueError("Pre-recorded projects require a list of video files.")
# ❌ Only checks if list is None
# ❌ Doesn't validate each file exists or is readable
```

**What Could Go Wrong:**
- Project created with non-existent video paths
- Batch processing fails hours later on first video
- No early validation feedback to user

**Suggested Fix:**
```python
if project_type == "pre-recorded" and not video_files:
    raise ValueError("Pre-recorded projects require a list of video files.")

# Validate each video file
for video_info in video_files:
    video_path = video_info.get("path") if isinstance(video_info, dict) else video_info
    if isinstance(video_path, str):
        path_obj = Path(video_path)
        if not path_obj.exists():
            raise ValueError(f"Video file not found: {video_path}")
        if not path_obj.is_file():
            raise ValueError(f"Path is not a file: {video_path}")
```

---

### WARNING: Migration Sets Defaults Without Bounds Check
**File:** `project_manager.py`
**Lines:** 1141-1144 (in `_apply_project_migrations()`)
**Severity:** MEDIUM

```python
if "camera_index" not in loaded_data or loaded_data["camera_index"] is None:
    loaded_data["camera_index"] = 0
    # ✓ Sets default correctly, but doesn't validate loaded value
    # If loaded value is -50 or 500, it passes unchecked
```

**What Could Go Wrong:**
- Corrupted project file with `camera_index: -50` loads without validation
- Silent failure when camera opens later

**Suggested Fix:**
```python
camera_index = loaded_data.get("camera_index", 0)
if camera_index < 0 or camera_index > 100:
    log.warning(
        "project.migration.invalid_camera_index",
        loaded=camera_index,
        using_default=0
    )
    camera_index = 0
loaded_data["camera_index"] = camera_index
```

---

## 4. CONFIGURATION SCHEMA ISSUES

### CRITICAL: Incomplete Cross-Field Validation
**File:** `settings.py`
**Lines:** 600-641 (in `Settings._validate_advanced_constraints()`)
**Severity:** MEDIUM

Missing validations for:

1. **Camera settings vs. video processing:**
   - No check that desired_width/height match reasonable aspect ratios
   - No validation that FPS doesn't exceed camera capabilities

2. **ROI settings:**
   - `roi_min_bbox_overlap_ratio` validates range but not context
   - `roi_buffer_radius_value` could be larger than entire image

3. **Model paths:**
   - Settings validates thresholds but not model file existence
   - No check if model format matches selected method (seg vs det)

**Suggested Fix:**
```python
@model_validator(mode="after")
def _validate_advanced_constraints(self) -> "Settings":
    # ... existing validation ...
    
    # Camera resolution sanity checks
    min_res = 320
    max_res = 7680
    if not (min_res <= self.camera.desired_width <= max_res):
        raise ValueError(
            f"desired_width must be {min_res}-{max_res}, got {self.camera.desired_width}"
        )
    if not (min_res <= self.camera.desired_height <= max_res):
        raise ValueError(
            f"desired_height must be {min_res}-{max_res}, got {self.camera.desired_height}"
        )
    
    # Aspect ratio sanity check (not too extreme)
    aspect = self.camera.desired_width / self.camera.desired_height
    if not (0.3 < aspect < 3.3):
        raise ValueError(
            f"Camera aspect ratio {aspect:.1f} is too extreme (should be 0.3-3.3)"
        )
    
    # FPS sanity check
    if self.video_processing.fps > 120:
        raise ValueError("FPS > 120 is unrealistic for typical hardware")
    
    # Model path validation
    model_path = Path(self.yolo_model.path)
    if not model_path.exists():
        raise ValueError(f"YOLO model not found: {self.yolo_model.path}")
```

---

## 5. SUMMARY TABLE OF CRITICAL ISSUES

| Issue | File | Line | Severity | Type | Impact |
|-------|------|------|----------|------|--------|
| No bounds on desired_width/height | settings.py | 63-68 | CRITICAL | Missing validation | Crashes, memory exhaustion |
| No bounds on fps | settings.py | 210 | CRITICAL | Missing validation | Division by zero, corrupt video |
| No bounds on processing_interval | settings.py | 211 | CRITICAL | Missing validation | Modulo division by zero |
| No model path validation | settings.py | 165 | CRITICAL | Missing validation | File not found at runtime |
| No detector name validation | wizard/models.py | 121 | MEDIUM | Missing validation | Silent detector lookup failure |
| No video file path validation | wizard/models.py | 139 | HIGH | Weak validation | Late failure on batch process |
| No bounds on num_aquariums | project_manager.py | 862 | CRITICAL | Missing validation | Invalid project state |
| No bounds on calibration dims | project_manager.py | 864-865 | CRITICAL | Missing validation | Division by zero in analysis |
| No bounds on analysis_interval | project_manager.py | 871 | CRITICAL | Missing validation | Modulo errors |
| No bounds on camera_index | project_manager.py | 873 | HIGH | Missing validation | Camera open failure |
| No validation on loaded camera_index | project_manager.py | 1141 | MEDIUM | Missing validation | Corrupted config accepted |
| Missing cross-field validation | settings.py | 600-641 | MEDIUM | Incomplete | Silent data corruption |

---

## 6. RECOMMENDED FIXES (Priority Order)

### Phase 1: CRITICAL (Do first - prevent runtime crashes)
1. Add bounds to camera settings (desired_width, desired_height)
2. Add bounds to fps and processing_interval  
3. Add file existence check for YOLO model path
4. Add bounds to project_manager calibration parameters

### Phase 2: HIGH (Prevent silent failures)
5. Add video file validation in wizard models
6. Add detector name validation
7. Add bounds checking in project migrations

### Phase 3: MEDIUM (Improve robustness)
8. Add cross-field validation for camera vs processing
9. Add Arduino port format validation
10. Improve error messages to explain constraints

---
