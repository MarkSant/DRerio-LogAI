# F2 — UI dialogs coverage front (TASK-087)

Scope: `ui/dialogs/camera_disconnect_recovery_dialog.py`, `ui/dialogs/multi_aquarium_live_preview_window.py`,
`ui/dialogs/aquarium_detection_progress_dialog.py`, `ui/wizard/custom_regex_dialog.py`,
`ui/components/project_views/report_asset_actions.py`, `ui/components/project_views/report_generator_actions.py`.

Method: Tk dialogs are built for real on `tkinter_root` and driven through their handlers
(`button.invoke()`, the `WM_DELETE_WINDOW` protocol command, the callback methods); decisions were
extracted into module-level pure functions where a method mixed deciding with drawing
(`grid_layout`, `progress_percent`, `format_mmss`, `thumbnail_geometry`, `match_value`,
`compile_patterns`, `match_path_rows`, `evaluate_path`). Expected values come from the input
(file names, geometry arithmetic), not from what the code returned. The two `project_views` classes
need no Tk, so their tests are fast-suite tests (no `gui` marker) against small fakes and real temp
folders.

Dead methods listed by the A2 audit were not tested: `CameraDisconnectRecoveryDialog.close_dialog`
(A2-D-322), `AquariumDetectionProgressDialog.show_completion` / `close_dialog` (A2-D-319/320),
`MultiAquariumLivePreviewWindow.update_recorded_count` / `update_aquarium_frame` (A2-D-329/330),
`CustomRegexDialog._match_path` (A2-D-360).

## Defects

