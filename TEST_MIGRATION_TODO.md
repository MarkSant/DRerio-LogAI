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

**tests/io/test_camera.py**
- Camera() requires settings_obj or raises RuntimeError
- Solution: Add settings fixture and pass to Camera(settings_obj=...)

**tests/io/test_recorder.py**
- Recorder() now accepts settings_obj
- Solution: Pass settings_obj to Recorder constructor

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

## Verification

After fixes, run:
```bash
poetry run pytest --no-cov -v
```

All tests should pass without settings import errors.
