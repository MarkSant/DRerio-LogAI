# DetectorService API Documentation

**Phase 6: Detector Management Service**

The `DetectorService` is a service layer component that encapsulates all detector initialization, zone configuration, and tracking parameter management logic. It was extracted from the controller in Phase 6 to improve separation of concerns and testability.

## Overview

**Location**: `src/zebtrack/core/detector_service.py`

**Purpose**: Manage detector lifecycle, zones, and tracking parameters independently from UI and workflow orchestration.

**Dependencies**:
- `StateManager`: Centralized state tracking
- `ProjectManager`: Zone data and configuration persistence
- `WeightManager`: Model path resolution
- `ModelService`: Weight details and OpenVINO paths

## Class: DetectorService

### Constructor

```python
def __init__(
    self,
    state_manager: StateManager,
    project_manager: ProjectManager,
    weight_manager: WeightManager,
    model_service: ModelService,
)
```

**Parameters**:
- `state_manager`: StateManager instance for centralized state tracking
- `project_manager`: ProjectManager for zone data and config persistence
- `weight_manager`: WeightManager for model path resolution
- `model_service`: ModelService for weight details and OpenVINO paths

**Example**:
```python
detector_service = DetectorService(
    state_manager=state_manager,
    project_manager=project_manager,
    weight_manager=weight_manager,
    model_service=model_service,
)
```

---

## Public Methods

### 1. initialize_detector()

Initializes the detector instance based on the animal detection method.

```python
def initialize_detector(
    self,
    animal_method: str | None = None,
    use_openvino: bool = False,
    active_weight_name: str | None = None,
    detector_plugins: dict | None = None,
) -> tuple[bool, str | None]
```

**Parameters**:
- `animal_method`: Detection method ('det' or 'seg'). If None, uses global settings
- `use_openvino`: Whether to use OpenVINO plugin (default: False)
- `active_weight_name`: Current active weight name for state tracking
- `detector_plugins`: Dict mapping plugin names to plugin classes (optional)

**Returns**:
- `tuple[bool, str | None]`: (success, error_message)
  - `success`: True if detector initialized successfully
  - `error_message`: Error description if initialization failed, None otherwise

**Side Effects**:
- Creates `self.detector` instance
- Updates StateManager detector state
- Saves detector configuration to project
- Configures single-subject tracker preference
- Sets plugin context to "tracking"

**Example**:
```python
success, error = detector_service.initialize_detector(
    animal_method="seg",
    use_openvino=False,
    active_weight_name="best_seg.pt",
)

if success:
    print("Detector initialized successfully")
else:
    print(f"Initialization failed: {error}")
```

**Exceptions**:
- `ValueError`: Invalid model path or plugin configuration
- `FileNotFoundError`: Model file not found
- `IntegrityError`: OpenVINO model integrity check failed

---

### 2. configure_zones()

Configures detection zones on the detector instance with proper scaling.

```python
def configure_zones(
    self,
    zone_data: ZoneData | None = None,
    width: int | None = None,
    height: int | None = None,
) -> bool
```

**Parameters**:
- `zone_data`: Zone configuration. If None, loads from project
- `width`: Frame width. If None, uses camera settings
- `height`: Frame height. If None, uses camera settings

**Returns**:
- `bool`: True if zones were configured successfully

**Side Effects**:
- Sets zones on detector with scaling
- Notifies plugin about aquarium region status

**Example**:
```python
zone_data = ZoneData(
    polygon=[[0, 0], [800, 0], [800, 600], [0, 600]],
    roi_polygons=[[[100, 100], [200, 100], [200, 200], [100, 200]]],
    roi_names=["ROI1"],
    roi_colors=[(255, 0, 0)],
)

success = detector_service.configure_zones(
    zone_data=zone_data,
    width=800,
    height=600,
)
```

---

### 3. update_tracking_parameters()

Updates detector tracking parameters with validation.

```python
def update_tracking_parameters(
    self,
    params: dict[str, float] | None = None,
    *,
    conf_threshold: float | None = None,
    nms_threshold: float | None = None,
    track_threshold: float | None = None,
    match_threshold: float | None = None,
    reset_overrides: bool = False,
) -> bool
```

**Parameters**:
- `params`: Dict of parameters to update (accepts both long and short form names)
- `conf_threshold`: Confidence threshold (0.0-1.0)
- `nms_threshold`: NMS threshold (0.0-1.0)
- `track_threshold`: ByteTrack track threshold (0.0-1.0)
- `match_threshold`: ByteTrack match threshold (0.0-1.0)
- `reset_overrides`: If True, reset to factory defaults

