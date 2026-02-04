# Multi-Aquarium Reporting Status (Dec 2025)

This note captures the current state of multi-aquarium reporting fixes to avoid regressions.

**Last Updated**: Dec 28, 2025 (v3.2)

## ✅ Resolved Issues (Dec 2025)

### Batch Processing Fixes (Dec 28, 2025)

- ✅ **Dialog Suppression**: Individual dialogs no longer appear between videos during batch processing
- ✅ **Unified Reports**: Geotaxis data now correctly appears in unified Excel reports
- ✅ **Subject Identification**: Unified reports now identify subjects (group, subject, day, experiment_id columns)
- ✅ **Column Ordering**: Priority columns (identification) appear first in unified reports

### Report Generation Fixes (Dec 23-28, 2025)

- ✅ **Aquarium 0/1 Reports**: Both aquariums now render correct cropped background with trajectory/heatmap aligned
- ✅ **Sequential Processing**: Both aquariums processed in order with Word reports per aquarium
- ✅ **Per-Aquarium Directories**: Output directories created under `<video>_results/aquarium_0/`, `aquarium_1/`
- ✅ **Zone Data Prioritization**: `generate_project_reports()` now uses `get_multi_aquarium_zone_data()` instead of `get_zone_data()`
- ✅ **Reports Tree UI**: Reports tab displays aquarium folders (`🐠 Aquário 0`, `🐠 Aquário 1`) with artifacts

### Analysis Fixes (Dec 28, 2025)

- ✅ **Max Speed Metric**: Added `max_speed_cm_s` to velocity statistics
- ✅ **Geotaxis Zone Naming**: 1-indexed user-friendly names ("Zona 1 - Fundo" instead of "Zone 0")
- ✅ **Column Display Names**: Word reports use proper formatting with units

## ⚠️ Known Limitations

- FFMPEG codec warnings may appear (`Could not find decoder for codec_id=61`) during background frame extraction - cosmetic only, reports still generate

## Regression Guards

- Keep the per-aquarium crop box derived from aquarium polygons when storing `outputs_by_aquarium`.
- Ensure sequential flow owns advancement between aquariums; avoid advancing inside `on_video_completed`.
- Maintain the frame_crop-aware visualization path in `VisualizationGenerator` (see new regression test).
- **CRITICAL**: In multi-aquarium report generation, ALWAYS use `get_multi_aquarium_zone_data()` instead of `get_zone_data()`.
- **CRITICAL**: `Reporter` legacy constructor must store `self.behavioral_config` before creating tidy_data.
