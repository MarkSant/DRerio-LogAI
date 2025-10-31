# FASE 6 - ConfigEditorWidget Extraction TODO

## 📋 Context

This document provides detailed instructions for extracting the **ConfigEditorWidget** component from `gui.py` as the final step of FASE 6: Componentização da UI.

### Current Status (Completed)

**Branch**: `claude/refactor-di-architecture-011CUfeRKwMRFBKXUgG8t7iL`

**Commits**:
1. `189e59f` - LiveConfigDialog extraction (166 lines)
2. `2a905d9` - ArduinoDashboardWidget extraction (323 lines)
3. `1d11bbb` - AnalysisDisplayWidget extraction (373 lines)

**Results**:
- **Reduction**: 10,753 → 10,206 lines (-547 lines, -5.1%)
- **Components created**: 3 robust, tested widgets
- **Code extracted**: 862 lines moved to reusable components
- **Quality**: ✅ All syntax checks and linting passed

---

## 🎯 Mission: Extract ConfigEditorWidget

### Objective

Create a new **ConfigEditorWidget** component to encapsulate the advanced configuration editor tab, currently implemented as `_create_configuration_tab()` in `gui.py`.

### Estimated Impact

- **Lines to extract**: ~270 lines (method) + ~150 lines (helpers) = **~420 lines**
- **Expected reduction**: 10,206 → ~9,786 lines (-420 lines, additional -4.1%)
- **Complexity**: **VERY HIGH** - touches critical configuration system
- **Risk level**: **VERY HIGH** - requires extensive testing

---

## 📊 Detailed Analysis

### Current Implementation Location

**File**: `src/zebtrack/ui/gui.py`

**Main method**: `_create_configuration_tab()` (starts at line ~1505)

**Supporting methods**:
- `_reload_config_editor_values()` (line ~1778) - 110 lines
- `_on_save_global_config()` (line ~1895) - 95 lines
- `_on_reset_global_config_form()` (line ~1887) - 8 lines
- `_extract_setting()` (line ~867) - 19 lines (static utility)
- `_on_roi_rule_change()` (line ~4171) - 10 lines

### State Variables (15+)

Located in `ApplicationGUI.__init__()`:

```python
# Video Processing
self.config_fps_var = StringVar(value="30")
self.config_processing_interval_var = StringVar(value="10")
self.config_processing_offset_var = StringVar(value="0")

# Trajectory Smoothing
self.config_window_length_var = StringVar(value="7")
self.config_polyorder_var = StringVar(value="3")

# Recorder Settings
self.config_flush_interval_var = StringVar(value="30")
self.config_flush_rows_var = StringVar(value="10000")

# ROI Parameters
self.roi_inclusion_rule_var = StringVar(value="centroid_in")
self.roi_buffer_radius_var = StringVar(value="0")
self.roi_overlap_ratio_var = StringVar(value="0.5")

# Internal state
self._config_roi_rule_widgets: list[ttk.Combobox] = []
self.config_tab_frame: ttk.Frame | None = None
```

### UI Sections (5 complex frames)

1. **Introduction text** - Explains config.yaml editing
2. **Video Processing** (LabelFrame)
   - FPS de saída
   - Intervalo de processamento
   - Offset inicial
3. **Trajectory Smoothing** (LabelFrame)
   - Janela de Suavização
   - Ordem do Polinômio
   - Validation info
4. **Recorder Settings** (LabelFrame)
   - Flush automático (seconds)
   - Limite de linhas por flush
5. **ROI Parameters** (LabelFrame)
   - Regra de inclusão (combobox with 4 options)
   - Raio de buffer
   - Sobreposição mínima
   - Conditional logic based on selected rule
6. **Action Buttons**
   - Recarregar valores atuais
   - Salvar em config.local.yaml

### Critical Dependencies

```python
import zebtrack.settings as settings_module

# Used by widget logic:
- settings_module.settings (global singleton)
- settings_module.load_settings()
- settings_module.save_local_config()
- settings_module.Settings (Pydantic model)
```

