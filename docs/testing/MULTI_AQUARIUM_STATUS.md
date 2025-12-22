# Multi-Aquarium Reporting Status (Dec 2025)

This note captures the current state of multi-aquarium reporting fixes to avoid regressions.

## Confirmed Improvements
- Aquarium 0 reports now render the correct cropped background with trajectory/heatmap aligned to the aquarium ROI.
- Sequential processing now runs both aquariums in order and emits individual Word reports per aquarium (aq0, aq1).
- Per-aquarium output directories are created under `<video>_results/` (e.g., `aquarium_0`, `aquarium_1`) with trajectory parquet files written there.

## Remaining Issues
- Aquarium 1 report still shows background content outside its aquarium ROI and is missing trajectory/heatmap overlays.
- Summary parquet files are not being emitted for either aquarium during the multi-aquarium summary step.
- FFMPEG codec warnings appear (`Could not find decoder for codec_id=61`) during background frame extraction.

## Next Steps
1. Fix summary generation to use per-aquarium zone data and crop boxes, ensuring heatmaps/trajectories render for aquarium 1.
2. Ensure summary parquet export runs per aquarium and is written inside each `aquarium_<id>` directory with the aquarium suffix.
3. Address codec fallback for background frame extraction so reports render even when a decoder is unavailable.

## Regression Guards
- Keep the per-aquarium crop box derived from aquarium polygons when storing `outputs_by_aquarium`.
- Ensure sequential flow owns advancement between aquariums; avoid advancing inside `on_video_completed`.
- Maintain the frame_crop-aware visualization path in `VisualizationGenerator` (see new regression test).