**Returns**:
- `bool`: True if parameters were updated successfully

**Side Effects**:
- Updates plugin parameters if detector exists
- Persists to global settings
- Saves to project configuration

**Parameter Name Normalization**:
- Accepts both `confidence_threshold` (long form) and `conf_threshold` (short form)
- Internally uses short form for consistency

**Validation**:
- All threshold values must be between 0.0 and 1.0
- Raises `ValueError` if validation fails

**Example**:
```python
# Using params dict
success = detector_service.update_tracking_parameters(
    params={
        "confidence_threshold": 0.35,
        "nms_threshold": 0.55,
        "track_threshold": 0.30,
        "match_threshold": 0.20,
    }
)

# Using individual parameters
success = detector_service.update_tracking_parameters(
    conf_threshold=0.35,
    nms_threshold=0.55,
)

# Reset to factory defaults
success = detector_service.update_tracking_parameters(
    params={},
    reset_overrides=True,
)
```

---

### 4. reset_tracking_state()

Resets tracker state between videos.

```python
def reset_tracking_state(self) -> None
```

**Side Effects**:
- Calls `detector.reset_tracking_state()` to clear tracker memory

**Example**:
```python
# Before processing a new video
detector_service.reset_tracking_state()
```

---

### 5. set_single_subject_mode()

Configures single-subject tracking mode.

```python
def set_single_subject_mode(self, enabled: bool) -> None
```

**Parameters**:
- `enabled`: True to enable single-subject mode, False for multi-subject

**Side Effects**:
- Updates detector's single-subject mode setting

**Example**:
```python
# Enable single-subject tracking
detector_service.set_single_subject_mode(True)

# Disable for multi-subject tracking
detector_service.set_single_subject_mode(False)
```

---

### 6. get_detector_parameters()

Gets current detector thresholds, falling back to saved or default values.

```python
def get_detector_parameters(self) -> dict[str, float]
```

**Returns**:
- `dict[str, float]`: Current detector parameters with short-form names:
  - `conf_threshold`: Confidence threshold
  - `nms_threshold`: NMS threshold
  - `track_threshold`: ByteTrack track threshold
  - `match_threshold`: ByteTrack match threshold

**Behavior**:
- If detector with plugin exists: Returns current plugin values
- Otherwise: Returns values from settings and project data

**Example**:
```python
params = detector_service.get_detector_parameters()
print(f"Confidence: {params['conf_threshold']}")
print(f"NMS: {params['nms_threshold']}")
print(f"Track: {params['track_threshold']}")
print(f"Match: {params['match_threshold']}")
```

---

### 7. get_factory_detector_parameters()

Gets factory default detector thresholds without any overrides.

```python
def get_factory_detector_parameters(self) -> dict[str, float]
```

**Returns**:
- `dict[str, float]`: Factory default parameters with short-form names

**Example**:
```python
factory_params = detector_service.get_factory_detector_parameters()
# Reset to factory defaults
detector_service.update_tracking_parameters(
    params=factory_params,
    reset_overrides=True,
)
```

---

### 8. restore_detector_settings()

Restores detector settings from saved configuration.

```python
def restore_detector_settings(self, saved_detector_config: dict) -> None
```

**Parameters**:
- `saved_detector_config`: Saved detector configuration from project

**Side Effects**:
- Updates plugin thresholds from saved config
- Logs restoration progress

**Example**:
```python
# After loading a project
saved_config = project_manager.get_detector_state()
if saved_config:
    detector_service.restore_detector_settings(saved_config)
```

---

## Properties

### detector

The current detector instance managed by this service.

```python
@property
def detector(self) -> Detector | None
```

**Returns**:
- `Detector | None`: Current detector instance or None if not initialized

**Example**:
```python
if detector_service.detector:
    print(f"Detector plugin: {detector_service.detector.plugin.get_name()}")
else:
    print("No detector initialized")
```

---

## Integration with Controller

The controller delegates detector management to DetectorService:

```python
# In controller.__init__()
self.detector_service = DetectorService(
    state_manager=self.state_manager,
    project_manager=self.project_manager,
    weight_manager=self.weight_manager,
    model_service=self.model_service,
)

# Controller provides backward-compatible property
@property
def detector(self) -> Detector | None:
    return self.detector_service.detector

# Controller delegates operations
def setup_detector(self, temp_animal_method=None):
    success, error = self.detector_service.initialize_detector(
        animal_method=temp_animal_method,
        use_openvino=self.use_openvino,
        active_weight_name=self.active_weight_name,
    )
    # Handle result...
```

