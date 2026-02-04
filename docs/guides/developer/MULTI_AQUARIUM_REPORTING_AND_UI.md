# Multi-Aquarium Reporting & Reports Tree (Dec 2025)

This document captures the engineering decisions, fixes, and integration contracts for the
multi-aquarium reporting pipeline and the Reports tab UI.

## Scope

This covers:

- Per-aquarium report generation (Word/Excel) for multi-aquarium videos
- Per-aquarium background frame extraction and ROI-local coordinate consistency
- Persistence contracts for `video_entry["multi_aquarium_outputs"]`
- Reports tab tree population and common failure modes

This does NOT cover:

- Multi-aquarium detection itself (see ADR-001)
- Wizard aquarium counting UX

## Symptoms We Fixed

1. Aquarium 1 report was using Aquarium 0 background crop.
2. Aquarium 1 trajectory/heatmap overlays were mispositioned.
3. Reports tab tree showed only one aquarium folder (or the wrong one).
4. Summary indicator sometimes did not update even when summary parquet existed.

## Root Causes

### 1) Wrong accessor for multi-aquarium zone data

The report code path used `ProjectManager.get_zone_data()` in multi-aquarium mode.
That accessor is backward-compatible and returns only the *first* aquarium in multi-mode.

Impact:

- Wrong polygon selected for `aq_id != 0`
- Wrong `frame_crop_box`
- Wrong transform constants (notably video height) for overlay alignment

Fix:

- Always use `get_multi_aquarium_zone_data()` in multi-aquarium report generation.
- Keep a single-aquarium fallback only when multi data is truly absent.

### 2) UI tree used a simplified hierarchy entry

The hierarchy builder may return a simplified `video` dict that omits custom fields like
`multi_aquarium_outputs`. When the Reports tree trusted that dict, it silently behaved as
single-aquarium even though the artifacts existed on disk.

Fix:

- In the Reports tree population logic, fall back to `ProjectManager.find_video_entry(video_path)`
  as the canonical source of truth.

### 3) Mixed key types in `multi_aquarium_outputs`

Depending on serialization paths, `multi_aquarium_outputs` keys may be stored as integers
or strings (`0` vs `"0"`). If the UI builds Treeview node IDs directly from those keys,
Treeview iid collisions can cause only one aquarium node to be visible.

Fix:

- Normalize aquarium IDs to integers and merge duplicate entries.

### 4) Summary/report generation updated files but did not persist metadata reliably

Some flows generated `*_summary.parquet` and `4_Relatorio_*.docx/.xlsx` but did not update
(or persist) the `ProjectManager` video entry flags in a way the UI reliably picked up.

Fix (Option B):

- After generating per-aquarium summary/report outputs, re-register the updated
  `multi_aquarium_outputs` into `ProjectManager.register_multi_aquarium_outputs(...)`.

## Contract: `video_entry["multi_aquarium_outputs"]`

Type: `dict[aquarium_id, dict]` (keys may be int or str; treat as numeric IDs).

Minimum expected per aquarium:

- `results_dir`: absolute path to `.../<video>_results/aquarium_<id>`
- `parquet_files`: map of artifact keys to filenames (relative within `results_dir`)

Common `parquet_files` keys used by UI/pipeline:

- `trajectory`
- `summary` (per-aquarium parquet)
- `summary_excel` (per-aquarium xlsx from report/export)
- `report_docx` (per-aquarium docx)

Optional:

- `frame_crop_box`: `(x, y, w, h)` crop used to render backgrounds consistently

Video-level flags:

- `has_summary`: should be set when any aquarium has `summary` or `summary_excel`

## Reports Tree Rules (UI)

- Build aquarium nodes when `multi_aquarium_outputs` is present.
- If `multi_aquarium_outputs` is missing on the hierarchy `video` dict, fetch the canonical
  entry via `ProjectManager.find_video_entry(video_path)`.
- Normalize aquarium IDs to integers and merge duplicates before creating nodes.
- Avoid filesystem scanning unless `results_dir` exists; treat missing folders as non-fatal.

## OpenCV/FFmpeg Warnings

On some Windows environments, OpenCV may emit FFmpeg warnings like:
`Could not find decoder for codec_id=61` (often MJPEG).

Guidance:

- Prefer extracted background frames (`.png`) for report plots.
- When a `.png` path is passed as background, load it with `cv2.imread` (do not use
  `cv2.VideoCapture`).

## Regression Tests

- `tests/ui/components/test_project_view_manager_reports_tree_multi_aquarium.py`
  - Ensures both aquarium nodes appear
  - Ensures mixed key types do not collide
  - Ensures canonical fallback is used when hierarchy dict omits multi outputs

- `tests/analysis/test_visualization_generator_background_image.py`
  - Ensures `.png` backgrounds use `cv2.imread` and do not call `cv2.VideoCapture`
