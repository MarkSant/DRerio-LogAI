# Multi-Aquarium Outputs Schema (Project Metadata)

This reference describes the persisted project metadata used to represent multi-aquarium
results and how the UI consumes it.

## Location

Multi-aquarium outputs are stored per video entry in the project data:

- `project_data["videos"][i]["multi_aquarium_outputs"]`

The structure is managed by `ProjectManager.register_multi_aquarium_outputs(...)`.

## Type

Conceptually:

- `multi_aquarium_outputs: dict[aquarium_id, AquariumOutputs]`

Where `aquarium_id` is numeric (may be serialized as `"0"`, `"1"` etc).

## AquariumOutputs

Expected fields:

- `results_dir` (str)
  - Absolute path to the aquarium results directory
  - Example: `.../<experiment_id>_results/aquarium_0`

- `parquet_files` (dict[str, str])
  - Map of artifact logical keys to filenames (generally relative to `results_dir`)

Optional / informational fields:

- `group` (str)
- `subject_id` (str)
- `day` (int | str)
- `frame_crop_box` (tuple[int, int, int, int])
  - `(x, y, w, h)` crop box used to extract aquarium-local frames for reporting

## Known `parquet_files` keys

These keys are consumed by the Reports tab and/or downstream report generation:

- `trajectory`: trajectory parquet (per aquarium)
- `summary`: summary parquet (per aquarium)
- `summary_excel`: excel summary/export produced during report generation
- `report_docx`: Word report produced during report generation

## Video-Level Derived Flag

- `video_entry["has_summary"]` should be `True` if ANY aquarium has:
  - `parquet_files["summary"]`, or
  - `parquet_files["summary_excel"]`

This flag is used by the UI to display the summary indicator in the video row.

## Normalization Rules (UI)

Consumers should be robust to key type differences:

- Treat aquarium IDs as numeric
- Normalize keys (`0` and `"0"` are the same aquarium)
- Merge duplicates (union `parquet_files`, prefer non-empty values)