### Complex Logic Patterns

1. **Nested Setting Extraction**:
```python
def _extract_setting(root: Any, path: tuple[str, ...], default: Any) -> Any:
    """Navigate nested settings dict/object"""
    current = root
    for key in path:
        if hasattr(current, key):
            current = getattr(current, key)
        elif isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current
```

2. **Pydantic Validation on Save**:
```python
def _on_save_global_config(self) -> None:
    # Parse all form values
    # Create nested dict structure
    # Validate with Pydantic Settings model
    # Save to config.local.yaml
    # Reload settings globally
    # Handle ValidationError with detailed messages
```

3. **Conditional ROI Rule UI**:
```python
def _on_roi_rule_change(self, event=None):
    """Update UI state based on selected inclusion rule"""
    # Enable/disable buffer radius based on rule
    # Update help text dynamically
```

---

## 🏗️ Implementation Strategy

### Recommended Approach: Hybrid Pattern

**Rationale**: The configuration system is too critical to refactor all at once. Use a hybrid approach that extracts the UI while keeping complex logic in the controller layer.

### Phase 1: Create ConfigEditorWidget (UI Layer)

**File**: `src/zebtrack/ui/components/config_editor.py`

**Responsibilities**:
- Build the UI structure (frames, labels, entries, comboboxes)
- Manage StringVar instances for all form fields
- Provide public API methods for getting/setting values
- Emit events for user actions (save clicked, reset clicked)

**Public API**:
```python
class ConfigEditorWidget(BaseWidget):
    def get_values(self) -> dict:
        """Return all form values as nested dict"""

    def set_values(self, values: dict) -> None:
        """Populate form from nested dict"""

    def reset(self) -> None:
        """Reset to default values"""

    # Events emitted:
    # - config.save_requested: User clicked save
    # - config.reset_requested: User clicked reset
```

### Phase 2: Keep Logic in ApplicationGUI

**Keep these methods in `gui.py`**:
- `_reload_config_editor_values()` - loads from settings
- `_on_save_global_config()` - validates and saves
- `_extract_setting()` - utility method
- Connect widget events to these handlers

**Why**: These methods interact deeply with the global settings system and require extensive validation. Keeping them in `gui.py` reduces risk.

---

## 📝 Step-by-Step Instructions

### Step 1: Create ConfigEditorWidget

**File**: `src/zebtrack/ui/components/config_editor.py`

**Template structure**:

