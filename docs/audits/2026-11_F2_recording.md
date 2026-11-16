# F2 — `core/recording/` coverage front (TASK-087)

Scope: `src/zebtrack/core/recording/` (11 files, the live-camera pipeline). Method: a real
`LiveCameraService` (or the real mixin) with the hardware faked at its boundary — a scripted
`Camera`, a deterministic clock, fake worker threads, a manual Tk `after` queue, a scripted frame
queue that drives the REAL `_processing_loop`, real trajectories and ledgers written to
`tmp_path` and read back by the post-analysis. Every expected value is derived from the test
input (frame sizes, timestamps, box areas, durations). One mutation block per module at the end
of `scripts/mutation_catalog.yaml`; every block scores 100 %.

## Defects

| id | `file:line` | what is wrong | evidence | status |
| --- | --- | --- | --- | --- |
| F2-R-001 (A4-02) | `core/recording/live_analysis_post_processor.py:461` and `:870` | The "tracks" figure of the live completion dialog (multi-aquarium total and single aquarium) was `df["track_id"].nunique()`: a one-row ByteTrack glitch showed as a second animal, and a trajectory with no identified row showed zero animals. The report counts animals after `screen_subjects` with `count_subjects` ("Um animal é um animal", #649/#671). | `TestCompletionTrackCount`: track of 1 s + one-row track gave `tracks == 2` (expected 1); an all-NaN trajectory gave `0` (expected 1); two aquariums, one with a glitch, gave `3` (expected 2). Red first. Fixed: both sites call `_count_live_subjects`, which runs `screen_window_subjects` (threshold `min_track_duration_from(settings)`) and `count_subjects`. Frames and detections still describe the raw recording. Mutation block `live_completion_subject_count` (4/4). | fixed |

No other defect was found: every other red test in this front was a wrong expectation in the
test itself.

## Observations (not defects)

| id | `file:line` | observation | status |
| --- | --- | --- | --- |
| F2-R-O1 | `core/recording/recording_service.py:337` (`_run_countdown.update_timer`) | If the countdown window stops existing before 0 (it has no close button — `overrideredirect` — so only the WM or a crash can remove it), `update_timer` returns without calling the callback: the recording silently never starts and no error is shown. Pinned by `test_window_closed_mid_countdown_never_starts_the_recording`; changing it is a UX decision (start anyway vs. abort with a message). | reported |
| F2-R-O2 | `core/recording/frame_processing_pipeline.py:1023-1029` (`_processing_loop`, phase 2) | The live loop warps every analysed frame with `project_data["calibration"]["homography_matrix"]`/`target_dims_px` when both exist. Nothing writes those keys today (grep: no producer), so the branch is dormant; if a future calibration step persisted them, the live trajectory would be recorded in the rectified space while ROIs and the arena stay in raw pixels — the exact corruption the "x1..y2 are RAW VIDEO PIXELS" rule in `CLAUDE.md` forbids. Not tested on purpose (pinning it would bless it); worth removing or guarding. | reported |
| F2-R-O3 | `tests/core/recording/test_live_session_manager_extended.py` (`TestLiveSessionManagerExtended5`, `TestLiveSessionManagerExtended4.test_arena_defined_event_initial`) | Pre-existing tests that only set and read attributes or a `threading.Event` — no production code runs. They pass `test_no_hollow_tests.py` (no `object.__new__`) but check nothing; the new `TestStartSession*` classes cover what they name. Left in place (not this front's to delete). | reported |
| F2-R-O4 | `tests/core/test_recording_service.py` + `tests/core/recording/test_recording_service_extended.py` | Two test files for one module (the "one test file per module" rule). New tests went into the first; the `_extended` file (4 tests) should be merged into it. | reported |
| F2-R-O5 | `core/recording/live_session_manager.py:988-989`, `live_analysis_post_processor.py:1330`, `:1482-1483` | Remaining uncovered lines: the `traceback.format_stack` failure branch of `_hung_thread_stacks` (needs a broken frame object), a single-row `np.median` branch and the `write_partitioned_detection_data` log of the multi detector. Left uncovered rather than reached through monkeypatched internals. | skipped |

## Coverage

Measured on the recording test subset (every test file that mentions `core.recording`,
`LiveCameraService` or `RecordingService`; `-m "not gui"`, `--cov=zebtrack --cov-branch`). The
"before" total equals the CI figure for `core.recording` (83.0 % line).

| module | line before | line after | branch before | branch after |
| --- | ---: | ---: | ---: | ---: |
| `camera_connection_handler.py` | 60.7 % | 100.0 % | 45.7 % | 93.5 % |
| `condition_runtime.py` | 97.1 % | 97.1 % | 94.1 % | 94.1 % |
| `frame_ledger.py` | 91.9 % | 91.9 % | 85.4 % | 85.4 % |
| `frame_processing_pipeline.py` | 84.1 % | 89.4 % | 72.8 % | 81.0 % |
| `live_analysis_post_processor.py` | 81.2 % | 99.4 % | 62.4 % | 92.5 % |
| `live_camera_mode.py` | 86.4 % | 100.0 % | 75.0 % | 100.0 % |
| `live_camera_service.py` | 86.4 % | 100.0 % | 16.7 % | 100.0 % |
| `live_output_paths.py` | 100.0 % | 100.0 % | — | — |
| `live_session_manager.py` | 75.4 % | 99.6 % | 64.9 % | 93.7 % |
| `recording_service.py` | 92.2 % | 99.4 % | 89.3 % | 96.4 % |
| **`core/recording/` total** | **83.0 %** (2624/3160) | **95.4 %** (3019/3165) | **70.9 %** (718/1012) | **88.1 %** (892/1012) |

## Mutation blocks added

| block | module | score |
| --- | --- | --- |
| `camera_connection_handler` | `camera_connection_handler.py` | 8/8 |
| `live_session_manager_lifecycle` | `live_session_manager.py` | 13/13 |
| `live_camera_service_facade` | `live_camera_service.py` | 6/6 |
| `recording_service_session` | `recording_service.py` | 8/8 |
| `live_camera_mode_selector` | `live_camera_mode.py` | 6/6 |
| `live_completion_subject_count` | `live_analysis_post_processor.py` (F2-R-001) | 4/4 |
| `live_post_processor_flow` | `live_analysis_post_processor.py` | 9/9 |
| `live_aquarium_detection_phase` | `frame_processing_pipeline.py` | 7/7 |

One survivor appeared on the way (`live_post_processor_flow/unnumbered-folder-accepted`: the
test's `aquarium_x` folder had no trajectory, so it was skipped for the wrong reason); the test
now puts a trajectory in it and the mutant dies.

## Not covered on purpose

- `frame_processing_pipeline.py` keeps ~115 uncovered lines: capture-loop error paths that need a
  failing `cv2.VideoCapture`, the video-writer thread's OSError branches and the dormant
  homography warp (F2-R-O2).
- `frame_ledger.py` and `condition_runtime.py` were already above 90 % and were not touched.
