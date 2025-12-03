# ZebTrack-AI Quick Reference

**Ultra-compact reference for AI assistants and developers**

## 🎯 One-Liners

```bash
poetry install && poetry run zebtrack              # Setup & run
poetry run pytest                                   # Test (712 tests, fast only)
poetry run ruff check --fix .                       # Lint & auto-fix
```

## 🏗️ Architecture (MVVM-S + DI)

```
# Pre-recorded
User → EventBus → MainViewModel → StateManager → UI (root.after)
                         ↓
         VideoSource → DetectorService → Recorder → AnalysisService → Reporter

# Live Camera Analysis (v2.0+)
User → LiveAnalysisDialog → LiveCameraService → [CaptureThread, ProcessingThread]
                                    ↓
                    Camera → DetectorService → Recorder + LivePreviewWindow
```

**DI Root**: `__main__.py` (lines 140-280) - inject `settings_obj` everywhere

## 📁 Critical Files

| Path | Purpose |
|------|---------|
| `core/main_view_model.py` | Orchestrator (11+ deps) |
| `core/state_manager.py` | Thread-safe state |
| `core/wizard_service.py` | Wizard logic + HW caching (30s TTL) |
| `io/recorder.py` | Parquet schema (IMMUTABLE) |
| `ui/gui.py` | Main window (10759 lines) |
| `ui/wizard/models.py` | Pydantic validation |
| `settings.py` | Config models (Pydantic v2) |

## 🔒 IMMUTABLE Parquet Schema

```
timestamp, frame, track_id, x1, y1, x2, y2, confidence, [x_center_px, y_center_px, x_cm, y_cm]*
```
**DO NOT REORDER** - Tests: `tests/test_recorder.py`

## ⚡ Critical Rules

1. **UI Updates**: ALWAYS `root.after(0, ...)` (Tkinter main thread)
2. **Settings**: NEVER hardcode - inject `settings_obj` via DI
3. **Zones**: MUST call `Detector.set_zones()` after video dims known
4. **Track IDs**: Handle missing: `detection.get("track_id", -1)`
5. **Logging**: `structlog` with `domain.action.result` pattern

## 🧵 Threading Pattern

```python
# ✅ CORRECT
def heavy_task():
    result = compute()  # Worker thread
    self.root.after(0, lambda: self.update_ui(result))  # UI update

# ❌ WRONG
def heavy_task():
    result = compute()
    self.label.config(text=result)  # Blocks/crashes UI
```

## 📦 Common Imports

```python
# DI & State
from zebtrack.settings import load_settings
from zebtrack.core.state_manager import StateManager

# Logging
import structlog
logger = structlog.get_logger()

# Detectors
from zebtrack.core.detector_service import DetectorService
from zebtrack.plugins import DETECTOR_PLUGINS
```

## 🧪 Testing Quick Reference

```bash
# Fast only (default)
pytest

# GUI tests
pytest -m gui -n0

# Specific test
pytest tests/test_module.py::test_func -v -s

# With coverage
pytest --cov=zebtrack --cov-report=html
```

**Markers**: `@pytest.mark.{gui,slow,integration,unit}`

## 🎨 Wizard Flow (v2.0)

1. **LiveConfigStep** → Camera/Arduino detection (cached 30s)
2. **ExperimentalDesignStep** → Days/Groups/Subjects
3. **CalibrationStep** → Arena detection
4. **ModelSelectionStep** → YOLO/OpenVINO
5. **ConfirmationStep** → Review & create

**Models**: `ui/wizard/models.py` (Pydantic validation)
**Service**: `core/wizard_service.py` (business logic)

## 📊 Data Flow Example

```python
# Project creation
settings_obj = load_settings()
wizard_service = WizardService(settings_obj)
cameras = wizard_service.detect_cameras()  # Cached 30s

# Detection
detector = DetectorService(settings_obj=settings_obj)
detector.set_zones(zones, width, height)  # MUST CALL
detections, cmd = detector.detect(frame, "live")

# Recording (IMMUTABLE schema)
recorder = Recorder(...)
recorder.write_detection_data(timestamp, frame_num, detections)

# Analysis
analyzer = AnalysisService(settings_obj=settings_obj)
results = analyzer.run_full_analysis(parquet_path, zones)
```

## 🔧 Configuration Hierarchy

```
config.yaml (base)
    ↓ overrides
config.local.yaml (machine-specific, git-ignored)
    ↓ overrides
ProjectManager.project_data (per-project)
```

