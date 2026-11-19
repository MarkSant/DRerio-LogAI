# A2 — exploratory `ruff --select ERA,ARG` pass (TASK-087)

A one-off report the A2 plan asked for next to the vulture ratchet. **Nothing here was
fixed**: each row is a candidate for the maintainer. The rules are not enabled in
`pyproject.toml`; most hits are signatures that a caller imposes, and turning the rules
on would mean dozens of `noqa` comments that say nothing.

## Method

```bash
ruff check --select ERA,ARG src/zebtrack --output-format json --no-cache
```

Run on 2026-11-19 against `claude/audit-guards-bd8d1c` (cut from
`worktree-cov-plugins-utils` at `858d0a13`). Every hit was put next to its enclosing
function, whether that function is passed as a callback anywhere in `src`, and how many
classes define a method of the same name. Callback signatures (Tk `bind`, `EventBusV2`
handlers, `StateManager` observers, worker callbacks) are false positives by
construction: the caller decides the arguments. Every other hit was read in the source.

## Summary

| Rule | Meaning | Hits | Real | False positive |
|---|---|---|---|---|
| `ARG001` | unused function argument | 15 | 2 | 13 |
| `ARG002` | unused method argument | 87 | 21 | 66 |
| `ARG004` | unused static-method argument | 6 | 6 | 0 |
| `ARG005` | unused lambda argument | 59 | 1 | 58 |
| `ERA001` | commented-out code | 29 | 4 | 25 |
| **total** | | **196** | **34** | **162** |

## Worth the maintainer's attention

Parameters that a docstring promises and the body ignores are the dangerous kind: the
caller believes the knob works.

- `AquariumDetector.detect_multiple_aquariums(max_area_ratio=...)` documents a per-aquarium
  maximum area and never applies it. It is the same idea as the reader-less setting
  `detection_zones.max_aquarium_area_ratio` (A7-01).
- `UIStateCoordinator._publish_processing_mode(force=...)` documents forcing the update; the
  flag does nothing.
- `LiveCameraSessionCoordinator.start_live_session(zones=...)` documents zone configurations
  for detection and ignores them (zones reach the detector by another path).
- `CalibrationCoordinator.get_calibration_scope_info(get_active_weight_name=...)` documents a
  callback it never calls.
- `SequentialProcessingCoordinator`: the per-aquarium `on_error` handler drops its second
  argument, which is the experiment id, so the warning does not say which video failed.

## Every hit

