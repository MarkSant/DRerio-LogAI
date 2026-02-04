# ZebTrack-AI Agent Playbook - COMPACT VERSION

## 🎯 Core Facts
- **Product**: Tkinter app (DRerio LogAI); package `zebtrack`
- **Runtime**: Python 3.12+, Poetry; `poetry run zebtrack` or `python -m zebtrack`
- **Debug**: `.vscode/launch.json` (F5); breakpoints in `docs/QUICK_DEBUG_GUIDE.md`
- **Config**: `from zebtrack import settings`; `config.yaml` < `config.local.yaml`

## 🏗️ Architecture (10 sec)
```text
VideoSource → DetectorService → ProcessingWorker → Recorder
                ↓
           StateManager → MainViewModel → UI (root.after only)
```

## 📁 Quick File Map
| Need | File |
|------|------|
| Entry | `zebtrack/__main__.py` |
| Config | `zebtrack/settings.py` |
| State | `core/state_manager.py` |
| ViewModel | `core/main_view_model.py` |
| Detector | `core/detector_service.py` |
| Video | `io/video_source.py` |
| Recorder | `io/recorder.py` |
| Wizard | `ui/wizard/wizard_manager.py` |
| Project | `core/project_manager.py` |

## ⚡ Token-Efficient Workflow

### User Reports Issue
1. **Check test first**: `tests/test_<module>.py` shows expected behavior
2. **Common issues**:
   - UI freeze → `ui_coordinator.py` + `root.after` pattern
   - Detection wrong → `detector_service.py` → zones → plugin
   - Wizard stuck → `ProjectWorkflowService.validate_step()`
   - Data mismatch → `recorder.py` schema + `tests/test_recorder.py`

### Before Changing Code
1. Read relevant test file
2. Check existing similar fix
3. Use semantic_search if unsure

### After Changes
```bash
pytest -q              # Fast suite
ruff check <file>      # Lint
```

## 🐛 Common Pitfalls
1. ❌ **Zone scaling**: Always call `Detector.set_zones()` with video dimensions
2. ❌ **UI blocking**: Must use `root.after(0, ...)` for async updates
3. ❌ **Parquet schema**: Never add columns mid-stream
4. ❌ **Track IDs**: Use `detection.get("track_id", -1)` - may be missing
5. ❌ **Thread safety**: Update via `StateManager`, not direct UI mutation

## 📝 Key Components (Reference Only)
- **MVVM**: `MainViewModel` orchestrates; `StateManager` thread-safe state
- **Wizard**: `ui/wizard/` → `ProjectWorkflowService` → 5 steps (1150×550)
- **Project data**: `ProjectManager` stores ROI/arena/intervals; rescale zones
- **Processing**: `ProcessingMode` (multi/single); overlay locks when single
- **Hardware**: `hardware_detection`; OpenVINO if XML in `openvino_model_cache/`
- **Logging**: `structlog` with `domain.action.result` keys
- **Data schema**: `timestamp,frame,track_id,x1,y1,x2,y2,confidence` + centers/cm
- **Analysis**: `analysis_service.py` → `behavior.py` + `reporter.py`
- **Plugins**: Extend `plugins/base.py`; register in `__init__.py`

## 🧪 Testing
- Fast: `pytest -q` | GUI: `pytest -m gui -n0` | Slow: `pytest -m slow`
- Coverage: `pytest --cov=zebtrack --cov-report=html` (70% min)
- Fixtures: `tests/fixtures/`, `test_scenarios/`
- Lint: `ruff check .` (line 100) | Format: `ruff format .`
- Pre-commit: `pre-commit run --all-files`

## 🎓 Strategy Summary
**GOAL**: Minimize token usage while maximizing accuracy

1. **Read test first** → understand contract
2. **Use quick file map** → navigate fast
3. **Check common pitfalls** → avoid known issues
4. **Follow existing patterns** → consistency
5. **Verify with tests** → ensure correctness

## 📚 Full Docs
- Architecture: `docs/ARCHITECTURE.md`
- Reference: `docs/REFERENCE_GUIDE.md`
- Debug Guide: `docs/QUICK_DEBUG_GUIDE.md`
- Transition: `TRANSITION_NOTE.md`
- Tests: `README_TESTS.md`
