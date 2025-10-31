# Dependency Injection Pattern - Implementation Guide

## Overview

ZebTrack-AI uses **constructor injection** throughout the codebase. The Composition Root pattern is implemented in `src/zebtrack/__main__.py`, where all dependencies are created and wired together.

## Settings Injection Strategy

All services receive settings via the `settings_obj` parameter in their constructors.

### Critical Services (RuntimeError on None)

Services that **cannot function** without settings raise `RuntimeError`:

**`io/camera.py`**
```python
def __init__(self, settings_obj: "Settings | None" = None):
    if settings_obj is None:
        raise RuntimeError("Camera: Settings not injected.")
    self.settings = settings_obj
    self._camera_index = self.settings.camera.index  # Required
```

**Reason**: Camera requires specific hardware configuration (index, resolution) and cannot operate with defaults.

**`analysis/analysis_service.py`**
```python
def run_full_analysis(...):
    if self.settings is None:
        raise RuntimeError("AnalysisService: Settings not injected.")
```

**Reason**: Analysis algorithms require precise thresholds (freezing velocity, smoothing windows) for scientific accuracy.

### Optional Services (Graceful Fallback)

Services that **can function** with reasonable defaults use graceful fallback:

**`plugins/openvino_detector.py`** and **`plugins/ultralytics_detector.py`**
```python
def __init__(self, model_path, settings_obj: Any | None = None):
    if settings_obj is not None:
        self.conf_threshold = settings_obj.yolo_model.confidence_threshold
        self.nms_threshold = settings_obj.yolo_model.nms_threshold
    else:
        # Fallback defaults
        self.conf_threshold = 0.25
        self.nms_threshold = 0.45
```

**Reason**: Detection plugins can operate with industry-standard defaults (0.25 confidence, 0.45 NMS).

### UI Components (Graceful Fallback)

UI widgets that display settings-based defaults use fallback to maintain usability:

**`ui/wizard/model_selection_step.py`**
```python
if self.settings and hasattr(self.settings, "yolo_model"):
    default_confidence = self.settings.yolo_model.confidence_threshold
else:
    default_confidence = 0.25  # Hardcoded fallback
```

**Reason**: UI should remain functional even if settings fail to load, using safe defaults.

## Design Principle

**Rule**: Use `RuntimeError` when the service's **core function** depends on settings. Use **graceful fallback** when reasonable defaults exist.

## Lazy Initialization

Some services accept `None` initially and are populated later:

**`core/video_processing_service.py`**
```python
def __init__(self, detector: Detector | None, ...):
    self.detector = detector  # Can be None initially
```

**Reason**: The detector is created lazily via `detector_service.initialize_detector()` when a project is loaded, as different projects may use different detection methods (seg/det) and backends (YOLO/OpenVINO).

## Composition Root

**ALL dependency creation happens in `__main__.py`:**

```python
# Load settings once
settings_obj = load_settings()

# Create services with injected settings
weight_manager = WeightManager(settings_obj=settings_obj)
detector_service = DetectorService(..., settings_obj=settings_obj)
analysis_service = AnalysisService(settings_obj=settings_obj)
camera = Camera(settings_obj=settings_obj)  # Will raise if settings is None

# Wire dependencies
controller = MainViewModel(
    settings_obj=settings_obj,
    detector_service=detector_service,
    analysis_service=analysis_service,
    ...
)
```

## Testing

Tests must inject settings or handle RuntimeError:

```python
@pytest.fixture
def test_settings():
    from zebtrack.settings import load_settings
    return load_settings()

def test_camera_requires_settings(test_settings):
    camera = Camera(settings_obj=test_settings)  # OK

def test_camera_fails_without_settings():
    with pytest.raises(RuntimeError, match="Settings not injected"):
        Camera(settings_obj=None)
```

## Migration Status

✅ **Phase 1**: Core services (WeightManager, DetectorService, ProjectManager)
✅ **Phase 2**: Analysis & IO layers (AnalysisService, Camera, Recorder, Plugins)
✅ **Phase 3**: UI layer (ApplicationGUI, WizardDialog, all dialogs)
✅ **Singleton Removed**: No global `settings` object exists

## References

- Composition Root: `src/zebtrack/__main__.py:140-280`
- Settings Model: `src/zebtrack/settings.py`
- Test Migration Guide: `TEST_MIGRATION_TODO.md`
