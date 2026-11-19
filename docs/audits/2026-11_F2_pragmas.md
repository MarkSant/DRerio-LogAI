# F2 — `# pragma: no cover` review (TASK-087, plan item 2.1)

Scope: every `# pragma: no cover` in `src/zebtrack` at the base of this branch (`858d0a13`, 111 sites in 36 files). Each site is
classified as:

- **testable now**: the pragma is removed and a test drives the branch and checks what it
  does (the value returned, the state left behind, what reaches the operator), with a
  `pragma_review_*` block at the end of `scripts/mutation_catalog.yaml` that breaks the
  handler and must be caught;
- **keep**: the pragma stays, with the reason;
- **dead**: unreachable; the pragma stays and the code is NOT deleted (the maintainer decides).

Result: 60 testable now (pragma removed), 49 keep, 2 dead. 51 pragmas remain.

Line numbers are those of the base commit. "Already covered" means an existing test drove
and asserted the branch; only the pragma was left, and the new mutation block proves the
assertion bites.

## Method

1. Every non-A2-07 pragma was stripped, the fast suite was run with coverage, and the
   handler bodies that ran were listed (5 were already covered).
2. For the rest, one test per behaviour was added to the module's existing test file (one new
   file, `tests/ui/wizard/test_design_editor_dialog.py`, for a module that had none). Failures
   are injected at the boundary the handler guards (a raising double, a path that is a file, a
   directory `os.remove` refuses), never by calling the handler.
3. Each mutation narrows the handler (`except Exception` -> `except KeyError`) or removes the
   fallback; all blocks kill every mutant.

## Findings

| id | `file:line` | finding | status |
| --- | --- | --- | --- |
| F2-PR-O1 | `tests/io/test_recorder_buffer_cap.py` (`test_reinjection_capped_on_error`, `test_reinjection_keeps_all_when_under_cap`) | Both tests re-implement the reinjection arithmetic inside the test and assert their own copy; no recorder code runs, so they pass whatever `_flush_detection_data` does. `TestFailedWriteKeepsTheRows` now drives the real flush; the two old tests were left in place (deleting tests is out of scope). | reported |
| F2-PR-O2 | `core/conditions/evaluator.py:225` | An unknown level node without a `children` attribute fails with `AttributeError` on line 225 before the intended `TypeError` on 230; still a loud failure. | reported |
| F2-PR-O3 | `core/project/asset_manager.py:535` | The `expected_values in (None, [], ())` guard is redundant with `if not expected_set: continue` a few lines below; the outcome is the same without it. | reported |
| F2-PR-O4 | `ui/components/analysis_window_panel.py:1307` | If the Barnes preset ever became unrepresentable the button would silently do nothing (log only, no status text). Unreachable today (see the dead row). | reported |

| F2-PR-O5 | `scripts/mutation_check.py` | The runner calls pytest with the default `-m` (no `gui`), so a block whose only tests are `gui` reports baseline 0 and every mutant survives. The UI tests of this review were written without Tk where possible (`_extended` files, `object.__new__` + real method); the one that needs a real dialog (`custom_regex_dialog.py:260`) was mutation-checked by hand. | fixed in #724: the runner passes `-m "" -n0`, starts a per-worker Xvfb when there is no `DISPLAY`, and a 0-test baseline exits 2 |

No newly covered branch turned out to be a real defect; no `xfail` was needed.

## Sites