```python
"""
Configuration editor widget component - advanced settings editor.

Provides a form-based interface for editing application configuration
parameters across multiple categories: video processing, trajectory
smoothing, recorder settings, and ROI parameters.
"""

from tkinter import StringVar, ttk
import structlog
from zebtrack.ui.components.base import BaseWidget
from zebtrack.ui.event_bus import EventBus

log = structlog.get_logger()


class ConfigEditorWidget(BaseWidget):
    """
    Reusable configuration editor widget.

    Provides:
    - Video processing settings (FPS, interval, offset)
    - Trajectory smoothing (window length, polynomial order)
    - Recorder settings (flush interval, row limit)
    - ROI parameters (inclusion rule, buffer, overlap)
    - Action buttons (save, reset)

    Events emitted:
    - config.save_requested: User clicked save (payload: dict of values)
    - config.reset_requested: User clicked reset
    - config.roi_rule_changed: ROI rule selection changed
    """

    def __init__(self, parent, event_bus: EventBus | None = None, **kwargs):
        # Initialize all StringVar instances
        self.fps_var = StringVar(value="30")
        self.processing_interval_var = StringVar(value="10")
        # ... etc for all 10+ variables

        # ROI rule widgets list for conditional enable/disable
        self._roi_rule_widgets: list[ttk.Widget] = []

        super().__init__(parent, event_bus=event_bus, **kwargs)

    def _build_ui(self) -> None:
        """Build the configuration editor UI."""
        self._build_intro()
        self._build_video_processing_section()
        self._build_trajectory_smoothing_section()
        self._build_recorder_section()
        self._build_roi_section()
        self._build_action_buttons()

    def _build_intro(self) -> None:
        """Build introduction text."""
        pass

    def _build_video_processing_section(self) -> None:
        """Build video processing settings frame."""
        pass

    # ... etc for each section

    def get_values(self) -> dict:
        """Get all form values as nested dict matching Settings structure."""
        return {
            "video_processing": {
                "fps": int(self.fps_var.get()),
                "processing_interval": int(self.processing_interval_var.get()),
                "processing_offset": int(self.processing_offset_var.get()),
            },
            "trajectory": {
                "savgol_window_length": int(self.window_length_var.get()),
                "savgol_polyorder": int(self.polyorder_var.get()),
            },
            # ... etc
        }

    def set_values(self, values: dict) -> None:
        """Populate form from nested dict."""
        # Extract and set each StringVar
        pass

    def _on_save_clicked(self) -> None:
        """Handle save button click."""
        try:
            values = self.get_values()
            self.emit_event("config.save_requested", {"values": values})
        except ValueError as e:
            self.emit_event("config.validation_error", {"error": str(e)})

    def _on_reset_clicked(self) -> None:
        """Handle reset button click."""
        self.emit_event("config.reset_requested", {})

    def _on_roi_rule_changed(self, event=None) -> None:
        """Handle ROI rule combobox change."""
        selected_rule = self.roi_inclusion_rule_var.get()
        self.emit_event("config.roi_rule_changed", {"rule": selected_rule})
        # Update UI state based on rule
```

### Step 2: Update components/__init__.py

Add to imports and `__all__`:
```python
from zebtrack.ui.components.config_editor import ConfigEditorWidget

__all__ = [
    # ... existing
    "ConfigEditorWidget",
]
```

### Step 3: Refactor gui.py

**In `__init__()`**, replace config variables:
```python
# OLD (delete these 15+ lines):
self.config_fps_var = StringVar(...)
# ... all config vars

# NEW (single line):
self.config_editor_widget: ConfigEditorWidget | None = None
```

**Replace `_create_configuration_tab()`**:
```python
def _create_configuration_tab_widget(self) -> None:
    """Creates the configuration tab using ConfigEditorWidget."""
    if not self.notebook:
        return

    # Create widget
    self.config_editor_widget = ConfigEditorWidget(
        self.notebook,
        event_bus=self.event_bus,
    )

    # Add to notebook
    self.notebook.add(self.config_editor_widget, text="Config. Avançadas")

    # Connect events
    if self.event_bus:
        self._event_bus_handlers["config.save_requested"] = (
            lambda data: self._on_save_global_config_from_widget(data["values"])
        )
        self._event_bus_handlers["config.reset_requested"] = (
            lambda data: self._on_reset_global_config_form_widget()
        )
        self._event_bus_handlers["config.roi_rule_changed"] = (
            lambda data: self._on_roi_rule_change_widget(data["rule"])
        )

    # Load current values
    self._reload_config_editor_values_widget()
```

**Adapt helper methods** to work with widget:
```python
def _reload_config_editor_values_widget(self) -> None:
    """Load current settings into widget."""
    current = settings_module.settings or settings_module.load_settings()

    values = {
        "video_processing": {
            "fps": self._extract_setting(current, ("video_processing", "fps"), 30),
            # ... etc
        },
        # ... all sections
    }

    if self.config_editor_widget:
        self.config_editor_widget.set_values(values)

def _on_save_global_config_from_widget(self, values: dict) -> None:
    """Validate and save config from widget values."""
    try:
        # Existing validation logic from _on_save_global_config
        # but using values dict instead of StringVar.get()

        # Save to config.local.yaml
        settings_module.save_local_config(values)

        # Reload
        settings_module.settings = settings_module.load_settings()

        messagebox.showinfo("Sucesso", "Configurações salvas em config.local.yaml")

    except ValidationError as e:
        # Show detailed error
        error_msg = "\n".join([f"• {err['loc']}: {err['msg']}" for err in e.errors()])
        messagebox.showerror("Erro de Validação", error_msg)
    except Exception as e:
        messagebox.showerror("Erro", f"Falha ao salvar: {str(e)}")
```

