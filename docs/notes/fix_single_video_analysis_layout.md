# Fix: Single Video Analysis Layout Issues

**Date**: 2025-10-21  
**Issue**: AttributeError and panel layout issues in single video analysis workflow

## Problems Identified

### 1. AttributeError: 'ApplicationGUI' object has no attribute 'fixed_button_frame'

**Error Log**:
```
File "src\zebtrack\ui\gui.py", line 9471, in setup_zone_definition_for_single_video
    self.fixed_button_frame,  # Add to the fixed button frame at bottom
    ^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'ApplicationGUI' object has no attribute 'fixed_button_frame'
```

**Root Cause**:
- The zone configuration tab was refactored to use the new `ZoneControlsWidget` component
- The old `_create_scrollable_controls_frame` method created a `fixed_button_frame` for buttons that should stay visible at the bottom
- The new `ZoneControlsWidget` didn't expose this frame
- Code in `setup_zone_definition_for_single_video` tried to add a button to `self.fixed_button_frame`, which no longer existed

### 2. Left Panel Layout Issue

**Problem**: When opening the single video analysis window, the left control panel was partially hidden, obscuring the scrollbar and buttons. Users had to manually resize the panel by dragging the sash.

**Root Cause**: The initial sash position (420px) was set via `after(10, ...)`, which sometimes didn't apply properly due to timing issues with widget realization.

## Solutions Implemented

### Fix 1: Add fixed_button_frame to ZoneControlsWidget

**File**: `src/zebtrack/ui/components/zone_controls.py`

**Change**:
```python
def _build_ui(self) -> None:
    """Build the zone controls widget UI."""
    from tkinter import Canvas
    from zebtrack.ui.window_utils import create_scrollbar

    # Create a frame for fixed buttons at the bottom (not scrollable)
    self.fixed_button_frame = ttk.Frame(self)
    self.fixed_button_frame.pack(side="bottom", fill="x", padx=5, pady=5)

    # Container for scrollable content
    self.controls_canvas = Canvas(self, highlightthickness=0)
    scrollbar = create_scrollbar(self, orient="vertical", command=self.controls_canvas.yview)
    
    # ... rest of the scrollable content setup
```

**Why**: This creates a non-scrollable frame at the bottom of the control panel where buttons that should always be visible can be placed (like the "Start Analysis" button).

### Fix 2: Expose fixed_button_frame in ApplicationGUI

**File**: `src/zebtrack/ui/gui.py`

**Change**:
```python
# ✨ NEW: Create ZoneControlsWidget instead of inline controls
self.zone_controls = ZoneControlsWidget(left_panel_frame, event_bus=self.event_bus)
self.zone_controls.pack(fill="both", expand=True)

# Keep reference to internal widgets for backward compatibility
# TODO: Migrate code to use ZoneControlsWidget API instead
self.zone_controls_frame = self.zone_controls.zone_controls_frame
self.fixed_button_frame = self.zone_controls.fixed_button_frame  # ← NEW
```

**Why**: This maintains backward compatibility by exposing the fixed button frame at the ApplicationGUI level, so existing code can continue to access `self.fixed_button_frame`.

### Fix 3: Improve Sash Positioning

**File**: `src/zebtrack/ui/gui.py`

**Change**:
```python
# Set initial sash position to 420 pixels for left panel width
# Increased to ensure template "Aplicar" button is fully visible
def _set_initial_sash():
    try:
        # Use update_idletasks to ensure geometry is calculated
        main_pane.update_idletasks()
        main_pane.sashpos(0, 420)
    except Exception:
        pass  # Sash position might fail if pane isn't fully realized yet

# Try multiple times with increasing delays to ensure it sticks
main_pane.after(10, _set_initial_sash)
main_pane.after(50, _set_initial_sash)
main_pane.after(100, _set_initial_sash)
```

**Why**: 
- Call `update_idletasks()` before setting sash position to ensure geometry is calculated
- Try multiple times with increasing delays to handle cases where the first attempt doesn't work
- This ensures the left panel width is correctly set even if widget realization is delayed

## Testing

Created `tests/test_zone_controls_fixed_frame.py` with two tests:

1. **test_zone_controls_has_fixed_button_frame**: Verifies that `ZoneControlsWidget` has a `fixed_button_frame` attribute and that buttons can be added to it

2. **test_gui_exposes_fixed_button_frame**: Verifies that `ApplicationGUI` properly exposes the `fixed_button_frame` from its `zone_controls` widget

Both tests pass successfully.

## Impact

### Fixed Issues:
✅ AttributeError when entering single video analysis workflow  
✅ Left panel width now correctly set on window open  
✅ Scrollbar and buttons are visible without manual resizing  

### Backward Compatibility:
✅ Existing code that accesses `self.fixed_button_frame` continues to work  
✅ No breaking changes to public APIs  

### Code Quality:
✅ Proper component encapsulation maintained  
✅ Clear separation between scrollable and fixed UI elements  
✅ Robust geometry management with retry logic  

## Files Modified

1. `src/zebtrack/ui/components/zone_controls.py` - Added fixed_button_frame
2. `src/zebtrack/ui/gui.py` - Exposed fixed_button_frame and improved sash positioning
3. `tests/test_zone_controls_fixed_frame.py` - New test file (created)

## Related Documentation

- Architecture: `docs/ARCHITECTURE.md` - MVVM and component structure
- Known Issues: `docs/KNOWN_ISSUES.md` - ttkbootstrap singleton issues
- Copilot Instructions: `.github/copilot-instructions.md` - Quick reference guide
