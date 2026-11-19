# A6 — Threads and the Tk main thread (TASK-087)

- Date: 2026-11-15
- Base: branch `worktree-cov-plugins-utils` (296ca6e0).
- Scope: `src/zebtrack`, read-only. Nothing was changed, run or profiled. Every "worst case"
  below is the sum of the constants visible in the code (`sleep`, `timeout=`, retry counts); a
  figure that depends on a driver or a disk is marked as an estimate and was not measured.
- Rules audited (CLAUDE.md, "Threading & UI"): UI updates from worker threads go through
  `root.after(0, ...)`; worker threads are `daemon=True`; nothing blocks the Tk main thread.

## Method

1. Listed every `time.sleep`, `.join(`, `.wait(`, `.get(timeout=`, `subprocess`, `urlopen`,
   `psutil` call and every `Thread(` / `Process(` / executor under `src/zebtrack`.
2. For each blocking call, traced the caller chain up to a Tk callback (a `command=`, a bind, an
   `after` callback or an `EventBusV2` handler). The bus is synchronous, so a handler runs on the
   publisher's thread (`ui/event_bus_v2.py`, class docstring and `publish`): a handler published
   from a Tk button runs on Tk, and one published from a worker runs on the worker.
3. Followed the other direction for widget access: for each event published from a non-Tk
   thread, read the subscriber to see whether it marshals (`_run_on_ui_thread`, `root.after`,
   `UIScheduler`) or touches a widget or a `tk.Variable` directly.
4. The `StateManager` was read to learn which thread runs state observers: they are submitted to
   a private `ThreadPoolExecutor(max_workers=4)` (`core/state_manager.py:381` and
   `_call_observer_with_timeout`, ~line 553), never to Tk and never to the caller.

How a Tk-thread claim is proven: "no `Thread`/`after` between the button and the call, and the
callee itself needs Tk (a modal dialog, `destroy()`, `winfo_*`)". Where that proof is missing the
finding is in the suspected section.

## Summary

| Section | Count |
| --- | --- |
| Confirmed: blocking the Tk thread | 10 (A6-01 to A6-08, A6-10, A6-11) |
| Confirmed: widget or `tk.Variable` access from a non-Tk thread | 1 (4 call sites) |
| Suspected | 4 |
| Daemon-thread rule | all `Thread(...)` are `daemon=True`; one non-daemon `multiprocessing.Process` |

Top three, in order of how often the user meets them:

1. A6-01 — opening the live wizard step blocks Tk on every visit (`psutil.cpu_percent(0.5)`, plus
   GPU probing with `import torch` and `openvino.Core()`).
2. A6-04 — camera enumeration (`WizardService.detect_available_cameras`) runs on Tk at five
   sites, one of them on dialog open.
3. A6-09 — project open fires `UI_REDRAW_ZONES`, `UI_UPDATE_ZONE_LIST`,
   `UI_NAVIGATE_TO_ANALYSIS_VIEW` and `UI_UPDATE_OPENVINO_STATUS` from a `StateManager` pool
   thread into subscribers that touch the canvas and `tk.Variable`s directly.

## Confirmed — blocking the Tk thread

### A6-01 — Live wizard step: hardware probe on every `on_show`

- Where: `ui/wizard/live_config_step.py:478` (`on_show` → `_detect_hardware_capability`, :530,
  `assess_capability()` at :544) → `utils/hardware_capability.py:129`
  (`psutil.cpu_percent(interval=0.5)`) and `_detect_gpu` (:193).
- Thread: Tk. `ui/wizard/wizard_dialog.py:282` calls `current_step.on_show()` from the
  Next/Back handler. Nothing in between starts a thread.
- Worst case: 0.5 s fixed (the `interval=`), plus `import torch` on the first call (not cached
  once imported, but `torch.cuda` is probed every time) and `openvino.Core()` device enumeration
  (:230 area). The torch and OpenVINO figures are estimates (seconds on a cold start), not
  measured. Nothing is cached: `self.hardware_report` is overwritten on every visit.
