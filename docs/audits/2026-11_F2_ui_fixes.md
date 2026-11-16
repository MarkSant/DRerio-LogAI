# F2 UI dialogs: fixes (TASK-087)

Follow-up to [`2026-11_F2_ui_dialogs.md`](2026-11_F2_ui_dialogs.md): the defects that file
reported and this pass fixed. One row per defect. Every fix has its test (the strict-xfail,
turned into a normal test, or a new one) and one block at the end of
`scripts/mutation_catalog.yaml` with no survivor.

| Id | Where | Root cause | Fix | Test | Mutation block | Status |
| -- | ----- | ---------- | --- | ---- | -------------- | ------ |
| F2-UI-002 | `core/recording/frame_processing_pipeline.py:1195` (call) vs `ui/dialogs/multi_aquarium_live_preview_window.py` | The pipeline calls `preview_window.update_frame(frame, detections, recorded_count)` on whichever window the camera handler built; `MultiAquariumLivePreviewWindow` only had `update_aquarium_frame`, which nothing called (A2-D-330). | The window gains `update_frame` with the same signature as `LivePreviewWindow.update_frame`. The pure `build_panel_views()` splits the whole camera frame per aquarium (crop to the region, detections placed by their centre, boxes drawn in crop coordinates, shared frame never painted on); the optional `aquarium_regions` constructor argument supplies the regions, an aquarium without one shows the whole frame. The call site is NOT touched. | `tests/ui/dialogs/test_multi_aquarium_live_preview_window.py` (`TestBuildPanelViews`, `TestUpdateFrame`, `TestUpdateFrameOnScreen`, `TestRegionHelpers`); the strict-xfail is gone | `multi_aquarium_preview_update_frame` (15/15) | fixed, with the finding below reported |
| F2-UI-007 | `ui/ui_coordinator.py` `_on_camera_disconnect` (~l.693) / `_on_camera_reconnected`; `ui/dialogs/camera_disconnect_recovery_dialog.py:226-250` | The coordinator built the recovery dialog and dropped the reference; nothing called `close_dialog`, so after "wait" the dialog kept its modal grab and ignored every further action. | The coordinator keeps the dialog (`_camera_disconnect_dialog`); `CAMERA_RECONNECTED` closes it through `_safe_ui_call` (Tk thread) via `_close_camera_disconnect_dialog()`; a new disconnect first closes a dialog still open, so two modal grabs never stack. | `tests/ui/test_ui_coordinator_helpers.py` (5 mock tests + 1 GUI test with the real dialog: wait, ignored stop, reconnect, gone) | `ui_coordinator_camera_disconnect_dialog` (7/7) | fixed |
| F2-UI-008 | `ui/ui_coordinator.py` `_on_aquarium_detection_progress` vs `core/recording/frame_processing_pipeline.py:984-990` | The coordinator opened the dialog only on `frame_number == 1`, sized it with a hard-coded 100 and closed it at `frame_number >= 100`; the publisher counts analysed frames from 0, publishes only frames that saw an aquarium and ends the phase at 10 frames or 4 boxes. The dialog (modal, window-close disabled by design) was never closed, or never opened. | The dialog opens on the first event of a phase; it is sized by the payload's `max_frames` (default 100 when absent or invalid); it closes on the phase's last frame (`frame_number + 1 >= max_frames`, the counter being 0-based); a final-frame event never reopens it; the creation is re-checked on the Tk thread (two racing events opened two dialogs); a watchdog (`AQUARIUM_DETECTION_STALE_MS`, 5 s, restarted by every event) closes it when the publisher goes quiet; the status bar counts against the same total (msgid `Detecting aquarium: frame {frame}/{total}`, pt_BR updated and compiled). | `tests/ui/test_ui_coordinator_helpers.py` (14 mock tests + 1 GUI test with the real dialog: events 0..9, gone after the last) | `ui_coordinator_aquarium_detection_dialog` (16/16) | fixed on the UI side; the publisher's mismatch is reported below |
| F2-UI-003 | `ui/wizard/custom_regex_dialog.py` (`match_value`, `evaluate_path`, `match_path_rows`); `ui/wizard/detection_step.py` `_process_path_with_individual_patterns`; `core/project/project_workflow_service.py:1589-1590, 1630-1631, 1664-1665` (the audit's `~1590-1665` lines) | `match.group(1) if match.groups() else match.group(0)` takes group 1 even when it did not take part (`Dia_(\d+)\|D(\d+)` on `D3.mp4`): the dialog showed `'None'`; the detection step and the import call `.isdigit()` / `.lower()` on `None`. | One function is the rule: `core/services/pattern_match.py` (`match_value`: first group that took part, else the whole match; `search_value`, `finditer_values`, `compile_user_pattern`). The dialog and the detection step call it. | `tests/core/services/test_pattern_match.py` (the old strict-xfail `test_a_group_that_did_not_participate_is_skipped` is now a normal test there), `tests/ui/wizard/test_custom_regex_dialog.py`, `tests/ui/wizard/test_detection_step_extended.py` | `pattern_match_rule` (9/9), `pattern_match_detection_step_caller` (5/5), `pattern_match_dialog_caller` (4/4) | fixed for 2 of the 3 places; the third is reported below |
| F2-UI-009 | same three places | Dialog and detection step searched case-sensitively; the import searches with `re.IGNORECASE`. `dia_2` read "no match" in the dialog, found no design in the detection step and was imported anyway. | The rule searches with `USER_PATTERN_FLAGS = re.IGNORECASE` (the import's behaviour, so the import needs no change); `compile_user_pattern` recompiles a pattern compiled without the flag, so no caller can opt out. | same as F2-UI-003 (`test_the_search_ignores_case_like_the_project_import` replaces the old `test_the_search_is_case_sensitive`) | same blocks | fixed for 2 of the 3 places; the third is reported below |

## Reported, not changed

### F2-UI-003 / F2-UI-009: the project import still carries its own copy of the rule

The three places of the rule were: (1) the pattern dialog, (2) the detection step's individual
patterns, (3) `ProjectWorkflowService._extract_group`, `_extract_day`, `_extract_subject`
(`core/project/project_workflow_service.py:1589`, `1630`, `1664`). (1) and (2) now call
`core/services/pattern_match`. (3) is in `core/project/**`, off limits for this front, so it keeps
its inline copy. Its case rule already equals the shared one (`re.IGNORECASE`), but its value rule
still crashes on an alternation of groups (`matched_group.lower()` / `.isdigit()` on `None`).
The switch is mechanical and behaviour-preserving for every input that did not crash. In each of
the three methods, replace

```python
match = re.search(<x>_pattern, path_text, re.IGNORECASE)
if match:
    matched_<x> = match.group(1) if match.groups() else match.group(0)
    ...
```

by

```python
matched_<x> = search_value(<x>_pattern, path_text)
if matched_<x> is not None:
    ...
```

(`from zebtrack.core.services.pattern_match import search_value`; the `import re` inside the three
methods then goes away). `_extract_subject` keeps `self._normalise_subject_id(matched_subject)`.
Until that is done a custom alternation pattern is previewed and detected correctly in the wizard
and can still fail at import.

### F2-UI-008: the live pipeline publishes `max_frames=300` but ends detection at 10 frames

`frame_processing_pipeline.py:986` ends the detection phase on `self._aquarium_detection_frames >= 10`
or `len(self._detected_aquarium_bboxes) >= 4`, both literals, while `live_camera_service.py:211`
sets `_aquarium_detection_max_frames = 300` ("Standard: 300 frames (10s)") and that value is what
the progress payload (`max_frames`), the preview status text ("Detecting aquarium... (n/300)") and
the session log carry. Nothing announces the end of the phase. So, with the publisher unchanged,
the dialog's bar reads `n / 300` and it is the 5 s watchdog (not the last-frame rule) that closes it.
This is a live-flow contract (`core/recording/**`, off limits for this front), so it was not changed.
Proposed: make `_aquarium_detection_max_frames` the single source (the `>= 10` literal compares
against it, with the default set to the real limit), or publish one final progress event on
completion. With either, the coordinator's last-frame rule closes the dialog immediately and the
watchdog becomes a safety net only.

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