| Rule | Where (`src/zebtrack/...`) | Argument | Verdict | Why |
|---|---|---|---|---|
| `ARG001` | `analysis/reporters/project_reporter.py:279` | `settings_obj` | real | accepted and ignored by `export_multi_aquarium_reports` |
| `ARG002` | `coordinators/calibration_coordinator.py:71` | `get_active_weight_name` | real | documented as the callback that names the active weight; never called |
| `ARG002` | `coordinators/dialog_coordinator.py:139` | `scanned_videos` | real | redundant: the docstring says it equals `with_data` here |
| `ARG002` | `coordinators/live_camera_session_coordinator.py:1014` | `zones` | real | documented as 'zone configurations for detection'; `start_live_session` ignores it |
| `ARG002` | `coordinators/progress_tracking_coordinator.py:463` | `frame_number` | real | passed by every caller of `_update_frame_display`, never read |
| `ARG002` | `coordinators/report_generation_coordinator.py:698` | `settings_obj` | real | `_process_summary_video` takes it and reads `self.settings` instead |
| `ARG005` | `coordinators/sequential_processing_coordinator.py:364` | `msg` | real | the second argument of `on_error` is the experiment id (see `tracking_session_runner.py:171`); the sequential per-aquarium handler names it `msg` and drops it, so its warning does not say which video failed |
| `ARG002` | `coordinators/ui_state_coordinator.py:443` | `force` | real | documented as 'force update even if mode hasn't changed'; ignored, so the flag does nothing |
| `ARG002` | `core/detection/aquarium_detector.py:944` | `max_area_ratio` | real | documented as the per-aquarium maximum area; ignored. Same knob as the reader-less `detection_zones.max_aquarium_area_ratio` (A7-01) |
| `ARG002` | `core/project/asset_manager.py:183` | `zone_data_to_dict_fn` | real | `save_roi_template` takes the converter and never calls it |
| `ARG002` | `core/project/parquet_io_manager.py:327` | `project_data` | real | ignored by `copy_zone_parquet_files` |
| `ARG004` | `core/project/project_lifecycle_manager.py:206` | `video_files` | real | ignored by `validate_project_parameters` |
| `ARG004` | `core/project/project_lifecycle_manager.py:348` | `add_video_batch_fn` | real | ignored by `create_new_project` |
| `ARG004` | `core/project/project_lifecycle_manager.py:349` | `save_project_fn` | real | ignored by `create_new_project` |
| `ERA001` | `core/project/project_service.py:122` | — | real | commented-out call `self._save_settings_snapshot(...)` marked DEPRECATED |
| `ARG004` | `core/project/video_manager.py:598` | `video_entry` | real | ignored by `remove_video_entry` |
| `ARG004` | `core/project/zone_orchestration_manager.py:288` | `project_data` | real | ignored by `sync_multi_aquarium_flags` |
| `ARG002` | `core/services/detector_service.py:362` | `config_name` | real | ignored by `get_parameter_definitions` (vulture reports it too) |
| `ARG002` | `core/state_manager.py:523` | `timeout_seconds` | real | the docstring says the caller does not wait; the timeout is never applied (vulture reports it too) |
| `ARG002` | `core/ui_scheduler.py:49` | `event_bus` | real | kept on purpose: the comment says 'kept for backward-compat signature; ignored in v2' |
| `ARG002` | `core/video/tracking_session_runner.py:52` | `detector` | real | ignored by `run_tracking_if_needed` |
| `ARG002` | `core/video/tracking_session_runner.py:53` | `recorder` | real | ignored by `run_tracking_if_needed` |
| `ARG002` | `core/video/tracking_session_runner.py:55` | `calibration_data` | real | ignored by `run_tracking_if_needed` |
| `ARG002` | `core/video/tracking_session_runner.py:58` | `video_context` | real | ignored by `run_tracking_if_needed` |
| `ARG002` | `core/video/video_processing_service.py:137` | `record_video` | real | ignored by `process_frame_source`, which has no caller (dead chain of A4-13) |
| `ERA001` | `ui/components/zone_controls.py:479` | — | real | commented-out `pack()` of the aquarium selector (the frame is shown elsewhere) |
| `ERA001` | `ui/ui_coordinator.py:250` | — | real | commented-out call to a `validate_zones` the comment above says does not exist |
| `ERA001` | `ui/ui_coordinator.py:251` | — | real | second line of the same commented-out block |
| `ARG001` | `ui/window_utils.py:23` | `window` | real | `_try_actions` receives the window and only runs the closures |
| `ARG002` | `ui/wizard/detection_step.py:706` | `paths` | real | `_pattern_days_as_folders` is a stub that returns None ('Simplified for MVP') |
| `ARG002` | `ui/wizard/detection_step.py:711` | `paths` | real | `_pattern_mixed_folders` is a stub that returns None ('Simplified for MVP') |
| `ARG004` | `ui/wizard/models.py:288` | `separator` | real | documented keyword of `build_combined_regex_pattern`; ignored (vulture reports it too) |
| `ARG002` | `utils/hardware_capability.py:270` | `cpu_usage` | real | intentional per the docstring (the tier must be stable, so live usage is not used); the parameter could go |
| `ARG002` | `utils/hardware_capability.py:271` | `memory_usage` | real | intentional per the docstring (the tier must be stable, so live usage is not used); the parameter could go |
| `ARG002` | `analysis/behavior.py:1242` | `step` | false positive | override or implementation of a shared interface; the signature is the interface's |
| `ARG005` | `analysis/reporters/word_reporter.py:94` | `p` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `analysis/reporters/word_reporter.py:94` | `s` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG002` | `analysis/roi.py:1051` | `x_coords` | false positive | uniform signature of the per-rule dispatch in `ROIAnalyzer` |
| `ARG002` | `analysis/roi.py:1051` | `y_coords` | false positive | uniform signature of the per-rule dispatch in `ROIAnalyzer` |
| `ERA001` | `analysis/visualization_generator.py:381` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ERA001` | `analysis/visualization_generator.py:391` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ERA001` | `analysis/visualization_generator.py:393` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ERA001` | `analysis/visualization_generator.py:394` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ERA001` | `analysis/visualization_generator.py:403` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ERA001` | `analysis/visualization_generator.py:578` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ARG002` | `coordinators/live_camera_session_coordinator.py:324` | `payload` | false positive | callback whose signature is imposed by its caller (bus, worker, `re.sub`) |
| `ARG002` | `coordinators/live_camera_session_coordinator.py:456` | `payload` | false positive | callback whose signature is imposed by its caller (bus, worker, `re.sub`) |
| `ARG002` | `coordinators/recording_session_coordinator.py:814` | `data` | false positive | callback whose signature is imposed by its caller (bus, worker, `re.sub`) |
| `ARG005` | `coordinators/sequential_processing_coordinator.py:359` | `exp_id` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `coordinators/sequential_processing_coordinator.py:359` | `frac` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `coordinators/sequential_processing_coordinator.py:359` | `idx` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `coordinators/sequential_processing_coordinator.py:359` | `msg` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `coordinators/sequential_processing_coordinator.py:359` | `stats` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `coordinators/sequential_processing_coordinator.py:359` | `total` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `coordinators/sequential_processing_coordinator.py:360` | `dets` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `coordinators/sequential_processing_coordinator.py:360` | `fn` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `coordinators/sequential_processing_coordinator.py:360` | `frame` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `coordinators/sequential_processing_coordinator.py:361` | `exp_id` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `coordinators/sequential_processing_coordinator.py:361` | `idx` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `coordinators/sequential_processing_coordinator.py:361` | `total` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `coordinators/sequential_processing_coordinator.py:369` | `data` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `coordinators/sequential_processing_coordinator.py:372` | `data` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `coordinators/sequential_processing_coordinator.py:372` | `msg` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `coordinators/video_processing_coordinator.py:391` | `data` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ERA001` | `core/application_bootstrapper.py:88` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ARG002` | `core/conditions/evaluator.py:349` | `ctx` | false positive | override or implementation of a shared interface; the signature is the interface's |
| `ARG002` | `core/conditions/evaluator.py:380` | `ctx` | false positive | override or implementation of a shared interface; the signature is the interface's |
| `ARG002` | `core/conditions/evaluator.py:390` | `ctx` | false positive | override or implementation of a shared interface; the signature is the interface's |
| `ARG002` | `core/conditions/evaluator.py:390` | `obs` | false positive | override or implementation of a shared interface; the signature is the interface's |
| `ARG002` | `core/detection/multi_aquarium_detector.py:590` | `project_type` | false positive | documented as kept for API compatibility |
| `ARG002` | `core/detection/single_detector.py:571` | `project_type` | false positive | callback whose signature is imposed by its caller (bus, worker, `re.sub`) |
| `ARG002` | `core/main_view_model.py:348` | `category` | false positive | `StateManager` observer: the observer signature is fixed |
| `ARG002` | `core/main_view_model.py:348` | `key` | false positive | `StateManager` observer: the observer signature is fixed |
| `ARG002` | `core/main_view_model.py:348` | `new` | false positive | `StateManager` observer: the observer signature is fixed |
| `ARG002` | `core/main_view_model.py:348` | `old` | false positive | `StateManager` observer: the observer signature is fixed |
| `ARG001` | `core/video/progress_notifier.py:175` | `progress_fraction` | false positive | callback whose signature is imposed by its caller (bus, worker, `re.sub`) |
| `ARG001` | `core/video/tracking_session_runner.py:162` | `idx` | false positive | callback whose signature is imposed by its caller (bus, worker, `re.sub`) |
| `ARG001` | `core/video/tracking_session_runner.py:162` | `total` | false positive | callback whose signature is imposed by its caller (bus, worker, `re.sub`) |
| `ARG005` | `core/video/tracking_session_runner.py:172` | `data` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `core/video/tracking_session_runner.py:172` | `out_dir` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `core/video/tracking_session_runner.py:175` | `data` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `core/video/tracking_session_runner.py:175` | `msg` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ERA001` | `core/viewmodels/analysis_control_view_model.py:509` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ARG002` | `core/viewmodels/main_view_model_runtime.py:373` | `category` | false positive | `StateManager` observer: the observer signature is fixed |
| `ARG002` | `core/viewmodels/main_view_model_runtime.py:373` | `new` | false positive | `StateManager` observer: the observer signature is fixed |
| `ARG002` | `core/viewmodels/main_view_model_runtime.py:373` | `old` | false positive | `StateManager` observer: the observer signature is fixed |
| `ARG002` | `core/viewmodels/main_view_model_runtime.py:389` | `category` | false positive | `StateManager` observer: the observer signature is fixed |
| `ARG002` | `core/viewmodels/main_view_model_runtime.py:389` | `old` | false positive | `StateManager` observer: the observer signature is fixed |
| `ARG002` | `core/viewmodels/main_view_model_runtime.py:410` | `category` | false positive | `StateManager` observer: the observer signature is fixed |
| `ERA001` | `io/arduino_manager.py:538` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ERA001` | `plugins/openvino_detector.py:381` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ARG001` | `ui/builders/analysis_widgets.py:175` | `data` | false positive | callback whose signature is imposed by its caller (bus, worker, `re.sub`) |
| `ARG005` | `ui/collapsible_frame.py:60` | `e` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/collapsible_frame.py:61` | `e` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/collapsible_frame.py:62` | `e` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/collapsible_frame.py:65` | `e` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/collapsible_frame.py:66` | `e` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG002` | `ui/components/behavioral_config_widget.py:373` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG002` | `ui/components/behavioral_config_widget.py:385` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG002` | `ui/components/behavioral_config_widget.py:406` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG002` | `ui/components/behavioral_config_widget.py:410` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG002` | `ui/components/canvas/event_handler.py:167` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG002` | `ui/components/canvas/event_handler.py:171` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG002` | `ui/components/canvas/event_handler.py:352` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG002` | `ui/components/canvas/event_handler.py:366` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG002` | `ui/components/canvas/event_handler.py:373` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG002` | `ui/components/canvas/event_handler.py:379` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG002` | `ui/components/canvas/event_handler.py:523` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG002` | `ui/components/canvas/event_handler.py:634` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG002` | `ui/components/canvas/event_handler.py:757` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG002` | `ui/components/canvas/event_handler.py:823` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG002` | `ui/components/canvas/event_handler.py:843` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG002` | `ui/components/canvas/video_frame_manager.py:540` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG002` | `ui/components/canvas/video_frame_manager.py:85` | `event` | false positive | Tk event handler: Tk passes the event |
| `ERA001` | `ui/components/class_roles_panel.py:1295` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ERA001` | `ui/components/config_editor.py:182` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ERA001` | `ui/components/config_editor.py:271` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ERA001` | `ui/components/config_editor.py:339` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ERA001` | `ui/components/config_editor.py:418` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ARG002` | `ui/components/config_editor.py:882` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG005` | `ui/components/event_dispatcher.py:1005` | `d` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/components/event_dispatcher.py:1009` | `d` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/components/event_dispatcher.py:1013` | `d` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/components/event_dispatcher.py:1019` | `d` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/components/event_dispatcher.py:1030` | `d` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/components/event_dispatcher.py:1042` | `d` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/components/event_dispatcher.py:1044` | `d` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG001` | `ui/components/event_dispatcher.py:1047` | `d` | false positive | callback whose signature is imposed by its caller (bus, worker, `re.sub`) |
| `ARG005` | `ui/components/event_dispatcher.py:1095` | `d` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG001` | `ui/components/event_dispatcher.py:310` | `d` | false positive | callback whose signature is imposed by its caller (bus, worker, `re.sub`) |
| `ARG001` | `ui/components/event_dispatcher.py:315` | `d` | false positive | callback whose signature is imposed by its caller (bus, worker, `re.sub`) |
| `ARG001` | `ui/components/event_dispatcher.py:320` | `d` | false positive | callback whose signature is imposed by its caller (bus, worker, `re.sub`) |
| `ARG005` | `ui/components/event_dispatcher.py:392` | `d` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG001` | `ui/components/event_dispatcher.py:713` | `d` | false positive | callback whose signature is imposed by its caller (bus, worker, `re.sub`) |
| `ARG005` | `ui/components/event_dispatcher.py:763` | `d` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/components/event_dispatcher.py:974` | `d` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/components/event_dispatcher.py:977` | `d` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/components/event_dispatcher.py:983` | `d` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/components/event_dispatcher.py:987` | `d` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/components/event_dispatcher.py:991` | `d` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG001` | `ui/components/menu_manager.py:245` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG005` | `ui/components/menu_manager.py:63` | `e` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG002` | `ui/components/processing_reports.py:362` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG002` | `ui/components/project_overview.py:270` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG002` | `ui/components/project_overview.py:288` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG002` | `ui/components/project_views/report_generator_actions.py:314` | `data` | false positive | callback whose signature is imposed by its caller (bus, worker, `re.sub`) |
| `ARG001` | `ui/components/project_views/report_generator_actions.py:43` | `exc_info` | false positive | callback whose signature is imposed by its caller (bus, worker, `re.sub`) |
| `ARG002` | `ui/components/state_synchronizer.py:106` | `category` | false positive | `StateManager` observer: the observer signature is fixed |
| `ARG002` | `ui/components/state_synchronizer.py:106` | `old_value` | false positive | `StateManager` observer: the observer signature is fixed |
| `ARG002` | `ui/components/state_synchronizer.py:112` | `category` | false positive | `StateManager` observer: the observer signature is fixed |
| `ARG002` | `ui/components/state_synchronizer.py:112` | `old_value` | false positive | `StateManager` observer: the observer signature is fixed |
| `ARG002` | `ui/components/state_synchronizer.py:118` | `category` | false positive | `StateManager` observer: the observer signature is fixed |
| `ARG002` | `ui/components/state_synchronizer.py:118` | `old_value` | false positive | `StateManager` observer: the observer signature is fixed |
| `ARG002` | `ui/components/state_synchronizer.py:590` | `kwargs` | false positive | deliberate catch-all |
| `ARG002` | `ui/components/state_synchronizer.py:97` | `category` | false positive | `StateManager` observer: the observer signature is fixed |
| `ARG002` | `ui/components/state_synchronizer.py:97` | `old_value` | false positive | `StateManager` observer: the observer signature is fixed |
| `ARG001` | `ui/components/tab_builder.py:256` | `event` | false positive | Tk event handler: Tk passes the event |
| `ERA001` | `ui/components/validation_manager.py:126` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ARG002` | `ui/components/video_display.py:87` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG002` | `ui/components/zone_controls.py:1029` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG002` | `ui/components/zone_controls.py:1348` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG005` | `ui/components/zone_controls.py:169` | `e` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG002` | `ui/components/zone_controls.py:335` | `payload` | false positive | callback whose signature is imposed by its caller (bus, worker, `re.sub`) |
| `ARG002` | `ui/components/zone_edit_guard.py:47` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG005` | `ui/dialogs/aquarium_assignment_dialog.py:552` | `e` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/dialogs/aquarium_assignment_dialog.py:553` | `e` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG002` | `ui/dialogs/aquarium_assignment_dialog.py:591` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG005` | `ui/dialogs/block_detail_dialog.py:237` | `e` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG002` | `ui/dialogs/diagnostic_progress_dialog.py:131` | `event` | false positive | Tk event handler: Tk passes the event |
| `ERA001` | `ui/dialogs/live_analysis_dialog.py:315` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ERA001` | `ui/dialogs/live_analysis_dialog.py:405` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ERA001` | `ui/dialogs/live_analysis_dialog.py:479` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ARG005` | `ui/dialogs/live_analysis_dialog.py:722` | `e` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/dialogs/live_analysis_dialog.py:723` | `e` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/dialogs/preview_polygon_dialog.py:250` | `e` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/dialogs/preview_polygon_dialog.py:251` | `e` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ERA001` | `ui/dialogs/single_video_config_dialog.py:186` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ERA001` | `ui/dialogs/single_video_config_dialog.py:256` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ERA001` | `ui/dialogs/single_video_config_dialog.py:316` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ERA001` | `ui/dialogs/single_video_config_dialog.py:365` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ERA001` | `ui/dialogs/single_video_config_dialog.py:399` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
| `ARG005` | `ui/dialogs/subject_selection_dialog.py:87` | `e` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/dialogs/zone_calibration_dialog.py:137` | `e` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/dialogs/zone_calibration_dialog.py:138` | `e` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/dialogs/zone_reuse_dialog.py:117` | `e` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/dialogs/zone_reuse_dialog.py:118` | `e` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG002` | `ui/gui.py:753` | `args` | false positive | callback whose signature is imposed by its caller (bus, worker, `re.sub`) |
| `ARG002` | `ui/gui.py:914` | `data` | false positive | callback whose signature is imposed by its caller (bus, worker, `re.sub`) |
| `ARG002` | `ui/ui_coordinator.py:378` | `data` | false positive | callback whose signature is imposed by its caller (bus, worker, `re.sub`) |
| `ARG002` | `ui/ui_coordinator.py:446` | `data` | false positive | callback whose signature is imposed by its caller (bus, worker, `re.sub`) |
| `ARG005` | `ui/wizard/discovery_step.py:92` | `event` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG005` | `ui/wizard/experimental_design_step.py:355` | `args` | false positive | lambda whose signature is imposed by the callee (Tk `bind`, bus handler, worker callback) |
| `ARG001` | `ui/wizard/models.py:359` | `m` | false positive | callback whose signature is imposed by its caller (bus, worker, `re.sub`) |
| `ARG002` | `ui/wizard/tooltip.py:40` | `event` | false positive | Tk event handler: Tk passes the event |
| `ARG002` | `ui/wizard/tooltip.py:49` | `event` | false positive | Tk event handler: Tk passes the event |
| `ERA001` | `utils/hardware_capability.py:307` | — | false positive | explanatory comment that only looks like code (formula, grid legend, data shape) |