### Step 4: Update Tab Creation Call

In `_build_project_workspace()`:
```python
# OLD:
self._create_configuration_tab()

# NEW:
self._create_configuration_tab_widget()
```

### Step 5: Remove Old Method

Delete the entire `_create_configuration_tab()` method (~270 lines).

---

## ⚠️ Critical Considerations

### 1. Pydantic Validation

The configuration system uses **Pydantic v2** with strict validation:

```python
from zebtrack.settings import Settings

# All config changes must pass this:
validated = Settings(**config_dict)
```

**Common validation errors**:
- `savgol_window_length` must be odd
- `savgol_polyorder` must be < window_length
- `processing_offset` must be < processing_interval
- ROI buffer radius required when rule is `centroid_in_on_buffered_roi`

**Testing requirement**: Test all validation edge cases.

### 2. Settings Reload Side Effects

When `settings_module.save_local_config()` is called:
- Global singleton `settings_module.settings` is updated
- All components that cache settings must reload
- Project manager may need to re-validate project data

**Testing requirement**: Verify no side effects on active projects.

### 3. Backward Compatibility

Some code in `gui.py` may directly access config StringVars:
```bash
# Search for direct access:
grep -n "self.config_.*_var" src/zebtrack/ui/gui.py
```

**Migration requirement**: Update all direct accesses to use widget API.

### 4. ROI Rule Conditional Logic

The UI behavior changes based on selected ROI inclusion rule:

```python
# When "centroid_in_on_buffered_roi" is selected:
# - Enable buffer_radius field
# - Make it required (>0)

# When "bbox_intersects" or "seg_overlap":
# - Enable overlap_ratio field
# - Range: 0.0 to 1.0

# When "centroid_in":
# - Disable both extra fields
```

**Implementation note**: This logic should be in the widget's `_on_roi_rule_changed()` method.

---

## 🧪 Testing Strategy

### Unit Tests

Create: `tests/ui/components/test_config_editor.py`

**Test cases**:
1. Widget initialization with default values
2. `get_values()` returns correct nested dict structure
3. `set_values()` populates all form fields correctly
4. Event emission on save/reset button clicks
5. ROI rule change triggers conditional UI updates
6. Invalid input handling (non-numeric, out of range)

### Integration Tests

Extend: `tests/test_wizard_integration.py` or create new file

**Test scenarios**:
1. Load project → Open config tab → Values match project config
2. Modify values → Save → Verify config.local.yaml updated
3. Modify values → Reset → Verify form restored to original
4. Invalid values → Save → Error dialog shown, config unchanged
5. Change ROI rule → Verify dependent fields enabled/disabled

### Manual Testing Checklist

```
[ ] Open config tab - all sections render correctly
[ ] Load existing project - form populated with project settings
[ ] Modify video processing settings - save successful
[ ] Modify trajectory smoothing - validation works (odd window, polyorder < window)
[ ] Modify recorder settings - save successful
[ ] Change ROI rule to "centroid_in" - extra fields disabled
[ ] Change ROI rule to "centroid_in_on_buffered_roi" - buffer field enabled and required
[ ] Change ROI rule to "bbox_intersects" - overlap field enabled
[ ] Enter invalid values (negative, non-numeric) - validation catches
[ ] Click reset - form restored to current settings
[ ] Click save with valid values - config.local.yaml updated
[ ] Restart app - saved settings persist
```

---

## 📦 Deliverables

### 1. New Files

- `src/zebtrack/ui/components/config_editor.py` (~400 lines)
- `tests/ui/components/test_config_editor.py` (~200 lines)

