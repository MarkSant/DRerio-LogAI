# A5 — Silent failures audit

Audit of `src/zebtrack` at `b03e5546` for TASK-087 (register rows A5-01 and A5-02 in
`docs/audits/2026-11_loose_ends.md`). Nothing under `src/` or `tests/` was changed. Every finding
below comes from reading the code in context; handlers are listed with the line of the `except`.

Classification: `legitimate` (deliberate, with the reason), `should log` (harmless but
invisible), `hides a real failure` (a concrete trigger exists, stated in the scenario).
Severity: `data` (wrong or missing research data), `ux` (the user gets no answer),
`diagnostic` (only harder to debug).

## Status of the `data` findings (2026-11-15)

All seven findings classified `hides a real failure` / `data` are fixed on branch
`worktree-cov-plugins-utils` (PR 717), each with a test that failed before the fix and a mutation
block:

| Finding | Fix | Commit |
| --- | --- | --- |
| A5-S-001 | `Recorder.stop_recording_multi_aquarium` raises one `RecorderError` naming every aquarium that failed, after stopping all of them | `b1a60ef5` |
| A5-S-002 | `LiveSessionManagerMixin._finalize_recorder` keeps the error and shows it to the operator | `b1a60ef5` |
| A5-S-003 | "Generate summaries" reports how many videos ended without a report and lists them | `03e4f9eb` |
| A5-S-004 | The unified batch report registers the sessions it really aggregated and warns about the rest | `3d4e471f` |
| A5-S-005 | A failed thigmotaxis or geotaxis adds a warning to the report | `876b7a39` |
| A5-S-006 | A failing multi-aquarium detection is shown once per session | this change |
| A5-S-007 | A recorder that does not start after the arena is shown to the operator | this change |
| A5-S-008 | The benchmark and OpenVINO-conversion buttons report success or failure (`UI_SHOW_INFO`/`UI_SHOW_ERROR`) | final pass, 2026-11-18 |
| A5-S-009 | The camera-disconnect dialog callback failure is logged and the buttons come back | earlier in this PR |
| A5-S-010 | An invalid stored multi-aquarium config is logged (`multi_aquarium.assignment.config_invalid`) instead of swallowed | final pass, 2026-11-18 |
| A5-S-011 | `VideoMetadataService.get_video_dimensions` releases the capture in `finally`; the other sites either hand the capture to its owner or are unreachable fallbacks (A2-07) | final pass, 2026-11-18 |

Two limits of these fixes, on purpose: A5-S-006 and A5-S-007 tell the operator but do not stop the
session by themselves (the caller runs on the processing thread, and stopping from there needs its
own design), and A5-S-004 still builds the report from the sessions that exist. The `ux` and
`diagnostic` findings below are not fixed.

## Summary

Section 1 (the 41 silent broad handlers) is counted per handler. Sections 2-5 are counted per
finding; a finding can span several sites.

| Classification | data | ux | diagnostic | Total |
| --- | --- | --- | --- | --- |
| hides a real failure (findings, A5-S) | 7 | 1 | 0 | 8 |
| should log (findings, A5-S) | 0 | 2 | 1 | 3 |
| legitimate (findings, A5-S) | 0 | 0 | 0 | 0 |
| hides a real failure (scan hits, section 1) | 0 | 0 | 0 | 0 |
| should log (scan hits, section 1) | 0 | 2 | 13 | 15 |
| legitimate (scan hits, section 1) | 0 | 0 | 26 | 26 |

The scan found **41** handler sites, one more than the first count of 40; the
extra one is probably the `contextlib.suppress(Exception)` in `global_model_configuration_panel.py:965`.
`A5-S` findings are the ones that carry an id; scan rows that point to an `A5-S` id are the
same defect, counted in both tables. `data` findings come first.

## Findings

