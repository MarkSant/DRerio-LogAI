# ZebTrack-AI Development Cheatsheet

## 🚀 Quick Start

### Run App
```bash
poetry run zebtrack                    # Standard launch
poetry run python -m zebtrack          # Alternative
F5 in VS Code                          # Debug mode
```

### Debug Configurations (F5)
- **ZebTrack: Run App** - Standard
- **ZebTrack: Debug Tests (Fast)** - Quick test suite
- **ZebTrack: Debug GUI Tests** - GUI-specific
- **ZebTrack: Debug Current Test File** - Active file

## 🧪 Testing

```bash
# Fast suite (default)
poetry run pytest -q

# GUI tests (no parallel)
poetry run pytest -m gui -n0

# Coverage report
poetry run pytest --cov=zebtrack --cov-report=html

# Single test
poetry run pytest tests/test_module.py::test_function -v

# Debug test
# Use F5 → "Debug Current Test File"
```

## 🔍 Common Debug Breakpoints

```python
# Video issues
zebtrack/io/video_source.py:VideoSource.get_frame()

# Detection issues
zebtrack/core/detector_service.py:DetectorService.detect()

# UI freezing
zebtrack/core/main_view_model.py:MainViewModel.update_ui_frame()

# Wizard stuck
zebtrack/ui/wizard/wizard_manager.py:WizardManager._advance_step()

# Data issues
zebtrack/io/recorder.py:Recorder._write_detection()
```

## 📁 File Navigation

| Component | Location |
|-----------|----------|
| Entry point | `zebtrack/__main__.py` |
| Settings | `zebtrack/settings.py` |
| Main ViewModel | `core/main_view_model.py` |
| State Manager | `core/state_manager.py` |
| Detector Service | `core/detector_service.py` |
| Video Source | `io/video_source.py` |
| Recorder | `io/recorder.py` |
| Wizard Manager | `ui/wizard/wizard_manager.py` |
| Project Manager | `core/project_manager.py` |
| UI Coordinator | `core/ui_coordinator.py` |

## 🐛 Common Issues & Fixes

### UI Freezing
```python
# ❌ WRONG: Blocking main thread
def on_analyze():
    results = heavy_analysis()

# ✅ RIGHT: Schedule async
def on_analyze():
    self.root.after(0, self._run_analysis_async)
```

### Zone Scaling
```python
# ❌ WRONG: Using template coords directly
detector.detect(frame, zones=project.roi_template.zones)

# ✅ RIGHT: Rescale first
detector.set_zones(zones, video_width, video_height)
```

### Missing Track IDs
```python
# ❌ WRONG: Assuming always present
track_id = detection["track_id"]

# ✅ RIGHT: Handle missing
track_id = detection.get("track_id", -1)
```

## 🛠️ Code Quality

```bash
# Lint check
poetry run ruff check .

# Auto-fix (careful!)
poetry run ruff check . --fix

# Format
poetry run ruff format .

# Pre-commit (mirrors CI)
poetry run pre-commit run --all-files
```

## 📝 Logging Pattern

```python
import structlog
logger = structlog.get_logger(__name__)

# Use domain.action.result format
logger.info("detector.scaling.start", zones=zones, dims=(w,h))
logger.debug("wizard.step.validate", step=current_step, valid=True)
logger.error("recorder.write.failed", error=str(e), detection=det)
```

## 🏗️ Architecture Flow

```
┌─────────────┐
│ VideoSource │ feeds frames
└──────┬──────┘
       ↓
┌──────────────────┐
│ DetectorService  │ wraps plugin + zones
└──────┬───────────┘
       ↓
┌──────────────────┐
│ ProcessingWorker │ background analysis
└──────┬───────────┘
       ↓
┌──────────────┐
│   Recorder   │ Parquet/MP4
└──────────────┘

┌──────────────┐
│ StateManager │ thread-safe state
└──────┬───────┘
       ↓
┌──────────────────┐
│  MainViewModel   │ orchestrates
└──────┬───────────┘
       ↓
┌──────────────┐
│   UI (Tk)    │ root.after only
└──────────────┘
```