- User-visible: the wizard freezes for at least half a second each time the live step is shown,
  and for several seconds the first time.
- Fix (smallest): `psutil.cpu_percent(interval=None)` after one priming call at construction
  (non-blocking), and cache the report on the step (`if self.hardware_report is None`). A full fix
  runs `assess_capability()` on a daemon thread and applies the result with `after(0, ...)`.
- Confidence: high for the 0.5 s; medium for the torch/OpenVINO cost.

### A6-02 — "Delete unified reports": sleeps in the delete retry loop

- Where: `ui/components/project_views/report_generator_actions.py:262`
  (`delete_all_unified_reports`), `rmtree` at :297, `time.sleep(0.5)` at :300 and :309.
- Thread: Tk. `ui/components/processing_reports.py:464-479` (button) emits
  `UIEvents.REPORTS_DELETE_UNIFIED`; `reports_tree_manager.py:156` subscribes this method
  directly, and the bus is synchronous.
- Worst case: 3 attempts, each followed by a 0.5 s sleep including the last one, so 1.5 s of pure
  sleep, plus three `shutil.rmtree` runs of a folder with `.docx`/`.xlsx`/`.parquet` files on
  OneDrive (the reason for the retry is exactly that OneDrive locks files).
- User-visible: window not responding for 1.5 s or more after the confirmation; then the dialog.
- Fix: do not sleep after the last attempt (one-line change), and move the loop to a daemon thread
  that posts the result dialog with `root.after(0, ...)`.
- Confidence: high.
- Status (2026-11-18): fixed. `delete_unified_reports_dir()` runs through `ui/background_task.run_in_background`; the result dialog and the buttons refresh on Tk; no pause after the last attempt; a second request while deleting is ignored. Block `unified_reports_delete_off_tk`.

### A6-03 — Live calibration: camera open, warm-up sleeps and detection on Tk

- Where: `coordinators/live_calibration_coordinator.py`
  - `run_live_calibration` (:879): `Camera(...)` at :980-995, `time.sleep(1.5)` at :992, then a
    loop of `stabilization_frames` (30 from the live flow) with `get_frame()` + `sleep(0.1)` at
    :1006 (`sleep(0.2)` at :1003 on a failed read), burst detection, then `time.sleep(0.5)` at
    :1418.
  - `_capture_reference_frame_for_zones` (:1433): `Camera(...)`, `sleep(0.5)` at :1487, warm-up
    loop with `sleep(0.05)` at :1508, up to 5 reads with `sleep(0.1)` at :1527.
  - `_retry_aquarium_detection` (:1906): 5 reads with `sleep(0.05)` at :1943, then inference.
- Thread: Tk. Entry points are `ensure_zones_before_recording`
  (`live_camera_session_coordinator.py:1900` and :2452, `recording_session_coordinator.py:348`),
  `single_video_workflow.py:395` (auto-detect button) and the retry callback of the preview
  dialog. `ensure_zones_before_recording` shows `ZoneCalibrationDialog(...).show()` immediately
  before (~:593), which is only possible on Tk; none of these files creates a thread.
- Worst case, from constants: 1.5 + 30 × 0.1 + 0.5 = 5.0 s of sleep in a successful calibration
  (more with failed reads: +0.2 s each), plus `cv2.VideoCapture` open (DirectShow, estimate
  1-3 s), plus 30-frame detector inference. Of the order of 6-10 s end to end.
- User-visible: the application is "not responding" between choosing "auto" and seeing the
  preview polygon; the only progress feedback is whatever was painted before the freeze.
- Fix (smallest): none that is one line. Run the camera warm-up and burst on a daemon thread, hand
  the frames to Tk via `after(0, ...)`, and open the preview dialog from there. At minimum, show a
  modal "Detecting arena..." window and call `update()` between stages (this is what
  `LiveSessionManager.start_session` already does for the countdown, see A6-08).
