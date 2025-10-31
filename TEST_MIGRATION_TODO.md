# Test Migration TODO - Settings DI

## Status
The settings singleton has been completely removed. Many tests still use `patch("module.settings")` which will fail.

## Required Changes

All tests need to:
1. Remove `patch("module.settings")` mocks
2. Use `load_settings()` or create test Settings objects
3. Pass `settings_obj` to service constructors

## Files Requiring Updates

### HIGH PRIORITY (Core Services)

**tests/core/test_weight_manager.py**
- Currently mocks `zebtrack.core.weight_manager.settings` (lines 25-31)
- Solution: Create fixture that loads settings and passes to WeightManager(settings_obj=...)
```python
@pytest.fixture
def test_settings():
    from zebtrack.settings import load_settings
    return load_settings()

@pytest.fixture
def wm_setup(tmp_path, test_settings):
    manager = WeightManager(config_dir=str(config_dir), settings_obj=test_settings)
    yield manager, config_dir, tmp_path
```

**tests/core/test_detector_service.py**
- Likely mocks settings
- Solution: Pass settings_obj to DetectorService constructor
```python
def test_detector_service(test_settings):
    detector_service = DetectorService(
        state_manager=mock_state,
        project_manager=mock_project,
        weight_manager=mock_weights,
        model_service=mock_model,
        settings_obj=test_settings
    )
```

**tests/analysis/test_analysis_service.py** (ALREADY MIGRATED ✅)
- AnalysisService requires settings_obj for run_full_analysis()
- **Error message**: `"AnalysisService: Settings not injected."`
- Example test:
```python
def test_analysis_requires_settings(test_settings):
    service = AnalysisService(settings_obj=test_settings)
    # run_full_analysis() will work

def test_analysis_fails_without_settings():
    service = AnalysisService(settings_obj=None)
    with pytest.raises(RuntimeError, match="AnalysisService: Settings not injected"):
        service.run_full_analysis(...)  # Raises when settings needed
```

**tests/io/test_camera.py**
- Camera() requires settings_obj or raises RuntimeError
- Solution: Add settings fixture and pass to Camera(settings_obj=...)
- **Error message**: `"Camera: Settings not injected."`
- Example test:
```python
def test_camera_requires_settings(test_settings):
    camera = Camera(settings_obj=test_settings)  # OK
    assert camera.settings is not None

def test_camera_fails_without_settings():
    with pytest.raises(RuntimeError, match="Camera: Settings not injected"):
        Camera(settings_obj=None)
```

**tests/io/test_recorder.py**
- Recorder() now accepts settings_obj
- Solution: Pass settings_obj to Recorder constructor
- **Note**: Recorder uses graceful fallback, does NOT raise RuntimeError
```python
def test_recorder_with_settings(test_settings):
    recorder = Recorder(settings_obj=test_settings)
    assert recorder._fps == test_settings.video_processing.fps

def test_recorder_without_settings():
    recorder = Recorder(settings_obj=None)
    assert recorder._fps == 30.0  # Default fallback
```

### MEDIUM PRIORITY (Integration Tests)

**tests/integration/** (multiple files)
- May instantiate services without settings_obj
- Review each file and add settings fixture

### LOW PRIORITY

**tests/test_wizard_service.py**
- WizardService static methods accept optional settings_obj
- Tests should work with defaults but can be improved

## Test Execution Note

Tests cannot currently run in this environment due to missing tkinter module in conftest.py.
This is an environment limitation, not a code issue.

## Recommended Approach

1. Create shared fixture in conftest.py:
```python
@pytest.fixture(scope="session")
def test_settings():
    \"\"\"Load settings once for all tests.\"\"\"
    from zebtrack.settings import load_settings
    return load_settings()
```

2. Update each test file to use the fixture
3. Pass settings_obj to ALL service instantiations
4. Remove ALL `patch("*.settings")` mocks

## Error Handling Patterns

### Services that Raise RuntimeError
These services **require** settings to function and will raise `RuntimeError` if None:

1. **Camera** (`io/camera.py`)
   - Error: `"Camera: Settings not injected."`
   - Reason: Requires hardware configuration (camera index, resolution)

2. **AnalysisService** (`analysis/analysis_service.py`)
   - Error: `"AnalysisService: Settings not injected."`
   - Reason: Requires scientific precision (thresholds, smoothing parameters)
   - Note: Constructor accepts None, but `run_full_analysis()` raises if None

### Services that Use Graceful Fallback
These services use **sensible defaults** when settings_obj is None:

1. **Detector** (`core/detector.py`)
   - Falls back to: 0.25 track threshold, 0.15 match threshold, 30 fps

2. **Recorder** (`io/recorder.py`)
   - Falls back to: 30.0 fps, 5.0s flush interval, snappy compression

3. **Plugins** (`plugins/openvino_detector.py`, `plugins/ultralytics_detector.py`)
   - Fall back to: 0.25 confidence, 0.45 NMS threshold

4. **UI Components** (`ui/**/*.py`)
   - Fall back to: Hardcoded defaults for display

### Testing Strategy

```python
# For RuntimeError services
def test_service_requires_settings(test_settings):
    service = Service(settings_obj=test_settings)  # OK
    assert service.method() works

def test_service_raises_without_settings():
    service = Service(settings_obj=None)  # Constructor may accept None
    with pytest.raises(RuntimeError, match="Service: Settings not injected"):
        service.critical_method()  # Raises when settings needed

# For graceful fallback services
def test_service_with_settings(test_settings):
    service = Service(settings_obj=test_settings)
    assert service.value == test_settings.expected_value

def test_service_without_settings():
    service = Service(settings_obj=None)
    assert service.value == DEFAULT_VALUE  # Uses fallback
```

## Verification

After fixes, run:
```bash
poetry run pytest --no-cov -v
```

All tests should pass without settings import errors.

## Common Test Failures and Fixes

### ❌ AttributeError: module 'zebtrack.settings' has no attribute 'settings'
**Cause**: Test patches `zebtrack.module.settings` but singleton no longer exists
**Fix**: Remove patch, use fixture with `load_settings()`

### ❌ RuntimeError: Camera: Settings not injected.
**Cause**: Camera instantiated without settings_obj
**Fix**: Pass `settings_obj=test_settings` to Camera constructor

### ❌ RuntimeError: AnalysisService: Settings not injected.
**Cause**: `run_full_analysis()` called but settings_obj was None
**Fix**: Pass `settings_obj=test_settings` to AnalysisService constructor
