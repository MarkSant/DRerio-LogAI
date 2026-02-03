# ZebTrack-AI Data Schema Reference

**Category:** Reference (Diátaxis)
**Status:** Canonical

## 1. Tracking Data (Parquet)

The persistence layer uses Apache Parquet (Snappy compression) for tracking data. All spatial coordinates are in pixels unless otherwise specified.

### File: `video_tracking.parquet`

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | `double` | Seconds since the start of recording. |
| `frame` | `int64` | Zero-indexed frame number. |
| `track_id` | `int64` | Unique ID. Multi-aquarium: `aquarium_id * 1000 + local_id`. |
| `x1`, `y1` | `double` | Top-left bounding box corner. |
| `x2`, `y2` | `double` | Bottom-right bounding box corner. |
| `confidence` | `double` | Detector confidence score (0.0 - 1.0). |
| `uncertainty` | `double` | (Optional) Bayesian or tracking uncertainty. |
| `x_center_px` | `double` | Bounding box center X (pixels). |
| `y_center_px` | `double` | Bounding box center Y (pixels). |
| `x_cm`, `y_cm` | `double` | (Optional) Real-world coordinates after calibration. |

## 2. Project Hierarchy

The project structure is organized according to the experimental design defined in the Wizard.

```
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

1.  `config.local.yaml` (Local overrides, ignored by Git)
2.  `config.yaml` (Project/User defaults)
3.  Pydantic model defaults in `src/zebtrack/settings.py`

**Critical Rule:** Never modify `config.yaml` directly from the code if you want to preserve user choice. Use `settings_obj` throughout the runtime.
