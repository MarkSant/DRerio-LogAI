# ADR-003: Live Analysis Canvas Integration Fix (Canvas Preto)

**Status**: Implemented
**Date**: 2025-12-30
**Deciders**: Development Team
**Issue**: Canvas Preto bug - live frames not appearing in Analysis tab

## Context

During Phase 3 Live Analysis Integration, users reported that when starting live camera analysis, the frames were not appearing in the integrated Analysis tab. Instead, they saw either:

1. A blank/white canvas ("Canvas Preto")
2. External window opening when it shouldn't
3. No video frames being displayed

This was a critical blocker for Phases A & B consolidation.

## Root Cause Analysis

The bug had **3 distinct root causes**:

### 1. Event Publication Inside Wrong Block (PRIMARY BUG)

**Location**: `src/zebtrack/core/live_camera_service.py` lines ~1180-1210

**Problem**: The code to publish `UI_UPDATE_LIVE_FRAME` events was **inside** the `if self.preview_window and should_display:` block:

```python
# ❌ WRONG: Inside preview_window check
if self.preview_window and should_display:
    # ... update preview window ...

    if not self._use_external_preview and self.event_bus:
        self.event_bus.publish_event(Events.UI_UPDATE_LIVE_FRAME, {...})
```

**Impact**: When `use_external_preview=False`, no `preview_window` is created, so the entire block never executes, and events are never published to the canvas.

**Fix**: Moved event publication **outside** the `preview_window` block:

```python
# ✅ CORRECT: Outside preview_window check
if self.preview_window and should_display:
    # ... update preview window ...

# CRITICAL: Must be outside preview_window check!
if should_display and not self._use_external_preview and self.event_bus:
    self.event_bus.publish_event(Events.UI_UPDATE_LIVE_FRAME, {...})
```

### 2. Inverted Logic for use_external_preview (SEMANTIC BUG)

**Location**: `src/zebtrack/core/live_camera_service.py` line 361

**Problem**: Window creation logic was **inverted**:

```python
# ❌ WRONG: Created window when use_external_preview=False
if not use_external_preview and not getattr(...):
    self._create_preview_window(...)
```

**Fix**:

```python
# ✅ CORRECT: Create window when use_external_preview=True
if use_external_preview and not getattr(...):
    self._create_preview_window(...)
```

### 3. Variable Name Error (RUNTIME BUG)

**Location**: `src/zebtrack/core/live_camera_service.py` lines 1191, 1207

**Problem**: Logs referenced `frame_count` but the variable was named `frame_number` (from queue).

**Fix**: Changed all references from `frame_count` → `frame_number`

## Decision

Implement all three fixes:

1. **Move event publication outside preview_window block** - Ensures events are published regardless of window creation
2. **Fix inverted use_external_preview logic** - Ensures window is created only when needed
3. **Fix variable naming** - Prevents runtime NameError crashes

## Consequences

### Positive

- ✅ Live frames now display correctly in integrated Analysis tab
- ✅ External window no longer opens unexpectedly
- ✅ No runtime crashes from undefined variables
- ✅ Proper separation of concerns: window vs canvas display
- ✅ User can see animal detections in real-time

### Negative

- ⚠️ Requires careful testing to prevent regression
- ⚠️ Need to document `use_external_preview` semantics clearly

### Neutral

- Statistics display is a separate concern (to be addressed later)
- `analysis_active` flag management still needs review

## Implementation

**Files Changed**:

1. `src/zebtrack/core/live_camera_service.py`
   - Line 361: Fixed window creation logic
   - Lines 1180-1210: Moved event publication outside block
   - Lines 1191, 1207: Fixed variable names

2. `src/zebtrack/ui/event_bus.py`
   - Added `RECORDING_STARTED` to suppression list (fire-and-forget event)

3. `src/zebtrack/coordinators/processing_coordinator.py`
   - Line 3143: Changed polygon validation from `error` to `debug` level

**Tests Added**:

- `tests/test_live_analysis_integration.py` - Comprehensive regression tests

**Verification**:

```bash
# Run live analysis tests
poetry run pytest tests/test_live_analysis_integration.py -v

# Full test suite
poetry run pytest -q
```

## Architecture Notes

### Event Flow (Correct)

```text
LiveCameraService._processing_loop
  ↓ (frame ready)
  ↓ should_display=True AND use_external_preview=False
  ↓
EventBus.publish_event(UI_UPDATE_LIVE_FRAME)
  ↓
CanvasManager._on_live_frame_update
  ↓
CanvasManager.update_video_frame
  ↓ (if analysis_active=True)
  ↓
GUI.analysis_display_widget.update_frame
  ↓
User sees frames in Analysis tab ✅
```

### Window vs Canvas Decision Matrix

| `use_external_preview` | Result |
| --- | --- |
| `False` | NO window, publish to EventBus → Canvas |
| `True` | CREATE window, NO EventBus publication |

### Critical Conditions

For frames to display in canvas, ALL must be true:

1. `should_display = (frame_number % display_interval_frames) == 0`
2. `use_external_preview = False`
3. `event_bus is not None`
4. `analysis_active = True` (in GUI)
5. `analysis_display_widget exists` (in GUI)

## Related Issues

- Canvas Preto bug (original report)
- External window appearing unexpectedly
- Statistics not updating (separate issue - TODO)
- Camera warmup failures (addressed with 30-frame stabilization)

## References

- Phase 3 Live Analysis Integration Plan
- `docs/architecture/ARCHITECTURE.md`
- `docs/reference/REFERENCE_GUIDE.md`
- `.github/copilot-instructions.md` - Quick Decision Trees

## Lessons Learned

1. **Scope Matters**: Code inside `if preview_window:` won't execute without a window
2. **Semantic Bugs**: Inverted boolean logic is hard to spot but critical
3. **Variable Naming**: Use consistent names from queue source
4. **Test Early**: Integration tests prevent these issues
5. **Log Levels**: Use `debug` for expected initialization states, not `error`

## Future Considerations

1. Consider adding `analysis_active` auto-detection during live sessions
2. Review statistics display requirements (separate feature)
3. Add visual indicator when frames are being received
4. Consider metrics for frame drop rates vs display rates