---

## Parameter Name Conventions

DetectorService uses **short-form parameter names** internally:
- `conf_threshold` (not `confidence_threshold`)
- `nms_threshold`
- `track_threshold`
- `match_threshold`

However, `update_tracking_parameters()` **accepts both forms** for backward compatibility.

For public API compatibility, the Controller normalizes these to long-form names:
```python
# Controller normalizes to long form for backward compatibility
def get_current_detector_parameters(self) -> dict[str, float]:
    params = self.detector_service.get_detector_parameters()
    if "conf_threshold" in params:
        params["confidence_threshold"] = params.pop("conf_threshold")
    return params
```

---

## Common Workflows

### 1. Initialize Detector for Video Processing

```python
# 1. Initialize detector
success, error = detector_service.initialize_detector(
    animal_method="seg",
    use_openvino=False,
    active_weight_name="best_seg.pt",
)

if not success:
    print(f"Failed to initialize: {error}")
    return

# 2. Configure zones
zone_data = project_manager.get_zone_data()
detector_service.configure_zones(zone_data, width=800, height=600)

# 3. Update parameters if needed
detector_service.update_tracking_parameters(
    conf_threshold=0.35,
    track_threshold=0.30,
)

# 4. Process videos
for video in videos:
    detector_service.reset_tracking_state()
    # Process frames...
```

### 2. Update Detector Configuration

```python
# Get current parameters
current = detector_service.get_detector_parameters()
print(f"Current confidence: {current['conf_threshold']}")

# Update specific parameters
detector_service.update_tracking_parameters(
    conf_threshold=0.40,
    nms_threshold=0.50,
)

# Verify update
updated = detector_service.get_detector_parameters()
print(f"Updated confidence: {updated['conf_threshold']}")
```

### 3. Reset to Factory Defaults

```python
# Get factory defaults
factory = detector_service.get_factory_detector_parameters()

# Reset to defaults
detector_service.update_tracking_parameters(
    params=factory,
    reset_overrides=True,
)
```

---

## Testing

### Unit Tests
Located in `tests/core/test_detector_service.py`:
- 28 test cases covering all methods
- Comprehensive error handling validation
- Parameter validation checks

### Integration Tests
Located in `tests/test_detector_service_integration.py`:
- 8 integration tests with Controller
- Full workflow verification
- State synchronization checks

Run tests:
```bash
# Unit tests
poetry run pytest tests/core/test_detector_service.py -v

# Integration tests
poetry run pytest tests/test_detector_service_integration.py -v

# All detector-related tests
poetry run pytest tests -k detector -v
```

---

## Migration Notes

### From Phase 5 (Before DetectorService)

**Before** (Controller handled everything):
```python
# In controller
self.detector = Detector(plugin=plugin_instance, ...)
self._persist_global_detector_defaults(config)
self._resolve_single_subject_tracker_preference()
```

**After** (DetectorService handles detector logic):
```python
# In controller
success, error = self.detector_service.initialize_detector(...)
# DetectorService handles persistence and preferences internally
```

### Backward Compatibility

- Controller maintains `detector` property for backward compatibility
- Controller normalizes parameter names to long form in public API
- Existing controller tests continue to work with minimal changes

---

## Performance Considerations

- **Lazy Initialization**: Detector only created when explicitly initialized
- **State Caching**: Plugin values cached in detector instance
- **Minimal Project Saves**: Only saves when values actually change
- **Validation Before Persistence**: Validates parameters before saving

---

## Error Handling

All methods use structured logging for troubleshooting:

```python
log.info("detector_service.initialize.start", animal_method=animal_method)
log.error("detector_service.initialize.failed", error=str(e), exc_info=True)
```

Common error scenarios:
1. **Model Not Found**: Check weight path configuration
2. **OpenVINO Not Ready**: Convert model to OpenVINO first
3. **Invalid Parameters**: Ensure thresholds are between 0.0 and 1.0
4. **No Detector**: Initialize detector before calling detector-dependent methods

---

## Future Enhancements

Potential improvements for future phases:
- Support for multiple detector types simultaneously
- Hot-swapping detector plugins without reinitialization
- Parameter profiles/presets
- Advanced zone validation
- Real-time parameter tuning feedback

---

## References

- **Phase 6 Implementation**: Controller refactoring for detector management
- **Related Services**: ModelService, StateManager, ProjectManager
- **Plugin Interface**: `zebtrack/plugins/base.py`
- **Detector Implementation**: `zebtrack/core/detector.py`