| id | `file:line` | what is wrong | evidence | status |
| --- | --- | --- | --- | --- |
| F2-UI-001 (= A5-S-009) | `camera_disconnect_recovery_dialog.py:245, 304-340` | A recovery callback that raises left the dialog latched (`action_taken = True`, every button a silent no-op, label stuck on "Waiting for the camera to reconnect..."). The audit named the "wait" thread; the synchronous "resume" and "stop" had the same latch (an exception bubbled into Tk's callback handler with the dialog still open). | `TestACallbackThatRaises` (8 tests) failed before the fix, with `PytestUnhandledThreadExceptionWarning` for the thread. Fix: `_invoke_callback` / `_invoke_callback_in_thread` log `camera_disconnect_dialog.callback.failed`, and `_restore_after_callback_failure` (through `after(0, ...)` from the worker) resets `action_taken`, re-enables the Wait button and says "The reconnection request failed. Choose how to continue." Resume/Stop only close the dialog when the callback ran. New string translated (pt_BR). | fixed |
| F2-UI-005 | `report_generator_actions.py:289-338` (`delete_all_unified_reports`) | Two defects in one method. (a) `shutil.rmtree(..., onerror=on_rm_error)`: the handler swallows what it cannot fix, so rmtree returns normally with a locked file still there and the old code announced "All unified reports have been deleted." (the retry loop and the "Could not delete the folder" error were unreachable for locked files). (b) The "There were no unified reports to delete." notice hung off `if widget and hasattr(...)` at the bottom, so it appeared AFTER the success message whenever the tab widget was absent, and never appeared for a missing folder when the widget was present. | Tests failed before the fix: locked file reported as success; contradictory second dialog; missing folder silent. Fix: success is decided by the folder being gone (a still-present folder is retried, then reported through the existing error dialog), the "nothing to delete" notice is the `else` of `os.path.exists`, and the button-state refresh runs once at the end. | fixed |
| F2-UI-006 | `multi_aquarium_live_preview_window.py` (`Status: Inicializando...`, `Status: Parando...`, `Tempo:`, `Fim:`, `ETA:`, `Frames gravados:`, the `Status:` prefix) | Portuguese literals outside `_()` in an English-source repo: the two-aquarium live window showed Portuguese in an English UI. | Test `test_initial_footer_has_placeholder_clocks_and_is_english` failed (`Status: Inicializando...`). Now English in `_()`, with the original Portuguese as the pt_BR `msgstr`, so Portuguese users see no change. `tests/i18n` stays green. | fixed |
| F2-UI-002 | `core/recording/frame_processing_pipeline.py:1195` vs `multi_aquarium_live_preview_window.py` | `FrameProcessingPipeline` calls `self.preview_window.update_frame(frame, detections, recorded_count)` on whatever window `camera_connection_handler._create_preview_window` built. For a multi-aquarium project that is `MultiAquariumLivePreviewWindow`, which has no `update_frame` (its `update_aquarium_frame` has no caller — A2-D-330). The bound-method lookup happens in the processing thread, so every displayed frame raises `AttributeError`; the window would draw no video. | Static: `grep update_frame` shows no definition on the multi window. Pinned by `xfail(strict=True)` `test_the_window_offers_the_update_frame_the_pipeline_calls`. Not exercised end to end (needs a live camera). Outside this front's files (recording is off limits). | reported |
| F2-UI-003 | `custom_regex_dialog.py:51` (`match_value`); same rule in `ui/wizard/detection_step.py:~520-540` and `core/project/project_workflow_service.py:~1590-1665` | `group(1) if groups else group(0)`: with an alternation of groups (`Dia_(\d+)\|D(\d+)` on `D3.mp4`) the match goes through group 2, `group(1)` is `None`. The preview shows `'None'`, and the detection step then calls `.isdigit()` on `None` (AttributeError outside its `except re.error`). The fix is "first participating group", but it must be applied in all three places together. | `xfail(strict=True)` `test_a_group_that_did_not_participate_is_skipped`. | reported |
| F2-UI-004 | `report_asset_actions.py:375` (`open_unified_report`) | Globs only the top level of `unified_reports/`; reports are written to `unified_reports/total/` and `unified_reports/selecionados/` (`_unified_report_mixin.py:99`), so it answers "No word report found." for every current project. The live Open buttons use `ProcessingReportsWidget._open_latest_unified_file`, which walks subfolders; this method (and its `ReportsTreeManager` delegate) has no production caller. | `xfail(strict=True)` `test_a_report_in_the_total_subfolder_is_found`. Either delete both or make it recursive. | reported |
| F2-UI-007 | `ui/ui_coordinator.py:693-701`, `camera_disconnect_recovery_dialog.py:226-250` | After "wait" the dialog is meant to be closed by the controller ("Callback should close it when camera reconnects"), but `close_dialog` has no caller and `ui_coordinator` does not keep a reference to the dialog it builds, so nothing closes it. It keeps its modal grab, and `WM_DELETE_WINDOW` maps to `_on_stop`, which returns immediately because `action_taken` is already True: the window can neither be closed nor dismissed. | Static reading of the two call sites plus `test_a_second_action_after_the_first_is_ignored` (pins that every action after "wait" is ignored). Not run against a real reconnect. | reported |
| F2-UI-008 | `ui/ui_coordinator.py:776-813` vs `core/recording/frame_processing_pipeline.py:984-990` | The coordinator creates the aquarium-detection dialog on the event with `frame_number == 1` and closes it at `frame_number >= 100`, with `max_frames=100` hard-coded (the payload's `max_frames` is ignored). The publisher ends the detection phase at `_aquarium_detection_frames >= 10` or 4 valid boxes, and the counter starts at 0 (`live_session_manager.py:664`). So the dialog, once created, is never closed (its `WM_DELETE_WINDOW` is a no-op and it holds a modal grab), and if no event carries frame 1 it is never shown. | Static reading; not run against a real session. Not fixed: the right behaviour (close on detection complete? use the payload's `max_frames`?) is a decision for the maintainer. | reported |
| F2-UI-009 | `custom_regex_dialog.py` (`evaluate_path`, `match_path_rows`) vs `project_workflow_service.py:1589,1630,1664` | The dialog's preview matches case-sensitively; the project import re-runs the same patterns with `re.IGNORECASE`, and the detection step without it. `dia_2` shows "no match" in the dialog and may still be imported. | `test_the_search_is_case_sensitive` pins today's preview behaviour. | reported |

## Observations

| id | `file:line` | observation | status |
| --- | --- | --- | --- |
| F2-UI-O1 | `report_generator_actions.py:295-309` | The deletion retry loop now really runs (before, locked files never reached it), so a locked folder blocks the Tk thread for 3 x 0.5 s. This is loose end A6-01 (`time.sleep` on the Tk thread), now reachable; not changed here. | reported |
| F2-UI-O2 | `custom_regex_dialog.py:760` | Right after construction `maxsize()` reads back the screen size (3456x1080 on the dev machine) although `_initialize_geometry` ran; calling it again once the window is mapped gives the intended (1000, 896). Cause not investigated (the tests reset the flag and call the method again). | reported |
| F2-UI-O3 | `custom_regex_dialog.py:576` | The `except Exception: return` around `resizable()` is legitimate (A5): the window keeps its default geometry and `_geometry_initialized` stays False. Pinned by `test_when_the_window_cannot_be_made_resizable_nothing_is_resized_and_nothing_is_raised`. | pinned |
| F2-UI-O4 | `camera_disconnect_recovery_dialog.py` | The Wait button is created disabled and never enabled in the normal flow (waiting is the automatic countdown outcome); the repair enables it so the user can retry. | pinned |

## Mutation

`scripts/mutation_catalog.yaml` (end of file, `# ui dialogs coverage (TASK-087)`): 23 mutations in 6
blocks, all killed. The runner deselects `gui` tests, so every block is killed by fast-suite tests:
the extracted pure functions, a Tk-free `object.__new__` instance of the camera dialog whose real
methods are driven (`TestDecisionsWithoutTk`), and the two `project_views` files.
