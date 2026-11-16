# F2 UI dialogs: fixes (TASK-087)

Follow-up to [`2026-11_F2_ui_dialogs.md`](2026-11_F2_ui_dialogs.md): the defects that file
reported and this pass fixed. One row per defect. Every fix has its test (the strict-xfail,
turned into a normal test, or a new one) and one block at the end of
`scripts/mutation_catalog.yaml` with no survivor.

| Id | Where | Root cause | Fix | Test | Mutation block | Status |
| -- | ----- | ---------- | --- | ---- | -------------- | ------ |
| F2-UI-002 | `core/recording/frame_processing_pipeline.py:1195` (call) vs `ui/dialogs/multi_aquarium_live_preview_window.py` | The pipeline calls `preview_window.update_frame(frame, detections, recorded_count)` on whichever window the camera handler built; `MultiAquariumLivePreviewWindow` only had `update_aquarium_frame`, which nothing called (A2-D-330). | The window gains `update_frame` with the same signature as `LivePreviewWindow.update_frame`. The pure `build_panel_views()` splits the whole camera frame per aquarium (crop to the region, detections placed by their centre, boxes drawn in crop coordinates, shared frame never painted on); the optional `aquarium_regions` constructor argument supplies the regions, an aquarium without one shows the whole frame. The call site is NOT touched. | `tests/ui/dialogs/test_multi_aquarium_live_preview_window.py` (`TestBuildPanelViews`, `TestUpdateFrame`, `TestUpdateFrameOnScreen`, `TestRegionHelpers`); the strict-xfail is gone | `multi_aquarium_preview_update_frame` (15/15) | fixed, with the finding below reported |

## Reported, not changed

### F2-UI-002: the multi-aquarium window is never built in production

`camera_connection_handler._create_preview_window` (`core/recording/camera_connection_handler.py:232-246`)
picks the window with `isinstance(self.project_manager.get_zone_data(), MultiAquariumZoneData)`.
`ProjectManager.get_zone_data()` is the aquarium-0 shim and always returns a `ZoneData` (CLAUDE.md,
"Live: the session's aquariums come from `_resolve_session_multi_zone_data()`"; the same shim
was the cause of #635 for the recorder). So today a two-aquarium live session gets the
single `LivePreviewWindow` with the whole frame, and the `AttributeError` the audit predicted
cannot be reached: the defect was latent.

What was fixed is the window's contract, so that the day the selection is corrected the pipeline
does not crash. What was NOT changed, because it alters which window every two-aquarium live
session opens (a contract of the live flows, in `core/recording/**`, off limits for this front):

1. `_create_preview_window` should read `self._live_multi_zone_data` (already resolved by
   `start_session` before the window is built, `live_session_manager.py:616`) instead of the shim.
2. It should then pass `aquarium_regions=` (the bounding box of each `AquariumData.polygon`, raw
   camera pixels) to `MultiAquariumLivePreviewWindow`; without regions every panel shows the
   whole frame.