| ID | file:line | Handler | Classification | Severity | Scenario | Smallest fix |
| --- | --- | --- | --- | --- | --- | --- |
| A5-S-001 | `io/recorder.py:953` | `except Exception as e: log.error("recorder.multi_aquarium.stop_failed", ...)` then the loop continues | hides a real failure | data | Two aquariums; the parquet write of aquarium 2 fails at stop (disk full, file locked by OneDrive). Aquarium 1 is saved, `stop_recording_multi_aquarium` returns `None`, `processing_worker.py:1579` falls through to `return True` and the worker posts `video_completed success=True`. The user sees a finished video; aquarium 2 has no trajectory. The single-aquarium path re-raises the same failure (`recorder.py:2040`), so the two modes disagree. | Collect the failing `aq_id`s in the loop and raise one aggregated error after the loop (so the worker's `worker.process.video_error` path reports it); keep the existing log key. |
| A5-S-002 | `core/recording/live_session_manager.py:1165` | `except Exception as e: log.warning("live_camera_service.recorder_stop_error", ...)` | hides a real failure | data | Live session ends and `recorder.stop_recording()` raises (the single recorder re-raises after writing `_BACKUP.json`). Only a warning is logged; the method goes on, restores the buttons, calls `on_session_stopped(False)` and returns `True`. The session is treated as complete and post-analysis runs on a trajectory parquet that was never finalised. | Log at `error` with key `live_camera_service.recorder_stop.failed`, remember the failure on the manager, and publish `SHOW_ERROR` (via `root.after(0, ...)`) naming the `_BACKUP.json`; pass `cancelled=True`-like semantics so the batch is not registered. |
| A5-S-003 | `core/viewmodels/analysis_control_view_model.py:551` | `except Exception as e: log.error("generate_summaries.failed", ...)` inside the per-video loop | hides a real failure | data | "Generate summaries" for N videos; one parquet is unreadable or the analysis raises. The loop logs and moves on, then publishes `SET_STATUS "Report generation finished."` and refreshes the tree unconditionally. If every video failed the user still reads "finished" and finds no report. | Count failures in the loop; after it publish `SHOW_ERROR` listing the failed videos and use a status such as `Report generation finished with {n} failure(s)`. The batch path (`report_generation_coordinator.py:270`) already does this with `errors`. |
| A5-S-004 | `coordinators/live_batch_coordinator.py:665-684; analysis/analysis_service.py:940; coordinators/_unified_report_mixin.py:317` | `continue` after `live_batch.unified_report.video_not_found/no_analysis`; `except Exception: log.warning("...aggregate_summaries.read_failed")`; `except (OSError, ValueError): log.warning("workflow.unified_report.read_failed")` | hides a real failure | data | A batch of 5 sessions in which one summary is missing or its `.xlsx`/`.parquet` is corrupt. The unified report is built from the other 4 and returns success; `register_batch_outputs(session_count=batch.session_count)` still claims 5. Group means in the unified workbook are computed over 4 animals with nothing saying so. (`_unified_report_mixin` already reports path collisions and videos without data, but not a read failure.) | Return or collect the omitted sessions from `aggregate_session_summaries` and the mixin, log them at `error` (`analysis_service.aggregate_summaries.session_omitted`) and stamp the omission in the workbook and in the batch status, as the duration caveat already is. |
| A5-S-005 | `analysis/analysis_service.py:547,571` | `except Exception as e: self.log.warning("analysis.thigmotaxis.failed" / "analysis.geotaxis.failed")` | hides a real failure | data | Thigmotaxis or geotaxis is configured for the project and the index computation raises (any exception from `b_analyzer`; I did not trace which input does it). The keys are simply not written, and `validation_warnings` (in scope, same object as `report["validacao"]["avisos"]`) is not extended, so the report has no row and no explanation for a metric the researcher asked for. | Append `_("Thigmotaxis could not be computed: {error}")` to `validation_warnings`; narrow to the analyser's own exception type. |
| A5-S-006 | `core/recording/live_analysis_post_processor.py:1454` | `except Exception as e: log.error("live_camera_service.multi_aquarium_detection_failed", ...)` then `detector.detect(frame, "live")` | hides a real failure | data | Two aquariums; `MultiAquariumDetector` raises on a frame (for example the tracker or zone state is broken). The fallback runs the single detector on the whole frame and returns its detections for the preview, but the write to the recorder is inside the `try`, so nothing is written for that frame. The operator watches animals being tracked while the per-aquarium trajectories stay empty; the log gets one traceback per frame. | Re-raise or count consecutive failures and stop the session with `SHOW_ERROR` after a small threshold; at least add a `ledger` outcome for the frame. |
| A5-S-007 | `core/recording/live_analysis_post_processor.py:1230,1237` | `except Exception as e: log.error("live_camera_service.recorder_init_error_after_arena", ...); return` | hides a real failure | data | Live session with arena detection: after the arena is confirmed the recorder fails to start (output folder not writable, codec missing). The method returns before `_setup_session_timer`, so there is no timer and no stop; the preview keeps running. I found no user-visible error on this path (not fully traced), so the operator can believe the session is recording. | Publish `SHOW_ERROR` and stop the session (`stop_session(cancelled=True)`) in both the `False` branch and the `except`; key `live_camera_service.recorder_start.failed`. |
| A5-S-008 | `core/viewmodels/main_view_model_runtime.py:245,255` | `threading.Thread(target=vm.hardware_vm.force_benchmark / convert_weight_to_openvino, daemon=True).start()` | hides a real failure | ux | "Force benchmark" and "Convert to OpenVINO" buttons. `force_benchmark` returns a dict (success) or `None` (failure, logged at `hardware_vm.benchmark.force_failed`); `convert_weight_to_openvino` returns a path or `None`. The thread target discards the value, so a success shows nothing and a failure only reaches the log; the button looks dead either way. | Wrap the target in a function that publishes `UI_SET_STATUS` / `SHOW_ERROR` through `root.after(0, ...)` from the return value. |
| A5-S-009 | `ui/dialogs/camera_disconnect_recovery_dialog.py:245` | `threading.Thread(target=lambda: self.on_action_callback("wait"), daemon=True).start()` (same shape for the other actions) | should log | ux | The recovery callback raises. Nothing reads the thread; Python prints the traceback to stderr (invisible in a packaged app) and the dialog stays on "Waiting for the camera to reconnect..." with `action_taken = True`, so the buttons no longer work. | Wrap in try/except that logs `camera_disconnect_dialog.callback.failed` and re-enables the buttons via `after(0, ...)`. |
| A5-S-010 | `coordinators/multi_aquarium_coordinator.py:352` | `except Exception: multi_aquarium_config = None` | should log | ux | `MultiAquariumData.model_validate` rejects the stored `calibration.multi_aquarium` dict (schema drift after an upgrade). The assignment dialog opens without the regex prefill; the researcher types group/day/subject by hand, with no hint why. | Narrow to `pydantic.ValidationError` and log `multi_aquarium.assignment.config_invalid` with the error. |
| A5-S-011 | `coordinators/video_processing_coordinator.py:262 (also report_generation_coordinator.py:1165,1210; core/video/video_metadata_service.py:26,67; core/video/video_context_factory.py:60)` | `cap = cv2.VideoCapture(...)` ... `cap.release()` outside `try/finally`; the coordinator one also has `except Exception: return None` | should log | diagnostic | An exception between open and release (a `cap.get` or the metadata read) leaves the handle open until garbage collection; on Windows that keeps the video locked for a later move or delete. The coordinator/report fallbacks are `pragma: no cover` branches that run only when the injected service is absent, and `cap.get` practically never raises, so no concrete trigger exists. Only the benchmark leak (A6-02) was real and is fixed. | Use `try/finally: cap.release()` (or `contextlib.closing`); in `video_processing_coordinator.py:262` log `video_processing.dimensions.probe_failed`. |

## 1. Broad handlers that neither log nor re-raise

Found with an AST script kept outside the repository: every `except Exception`,
`except BaseException`, bare `except` and `contextlib.suppress(Exception)` whose body is only
`pass`, `continue`, `break`, `return <constant>` or an assignment of a constant, with no
log/print/raise call. Each was read in context. The ones with a real consequence are in the
Findings table; the rest:

| Site | Body | Classification | Severity | Why, and the fix if it should log |
| --- | --- | --- | --- | --- |
| `__main__.py:39` | `log_path = "logs/analysis.log"` | legitimate | diagnostic | Crash reporter before logging exists; the fallback path is the point. |
| `coordinators/calibration_coordinator.py:89` | `project_name = None` | should log | diagnostic | `get_project_name()` failing shows an unnamed project; log `calibration.project_name.failed`. |
| `coordinators/live_calibration_coordinator.py:1894` | `confidences = None` | legitimate | diagnostic | Documented: `conf` shape varies by Ultralytics version; degrades to area ordering. |
| `coordinators/multi_aquarium_coordinator.py:352` | `multi_aquarium_config = None` | should log | ux | See A5-S-010. |
| `coordinators/video_processing_coordinator.py:262` | `return None` | should log | diagnostic | See A5-S-011. |
| `core/detection/zone_scaler.py:33` | `return "centroid"` | legitimate | diagnostic | Documented default for stub settings; `getattr` with default cannot hide a real error. |
| `core/recording/live_session_manager.py:881` | `elapsed_s = 0.0` | should log | diagnostic | Only feeds the `.cancelled` marker text; log `live_camera_service.cancel.elapsed_failed`. |
| `core/recording/live_session_manager.py:988` | `stacks[name] = "<stack formatting failed>"` | legitimate | diagnostic | Thread-dump text built at a hung shutdown; a failure is recorded in the dump itself. |
| `core/services/zone_autoimport_policy.py:82` | `return ""` | legitimate | diagnostic | Documented: an unusable path never matches. |
| `core/video/shared_frame_buffer.py:198` | `pass` | legitimate | diagnostic | `SharedMemory.close()` cleanup, `noqa: S110` states why. |
| `core/viewmodels/hardware_status_view_model.py:318` | `aquarium_method = None` | legitimate | diagnostic | Documented: settings may be a mock in tests; the slot list falls back to all slots. |
| `io/arduino.py:253` | `break` | should log | diagnostic | A serial read error ends the probe exactly like a timeout, so the panel says "no answer"; log `arduino.probe.read_failed`. |
| `ui/components/analysis_view_controller.py:195,210`; `ui/components/event_dispatcher.py:162,177`; `ui/components/state_synchronizer.py:186,198` | `processing_state = None` / `return False` | should log | diagnostic | Three copies of "is a live session active?"; an exception is read as "not live", which flips the flow the metadata events take. No realistic trigger (`get_processing_state` does not raise), so log only: `ui.live_session_probe.failed`. The duplication belongs in A3. |
| `ui/components/analysis_window_panel.py:1086,1201`; `ui/components/arduino_bindings_panel.py:262`; `ui/components/class_roles_panel.py:1031`; `ui/components/zone_controls.py:314`; `ui/gui.py:98,108` | `return False` around `winfo_exists()` / `is_alive()` | legitimate | diagnostic | Tk teardown: once the interpreter is gone `winfo_exists` raises; "not alive" is the answer, and each carries a justification comment. |
| `ui/components/analysis_window_panel.py:1581` | `zone_data = None` | should log | diagnostic | Comment says "unavailable early on"; a genuinely broken `get_zone_data()` would give an empty ROI list in the window editor. Narrow to `AttributeError` or log `analysis_window_panel.zone_data.failed`. |
| `ui/components/canvas/event_handler.py:207,535,540`; `ui/components/canvas/renderer.py:98,518`; `ui/components/canvas_manager.py:156` | `return None` / `continue` / `return` | legitimate | diagnostic | Canvas destroyed or item vanished during a drag or redraw; these run per mouse event, so logging would flood. |
| `ui/components/dialog_manager.py:1283` | `formatted_day = None` | legitimate | diagnostic | Cosmetic day label; falls back to the raw value. |
| `ui/components/global_model_configuration_panel.py:965` | `contextlib.suppress(Exception)` around `after_cancel` | legitimate | diagnostic | `destroy()` cleanup. |
| `ui/components/menu_manager.py:211` | `version = "Unknown"` | should log | diagnostic | About dialog; a wrong `pyproject.toml` path in a packaged build would be invisible. Log `menu.about.version_failed`. |
| `ui/components/model_diagnostics_panel.py:789` | `resolved_openvino = False` | should log | ux | `resolve_project_model_settings` raising makes the weights summary say OpenVINO is off while the project uses it; log `model_diagnostics.project_summary.failed`. |
| `ui/components/polygon_drawing_service.py:42` | `return False` | legitimate | diagnostic | Reading a Tk variable of a destroyed panel. |
| `ui/components/weight_hardware_manager.py:296` | `return False` | legitimate | diagnostic | Documented probe during UI refresh. |
| `ui/dialogs/block_detail_dialog.py:131` | `self._project_has_polygon = False` | should log | diagnostic | Only drives the "reused" badge; log `block_detail.zone_probe.failed`. |
| `ui/wizard/custom_regex_dialog.py:576`; `ui/wizard/wizard_dialog.py:336` | `return` after `self.resizable(True, True)` | legitimate | diagnostic | Dialog destroyed while its geometry is being set. |

## 2. Handlers that log and then continue (data paths)

Read: `io/recorder.py`, `core/video/processing_worker.py`, `coordinators/report_generation_coordinator.py`,
`analysis/analysis_service.py`, `analysis/roi.py`, `analysis/metrics_cache.py`, `core/project/*`,
`core/recording/live_*`. Findings are A5-S-001 to A5-S-006. Handlers that were checked and are
**fine** (the report or the user does learn of the loss):

- `recorder.py` mask sidecar (`recorder.masks.flush.error`, `_atomic`) and object sidecar
  (`_abandon_object_sidecar`): optional data; the analysis degrades with a warning in the report
  (`ROIAnalyzer.degradation_warnings`). Residual risk: a mask flush that fails midway leaves a
  sidecar covering only part of the session; I did not verify that the reader rejects a partial
  file.
- `recorder.py:1774` flush failure: rows are re-injected and retried; the final save writes a
  `_BACKUP.json` and re-raises.
- `processing_worker.py:664` and `:686`: post `error` / `fatal_error` to the result queue.
- `report_generation_coordinator.py:270`: collects `errors` and calls `_finalize_report_generation`.
- `roi.py` mask readers: degrade through `_degrade`, which feeds the report warnings.
- `zone_manager.py:998`, `project_service.py:364`, `metadata_manager.py:79`: return `False`/`None`;
  callers were not all traced (see What I did not cover).
- `analysis_service.py:900` (`results[aq_id] = None`): `run_multi_aquarium_analysis` has no caller
  outside its own docstring, so no finding; it is dead-code material for A2.

## 3. Threads and executors whose result is thrown away

Every `threading.Thread(target=...)` and `submit` in `src/zebtrack` was checked.

| Site | Result read? |
| --- | --- |
| `main_view_model_runtime.py:245,255` | No: A5-S-008. |
| `camera_disconnect_recovery_dialog.py:245` | No: A5-S-009. |
| `block_detail_dialog.py:2053`, `arduino_bindings_panel.py:516`, `class_roles_panel.py:851,1084` | Yes: the worker catches and reports through `after(0, ...)`. |
| `analysis_control_view_model.py:244` (`_await_shutdown`) | Joins only, nothing to report. |
| `analysis_control_view_model.py:279` (`_generate_summaries_impl`) | Per-video exceptions are caught but the final status ignores them: A5-S-003. |
| `live_analysis_post_processor.py:889` | Yes: `post_analysis_error` shows the completion dialog with an error. |
| `state_manager.py:676` | Yes: `_on_observer_complete` logs. |
| `multi_aquarium_detector.py:834`, `visualization_generator.py:1292` | Yes: `future.result()` inside `try`; the plot fallback is an empty buffer, and `document.add_picture` on it raises, which the per-video handler reports. |
| `frame_processing_pipeline.py`, `frame_ledger.py`, `recorder.py:520`, `io/camera.py`, `io/arduino_manager.py`, `processing_worker.py:267` | Long-running loops with their own handlers; not read line by line. |

## 4. Event handlers swallowed by the bus

`EventBusV2.publish` (`ui/event_bus_v2.py`, `log.exception`) is the only net, so any
subscriber that raises is invisible to the user. Checked: `PROJECT_OPEN` goes through
`ProjectWorkflowAdapter.open_project_workflow`, which turns a failure into `SHOW_ERROR`, so
it is fine. `MainViewModelRuntime.handle_event` has no outer catch; the dispatch of
`PROJECT_CREATE` reaches `ProjectLifecycleCoordinator.create_project`, whose only handlers are
inner ones. Whether a `ProjectInvalidError` from the save step is converted to `SHOW_ERROR`
before it reaches the bus was **not** traced; the comment at
`project_lifecycle_manager.py:37-41` records that it was the cause of a past "wizard closes
and nothing happens" bug. This is the first thing to verify.

## 5. Resources not released on the error path

An AST scan of every function that calls `cv2.VideoCapture` without a `release()` inside a
`finally` gave 15 functions; the full list is in A5-S-011 (`coordinators/` and `core/video/`)
plus `wizard_service.detect_available_cameras`, `io/camera.py`, `io/video_source.py`,
`ui/components/canvas/video_frame_manager.py`, `ui/components/video_display.py` and
`utils/hardware_benchmark.py` (the last was A6-02 and is fixed). None has a concrete trigger
in the code read, which is why the finding is `should log`/`diagnostic` and not worse.

## What I did not cover

- `core/recording/frame_processing_pipeline.py` (38 broad handlers) and `frame_ledger.py` (10):
  only the ones reached from the findings above were read. They are the biggest remaining
  surface for "logged, then continued" on the live data path.
- The other 250 or so broad handlers that do log: only those on the paths in section 2.
- Callers of `ZoneManager.save_multi_aquarium...` (returns `False`),
  `ProjectService.load_metadata` (returns `None`) and `ParquetIOManager.import_*` (returns
  `False`): not every caller checks the value.
- `ProjectWorkflowAdapter.create_project_workflow` failure path and the
  `setup_detector_callback` `return False` (`project_workflow_adapter.py`,
  `open_project.detector_setup_failed`, warning only): the callback may show its own dialog.
- Partial mask sidecar after a mid-session `recorder.masks.flush.error`: whether the reader
  rejects it.
- `analysis_control_view_model._generate_summaries_impl` uses `entry.get("fps", 30.0)` and
  a 1.0 pixel/cm default; the second is the documented "no calibration" meaning, the first
  belongs in A4 (time base).
- No handler was exercised: scenarios are derived from reading, not from a failing test. Per the
  register rules each `hides a real failure` row needs a red test before its fix.