## 📊 Data Schema

Parquet output columns:
```
timestamp, frame, track_id, x1, y1, x2, y2, confidence
+ derived: center_x, center_y, center_x_cm, center_y_cm
```

## 🐟 Multi-Aquarium Processing

### Data Structures
```python
from zebtrack.core.detector import AquariumData, MultiAquariumZoneData

# Per-aquarium config
aq = AquariumData(id=0, polygon=[[0,0],[100,0],[100,100],[0,100]])

# Multi-aquarium container
multi = MultiAquariumZoneData(
    aquariums=[aq0, aq1],
    video_width=1280,
    video_height=720,
    sequential_processing=False  # True = 2 passes, False = 1 pass
)
```

### Processing Modes
- **Parallel** (default): `sequential_processing=False` - 1 video pass, both aquariums
- **Sequential**: `sequential_processing=True` - 2 video passes, 1 aquarium each

### Track ID Convention
```python
global_id = aquarium_id * 1000 + local_id
# Aquarium 0: IDs 0-999
# Aquarium 1: IDs 1000-1999
```

### Key Events
```python
Events.ZONE_PROCESSING_MODE_CHANGED  # {sequential: bool}
Events.ZONE_AQUARIUM_SELECTED        # {aquarium_id: int}
Events.ZONE_MULTI_DETECT_COMPLETED   # {count: int, aquariums: list}
```

### Output Structure
```
video_results/
├── aquarium_0/
│   ├── 3_CoordMovimento_{video}.parquet
│   ├── 4_Relatorio_{video}_aq0.docx
│   └── {video}_aq0_summary.parquet
└── aquarium_1/
    └── ...
```

## 🎯 Task Shortcuts (Ctrl+Shift+B)

- Run ZebTrack (default)
- Run Tests (Fast)
- Run Tests with Coverage
- Lint with Ruff
- Format with Ruff
- Pre-commit All

## 📚 Documentation

- `docs/ARCHITECTURE.md` - System design
- `docs/QUICK_DEBUG_GUIDE.md` - Debug tips
- `docs/REFERENCE_GUIDE.md` - API reference
- `README_TESTS.md` - Test guide
- `TRANSITION_NOTE.md` - Migration notes

## 🔧 Performance

```bash
# Profile with cProfile
poetry run python -m cProfile -o output.prof -m zebtrack

# Analyze
poetry run python -m pstats output.prof
# >>> sort cumtime
# >>> stats 20

# Memory tracking
poetry run python -X tracemalloc=5 -m zebtrack
```

## ⚙️ Configuration

```yaml
# config.local.yaml (overrides config.yaml)
logging:
  level: DEBUG  # ERROR | WARNING | INFO | DEBUG
  file: logs/debug.log

ui_features:
  enable_event_queue: true

hardware:
  backend: openvino  # auto | cpu | cuda | openvino
```

## 🎨 UI Guidelines

- Never block main thread
- Use `root.after(0, callback)` for async
- Wizard: 1150×550 layout
- Update state via `StateManager`
- Schedule updates via `UICoordinator`

## 🔌 Plugin Development

```python
# Extend plugins/base.py
from zebtrack.plugins.base import BaseDetector

class MyDetector(BaseDetector):
    def detect(self, frame, zones):
        # Return list of detections
        return [{"x1": ..., "y1": ..., ...}]

    def set_zones(self, zones, width, height):
        # Rescale zones
        self.zones = rescale_zones(zones, width, height)

# Register in plugins/__init__.py
```

## 🎓 Best Practices

1. **Read tests first** - Understand expected behavior
2. **Check existing patterns** - Consistency matters
3. **Use StateManager** - Thread-safe updates
4. **Test after changes** - `pytest -q`
5. **Log with structure** - `domain.action.result`
6. **Handle edge cases** - Missing track_id, etc.
7. **Never block UI** - Use `root.after`
8. **Validate schema** - Check recorder tests