### 2. Modified Files

- `src/zebtrack/ui/components/__init__.py` (add export)
- `src/zebtrack/ui/gui.py` (reduce ~420 lines)

### 3. Expected Results

- **Line reduction**: 10,206 → ~9,786 lines (-420 lines, -4.1%)
- **Total FASE 6 reduction**: 10,753 → ~9,786 lines (-967 lines, -9.0%)
- **All tests passing**: pytest coverage maintained at 70%+
- **No regressions**: All existing config functionality works

---

## 🚀 Git Workflow

### Branch Strategy

**New branch** (branching from `claude/refactor-di-architecture-011CUfeRKwMRFBKXUgG8t7iL`):
```bash
git checkout claude/refactor-di-architecture-011CUfeRKwMRFBKXUgG8t7iL
git checkout -b claude/fase6-configeditor-widget
```

### Commit Strategy

**Recommended approach**: Multiple small commits

1. **Commit 1**: Create ConfigEditorWidget (UI only)
   ```
   refactor(ui): create ConfigEditorWidget component structure

   Create new ConfigEditorWidget with all UI sections and form fields.
   Widget provides get_values/set_values API but does not handle
   persistence logic yet.
   ```

2. **Commit 2**: Integrate widget into gui.py
   ```
   refactor(ui): integrate ConfigEditorWidget into ApplicationGUI

   Replace _create_configuration_tab with _create_configuration_tab_widget.
   Connect widget events to existing save/reset handlers.
   ```

3. **Commit 3**: Remove old method
   ```
   refactor(ui): remove _create_configuration_tab method

   Delete old inline config tab creation method (270 lines removed).
   gui.py: 10,206 → 9,786 lines (-420 lines, -4.1%)
   ```

4. **Commit 4**: Add tests
   ```
   test(ui): add ConfigEditorWidget unit tests

   Add comprehensive tests for widget initialization, value
   get/set, event emission, and ROI rule conditional logic.
   ```

### Push and PR

```bash
git push -u origin claude/fase6-configeditor-widget
```

**PR Title**: `refactor(ui): extract ConfigEditorWidget - complete FASE 6 componentização`

**PR Description**:
```markdown
## Summary

Extracts ConfigEditorWidget as the final component of FASE 6: Componentização da UI.

## Changes

- Create `config_editor.py` with ConfigEditorWidget (~400 lines)
- Update `gui.py` to use widget (-420 lines)
- Add comprehensive unit tests
- Total FASE 6 reduction: 10,753 → 9,786 lines (-967 lines, -9.0%)

## Testing

- [ ] All unit tests pass
- [ ] Manual testing: config load/save/reset flows
- [ ] Validation: Pydantic errors handled correctly
- [ ] ROI rule conditional logic works
- [ ] No regressions in existing config functionality

## Related

- Completes FASE 6 started in commits 189e59f, 2a905d9, 1d11bbb
- Previous extractions: LiveConfigDialog, ArduinoDashboardWidget, AnalysisDisplayWidget
```

---

## 📚 Reference Materials

### Existing Component Patterns

Study these completed components for consistent patterns:

1. **LiveConfigDialog** (`src/zebtrack/ui/dialogs/live_config_dialog.py`)
   - Simple dialog pattern
   - Device detection logic
   - Form validation

2. **ArduinoDashboardWidget** (`src/zebtrack/ui/components/arduino_dashboard.py`)
   - BaseWidget inheritance
   - Event emission pattern
   - Public API methods (append_log, update_status, etc.)

3. **AnalysisDisplayWidget** (`src/zebtrack/ui/components/analysis_display.py`)
   - Complex multi-section UI
   - Progress tracking
   - Conditional visibility (show/hide progress)

### Key Files to Review

- `src/zebtrack/ui/components/base.py` - BaseWidget interface
- `src/zebtrack/ui/event_bus.py` - Event system
- `src/zebtrack/settings.py` - Pydantic Settings model (study structure)
- `config.yaml` - Default configuration (understand nesting)

