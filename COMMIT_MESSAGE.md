# Commit Message

## Title
fix(ui): correct interactive buttons position with dynamic pack positioning

## Description
Fix the visual positioning of interactive ROI editing buttons (Save/Discard) by adding proper positioning parameters to the dynamic pack() call. The buttons now correctly appear between the zone list and ROI inclusion parameters panel as intended.

## Problem
The interactive_buttons_frame was created in the correct code position (after zone list, before ROI parameters), but when dynamically shown via pack(), it appeared at the bottom of the panel instead of the intended position. This happened because pack() without positioning parameters always appends widgets to the end of their parent container.

## Solution
Added `before=self.roi_inclusion_frame` parameter to the pack() call in `setup_interactive_polygon()` method. This ensures the buttons are visually positioned correctly when shown dynamically.

## Changes

### Modified Files
- `src/zebtrack/ui/gui.py` (line ~5343)
  - Updated `interactive_buttons_frame.pack()` call with positioning parameter

### Code Change
```python
# Before
self.interactive_buttons_frame.pack(fill="x", padx=5, pady=5)

# After
self.interactive_buttons_frame.pack(fill="x", padx=5, pady=5, before=self.roi_inclusion_frame)
```

### Documentation
- Created `BUTTON_POSITION_FIX.md` with technical details

## Testing
All tests passing (12/12):
- `test_gui_zone_config_fixes.py` (5 tests)
- `test_gui_pipeline_indicators.py` (3 tests)
- `test_interactive_buttons_position.py` (2 tests)
- `test_roi_snap_indicator_arena_clamp.py` (2 tests)

## Impact
- **User Experience**: ROI editing buttons now appear in the logical position within the zone controls panel
- **UI Layout**: Maintains proper visual hierarchy between zone list, editing buttons, and ROI parameters
- **Compatibility**: No breaking changes, backward compatible

## Related
- Part of ROI editing workflow improvements
- Follows up on previous button repositioning attempt (code structure only)
- Complements ROI snap indicator arena clamping features

---

## Suggested Git Commit Message

```
fix(ui): correct interactive buttons position with dynamic pack positioning

Add `before=self.roi_inclusion_frame` parameter to interactive_buttons_frame.pack()
call in setup_interactive_polygon() method to ensure buttons appear in correct
visual position between zone list and ROI inclusion parameters.

Previous attempt only changed code creation order, but dynamic pack() without
positioning parameters was still appending to end of parent container.

Changes:
- src/zebtrack/ui/gui.py: Add positioning parameter to pack() call (line ~5343)
- BUTTON_POSITION_FIX.md: Technical documentation

Tests: All 12 GUI-related tests passing
```

---

## Alternative Short Commit Message

```
fix(ui): add positioning parameter to interactive buttons pack() call

Fixes visual position of Save/Discard ROI editing buttons by adding
before=self.roi_inclusion_frame to pack() call in setup_interactive_polygon().
```
