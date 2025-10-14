# Interactive Buttons Dynamic Packing Fix

## Issue
After moving the `interactive_buttons_frame` creation to the correct position in code (after zone list, before ROI inclusion parameters), the buttons still appeared in the wrong visual position in the UI.

## Root Cause
The `interactive_buttons_frame` uses dynamic visibility - it's created but not initially packed. When edit mode is activated via `setup_interactive_polygon()`, the frame is packed with:

```python
self.interactive_buttons_frame.pack(fill="x", padx=5, pady=5)
```

Without positioning parameters, tkinter's `pack()` appends the widget to the end of its parent container, regardless of where it was created in code.

## Solution
Added the `before=self.roi_inclusion_frame` parameter to the pack() call:

```python
self.interactive_buttons_frame.pack(
    fill="x", padx=5, pady=5, before=self.roi_inclusion_frame
)
```

This ensures that when the buttons are dynamically shown, they appear between the zone list and the ROI inclusion parameters panel, as intended.

## Implementation Details

### Modified File
- `src/zebtrack/ui/gui.py`

### Changed Method
- `setup_interactive_polygon()` at line ~5343

### Before
```python
# Show the save/discard buttons
if self.interactive_buttons_frame:
    self.interactive_buttons_frame.pack(
        fill="x", padx=5, pady=5
    )
```

### After
```python
# Show the save/discard buttons
if self.interactive_buttons_frame:
    self.interactive_buttons_frame.pack(
        fill="x", padx=5, pady=5, before=self.roi_inclusion_frame
    )
```

## UI Layout Hierarchy
```
zone_controls_frame (parent)
├─ zone_listbox_frame
├─ interactive_buttons_frame ← Dynamically shown here
└─ roi_inclusion_frame
```

## Testing
- Existing tests continue to pass (9/9)
- `tests/test_interactive_buttons_position.py`: Validates code structure
- `tests/test_roi_snap_indicator_arena_clamp.py`: Validates clamping logic

## User-Visible Changes
When entering ROI edit mode:
- **Before**: Save/Discard buttons appeared at the bottom, near the "Start Analysis" button
- **After**: Save/Discard buttons appear between the zone list and ROI inclusion parameters

## Technical Notes
- This demonstrates the importance of positioning parameters (`before=` or `after=`) in dynamic tkinter layouts
- Code creation order alone doesn't determine visual position when using `pack_forget()` / `pack()` patterns
- The `before=` parameter references another widget in the same parent container to establish relative positioning

## Related Documentation
- `BUTTON_REPOSITION_SUMMARY.md`: Initial attempt at repositioning (code structure only)
- `docs/ARCHITECTURE.md`: Overall GUI architecture
- `.github/copilot-instructions.md`: Project coding guidelines

## Date
2025-01-XX
