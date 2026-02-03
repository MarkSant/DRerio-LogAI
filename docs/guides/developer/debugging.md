# Quick Debug Guide for ZebTrack-AI

## VS Code Debug Configurations

Use `F5` or Run & Debug panel to launch:

### Available Configurations
- **ZebTrack: Run App** - Standard app launch
- **ZebTrack: Run with Local Config** - Uses `config.local.yaml`
- **ZebTrack: Debug Tests (Fast)** - Quick test suite
- **ZebTrack: Debug GUI Tests** - GUI-specific tests (no parallel)
- **ZebTrack: Debug Current Test File** - Debug active test file
- **ZebTrack: Debug Specific Test** - Debug single test by name

## Common Debug Breakpoints

### Video Processing Issues
```python
# Frame acquisition
zebtrack/io/video_source.py:VideoSource.get_frame()

# Detection pipeline
zebtrack/core/detector_service.py:DetectorService.detect()
zebtrack/plugins/yolov8_detector.py:YOLOv8Detector.detect()
```

### UI Freezing/Responsiveness
```python
# Main update loop
zebtrack/core/main_view_model.py:MainViewModel.update_ui_frame()

# UI coordination
zebtrack/core/ui_coordinator.py:UICoordinator.schedule_ui_update()

# Event handling
zebtrack/ui/gui.py:MainWindow._on_*()
```

### Wizard Flow Issues
```python
# Step management
zebtrack/ui/wizard/wizard_manager.py:WizardManager._advance_step()

# Validation
zebtrack/core/project_workflow_service.py:ProjectWorkflowService.validate_step()

# Project data
zebtrack/core/project_manager.py:ProjectManager.get_roi_template()
```

### Recording/Data Issues
```python
# Data writing
zebtrack/io/recorder.py:Recorder._write_detection()

# Schema validation
zebtrack/io/recorder.py:Recorder._validate_schema()
```

### Zone Scaling Problems
```python
# Zone rescaling
zebtrack/core/detector_service.py:DetectorService.set_zones()
zebtrack/utils/geometry.py:rescale_zones()
```

## Quick Debug Scenarios

### 1. App Won't Start
**Breakpoint**: `zebtrack/__main__.py:main()`
**Check**: Config loading, hardware detection, model availability

### 2. Detection Not Working
**Breakpoint**: `DetectorService.detect()`
**Inspect**:
- `frame` shape and dtype
- `zones` coordinates after scaling
- `plugin` initialization

### 3. UI Not Updating
**Breakpoint**: `MainViewModel.update_ui_frame()`
**Check**:
- `root.after()` calls present
- No blocking operations in main thread
- `StateManager.update_state()` called

### 4. Wizard Stuck
**Breakpoint**: `ProjectWorkflowService.validate_step()`
**Check**:
- Current step data in `project_manager`
- Required fields populated
- File paths valid

### 5. Wrong Data in Parquet
**Breakpoint**: `Recorder._write_detection()`
**Inspect**:
- `detection` dict keys
- Match against `self.schema`
- Column dtypes

## Performance Profiling

```powershell
# cProfile
poetry run python -m cProfile -o output.prof -m zebtrack

# Analyze with pstats
poetry run python -m pstats output.prof
# >>> sort cumtime
# >>> stats 20
```

## Memory Analysis

```powershell
# tracemalloc
poetry run python -X tracemalloc=5 -m zebtrack

# Watch for leaks in:
# - Frame buffers (VideoSource)
# - Detection results (ProcessingWorker)
# - UI canvases (VideoDisplay)
```

## Logging Tips

### Enable Debug Logging
Edit `config.local.yaml`:
```yaml
logging:
  level: DEBUG
  file: logs/debug.log
```

### Key Log Patterns
```python
# Domain-based structlog
logger.debug("detector.scaling.start", zones=zones, frame_dims=(w,h))
logger.info("wizard.step.advance", from_step=current, to_step=next)
logger.error("recorder.write.failed", error=str(e), detection=det)
```

### Grep for Issues
```powershell
# Find errors
Select-String -Path logs\*.log -Pattern "ERROR"

# Track specific domain
Select-String -Path logs\*.log -Pattern "detector\."
```

## Test Debugging

### Run Single Test
```powershell
poetry run pytest tests/test_detector_service.py::test_specific_function -v -s
```

### Debug Test Fixture
```python
# In test file, add:
import pytest
pytest.set_trace()  # or use breakpoint()
```

### GUI Test Tips
- Always use `-n0` (no parallel)
- Tests run in separate Tk instance
- Use `caplog` fixture for log inspection

## Common Pitfalls

### ❌ Forgetting Zone Rescaling
```python
# WRONG: Using template coords directly
detector.detect(frame, zones=project.roi_template.zones)

# RIGHT: Rescale first
detector.set_zones(zones, video_width, video_height)
```

### ❌ Blocking Main Thread
```python
# WRONG: Heavy computation in UI callback
def on_analyze():
    results = heavy_analysis()  # Blocks UI

# RIGHT: Use after() or background worker
def on_analyze():
    self.root.after(0, self._run_analysis_async)
```

### ❌ Missing Track IDs
```python
# WRONG: Assuming track_id always present
track_id = detection["track_id"]

# RIGHT: Handle missing gracefully
track_id = detection.get("track_id", -1)
```

## VS Code Tasks

Use `Ctrl+Shift+B` to run build tasks:
- **Run ZebTrack** (default)
- **Run Tests (Fast)**
- **Run Tests with Coverage**
- **Lint with Ruff**
- **Format with Ruff**
- **Pre-commit All**

## References

- Architecture: `docs/explanation/architecture.md`
- Test Guide: `docs/guides/developer/testing_gui_windows.md`
- Agent Playbook: `.github/copilot-instructions.md`
- Reference: `docs/reference/operational_reference.md`