- Confidence: high for the chain and the constants; the open time is an estimate.
- Status (2026-11-18): fixed as decided by the maintainer (same shape as A6-07). With a Tk root, the camera open, warm-up, burst, model load and detection run on a daemon worker (`_calibration_work`) under a modal "Detecting the aquarium..." window; the fallbacks, the preview dialog and the zone save run back on Tk (`_calibration_finish`). The reference-frame capture of the reuse and manual branches does the same under "Opening the camera...", and the preview dialog's retry runs on a worker. `ensure_zones_before_recording` then returns False with `pending_zone_confirmation` and `calibration_in_progress` set (callers already read that as deferred, never as an error) and reports the outcome through the new `on_pending` / `on_abandoned` callbacks: the live coordinator publishes the pending session only from `on_pending`, so the "Start Recording" banner never appears before a polygon exists; the legacy recording coordinator drops its context in `on_abandoned`; the single-video auto-detect refreshes the zone tab from `on_done`. The camera is opened on a read-through settings view, never by mutating the shared `settings.camera.index`. Without a root everything runs inline, as before. Blocks `live_calibration_off_tk`, `live_session_defers_after_calibration`, `recording_gate_abandoned_clears_context`, `single_video_autodetect_on_done`, `preview_retry_off_tk`. The camera release after an approved preview stays on Tk (bounded joins, and the next session needs the device free).

### A6-04 — Camera enumeration on Tk at five sites

- Where: `core/services/wizard_service.py:211` (`detect_available_cameras`). Per index 0-5:
  `cv2.VideoCapture(i, CAP_DSHOW)` (blocking open), a reader thread, and
  `read_event.wait(timeout=3.0)` at :329 (the worker is a daemon thread, but the caller waits for
  it). Stops after 3 consecutive failures; result cached 30 s unless `use_cache=False`.
- Thread: Tk at every call site:
  - `ui/wizard/live_config_step.py:720` — button (`command=`, :220) and
    `_restore_from_template_once` (:511) from `on_show`;
  - `ui/dialogs/live_analysis_dialog.py:745` — button (:293) and **automatically on dialog
    open** (`self.after(0, self._detect_cameras)`, :706);
  - `ui/dialogs/block_detail_dialog.py:728` — "change camera" chooser, `use_cache=False`;
  - `ui/components/dialog_manager.py:811` and `ui/gui.py:1001` — `camera_provider` for
    `StartRecordingDialog`, `use_cache=False`.
- Worst case: per camera that opens but returns no frame, 3 s; per index, the open itself. With 6
  indexes and no early stop this is above 18 s of waits alone; with one working camera and three
  absent indexes, an estimate of 3-6 s. The code comment states the 3 s is "ample slack", so the
  design accepts it.
- User-visible: "Detectar" and the auto-detect on opening the live dialog freeze the window; the
  label is set to "Detecting..." and `update_idletasks()` is called once
  (`live_analysis_dialog.py:741-742`), which paints the label but does not keep the window alive.
- Fix: one helper that runs `detect_available_cameras` on a daemon thread and delivers the list
  with `after(0, ...)`; the five sites then differ only in the callback. The reader thread inside
  is already daemon.
- Confidence: high.
- Status (2026-11-18): fixed at all five sites with one helper, `ui/background_task.run_in_background` (daemon worker that never touches Tk; the Tk thread polls with `after` and runs the callbacks; a destroyed widget drops them). The wizard's template restore detects first and replays `set_data` on Tk. A second click while detecting is ignored. Blocks `ui_background_task`, `live_config_detection_off_tk`, `live_dialog_camera_detection_off_tk`, `start_recording_camera_chooser_off_tk`, `block_detail_camera_chooser_off_tk`.

### A6-05 — Arduino port scan with handshake on Tk

- Where: `io/arduino.py:224` (`probe_port`: `serial.Serial` open, `time.sleep(warmup)` at :247
  with `_PROBE_WARMUP_SECONDS = 0.1`, then a `readline()` loop until `timeout=1.5`) and :272
  (`scan_available_ports`, one probe per COM port). Reached through
  `WizardService.detect_arduino_ports` (`wizard_service.py:546`, cached 30 s).
