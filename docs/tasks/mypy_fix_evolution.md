# Task: Mypy Type Checking Fixes (Evolution)

This task tracks the progress of fixing `mypy` type checking errors across the ZebTrack-AI project to ensure code stability and type safety.

## 📊 Summary

- **Current Status**: In Progress
- **Total Files with Errors**: ~10
- **Total Initial Errors**: ~150+
- **Remaining Critical Errors**: 51 (mainly in `gui.py`)

## 🛠 Progress Tracking

### Phase 1: Core and Basic Scripts (Completed)

- [x] Fix `mypy` errors in `__main__.py` (Type casting for OpenVINO settings, `ui_coordinator` types).
- [x] Fix `mypy` errors in `main_view_model.py` (Added `view: Any`).
- [x] Fix `mypy` errors in `extract_dialogs_ast.py` (`None` checks for AST nodes).
- [x] Fix `mypy` errors in `audit_events.py` (defaultdict type annotations).
- [x] Fix `mypy` errors in `delegate_methods.py` (`None` operand errors).
- [x] Fix `mypy` errors in `docs/api/source/conf.py` (type annotation for `exclude_patterns`).
- [x] Fix `mypy` errors in `safe_gui_test_runner.py` (type annotation for `tests_by_file`).
- [x] Fix `mypy` errors in `update_gui_imports.py` (`None` checks for `end_lineno`).
- [x] Fix `mypy` errors in `validate_docs.py` (type annotations for `issues`).
- [x] Add `types-polib` to `pyproject.toml` dev-dependencies.
- [x] Fix errors in extracted dialogs (`template_dialog.py`, `subject_selection_dialog.py`).

### Phase 2: GUI and Complex Components (In Progress)

- [ ] Resolve 51 errors in `src/zebtrack/ui/gui.py`
  - [ ] Fix attribute errors (e.g., `analysis_profile_var`, `controls_canvas`).
  - [ ] Fix duplicate method definitions (e.g., `_filter_video_tree`, `_refresh_video_selector_tree`).
  - [ ] Fix `CanvasManager` missing `_render_last_analysis_frame` call.
  - [ ] Add missing type annotations to GUI callbacks.
- [ ] Verify `CanvasManager` and `CanvasRenderer` integration.

### Phase 3: Validation and Verification

- [ ] Run full project `mypy` scan.
- [ ] Run regression tests (`pytest -m "not (gui or slow)"`).
- [ ] Verify GUI functionality manually if possible.

## 📝 Current Action Item

- Fixing `src/zebtrack/ui/gui.py` attribute errors and duplicate definitions.