### Settings System Documentation

The widget must match the structure defined in `Settings` Pydantic model:

```python
class VideoProcessingSettings(BaseModel):
    fps: int = 30
    processing_interval: int = 10
    processing_offset: int = 0

class TrajectorySettings(BaseModel):
    savgol_window_length: int = 7
    savgol_polyorder: int = 3

class RecorderSettings(BaseModel):
    auto_flush_interval_s: int = 30
    flush_row_limit: int = 10000

class ROISettings(BaseModel):
    default_inclusion_rule: str = "centroid_in"
    default_buffer_radius: int = 0
    default_overlap_ratio: float = 0.5

class Settings(BaseModel):
    video_processing: VideoProcessingSettings
    trajectory: TrajectorySettings
    recorder: RecorderSettings
    roi: ROISettings
    # ... etc
```

---

## ⏱️ Estimated Effort

**Complexity**: Very High
**Risk**: Very High
**Estimated time**: 3-4 hours for experienced developer

**Breakdown**:
- Widget creation: 1.5 hours
- Integration and refactoring: 1 hour
- Testing: 1 hour
- Bug fixes and edge cases: 0.5-1 hour

---

## 🎯 Success Criteria

### Functional Requirements

- [x] ConfigEditorWidget renders all 5 configuration sections
- [x] All form fields are editable
- [x] Save button validates and persists to config.local.yaml
- [x] Reset button reloads current settings
- [x] ROI rule combobox triggers conditional UI updates
- [x] Invalid inputs show clear validation errors
- [x] Backward compatibility maintained

### Quality Requirements

- [x] All unit tests pass (70%+ coverage maintained)
- [x] No linting errors (ruff check passes)
- [x] No syntax errors (py_compile passes)
- [x] No regressions in existing tests
- [x] Manual testing checklist completed

### Performance Requirements

- [x] Config tab loads in <500ms
- [x] Form validation completes in <100ms
- [x] Save operation completes in <1s

---

## 🆘 Troubleshooting

### Common Issues

**Issue 1**: Validation errors on save
- **Cause**: Form values don't match Pydantic types
- **Solution**: Ensure all `int()` conversions before creating dict
- **Example**: `int(self.fps_var.get().strip())`

**Issue 2**: ROI rule conditional logic not working
- **Cause**: Event handler not connected
- **Solution**: Verify `<<ComboboxSelected>>` binding in `_build_roi_section()`

**Issue 3**: Settings not persisting
- **Cause**: config.local.yaml not being written
- **Solution**: Check `settings_module.save_local_config()` permissions

**Issue 4**: Circular import errors
- **Cause**: Importing Settings model in widget
- **Solution**: Keep Settings import in gui.py, not in widget

### Debug Commands

```bash
# Check current line count
wc -l src/zebtrack/ui/gui.py

# Find all config var references
grep -n "self.config_.*_var" src/zebtrack/ui/gui.py

# Test widget import
poetry run python -c "from zebtrack.ui.components import ConfigEditorWidget; print('✓ Import successful')"

# Run syntax check
poetry run python -m py_compile src/zebtrack/ui/components/config_editor.py

# Run linting
poetry run ruff check src/zebtrack/ui/components/config_editor.py

# Run specific tests
poetry run pytest tests/ui/components/test_config_editor.py -v
```

---

## 📞 Contact & Support

If you encounter issues during implementation:

1. **Review completed components** for patterns
2. **Check CLAUDE.md** for project-specific guidelines
3. **Test incrementally** - don't wait until the end
4. **Ask for clarification** if instructions are unclear

---

## 🏁 Final Notes

This is the **final component extraction** of FASE 6. Upon completion:

- ✅ 4 major components extracted
- ✅ ~1,000 lines removed from gui.py (~9% reduction)
- ✅ UI fully modularized and testable
- ✅ FASE 6 objective achieved

**Good luck! 🚀**
