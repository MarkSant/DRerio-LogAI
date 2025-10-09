# Test Fixtures

This directory contains test data files used by the ZebTrack-AI test suite.

## Video Files

- **sample_video.mp4** - Standard test video (10s, 640x480, 2-3 zebrafish)
  - Used by: `test_video_source.py`, `test_detector.py`, `test_overlay_integration.py`
  - Purpose: Video processing pipeline tests

- **sample_video_long.mp4** - Extended test video (30s+)
  - Used by: Performance and memory tests
  - Purpose: Long-running analysis validation

## Project Files

- **zones_project.yaml** - Pre-configured project with 3 ROIs
  - Zones: Arena (full frame), Top zone, Bottom zone
  - Used by: `test_interval_frames_config.py`, zone persistence tests
  - Purpose: Project loading and zone configuration validation

- **calibration_project.yaml** - Project with pixel-to-cm calibration
  - Calibration: 10px = 1cm
  - Used by: `test_calibration.py`, `test_recorder.py`
  - Purpose: Calibration and cm-coordinate output tests

## Detection Data

- **sample_detections.parquet** - Pre-recorded detection results
  - Schema: `timestamp, frame, track_id, x1, y1, x2, y2, confidence`
  - Used by: `test_concrete_behavioral_analyzer.py`, `test_reporter.py`
  - Purpose: Analysis and reporting tests without running full detection

- **sample_detections_with_calibration.parquet** - Detections with cm coordinates
  - Additional columns: `x_center_px, y_center_px, x_cm, y_cm`
  - Used by: Calibrated analysis tests
  - Purpose: Validate cm-based metrics

## Model Weights

- **yolo11n.pt** - YOLOv11 Nano weights (if available)
  - Size: ~6MB
  - Used by: Detector integration tests
  - Purpose: Real detection model validation

- **test_model.xml** / **test_model.bin** - OpenVINO test model
  - Used by: OpenVINO plugin tests
  - Purpose: OpenVINO inference validation

## Creating New Fixtures

1. **Small files** (<1MB): Commit directly to repository
2. **Large files** (>1MB): Use Git LFS or document external download location
3. **Sensitive data**: Never commit real experiment data; use synthetic fixtures
4. **Documentation**: Update this README when adding new fixtures

## Fixture Generation Scripts

Run these to regenerate fixtures if needed:

```powershell
# Generate sample video (requires ffmpeg)
poetry run python scripts/generate_test_video.py

# Generate sample detections from video
poetry run python scripts/generate_test_detections.py

# Generate project configs
poetry run python scripts/generate_test_projects.py
```

## Notes

- All fixtures should be platform-independent (avoid absolute paths)
- Use minimal file sizes to keep repository lean
- Fixtures should be representative of real data but not actual experimental data
- Update tests if fixture format changes
