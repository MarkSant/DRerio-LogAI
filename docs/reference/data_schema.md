# DRerio LogAI Data Schema Reference

**Category:** Reference (Diátaxis)
**Status:** Canonical

## 1. Tracking Data (Parquet)

The persistence layer uses Apache Parquet (Snappy compression) for tracking data. All spatial coordinates are in pixels unless otherwise specified.

### File: `video_tracking.parquet`

| Column         | Type     | Description                                                 |
| -------------- | -------- | ----------------------------------------------------------- |
| `timestamp`    | `double` | Seconds since the start of recording.                       |
| `frame`        | `int64`  | Zero-indexed frame number.                                  |
| `track_id`     | `int64`  | Unique ID. Multi-aquarium: `aquarium_id * 1000 + local_id`. |
| `x1`, `y1`     | `double` | Top-left bounding box corner, in RAW VIDEO PIXELS.          |
| `x2`, `y2`     | `double` | Bottom-right bounding box corner, in RAW VIDEO PIXELS.      |
| `confidence`   | `double` | Detector confidence score (0.0 - 1.0).                      |
| `uncertainty`  | `double` | (Optional) Bayesian or tracking uncertainty.                |
| `x_center_px`  | `double` | Bounding box center X (pixels).                             |
| `y_center_px`  | `double` | Bounding box center Y (pixels).                             |
| `x_cm`, `y_cm` | `double` | Real-world coordinates. **Never written today** - see below. |

### Coordinate space

`x1..y2` are **raw video pixels** in every pipeline. Live and pre-recorded both
call `Recorder.start_recording()` without `calibration=`, so
`Calibration.transform_bbox` never runs.

Do not "fix" that in passing. The homography rectifies coordinates into a
600 px-wide space, while `ReportGenerationCoordinator._normalize_df_to_local_space`
subtracts an arena offset measured in raw pixels, and ROIs are stored in raw
pixels too. Supplying a calibration would corrupt every distance, speed and ROI
membership while the run still reported success.

The `x_cm`/`y_cm` columns need `pixel_per_cm_ratio` on `start_recording()`, which
no production caller passes. Centimetres are derived at REPORT time instead,
from the arena bounding box and the video entry's metadata
(`ReportGenerationCoordinator._resolve_pixel_cm`). Adding the columns is a
deliberate schema change: pass `pixel_per_cm_ratio` **without** `calibration`,
do it on the live side too, and update `tests/test_recorder.py`.

## 2. Project Hierarchy

The project structure is organized according to the experimental design defined in the Wizard.

```text
project_root/
├── config.yaml               # Static project metadata
├── arena_templates/          # Saved ROI geometries
└── [Group_Name]/
    └── [Day_Number]/
        └── [Subject_ID]/
            ├── video_tracking.parquet
            ├── [video_name]_processed.mp4
            ├── 1_summary.xlsx
            ├── 2_detailed_report.docx
            └── 3_trajectories.png
```

## 3. Settings Resolution

The application loads settings in the following order of precedence (higher wins):

1. `config.local.yaml` (Local overrides, ignored by Git)
2. `config.yaml` (Project/User defaults)
3. Pydantic model defaults in `src/zebtrack/settings.py`

**Critical Rule:** Never modify `config.yaml` directly from the code if you want to preserve user choice. Use `settings_obj` throughout the runtime.