- Thread: Tk. `ui/wizard/live_config_step.py:765` is the button handler (`command=` at :270) and
  is also called from `_on_arduino_toggle` (:683) and `_restore_from_template_once` (:513).
- Worst case: 0.1 s + 1.5 s per port that does not answer the handshake, so 1.6 s × N ports
  (4 ports: 6.4 s). Ports that answer return sooner.
- User-visible: ticking "Use Arduino" or pressing "Detectar" freezes the wizard.
- Fix: same helper as A6-04 (thread + `after(0, ...)`); the scan itself is thread-safe.
- Confidence: high.
- Status (2026-11-18): fixed with the A6-04 helper (button, checkbox and template restore). Block `live_config_detection_off_tk`.

### A6-06 — `ArduinoManager.connect`/`disconnect` on Tk, holding a lock

- Where: `io/arduino_manager.py:104` (`connect`): `candidate.connect()` runs inside
  `with self._lock`; with `handshake="ready_line"` it blocks in `readline()` up to the serial
  `timeout=2` (`io/arduino.py:53-80`). `_shutdown_reader_locked` (:483) joins the reader and the
  writer, `join(timeout=1.0)` each, and the reader is itself parked in `serial.readline()`.
- Thread: Tk. `ui/components/project_initializer.py:394` calls
  `arduino_manager.connect(...)` from `initialize_live_components` on project open;
  `disconnect()` is reached from project close and from the UI.
- Worst case: 2 s (handshake) for `connect`, up to 2 s for `disconnect` (two joins). With the
  default `handshake="none"` the connect is the cost of opening the port.
- User-visible: opening a live project with Arduino enabled hangs for up to ~2 s; a failed
  connection ends in a warning dialog right after.
- Fix: connect on a daemon thread and publish the result; `_notify_status` already marshals to
  Tk in the dashboard widget (`arduino_dashboard.py` `_run_on_ui_thread`).