| `file:line` | class | reason | test / mutation block |
| --- | --- | --- | --- |
| `coordinators/calibration_coordinator.py:89` | testable now | `get_project_name()` raising leaves the scope info with a project label and no name. | `test_calibration_coordinator.py::test_get_calibration_scope_info_survives_an_unreadable_project_name`; block `pragma_review_calibration_scope_name` |
| `coordinators/live_calibration_coordinator.py:277` | testable now | Stop event that raises must not skip the device release. | `test_live_calibration_coordinator.py::test_release_calibration_camera_still_releases_when_stop_signal_fails`; block `pragma_review_live_calibration_release` |
| `coordinators/live_calibration_coordinator.py:285` | testable now | Already covered and asserted by the existing `test_release_calibration_camera_swallows_release_exceptions`; only the pragma was left. | block `pragma_review_live_calibration_release` |
| `coordinators/model_diagnostics_coordinator.py:708` | testable now | OpenVINO predict that raises aborts the run and tells the user the frame number. | `test_model_diagnostics_coordinator.py::...::test_openvino_failure_aborts_with_the_frame_number`; block `pragma_review_model_diagnostics_openvino` |
| `coordinators/project_lifecycle_coordinator.py:164` | testable now | Already covered and asserted by `test_close_project_swallows_live_stop_errors`. | block `pragma_review_project_lifecycle_live_stop` |
| `coordinators/project_lifecycle_coordinator.py:672` | testable now | A failing `can_remove_asset` refuses the removal with a translated message. | `test_project_lifecycle_coordinator.py::test_can_remove_failure_refuses_with_a_message`; block `pragma_review_project_lifecycle_failures` |
| `coordinators/project_lifecycle_coordinator.py:717` | testable now | A failing `ProjectManager` call returns `False` and publishes no tree refresh. | `test_project_lifecycle_coordinator.py::test_removal_failure_reports_false_and_refreshes_nothing` (4 cases); block `pragma_review_project_lifecycle_failures` |
| `coordinators/project_lifecycle_coordinator.py:810` | testable now | A failing `ProjectManager` call returns `False` and publishes no tree refresh. | `test_project_lifecycle_coordinator.py::test_removal_failure_reports_false_and_refreshes_nothing` (4 cases); block `pragma_review_project_lifecycle_failures` |
| `coordinators/project_lifecycle_coordinator.py:851` | testable now | A failing `ProjectManager` call returns `False` and publishes no tree refresh. | `test_project_lifecycle_coordinator.py::test_removal_failure_reports_false_and_refreshes_nothing` (4 cases); block `pragma_review_project_lifecycle_failures` |
| `coordinators/project_lifecycle_coordinator.py:889` | testable now | A failing `ProjectManager` call returns `False` and publishes no tree refresh. | `test_project_lifecycle_coordinator.py::test_removal_failure_reports_false_and_refreshes_nothing` (4 cases); block `pragma_review_project_lifecycle_failures` |
| `coordinators/report_generation_coordinator.py:117` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:119` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1128` | keep | Same pattern as A2-07, not listed there: `cv2.imwrite` when no `FrameExtractor` is injected. DI always injects it. | — |
| `coordinators/report_generation_coordinator.py:1130` | keep | Same pattern as A2-07, not listed there: `cv2.imwrite` when no `FrameExtractor` is injected. DI always injects it. | — |
| `coordinators/report_generation_coordinator.py:1166` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1168` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1169` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1170` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1171` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1172` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1173` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1174` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1211` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1213` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1214` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1215` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1216` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1217` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1221` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1222` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1223` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1224` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1225` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1226` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1227` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1228` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1229` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/report_generation_coordinator.py:1230` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. | — |
| `coordinators/video_processing_coordinator.py:251` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. Line 251 is the pragma text inside a comment. | — |
| `coordinators/video_processing_coordinator.py:252` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. Line 251 is the pragma text inside a comment. | — |
| `coordinators/video_processing_coordinator.py:253` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. Line 251 is the pragma text inside a comment. | — |
| `coordinators/video_processing_coordinator.py:255` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. Line 251 is the pragma text inside a comment. | — |
| `coordinators/video_processing_coordinator.py:256` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. Line 251 is the pragma text inside a comment. | — |
| `coordinators/video_processing_coordinator.py:257` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. Line 251 is the pragma text inside a comment. | — |
| `coordinators/video_processing_coordinator.py:258` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. Line 251 is the pragma text inside a comment. | — |
| `coordinators/video_processing_coordinator.py:259` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. Line 251 is the pragma text inside a comment. | — |
| `coordinators/video_processing_coordinator.py:260` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. Line 251 is the pragma text inside a comment. | — |
| `coordinators/video_processing_coordinator.py:261` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. Line 251 is the pragma text inside a comment. | — |
| `coordinators/video_processing_coordinator.py:262` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. Line 251 is the pragma text inside a comment. | — |
| `coordinators/video_processing_coordinator.py:263` | keep | `cv2`/`pandas` fallback for a coordinator built without its injected service. DI always injects the service, so production never runs it; accepted as A2-07 in `2026-11_loose_ends.md`. Line 251 is the pragma text inside a comment. | — |
| `core/conditions/evaluator.py:230` | testable now | Unknown level node raises `TypeError` naming it. Reachable through `model_construct`, which skips validation. Note: an unknown node WITHOUT a `children` attribute raises `AttributeError` one line earlier (line 225); still loud, only less clear. | `test_evaluator.py::TestUnknownNodes`; block `pragma_review_evaluator_unknown_nodes` |
| `core/conditions/evaluator.py:275` | keep | Body of the abstract `_Trigger._feed`; every concrete trigger overrides it and the base class is never instantiated. Testing it would only pin `NotImplementedError` on a private base. | — |
| `core/conditions/evaluator.py:475` | testable now | Unknown trigger node (START or STOP) raises `TypeError` naming it. | `test_evaluator.py::TestUnknownNodes`; block `pragma_review_evaluator_unknown_nodes` |
| `core/detection/single_detector.py:647` | testable now | Plugin rejecting single-subject mode: the detector still switches and the next ByteTrack is single-animal. | `test_single_detector_extended.py::TestPluginAndTrackerFailuresDegrade`; block `pragma_review_single_detector_degrades` |
| `core/detection/single_detector.py:719` | testable now | Plugin reset failing: the global track-id counter still restarts at 1. | same class and block |
| `core/detection/single_detector.py:1073` | testable now | ByteTrack construction failing returns `None` and is retried on the next call. | same class and block |
| `core/project/asset_manager.py:132` | testable now | Global template library failing still lists the project's templates. | `test_asset_manager.py::test_list_roi_templates_keeps_project_templates_when_global_listing_fails`; block `pragma_review_asset_manager` |
| `core/project/asset_manager.py:535` | testable now | Criterion with `None`/empty values is skipped. Redundant with the `if not expected_set: continue` below it (same outcome without it), kept as is. | `test_asset_manager.py::test_profile_criterion_without_values_is_ignored_not_failed`; same block |
| `core/project/asset_manager.py:599` | testable now | `os.remove` refused by the OS (a directory) returns `False` and leaves it. | `test_asset_manager.py::test_delete_file_if_exists_reports_false_when_the_os_refuses`; same block |
| `core/project/parquet_io_manager.py:474` | testable now | A locked destination folder skips that copy and keeps the one next to the video. | `test_parquet_io_manager.py::TestCopyZoneParquets::test_failed_destination_does_not_stop_the_other_copy`; block `pragma_review_parquet_io_copy_failure` |
| `core/project/project_manager.py:883` | testable now | Unknown asset type raises `ValueError` and changes nothing. The `AssetType` literal does not stop a string from the UI. | `test_project_manager.py::...::test_remove_unknown_asset_type_is_refused_and_changes_nothing`; block `pragma_review_project_manager_unknown_asset` |
| `core/recording/frame_processing_pipeline.py:233` | testable now | `root.after` failing at shutdown falls back to a direct status update. | `test_frame_processing_pipeline_extended.py::TestShutdownFailuresDegrade`; block `pragma_review_frame_pipeline_teardown` |
| `core/recording/frame_processing_pipeline.py:354` | testable now | A previous ledger that fails to finalize is still replaced. | same class and block |
| `core/services/roi_rule_resolver.py:154` | keep | `__repr__` of a private sentinel, read only when debugging; no code reads the string. | — |
| `core/services/zone_autoimport_policy.py:82` | testable now | A path value whose `str()` fails never matches: candidate is not project-owned (ASK), a wizard entry does not match the video. | `test_zone_autoimport_policy.py::TestUnusablePaths`; block `pragma_review_zone_autoimport_unusable_path` |
| `core/services/zone_readiness.py:31` | keep | `if TYPE_CHECKING:` import, never executed at runtime. | — |
| `core/state_manager.py:558` | testable now | After `shutdown()` observers run inline; a failing one does not block the next. | `test_state_manager_observer_pattern.py::TestObserversAfterShutdown`; block `pragma_review_state_manager_inline_observers` |
| `core/video/progress_notifier.py:261` | testable now | Already covered and asserted by `test_build_metadata_context_handles_errors`. | block `pragma_review_progress_notifier_metadata` |
| `core/video/video_context_factory.py:332` | testable now | Results path that is a FILE: snapshot is empty. | `test_video_context_factory.py::TestResultsDirectoryThatIsAFile`; block `pragma_review_video_context_results_dir` |
| `core/video/video_context_factory.py:368` | testable now | Results path that is a FILE: cancel cleanup leaves it untouched. | same class and block |
| `core/viewmodels/main_view_model_runtime.py:527` | testable now | Already covered and asserted by `test_manager_replaced_isolates_a_failing_hook_from_the_next_service`. | block `pragma_review_runtime_manager_replaced_isolation` |
| `fetch_weights.py:415` | keep | `if __name__ == "__main__":` guard; `main()` is tested directly. | — |
| `io/arduino.py:243` | testable now | Driver without `reset_input_buffer` still completes the handshake probe. | `test_arduino.py::test_probe_succeeds_when_flush_and_close_are_unsupported`; block `pragma_review_arduino_probe_quirks` |
| `io/arduino.py:253` | testable now | `readline` raising ends the probe at once (no wait until the timeout). | `test_arduino.py::test_probe_gives_up_at_once_when_the_read_fails`; same block |
| `io/arduino.py:268` | testable now | `close` raising does not turn a port that answered into an error. | `test_arduino.py::test_probe_succeeds_when_flush_and_close_are_unsupported`; same block |
| `io/arduino.py:281` | testable now | `serial.tools.list_ports` missing: the scan finds nothing instead of raising. | `test_arduino.py::test_scan_without_list_ports_finds_nothing`; same block |
| `io/arduino.py:287` | testable now | `comports()` raising: the scan finds nothing. | `test_arduino.py::test_scan_survives_a_driver_that_cannot_enumerate`; same block |
| `io/arduino_manager.py:31` | keep | Import-time fallback for a missing pyserial; pyserial is a hard dependency, and exercising it means reloading the module other modules already hold. | — |
| `io/arduino_manager.py:35` | keep | Import-time fallback for a missing pyserial; pyserial is a hard dependency, and exercising it means reloading the module other modules already hold. | — |
| `io/arduino_manager.py:141` | testable now | Port object that cannot be built: `connect` returns `False` and tells the operator. | `test_io_arduino_manager.py::test_connect_reports_false_when_the_port_object_cannot_be_built`; block `pragma_review_arduino_manager_failures` |
| `io/arduino_manager.py:487` | testable now | `close` failing still disconnects. | `test_io_arduino_manager.py::test_disconnect_completes_when_close_fails`; same block |
| `io/arduino_manager.py:655` | testable now | Controller event handler raising does not kill the reader thread. | `test_io_arduino_manager.py::test_a_failing_controller_handler_does_not_stop_the_reader`; same block |
| `io/arduino_manager.py:662` | testable now | Status/log/command UI callbacks raising do not break connect, send or disconnect. | `test_io_arduino_manager.py::test_failing_controller_callbacks_do_not_break_connect_send_or_disconnect`; same block |
| `io/arduino_manager.py:669` | testable now | Status/log/command UI callbacks raising do not break connect, send or disconnect. | `test_io_arduino_manager.py::test_failing_controller_callbacks_do_not_break_connect_send_or_disconnect`; same block |
| `io/arduino_manager.py:676` | testable now | Status/log/command UI callbacks raising do not break connect, send or disconnect. | `test_io_arduino_manager.py::test_failing_controller_callbacks_do_not_break_connect_send_or_disconnect`; same block |
| `io/camera.py:267` | testable now | Release failing when reconnection is abandoned still stops the capture thread. | `test_camera.py::test_reconnect_abort_still_stops_when_the_driver_release_fails`; block `pragma_review_camera_reconnect_abort` |
| `io/recorder.py:533` | testable now | A failing periodic flush does not kill the flush thread; data drains later. | `test_recorder_async_flush.py::test_flush_thread_survives_a_failing_flush_and_drains_later`; block `pragma_review_recorder_failures` |
| `io/recorder.py:542` | testable now | A failing final drain is handled inside the thread (no unhandled thread exception) and `stop_recording` still saves the rows. | `test_recorder_async_flush.py::test_failing_final_drain_still_stops_the_thread`; block `pragma_review_recorder_failures` |
| `io/recorder.py:1264` | testable now | Mask sidecar failing never costs the trajectory; a hand drain does not raise. | `test_recorder_masks.py::test_mask_sidecar_failure_never_costs_the_trajectory`, `::test_mask_flush_failure_is_contained_without_the_flush_thread`; block `pragma_review_recorder_failures` |
| `io/recorder.py:1284` | testable now | Mask/object/trajectory writer `close` failing still drops the writer. | `test_recorder_extended.py::TestWriterCloseFailures` (3 cases); block `pragma_review_recorder_failures` |
| `io/recorder.py:1482` | testable now | Mask/object/trajectory writer `close` failing still drops the writer. | `test_recorder_extended.py::TestWriterCloseFailures` (3 cases); block `pragma_review_recorder_failures` |
| `io/recorder.py:1689` | testable now | A failed write puts the rows back for the next flush, keeping only the newest `_max_buffer_rows`. The two existing `test_reinjection_*` tests copy the arithmetic instead of driving the flush (they pass whatever the recorder does); the new ones drive it. | `test_recorder_buffer_cap.py::TestFailedWriteKeepsTheRows`; block `pragma_review_recorder_failures` |
| `io/recorder.py:1813` | dead | `FileMetaData.num_row_groups` is never negative: pyarrow reports a count. The branch cannot be reached with any file `pq.read_metadata` accepts. | — |
| `io/recorder.py:1841` | testable now | Mask/object/trajectory writer `close` failing still drops the writer. | `test_recorder_extended.py::TestWriterCloseFailures` (3 cases); block `pragma_review_recorder_failures` |
| `ui/components/analysis_window_panel.py:1307` | dead | `drafts_from_spec(barnes_maze_preset(...))` cannot be `None`: the preset is a fixed structure (only the burrow ROI name varies) and its round trip is pinned by `test_analysis_window_panel.py::TestDraftsFromSpec::test_barnes_fixture_becomes_the_documented_lines`. If it ever became reachable the button would do nothing visible (only a log line). | — |
| `ui/components/arduino_bindings_panel.py:564` | testable now | `after` on a destroyed widget drops the update and never runs it off the Tk thread. | `test_arduino_bindings_panel.py::TestScheduleUi`; block `pragma_review_arduino_panel_schedule_ui` |
| `ui/components/dialog_manager.py:383` | testable now | Library import failing shows "Import error" and refreshes nothing. | `test_dialog_manager_extended.py::TestROITemplateImportFailures`; block `pragma_review_dialog_manager_template_import` |
| `ui/components/dialog_manager.py:417` | testable now | Pending single video that cannot be activated still receives the zones. | `test_dialog_manager_extended.py::TestROITemplateImportFailures`; block `pragma_review_dialog_manager_template_import` |
| `ui/components/dialog_manager.py:469` | testable now | Unreadable template shows the error, saves nothing, publishes no `ZONES_UPDATED`. | `test_dialog_manager_extended.py::TestROITemplateImportFailures`; block `pragma_review_dialog_manager_template_import` |
| `ui/components/dialog_manager.py:511` | testable now | Library copy failing after the apply keeps the applied zones and still confirms them (file stem as the name). | `test_dialog_manager_extended.py::TestROITemplateImportFailures`; block `pragma_review_dialog_manager_template_import` |
| `ui/components/event_dispatcher.py:265` | testable now | Bus refusing `unsubscribe` still drops the handler entry. | `test_event_dispatcher_extended.py::TestUnregisterWhenTheBusRefuses`; block `pragma_review_event_dispatcher_unsubscribe` |
| `ui/dialogs/live_preview_window.py:322` | testable now | Progress bar raising `TclError` at stop does not skip the ETA reset. | `test_live_analysis_ui.py::TestFreezeStopTimeWithoutAWindow` (`object.__new__`, real method); block `pragma_review_live_preview_freeze` |
| `ui/gui.py:23` | keep | Import-time fallback for optional `ttkbootstrap` in the main window module; exercising it means reloading `gui.py` under a blocked import. | — |
| `ui/window_utils.py:19` | keep | Import-time fallback for optional `ttkbootstrap`; same reason as `ui/gui.py:23`. | — |
| `ui/wizard/custom_regex_dialog.py:260` | testable now | Window manager refusing `resizable` in `body()` still builds the full dialog. | `test_custom_regex_dialog.py::TestGeometry::test_a_window_manager_that_refuses_resizing_still_gets_the_full_dialog` (`gui`). Block `pragma_review_custom_regex_resizable` (added in #724, once the runner ran `gui` tests; first applied by hand in this review). |
| `ui/wizard/design_editor_dialog.py:368` | testable now | Canvas refusing `yview_moveto` still loads the design. | `test_design_editor_dialog.py::TestLoadDesign` (new file: the module had none); block `pragma_review_design_editor_failures` |
| `ui/wizard/design_editor_dialog.py:389` | testable now | Regex callback raising keeps the patterns, clears the design and warns "Regex with no results". | `test_design_editor_dialog.py::TestCustomRegexCallback`; same block |
| `ui/wizard/model_selection_step.py:393` | testable now | OpenVINO device discovery failing offers only AUTO. | `test_model_selection_step_extended.py::TestOpenVinoDeviceDiscovery`; block `pragma_review_model_selection_openvino_devices` |
| `ui/wizard/wizard_dialog.py:139` | keep | `resizable` failing inside `WizardDialog.body()`: reaching it means building the whole modal wizard and its service graph (`test_wizard_integration.py` documents why that is not done in unit tests). One log line around a window-manager call. | — |
| `utils/__init__.py:66` | testable now | Torch present: seeded with the same seed; absent: left alone. | `test_utils_init.py::TestSetSeedTorch`; block `pragma_review_set_seed_torch` |
| `utils/__init__.py:68` | testable now | CUDA visible: both CUDA seeds and the cuDNN determinism flags are set. GPU-specific on real hardware, testable with a fake `torch`. | `test_utils_init.py::TestSetSeedTorch`; same block |
