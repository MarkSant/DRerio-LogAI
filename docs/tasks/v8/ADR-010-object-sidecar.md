# ADR-010: Non-subject detections live in a `3c_Objetos_<base>.parquet` sidecar

**Status:** Accepted · **Date:** 2026-10-30 · **Version:** 8.0.0

## Context

Start/stop conditions need, per processed frame, which classes were present — including context
classes (experimenter, start box) and frames where nothing was detected. `3_CoordMovimento` has
no class column and its schema is immutable. Two options were weighed.

**Add a class column to the trajectory.** Writing is trivial (the class already reaches
`recorder.py:875`), but every consumer would then have to filter by role: 7 analysis entry
points, the recorder dedup, the trajectory validator (`unique_tracks > 1` switches semantics),
`ArduinoRoiEvaluator.occupied_rois` and `script_exporter` (since removed, #696). A single
omission yields plausible, wrong numbers. It also breaks 5 exact-column tests and the golden, and needs migration of every
existing file.

**A sidecar, following `3b_Mascaras_`.** ~150 lines mirroring `write_mask_data`; the trajectory
stays "subjects only" by construction.

## Decision

Sidecar `3c_Objetos_<base>.parquet`, next to the trajectory (per `aquarium_N/` folder in
multi-aquarium). The name must never start with `3_CoordMovimento` (readers glob that prefix and
take `[0]`).

Columns, fixed order, additions only:

```text
frame:int64, timestamp:float64 (same value as 3_CoordMovimento),
t_event_s:float64 (PTS or capture clock), class_id:int16 (-1 = heartbeat),
class_name:dictionary<string>, role:dictionary<string> (subject|context|frame),
x1, y1, x2, y2:float32 (null on heartbeat), confidence:float32,
track_id:int64 (nullable), aquarium_id:int16 (nullable)
```

Parquet key-value metadata: `zebtrack.objects_schema=1`, `class_names`, `class_roles`,
`weight_sha256`, `clock` (`pts` | `capture_perf`), `analysis_interval_frames`.

Rules:

- **One heartbeat row per processed frame**, even with no detection — absence must be
  distinguishable from "frame not processed".
- **Raw video pixels**, never calibrated (same convention as the trajectory).
- Lazy writer on the recorder's flush thread, same buffer ceiling; a write failure degrades with
  a warning and never kills the session.
- `start_recording` deletes stale `3b_`, `3c_` and `7_` files of the same base (fixes the stale
  mask bug found in the audit).
- Import (`parquet_io_manager.py:747`) copies the whole set `3_`, `3b_`, `3c_`, `6_`, `7_`.
- Written always; kill switch `recorder.persist_object_sidecar` (default `True`). For zebrafish
  this is ~2 rows per processed frame, and it keeps "change the condition later" possible without
  re-detection (user decision 1).
- Context rows with `aquarium_id = null` apply to every aquarium.

## Consequences

- `3_CoordMovimento` schema unchanged; `tests/test_recorder.py` immutability tests stay green.
- New file in the output folder, labelled by `report_files.describe_session_output`.