- Confidence: medium (depends on the project's handshake setting).
- Status (2026-11-18): `connect` fixed. `ProjectInitializer` connects on a worker and shows the offline warning on Tk; `ArduinoManager.connect` no longer holds `_lock` across the port open and handshake (the dashboard asks `is_connected()` on Tk), and a new `_connect_lock` serialises connects. `disconnect` (two bounded joins under the lock, on project close) is unchanged. Blocks `arduino_connect_lock_split`, `project_open_arduino_off_tk`.

### A6-07 — Live `stop_session` joins and flushes on Tk

- Where: `core/recording/live_session_manager.py:1015` (`stop_session`):
  - drain of the video queue, bounded by `_stop_drain_timeout_s = 2.0` (:59);
  - 0.1 s tick loop until the three threads exit, bounded by `_max_join_wait_s = 5.0` (:54), see
    :1123 `time.sleep(TICK_S)`;
  - `_finalize_recorder` → `Recorder.stop_recording` → `_stop_flush_thread`
    (`io/recorder.py:569-586`, `thread.join(timeout=10.0)`) and the final Parquet flush;
  - `camera.release()` (`io/camera.py:443`: `join(timeout=2)` + `join(timeout=1)`);
  - on a manual cancel, `shutil.rmtree` of the session folder (:1157).
- Thread: Tk. The method destroys the preview window and calls `root.after_cancel` (:1033-1041,
  :1166-1171); both require Tk. Callers: stop button, session timer (`root.after`),
  `camera_connection_handler.py:381` (recovery dialog "stop"), `live_camera_session_coordinator`
  :1293.
- Worst case, constants only: the drain and join share a 5 s budget by design (comment at :1058);
  then up to 10 s for the flush thread and up to 3 s for the camera: 18 s. The common case is a
  fraction of a second to a few seconds.
- User-visible: after "Stop" or when the timer fires, the window stops responding for the length
  of the flush; a long session on OneDrive is the likely slow case.
- Fix: the budget is an explicit design decision (tests assert it), so the smallest change is
  presentation: show a modal "Finalizing recording..." before the call and pump `update()`. The
  real fix runs the teardown from `_finalize_recorder` onward on a worker and finishes the UI
  steps in `after(0, ...)`.
- Confidence: high for the thread, medium for the real-world duration.
- Status (2026-11-18): fixed as decided by the maintainer (asynchronous stop). With a Tk root, `stop_session` cancels the timer on Tk, runs the teardown (drain, joins, ledger, recorder flush, discard `rmtree`, camera release) on a daemon worker under a modal "Finalizing recording..." window, and finishes on Tk (preview, state, buttons, `on_session_stopped`, then the new `on_stopped` callback). The post-analysis and the cancel finalization of the coordinator run from `on_stopped`; a stop requested during a stop only queues its callback; `join_threads` waits up to 20 s for an in-flight teardown before exit. Without a root (headless, end-to-end tests) the stop stays synchronous. Blocks `live_stop_async_and_countdown`, `live_post_analysis_after_stop`, `live_cancel_finalizes_once`, `app_exit_waits_for_live_stop`.

### A6-08 — Live `start_session`: camera warm-up and a nested event loop

- Where: `core/recording/camera_connection_handler.py:114-141` (`_setup_camera`: `Camera(...)`,
  then up to 50 warm-up reads with `sleep(0.05)` and, on a failed read, `sleep(0.1)`, capped by
  `warmup_timeout = 5.0`), and `core/recording/live_session_manager.py:741-763` (countdown: a
  `while not countdown_done.is_set()` loop calling `root.update_idletasks()` and `root.update()`
  every 0.05 s, or `time.sleep(countdown_seconds)` when there is no root).
- Thread: Tk. `start_session` is reached from the live coordinators without any thread, and the
  countdown loop itself calls `root.update()`, which is only valid on Tk.
- Worst case: 5 s warm-up (+ camera open) and then the countdown length, during which the loop
  re-enters Tk event processing.
- User-visible: the warm-up freezes the window; the countdown does not, but `root.update()` inside
  a handler lets the user press Start again, close the window or click another tab while
  `start_session` is half way (re-entrancy). This is the only `root.update()` pump in
  `src/zebtrack` outside the startup code (`app_runner.py:204`) and the splash screen.
- Fix: replace the pump with `root.after` chaining (the recording service already has
  `_run_countdown(seconds, on_complete)`, which is what this loop waits on) and move the warm-up to
  the capture thread.
- Confidence: high.
- Status (2026-11-18): the nested `root.update()` loop is gone. With a root the countdown is armed and `start_session` returns `True`; threads, recorder and status start from the countdown's completion callback (`_finish_start_after_countdown`). A failure after the countdown shows "Could not start the recording." and stops the session. Camera warm-up stays on Tk, as decided. Block `live_stop_async_and_countdown`.

### A6-10 — Recursive delete with OneDrive retry sleeps on Tk

- Where:
  - `core/services/weight_manager.py:1448` (`_rmtree_with_unlock`, `time.sleep(0.5)` at :1479),
    used by `clear_openvino_cache` (:1522, :1560) and reached from
    `ui/components/global_model_configuration_panel.py:721` and :743 (buttons) and
    `core/viewmodels/main_view_model_runtime.py:237` (`MODEL_CLEAR_OPENVINO_CACHE`);
  - `core/project/asset_manager.py:1243` (`_rmtree_safe`, sleep at :1262), used by
    `remove_aquarium_subject_data` (:1104); the sibling `remove_video_entry` (:918) calls
    `shutil.rmtree(results_path, ignore_errors=True)` at :959 and :1021 with no sleep.
- Thread: Tk for the weight panel (button + synchronous bus). The asset manager is reached from
  the project-view delete handlers; I did not trace each of them to a button.
- Worst case: the sleeps occur only after an `OSError`, 2 × 0.5 s per call; the cost that is
  always there is deleting an OpenVINO cache (hundreds of MB) or a results folder on OneDrive.
- User-visible: "Delete OpenVINO cache" and removing a video/aquarium with its files stall the
  window.
- Fix: run `clear_openvino_cache` and the project deletes on a daemon thread and report through
  the existing report dialog with `after(0, ...)`. For the sleeps, do not sleep after the last
  attempt.
- Confidence: high for the panel path, medium for the asset manager.
- Status (2026-11-18): weight panel fixed (`clear_openvino_cache` on a worker, report on Tk; block `openvino_cache_clear_off_tk`). `asset_manager._rmtree_safe` is unchanged: it mutates `project_data` and saves the project, so moving it off Tk is a ProjectManager contract change; its sleeps already skip the last attempt.

### A6-11 — Window close and cancel: bounded joins on Tk

- Where: `core/viewmodels/main_view_model_runtime.py:524-560` (`join_threads`, three
  `join(timeout=5.0)` plus `camera.release()`), reached from `core/main_view_model.py:381` after
  the exit confirmation; `coordinators/progress_tracking_coordinator.py:686`
  (`worker.cancel(timeout=2.0)`) from the cancel button.
- Thread: Tk.
- Worst case: close: up to 15 s of joins plus 3 s of camera release (only when threads do not
  respond); cancel: 2 s. Both are bounded on purpose (the docstring of `cancel_processing` says
  "bounded timeout keeps the UI thread responsive").
- User-visible: the window freezes while closing, or for up to 2 s after "Cancel".
- Fix: none required for a normal close; if wanted, call `cancel_processing` from a thread and
  disable the button first. Listed for completeness.
- Confidence: high; severity low.
- Status (2026-11-18): Cancel fixed (the bounded wait for the worker runs on a daemon thread; block `processing_cancel_off_tk`). Window close unchanged: the exit has to wait for the teardown, as this finding already says.

## Confirmed — widget or `tk.Variable` access from a non-Tk thread

### A6-09 — `StateManager` observers publish UI events that subscribers do not marshal

- Where (publishers, they run on the `StateManager` pool, `state_manager.py:381`):
  `core/viewmodels/main_view_model_runtime.py`
  - `on_project_state_changed` (:353): on `active_zone_video` / `project_data` publishes
    `UI_REDRAW_ZONES` and `UI_UPDATE_ZONE_LIST` (:360-367), and calls
    `project_manager.get_zone_data()` on the pool thread;
  - `on_detector_state_changed` (:369): `use_openvino` calls
    `ui_state_controller.update_openvino_status()` (:388), which publishes
    `UI_UPDATE_OPENVINO_STATUS`;
  - `on_processing_state_changed` (:390): `is_processing=True` publishes
    `UI_NAVIGATE_TO_ANALYSIS_VIEW` (:409).
- Where (subscribers, no marshalling), all in `ui/components/event_dispatcher.py`:
  - :760 `UI_REDRAW_ZONES` → `canvas_manager.redraw_zones_from_project_data` → `renderer.redraw_zones`
    (canvas item creation/deletion);
  - :766 `UI_UPDATE_ZONE_LIST` → `zone_editor.update_zone_listbox` (listbox and `winfo_exists()`);
  - :727 `UI_NAVIGATE_TO_ANALYSIS_VIEW` → `analysis_view_controller.start_analysis_view_mode`
    (`analysis_view_controller.py:147`: `StringVar.set`, `show_progress_bar`, notebook switch);
  - :676 `UI_UPDATE_OPENVINO_STATUS` → `weight_hardware_manager.update_openvino_status_display`
    (`StringVar.set`).
- How I know: `StateManager._call_observer_with_timeout` always hands the observer to
  `_observer_executor.submit(...)` (the inline path is only the shutdown fallback). The same
  dispatcher already wraps the sibling subscriptions of the same publisher in
  `self._run_on_ui_thread(...)`: `UI_SET_ACTIVE_WEIGHT` (:668) and `UI_UPDATE_OPENVINO_CHECKBOX`
  (:682) come out of the very same `on_detector_state_changed`, so the pattern was applied to two
  of the three events of that function. `UI_SET_STATUS`/`SET_STATUS` carry a comment explaining
  why unmarshalled `StringVar.set` is a bug; the four above were missed.
  `project_data`/`active_zone_video` are set on every open/close
  (`project_workflow_service.py:1114`, :1278, `project_workflow_adapter.py:106`), so (a) and (b)
  run once per project open and close.
- Failure mode: with a threaded Tcl, tkinter forwards the call to the main thread and blocks the
  pool thread until the mainloop serves it, so most runs "work". It fails (`RuntimeError: main
  thread is not in main loop`, or a lost update) when the loop is not running or a modal dialog
  is in the middle of `wait_window`, and it makes the canvas redraw race with Tk-thread edits of
  the same zone data. This is the class of bug `canvas_manager._on_live_frame_update` documents
  as "the classic source of sporadic freezes".
- Fix (smallest): wrap the four subscriptions with `self._run_on_ui_thread(lambda: ...)`, exactly
  like :668-686. No behaviour change on the Tk thread.
- Confidence: high for the thread of the publisher and the absence of marshalling; medium on how
  often the Tcl layer turns it into a visible failure (not reproduced).

## Suspected

### A6-S1 — Legacy `VideoProcessingService` path publishes frames from the monitor thread

- Where: `core/video/progress_notifier.py:231` (live `_make_progress_callback`; the :153 twin is
  inside `create_progress_callback`, which has no caller, see A2-D-199 in
  `docs/audits/2026-11_A2_tail_review.md`), `core/video/tracking_session_runner.py:153`,
  `core/video/video_context_factory.py:165`, :177 publish `UI_DISPLAY_FRAME`,
  `UI_UPDATE_DETECTION_OVERLAY` and `UI_UPDATE_ANALYSIS_TASK_STATUS`. Their subscribers
  (`event_dispatcher.py:625`, :629, :746) are unmarshalled: `canvas_manager.update_video_frame`
  reads `winfo_width()` and updates a `PhotoImage`; `update_analysis_task_status`
  (`state_synchronizer.py:778`) does `task_var.set`.
- Why only suspected: the batch path that the app uses today goes through
  `ProgressTrackingCoordinator`, which marshals with `root.after` (`progress_tracking_coordinator.py`
  :231, :374, :410, :458). The unmarshalled path is `VideoProcessingService.process_single_video`
  (`analysis_control_view_model.py:626`) and `process_frame_source`; I did not establish which
  thread calls them in each flow.
- Fix: marshal these three subscriptions in the dispatcher the same way as A6-09; it is harmless
  if they already run on Tk.
- Confidence: low-medium.
- Status (2026-11-18): not confirmed. `VideoProcessingService.process_single_video` is reached only from `AnalysisService.process_videos_batch`, which has no caller, and `process_frame_source` has none either; the reachable publishers of these events (live session) run on Tk. No change.

### A6-S2 — `_WorkerProcess` is a non-daemon `multiprocessing.Process`

- Where: `core/video/processing_worker.py:485` (`super().__init__(name=...)`, no `daemon=True`).
  The only termination is `self.process.terminate()` in `_monitor_loop` (:477), which runs on a
  daemon thread.
- Risk: if the app closes while a batch is running and the cancel does not reach the child, the
  interpreter's `multiprocessing` exit hook joins non-daemon children and the process lingers
  until the batch ends. Close does send the cancel (`join_threads` → `cancel_current_analysis`),
  so the normal case is covered; the gap is a hung or very slow worker.
- Fix: `daemon=True` in `__init__` (children are killed with the parent) — check that nothing
  relies on the worker surviving the parent.
- Confidence: low.
- Status (2026-11-18): confirmed and fixed. The only `terminate()` is at the end of `_monitor_loop`, a daemon thread that dies with the interpreter, so a worker that ignored the cancel kept the closed app alive. `_WorkerProcess` is now `daemon=True`; nothing relies on it outliving the app and it spawns no processes. Block `processing_worker_daemon`.

### A6-S3 — Opening a video file to draw one frame, on Tk

- Where: `ui/components/canvas/video_frame_manager.py:154` and :511,
  `ui/components/video_display.py:121`, `ui/components/canvas/multi_aquarium_overlay.py:113`.
- Risk: `cv2.VideoCapture` + seek + read on selection. Local files are fast; on OneDrive with
  Files On-Demand an unhydrated 100+ MB video is downloaded on first open, which blocks Tk for
  as long as the download takes. Not measured.
- Fix: none unless the lag is reported; if so, load the frame on a daemon thread with the cached
  `PhotoImage` delivered by `after(0, ...)`.
- Confidence: low.
- Status (2026-11-18): confirmed on Tk; left as recommended above (no lag reported).

### A6-S4 — `UI_UPDATE_WEIGHTS_LIST` subscriber is unmarshalled

- Where: `ui/components/event_dispatcher.py:690` →
  `weight_hardware_manager.update_weights_dropdown` (:133) → `refresh_weights_summary` (sets a
  `StringVar`). The publisher's thread was not traced; the neighbouring weight events are
  marshalled, this one is not.
- Fix: wrap with `_run_on_ui_thread`, same as A6-09.
- Confidence: low.
- Status (2026-11-18): not confirmed. The publishers (`add_new_weight`, `delete_weight`) run from the weight panel buttons, after a `filedialog`, through the synchronous bus: Tk thread. No change.

## Checked and fine

| Item | Why it is not a finding |
| --- | --- |
| `time.sleep` in `frame_processing_pipeline.py` (:484-693, :2505), `arduino_manager` reader/writer (:566-596), `camera.py:330`, `frame_ledger` | Worker threads, all `daemon=True`. |
| `core/app_runner.py:321` (`_rmtree_with_unlock` on reset) | CLI `--reset` path, before any Tk root exists. |
| `ui/splash_screen.py:215-231` (`sleep`) | Pumps `splash.update()` in 50 ms slices; the docstring says why a plain sleep is wrong. |
| `io/camera.py:550-556`, `io/recorder.py:2192`, `io/arduino.py:331` | `__main__`/self-test blocks. |
| `StateManager` observers | Fire and forget (`_call_observer_with_timeout`); the caller never waits. `ui/components/state_synchronizer.py` marshals each one with `root.after(0, ...)`. |
| Arduino status/log/command callbacks | `arduino_dashboard.py` `_run_on_ui_thread` / `append_log` marshal. |
| `UI_UPDATE_LIVE_FRAME` | `canvas_manager._on_live_frame_update` stores the frame and schedules a single `after(0)` (drop-latest). |
| `UI_SHOW_*`, `SHOW_*`, `UI_SET_STATUS`, `SET_STATUS`, `UI_REFRESH_PROJECT_VIEWS` | Marshalled in `event_dispatcher.py`. |
| Workers in `arduino_bindings_panel.py:516`, `block_detail_dialog.py:2053`, `camera_disconnect_recovery_dialog.py:321`, `model_diagnostics_coordinator.py:360`, `live_analysis_post_processor.py:889`, `analysis_control_view_model.py:244,279` | Read: all deliver UI results with `after(0, ...)` or `UIScheduler`. |
| `ProgressTrackingCoordinator` callbacks | Marshal with `root.after` (:231, :374, :410, :458). |

## Daemon-thread rule

Every `threading.Thread(...)` under `src/zebtrack` passes `daemon=True` (checked at each of the
21 construction sites; `ProcessingMonitor` sets `thread.daemon = True` on the next line,
`processing_worker.py:268`). `ThreadPoolExecutor`s (`state_manager`, `visualization_generator`,
`multi_aquarium_detector`) use the executor's own threads; the first one is shut down with
`wait=False`. The only exception is A6-S2.
