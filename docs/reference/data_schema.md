# DRerio LogAI Data Schema Reference

**Category:** Reference (Diátaxis)
**Status:** Canonical · updated for v8.0.0

## 1. Tracking Data (Parquet)

The persistence layer uses Apache Parquet (Snappy compression by default,
`performance.parquet_compression`) for tracking data. All spatial coordinates
are in **raw video pixels** unless otherwise specified.

Output files of one video, side by side in its results folder (multi-aquarium:
one `aquarium_{id+1}/` subfolder per aquarium, base name suffixed
`_aquarium_{id+1}`):

| File | Content | Since |
| --- | --- | --- |
| `1_ProcessingArea_<base>.parquet` | Arena (processing area) polygon | — |
| `2_AreasOfInterest_<base>.parquet` | ROIs | — |
| `3_CoordMovimento_<base>.parquet` | Trajectory — subjects only, immutable schema (§1.1) | — |
| `3b_Mascaras_<base>.parquet` | Segmentation masks (only with `recorder.persist_masks`) | 5.x |
| `3c_Objetos_<base>.parquet` | Per-frame heartbeat + subject and context detections (§1.2) | 8.0 |
| `6_FrameLedger_<base>.{csv,parquet}` + `_anchor.json` | One row per captured frame (live only) | 6.x |
| `7_AnalysisWindow_<base>.json` | Resolved analysis window (§1.3) | 8.0 |

No file may start with `3_CoordMovimento` except the trajectory itself: several
readers glob that prefix and take the first match. `Recorder.start_recording()`
deletes stale `3b_`, `3c_` and `7_` files of the same base before recording, so
a reprocessed video never joins the new trajectory with an old sidecar.

### 1.1 File: `3_CoordMovimento_<base>.parquet`

Column order is fixed in `io/recorder.py`; any change requires updating
`tests/test_recorder.py`.

```text
timestamp, frame, track_id, x1, y1, x2, y2, confidence,
[x_center_px, y_center_px, x_cm, y_cm]?, [uncertainty, bbox_iou]?
```

