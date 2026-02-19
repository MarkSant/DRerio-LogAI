# ADR-004: Live Camera Display Divergence

**Status**: Accepted
**Decision Date**: November 2025
**Phases**: 6, 8 (Unification), 9 (Legacy Removal)

## Context

ZebTrack-AI has two distinct video analysis modes with fundamentally
different display requirements:

1. **Recorded Video Analysis**: Processes pre-recorded video files via
   `ProcessingWorker`, displaying frames through `CanvasManager` on the
   main Tkinter canvas using `Events.UI_DISPLAY_FRAME`.

2. **Live Camera Analysis**: Captures real-time frames via
   `LiveCameraService` with parallel capture + processing threads,
   displaying a preview in a separate `LivePreviewWindow`.

During Phase 6 (Live Camera Feature), both modes initially shared
`gui.py` thread implementations. Phase 8 (Unification) revealed critical
bugs from this coupling:

- Wrong camera selection (always camera 0)
- Multiple cameras activating simultaneously
- Preview failures from thread contention
- Analysis interval settings being ignored

## Decision

**Live Camera uses a separate `LivePreviewWindow` and `LiveCameraService`
instead of the main `CanvasManager` display pipeline.**

### Rationale

1. **Thread model divergence**: Recorded video uses a single
   `ProcessingWorker` with queue-based frame delivery. Live camera
   requires two daemon threads (`_capture_loop`, `_processing_loop`)
   operating in parallel with minimal latency.

2. **Window lifecycle**: The preview window is tied to the camera
   session's lifetime. It opens when analysis starts and closes when
   the session ends. This is fundamentally different from the main
   canvas, which persists across the entire application lifecycle.

3. **Frame rate constraints**: Live camera must maintain real-time
   frame rates (~30 fps), while recorded video can process at
   variable speed. Routing live frames through the same display
   pipeline as recorded video would add unnecessary indirection
   and latency.

4. **Resource isolation**: Live camera sessions need their own
   `Recorder` instance (lightweight recording), independent of the
   main analysis `Recorder`. Coupling them caused state pollution
   (Phase 8 bug #6).

### Architecture

```text
Recorded Video Path:
  VideoSource → ProcessingWorker → EventBus(UI_DISPLAY_FRAME) → CanvasManager

Live Camera Path:
  Camera → LiveCameraService → root.after() → LivePreviewWindow
                             → Recorder (lightweight, session-scoped)
```

### Legacy Code Removal (v3.0, Phase 9)

All legacy thread implementations in `gui.py` were removed:

- `_live_frame_capture_loop()` (~30 lines)
- `_live_processing_loop()` (~60 lines)
- `capture_thread` initialization and cleanup

All live camera functionality is exclusively through `LiveCameraService`.

## Consequences

### Positive

- 50% reduction in threads (4 → 2) for live camera sessions.
- 50% reduction in memory (eliminated duplicate frame buffers).
- Eliminated lock contention between capture and display threads.
- Clean separation of concerns: `LiveCameraService` owns the entire
  session lifecycle.
- Camera settings (`camera_index`, `analysis_interval_frames`) are
  now correctly respected.

### Negative

- Two distinct display codepaths must be maintained.
- UI changes to the main canvas do not automatically apply to the
  live preview window (e.g., overlay styles, zoom controls).
- Testing requires separate fixtures for live camera vs recorded video
  display scenarios.

### Migration Note

Code depending on the legacy `gui.py` thread system for live camera
functionality will fail as of v3.0. Use `LiveCameraService` API
exclusively.

## References

- `src/zebtrack/core/recording/live_camera_service.py`
- `src/zebtrack/ui/dialogs/live_analysis_dialog.py`
- `src/zebtrack/ui/dialogs/live_preview_window.py`
- `docs/archive/LIVE_CAMERA_UNIFICATION.md`
