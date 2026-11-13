# Live Camera & Analysis Reference

**Status:** Canonical Reference
**Last Updated:** November 4, 2026
**Category:** Reference (Diátaxis)

## 1. Overview

The Live Camera system handles real-time video streaming, recording, and analysis. In v2.2+, it was unified to support both single-aquarium and multi-aquarium configurations with shared frame-buffering logic.

## 2. Hardware Interface

- **VideoSource (`io/video_source.py`):** The abstraction layer for OpenCV/Camera captures. Handles exposure, white balance, and resolution settings.
- **Recording (`io/recorder.py`):** Synchronous frame writing to MP4 while simultaneously persisting detection coordinates to Parquet.

## 3. Live Analysis Pipeline

Live analysis operates in two modes:

1. **Preview Only:** Standard 30/60 FPS stream for setup.
2. **Analysis Mode:** Frames are processed by `DetectorService` before display.

### 3.1. Multi-Aquarium Partitioning

For multi-aquarium live analysis, the system:

- Crops the full frame into $N$ sub-regions based on assigned aquariums.
- Parallelizes detection using a `ThreadPoolExecutor` to maintain frame rates.
- Re-maps local IDs to global IDs (`aquarium_id * 1000 + id`).

### 3.2. Analysis Window, Capture Clock and Object Sidecar (v8)

A live session can carry an **analysis window** (ADR-011): START/STOP conditions evaluated
online by `core/recording/condition_runtime.ConditionRuntime`. The recording is always
complete; the window only marks where the analysis starts and stops (and, with
`on_stop="end_session"`, ends the session through the same "End and Save" path).

- **Where the spec comes from:** live project → `project_data["analysis_window"]`; ad hoc →
  the dialog config's `analysis_window`. Never the shared `Settings`.
- **Clock:** every analysed frame is dated `t_capture_perf − t0_perf`, where `t0` is pinned on
  the frame ledger by the capture thread at frame 1. The trajectory `timestamp` is a processing
  clock and is never used to date an event.
- **Inputs per frame:** class presence from `pop_class_observations()` (subject + context
  roles of the detector's role map), subject ROIs by the same rule as the Arduino per-ROI
  commands, and external events — Arduino codes (stamped by the serial reader at
  `readline()`) and the **Mark start/stop** button of the live project controls.
- **Arduino:** with a window, per-ROI commands run only inside it and the exit sweep runs at
  its STOP. Codes the window waits for are claimed by the window and never start or stop a
  session. See `external_trigger_gate` for the start-time rules.
- **UI:** the external-trigger notice becomes a "waiting for the start condition" banner
  (`ANALYSIS_WINDOW_STATE_CHANGED`), mirrored on the status bar and the preview status.
- **Outputs:** `3c_Objetos_<base>.parquet` gets a heartbeat on EVERY analysed frame
  (`clock="capture_perf"` in its metadata); `7_AnalysisWindow_<base>.json` gets the `online`
  section and `external_events` at session end.
- **Multi-aquarium (#656):** one window per aquarium, each on its own animal, ROIs and
  classes; Arduino codes and the manual mark reach every aquarium. One aquarium's STOP
  sweeps only its own scoped bindings, and `on_stop="end_session"` waits for every
  aquarium. The banner shows one line per aquarium.

## 4. Operational Parameters

| Parameter      | Default | Description                                    |
| -------------- | ------- | ---------------------------------------------- |
| `fps_limit`    | 30      | Target capture rate to prevent CPU saturation. |
| `buffer_size`  | 5       | Shared memory buffer for frame stabilization.  |
| `use_openvino` | Auto    | Enables hardware acceleration if available.    |

---

**Developer Tip:** UI updates during live streaming **must** use `UIScheduler.schedule_update()` to avoid blocking the capture thread.