| Column         | Type     | Description                                                 |
| -------------- | -------- | ----------------------------------------------------------- |
| `timestamp`    | `double` | Pre-recorded: the frame's PTS in seconds. Live: a PROCESSING clock — never use it to date an event (see §1.4). |
| `frame`        | `int64`  | Zero-indexed frame number (live: the pipeline frame, joined to the ledger's `pipeline_frame`). |
| `track_id`     | `int64`  | Unique ID. Multi-aquarium: `aquarium_id * 1000 + local_id`. |
| `x1`, `y1`     | `double` | Top-left bounding box corner, in RAW VIDEO PIXELS.          |
| `x2`, `y2`     | `double` | Bottom-right bounding box corner, in RAW VIDEO PIXELS.      |
| `confidence`   | `double` | Detector confidence score (0.0 - 1.0).                      |
| `x_center_px`  | `double` | (Optional) Bounding box center X (pixels).                  |
| `y_center_px`  | `double` | (Optional) Bounding box center Y (pixels).                  |
| `x_cm`, `y_cm` | `double` | Real-world coordinates. **Never written today** - see below. |
| `uncertainty`  | `double` | (Optional, multi-aquarium) `1 - confidence`.                |
| `bbox_iou`     | `double` | (Optional, multi-aquarium) tracking stability.              |

The trajectory holds **subject** detections only (class roles, ADR-009); a
context class (experimenter, start box) never reaches it — it goes to the `3c`
sidecar. A row exists only when something was detected, so a frame without a
row may be "nothing seen" or "not processed"; the `3c` heartbeat tells them
apart.

#### Coordinate space

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

### 1.2 File: `3c_Objetos_<base>.parquet` (v8, ADR-010)

Written when `core/services/object_capture.should_capture_objects()` is true
(`recorder.persist_object_sidecar`, default `True`). Read through
`io/object_sidecar.read_object_sidecar()`: a missing, corrupted or incompatible
file is `None` with a warning, never an exception. Columns in fixed order,
additions only:

| Column | Type | Description |
| --- | --- | --- |
| `frame` | `int64` | Processed frame number (same key as the trajectory). |
| `timestamp` | `float64` | Same value as `3_CoordMovimento.timestamp` for that frame. |
| `t_event_s` | `float64` | The frame on the **event clock**: PTS pre-recorded, `t_capture_perf − t0_perf` live. |
| `class_id` | `int16` | Model class id; `-1` on the heartbeat row. |
| `class_name` | `dictionary<string>` | Class name as declared by the weight. |
| `role` | `dictionary<string>` | `subject`, `context` or `frame` (heartbeat). |
| `x1`, `y1`, `x2`, `y2` | `float32` | Raw video pixels, never calibrated; null on the heartbeat. |
| `confidence` | `float32` | Detector confidence; null on the heartbeat. |
| `track_id` | `int64` | Track id of a subject row; null otherwise. |
| `aquarium_id` | `int16` | Aquarium of the row; null for a context object outside every aquarium (it then applies to all). |

**One heartbeat row per processed frame**, even when nothing was detected — that
is what lets an analysis tell "absent" from "not processed". Subject rows go only
to their own aquarium; a context row goes to the aquarium that contains its
centroid, or to every aquarium with `aquarium_id = null`.

Parquet key-value metadata: `zebtrack.objects_schema=1`, `class_names`,
`class_roles`, `class_roles_source`, `weight_sha256`, `clock` (`pts` |
`capture_perf`), `analysis_interval_frames`.

### 1.3 File: `7_AnalysisWindow_<base>.json` (v8, ADR-011)

Written atomically (temporary file + `os.replace`) by
`core/conditions/artifact.write_artifact()`; read by `read_artifact()`, which
returns `None` for a missing or invalid file (including one whose `spec_hash` no
longer matches its `spec`), meaning "recompute".

```json
{
  "schema": "zebtrack.analysis_window/1",
  "spec": {"version": 1, "start": {}, "stop": {}, "on_start_not_met": "whole_recording", "on_stop": "mark"},
  "spec_hash": "sha256:<64 hex>",
  "clock": "pts",
  "fps_video": 9.9,
  "aquarium_id": null,
  "external_events": [{"t_s": 3.2, "source": "arduino", "code": 1}],
  "online": {"start": {"frame": 66, "t_s": 6.68, "reason": "persist"}, "stop": null},
  "offline": {
    "start": {"frame": 67, "t_s": 6.71, "reason": "persist"},
    "stop": {"frame": 1840, "t_s": 186.0, "reason": "end_of_stream"},
    "status": "censored",
    "inputs": {"trajectory_sha": "…", "objects_sha": "…"}
  }
}
```

| Field | Meaning |
| --- | --- |
| `spec` / `spec_hash` | The `WindowSpec` (persisted condition `kind`s, `"class"` alias) and its hash; the artifact is reused only while both match the project's rule and the input hashes match the files. |
| `clock` | `pts` (pre-recorded) or `capture_perf` (live). |
| `external_events` | Arduino/manual events recorded live; kept when `offline` is rewritten. |
| `online` | What the live runtime decided; drives display and session end only. |
| `offline` | What the analysis computed; **governs the metrics**. A divergence of more than one frame from `online` is a report warning. |
| `reason` | `first_frame`, `persist`, `roi_edge`, `time`, `frame`, `delay`, `external`, `end_of_stream`. Events are back-dated to the first frame of the run that satisfied them. |
| `status` | `complete`, `start_not_met`, `censored` (STOP never met) or `inputs_missing` (e.g. a context-class condition without a `3c`). |

### 1.4 Time

The event clock is PTS for pre-recorded videos and the capture instant from
`6_FrameLedger` for live sessions. `analysis/time_base.retime_from_ledger()`
re-dates a live trajectory **in memory** (`t_capture_perf − t0_perf`, joined on
`pipeline_frame == frame`); the Parquet is never rewritten. fps and duration come
from `analysis/time_base.resolve_time_base()`: 3c heartbeat > ledger > unique
trajectory timestamps > `settings.video_processing.fps` (with a report warning).

## 2. Project Hierarchy

The project structure follows the experimental design defined in the wizard.
The folder names are persistence contracts and are never translated
(`scripts/i18n_allowlist.txt`).

```text
project_root/
├── project_config.json       # Project data (videos, zones, model_selection,
│                             #   model_overrides, analysis_window, ...)
└── Grupo_<group>/
    └── Dia_<day>/
        └── Sujeito_<subject>/
            ├── 1_ProcessingArea_<base>.parquet
            ├── 2_AreasOfInterest_<base>.parquet
            ├── 3_CoordMovimento_<base>.parquet
            ├── 3c_Objetos_<base>.parquet
            ├── 7_AnalysisWindow_<base>.json
            ├── 4_Relatorio_<base>.docx
            └── 4_Relatorio_<base>.xlsx
```

Unassigned levels use `Sem_Grupo`, `Dia_Indefinido` and `Sujeito_Indefinido`.
The folder is resolved by `ProjectManager.resolve_results_directory()` from the
video's path or metadata, never from its `experiment_id` alone (two days of the
same subject share the id).

## 3. Settings Resolution

The application loads settings in the following order of precedence (higher wins):

1. `ProjectManager.project_data` (per-project values such as `model_selection`,
   `model_overrides`, `analysis_window`)
2. `config.local.yaml` (Local overrides, ignored by Git)
3. `config.yaml` (Project/User defaults)
4. Pydantic model defaults in `src/zebtrack/settings.py`

**Critical Rule:** Never modify `config.yaml` directly from the code if you want to preserve user choice. Use `settings_obj` throughout the runtime.
