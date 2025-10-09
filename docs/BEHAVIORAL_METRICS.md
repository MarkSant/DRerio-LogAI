# Behavioral Metrics Reference

This document summarizes the behavioral metrics produced by ZebTrack-AI and the configuration filters that influence each calculation.

## Trajectory Smoothing Filters

Savitzky-Golay smoothing is applied to every trajectory before metrics are computed. You can control two parameters in `config.yaml` under `trajectory_smoothing` or directly from the single-video analysis dialog:

- **`window_length`** (odd integer ≥ 3): number of frames included in each smoothing window.
- **`polyorder`** (integer < `window_length`): polynomial degree used to fit each window.

These constraints are validated automatically (`polyorder < window_length`, and `window_length` must be odd). Lower values preserve fast oscillations, while larger windows/degree combinations aggressively denoise at the risk of flattening peaks.

## ROI Inclusion Rules

Region-of-interest filters define how detections are classified inside or outside polygons drawn on the warped (perspective-corrected) view:

| Rule | Description | Notes |
| --- | --- | --- |
| `centroid_in` | Uses the centroid of each detection (post-warp pixels) to test containment. | Fastest option; sensitive to jitter. |
| `centroid_in_on_buffered_roi` | Expands ROI by a configurable radius before testing the centroid. | Buffer radius expressed in centimeters, automatically converted to pixels. |
| `bbox_intersects` | Requires a minimum overlap ratio between the detection bounding box and the ROI polygon. | Works well for elongated shapes; overlap threshold is percentage-based. |
| `seg_overlap` | Reserved for future segmentation overlays. | Currently raises a descriptive error if segmentation masks are unavailable. |

All ROI presence checks run in warped pixel space to ensure they are aligned with the calibrated arena. Metric aggregation (durations, distances) continues to use centimeter coordinates for reporting.

## Thigmotaxis Metrics

`ConcreteBehavioralAnalyzer.get_thigmotaxis_timeseries()` now returns the per-frame distance (in cm) between the smoothed centroid and the arena boundary. The series is used by:

- **Average distance to wall**: mean of the time series.
- **Time near wall**: share of the recording where the distance is below a user-specified threshold.

If smoothed coordinates are unavailable for a frame, raw centimeter positions are used as a fallback so that thigmotaxis metrics remain available even with short or noisy trajectories.

## Freezing and Speed Filters

Behavioral filters still rely on the following configurable thresholds exposed in the single-video dialog and `video_processing` settings:

- `freezing_velocity_threshold`
- `freezing_min_duration_s`
- `sharp_turn_threshold_deg_s`

These parameters combine with the smoothing setup to control downstream metrics such as freezing episodes, sharp turns, and speed bursts.