**Access**: `from zebtrack import settings` (after `load_settings()`)

## 🚨 Common Pitfalls

| Issue | Solution |
|-------|----------|
| UI freeze | Use `root.after(0, ...)` |
| Zone mismatch | Call `Detector.set_zones()` |
| Missing track_id | Use `.get("track_id", -1)` |
| Hardcoded values | Inject `settings_obj` |
| Schema changes | Update `tests/test_recorder.py` |

## 📚 Documentation Index

| Need | See |
|------|-----|
| **Quick commands** | `docs/CHEATSHEET.md` |
| **Architecture deep-dive** | `docs/ARCHITECTURE.md` |
| **Wizard dev** | `docs/DEVELOPER_GUIDE_WIZARD.md` |
| **Testing guide** | `README_TESTS.md` |
| **Coordinates** | `docs/COORDINATE_SYSTEMS.md` |
| **State mgmt** | `docs/STATE_MANAGER_GUIDE.md` |
| **DI patterns** | `docs/DEPENDENCY_INJECTION_GUIDE.md` |
| **Full reference** | `docs/REFERENCE_GUIDE.md` |
| **Debug tips** | `docs/QUICK_DEBUG_GUIDE.md` |
| **Historical** | `docs/archive/` |

## 🔍 Quick Debugging

```python
# Enable debug logging in config.local.yaml
logging:
  level: DEBUG
  file: logs/debug.log

# Breakpoints (VS Code F5)
zebtrack/io/video_source.py:VideoSource.get_frame()
zebtrack/core/detector_service.py:DetectorService.detect()
zebtrack/core/main_view_model.py:MainViewModel.update_ui_frame()
```

## 📈 Performance Settings

```yaml
performance:
  max_parallel_videos: 2
  max_parallel_plots: 3
  parquet_compression: "snappy"
  enable_parallel_analysis: true
```

## 🎓 Version Context

- **v2.0 (Oct-Nov 2025)**: WizardService, HW caching, LiveCameraService (live analysis), 712 tests
- **v1.8**: StateManager (thread-safe)
- **v1.7**: Pydantic v2 settings
- **v1.6**: 5-step wizard

## 📹 Live Camera Analysis (v2.0+ Nov 2025)

**Quick Access**: Menu File → "Analisar Câmera ao Vivo..." or `controller.start_live_camera_analysis()`

**Architecture**:
- **LiveCameraService**: Coordinates capture & processing threads
- **LiveAnalysisDialog**: Configuration UI
- **LivePreviewWindow**: Real-time preview
- **Output**: `live_analysis_sessions/{experiment_id}_{timestamp}/`

**Key Files**:
- `core/live_camera_service.py` - Service (446 lines)
- `ui/dialogs/live_analysis_dialog.py` - Dialog
- `io/live_stream_source.py` - Time-limited Camera wrapper

**Threading**:
- `_capture_loop()`: Frame acquisition from Camera
- `_processing_loop()`: Detection processing
- Integrated with `RecordingService` for timed sessions

**Data Flow**:
1. User configures via `LiveAnalysisDialog`
2. `LiveCameraService.start_session()` creates threads + preview
3. Capture thread: Camera → frame_queue
4. Processing thread: frame_queue → DetectorService → Recorder
5. Preview updates: LivePreviewWindow displays frames + detections
6. Auto-stop after duration via RecordingService

## ⚙️ Hardware

- **Arduino**: Optional, `arduino.port` in config
- **Camera**: `camera.index` (default: 0)
- **OpenVINO**: Auto-cached in `openvino_model_cache/`

## 🔗 Pre-Merge Checklist

```bash
# 1. Read relevant tests
cat tests/test_*.py

# 2. Run tests
poetry run pytest -q

# 3. Lint
poetry run ruff check .

# 4. Pre-commit
poetry run pre-commit run --all-files

# 5. Update docs if user-facing changes
```

## 💡 Pro Tips

- **Before coding**: Read existing tests first
- **DI everywhere**: Always inject `settings_obj`
- **Thread-safe**: Use `StateManager` for cross-thread state
- **Immutable schema**: Never reorder Parquet columns
- **Logging**: Use `structlog` with `domain.action.result`
- **UI updates**: Only via `root.after(0, ...)`
- **Zone scaling**: Always call `set_zones()` after dims known

---

**For full details**: See `CLAUDE.md` and linked documents above
