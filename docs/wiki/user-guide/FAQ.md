<!-- markdownlint-disable MD024 -->

# Frequently Asked Questions (FAQ)

## Table of Contents

1. [General Questions](#general-questions)
2. [Installation and Setup](#installation-and-setup)
3. [Technical Requirements](#technical-requirements)
4. [Video and Camera](#video-and-camera)
5. [Detection and Tracking](#detection-and-tracking)
6. [Analysis and Results](#analysis-and-results)
7. [Performance and Optimization](#performance-and-optimization)
8. [Advanced Features](#advanced-features)
9. [Troubleshooting](#troubleshooting)

---

## General Questions

### What is DRerio LogAI (ZebTrack-AI)?

DRerio LogAI is a comprehensive Python application for automated zebrafish behavioral tracking and analysis. It uses AI-powered detection (YOLO, OpenVINO) to track subjects in videos or live camera feeds, calculate behavioral metrics, and generate detailed reports.

### What animals does ZebTrack-AI support?

Primarily zebrafish (Danio rerio), but the system works with any small aquatic animals including:

- Medaka fish
- Zebrafish larvae
- Small fish species (guppies, etc.)
- Aquatic invertebrates (with appropriate model training)

### Is ZebTrack-AI free to use?

Yes! ZebTrack-AI is open-source software released under the MIT License. You can use, modify, and distribute it freely for academic or commercial purposes.

### Can I use ZebTrack-AI for publications?

Absolutely! ZebTrack-AI is designed for scientific research. When citing, please use:

```text
ZebTrack-AI: DRerio LogAI - Automated Zebrafish Behavioral Tracking System
https://github.com/MarkSant/ZebTrack-AI
```

(Formal citation format coming soon with publication)

### What programming knowledge is required?

**For basic use**: None! The GUI is designed for non-programmers.

**For advanced use**: Python knowledge helpful for:

- Custom analysis scripts
- Model training
- Plugin development
- Batch processing automation

---

## Installation and Setup

### Which Python version do I need?

**Python 3.12 or higher** is required. Python 3.11 and below are not supported.

To check your Python version:

```bash
python --version
```

### Do I need to install CUDA for GPU support?

**For NVIDIA GPUs**: Yes, install:

- CUDA Toolkit 11.8 or 12.1
- cuDNN 8.x
- Compatible NVIDIA drivers

**For Intel GPUs**: OpenVINO provides Intel GPU support without CUDA.

### Why does installation take so long?

First-time installation downloads:

- AI models (~200MB)
- Python dependencies (~500MB)
- OpenVINO runtime (~800MB if using)

Total: ~1.5GB. Subsequent launches are instant.

### Can I install without Poetry?

Poetry is recommended but not strictly required. Alternative:

```bash
# Using pip (advanced users)
pip install -e .
```

However, Poetry ensures consistent dependency versions and is strongly recommended.

### How do I update to the latest version?

```bash
cd ZebTrack-AI
git pull origin main
poetry install  # Update dependencies
```

---

## Technical Requirements

### What are the minimum system requirements?

### Minimum

- CPU: Dual-core, 2.0 GHz
- RAM: 8GB
- Storage: 5GB free space
- OS: Windows 10, Linux (Ubuntu 20.04+), macOS 11+

### Recommended

- CPU: Quad-core, 3.0 GHz+
- RAM: 16GB+
- GPU: NVIDIA GTX 1060 or better (6GB VRAM)
- Storage: 20GB+ SSD

### Can I run ZebTrack-AI without a GPU?

Yes! CPU-only mode works but is slower:

- **With GPU**: 25-60 FPS real-time processing
- **CPU only**: 5-15 FPS (adequate for pre-recorded videos)

For live analysis, GPU strongly recommended.

### How much disk space do I need?

**Application**: ~2GB (including models)

### Per video analysis

- 1-minute 1080p video: ~50MB results
- 10-minute 1080p video: ~300MB results
- 1-hour 4K video: ~2GB results

Plan for 2-3x video file size for complete results.

### Can I run on a laptop?

Yes, if it meets minimum requirements. Performance tips:

- Close other applications
- Use power adapter (not battery)
- Ensure adequate cooling
- Consider external GPU (eGPU) for better performance

---

## Video and Camera

### What video formats are supported?

All formats supported by OpenCV:

- **Recommended**: MP4 (H.264 codec)
- **Supported**: AVI, MOV, MKV, WEBM, FLV
- **Not recommended**: Uncompressed formats (huge file sizes)

### What is the maximum video resolution?

**Tested up to**: 4K (3840×2160)
**Recommended**: 1080p (1920×1080)
**Minimum**: 480p (640×480)

Higher resolutions:

- ✅ Better detection accuracy
- ❌ Slower processing
- ❌ Larger output files

### What is the ideal video resolution and frame rate?

**Resolution**: 1080p (1920×1080)
**Frame rate**: 30 FPS

This balances:

- Detection accuracy
- Processing speed
- File size
- Temporal resolution

### Can I use multiple cameras simultaneously?

**Current version**: No, single camera per session

**Workaround**: Run multiple instances of the application (resource-intensive)

**Roadmap**: Multi-camera support planned for v3.0

### How do I improve video quality for better tracking?

### Lighting

- Uniform, diffuse lighting (no harsh shadows)
- Avoid glare and reflections
- Consistent brightness across frames

### Camera

- Fixed position (no movement)
- Perpendicular to water surface
- High-quality lens (minimize distortion)

### Recording

- High bitrate (minimize compression artifacts)
- Consistent frame rate (no drops)
- Clean tank (no debris, algae)

### Can I analyze videos from smartphones?

Yes, but consider:

- Transfer video to computer first (don't run on phone)
- Use landscape orientation
- Stabilize phone during recording
- Export at highest quality
- Convert to MP4 if needed

---

## Detection and Tracking

### What is "confidence threshold"?

Confidence threshold is the minimum score (0.0-1.0) required to accept a detection.

### Low threshold (e.g., 0.3)

- ✅ Detects more subjects (fewer misses)
- ❌ More false positives (debris detected as fish)

### High threshold (e.g., 0.7)

- ✅ Fewer false positives (high precision)
- ❌ May miss some subjects (lower recall)

**Default (0.5)**: Good balance for most scenarios

### How do I choose between YOLO and OpenVINO?

### YOLO

- ✅ Better accuracy (state-of-the-art)
- ✅ Works on NVIDIA GPUs
- ❌ Slower on CPU

### OpenVINO

- ✅ Optimized for Intel CPUs
- ✅ Faster on Intel hardware
- ❌ Slightly lower accuracy

**Recommendation**: Start with YOLO. Switch to OpenVINO if you have Intel CPU and no NVIDIA GPU.

### What is "track ID" and why does it change?

**Track ID** is a unique identifier assigned to each detected subject across frames.

**ID changes** (re-identification failures) occur when:

- Subject occlusions (one fish hides another)
- Subject exits and re-enters frame
- Similar-looking subjects swap positions
- Detection gaps (subject temporarily not detected)

### To minimize ID changes

- Increase confidence threshold (more consistent detections)
- Enable multi-subject tracking algorithms
- Improve video quality (better feature extraction)

### Can I track multiple fish in the same video?

Yes! Enable **Multi-Subject Tracking** in Wizard Step 4.

### Supports

- Up to 10 subjects simultaneously (tested)
- Individual metrics per track ID
- Track-by-track analysis in reports

### Limitations

- More prone to ID swaps (re-identification challenges)
- Slightly slower processing
- Requires higher confidence threshold

### How accurate is the detection?

**Typical accuracy** (on zebrafish):

- Precision: 95-98% (few false positives)
- Recall: 92-96% (few misses)
- F1 Score: 93-97%

### Factors affecting accuracy

- Video quality (lighting, resolution, clarity)
- Subject size (larger = easier to detect)
- Background complexity (clean tank = better)
- Model selection (YOLO vs OpenVINO)

### Can I train my own detection model?

Yes, for custom species or setups. Requires:

1. Annotated dataset (100+ images with bounding boxes)
2. YOLO training pipeline (see `docs/MODEL_TRAINING.md` - coming soon)
3. GPU for training (6GB+ VRAM)
4. ~4-8 hours training time

Custom models can be loaded in Wizard Step 4.

---

## Analysis and Results

### What metrics does ZebTrack-AI calculate?

### Spatial metrics

- Total distance traveled (cm)
- Average speed (cm/s)
- Maximum speed (cm/s)
- Time in each ROI (seconds, %)

### Behavioral metrics

- ROI entries and exits
- Dwell time per ROI
- Movement patterns (trajectory)
- Activity levels (speed over time)

**Custom metrics** can be calculated from raw tracking data (Parquet files).

### What is a Parquet file and how do I open it?

**Parquet** is a columnar binary format for efficient data storage.

### Opening Parquet files

### Python (pandas)

```python
import pandas as pd
df = pd.read_parquet("3_CoordMovimento_my_video.parquet")
print(df.head())
```

### R

```r
library(arrow)
df <- read_parquet("3_CoordMovimento_my_video.parquet")
head(df)
```

**Excel/Viewer**: Use [Parquet Viewer](https://github.com/mukunku/ParquetViewer) (Windows GUI)

### Can I export to CSV instead of Parquet?

Yes! Change export format in **Wizard Step 5 → Export Format**.

### Formats

- Parquet (default, most efficient)
- CSV (Excel-compatible, larger files)
- JSON (web applications, human-readable)

Or convert after analysis:

```python
import pandas as pd
df = pd.read_parquet("file.parquet")
df.to_csv("file.csv", index=False)
```

### How do I calculate custom metrics?

Load Parquet file in Python and use pandas:

### Example: Calculate time above speed threshold

```python
import pandas as pd

df = pd.read_parquet("3_CoordMovimento_video.parquet")

# Calculate instantaneous speed
df['speed'] = df.groupby('track_id')[['x_cm', 'y_cm']].diff().pow(2).sum(axis=1).pow(0.5)

# Time above threshold (5 cm/s)
fast_frames = df[df['speed'] > 5].shape[0]
fps = 30  # Video frame rate
time_fast = fast_frames / fps
print(f"Time swimming fast: {time_fast:.2f} seconds")
```

**More examples**: See `docs/CUSTOM_ANALYSIS.md` (coming soon)

### What is calibration and why is it important?

**Calibration** converts pixel coordinates to physical units (cm).

### Without calibration

- Coordinates in pixels (px)
- No distance/speed metrics

### With calibration

- Coordinates in centimeters (cm)
- Distance traveled (cm)
- Speed (cm/s)

**To calibrate**: Place object of known size in arena, measure in pixels, specify real size.

### How long are results stored?

**Forever** (until you delete them). Results are saved locally in:

- `<video_name>_results/` (pre-recorded videos)
- `live_analysis_sessions/` (live camera sessions)

### Best practices

- Archive old results to external storage
- Use descriptive experiment IDs for organization
- Back up important results

---

## Performance and Optimization

### Why is analysis slow?

### Common causes

1. **No GPU acceleration**: CPU-only mode is 3-5x slower
2. **High resolution**: 4K videos take 4x longer than 1080p
3. **Low confidence threshold**: More detections = more processing
4. **Insufficient RAM**: System swapping to disk

**Solutions**: See [Troubleshooting Guide](TROUBLESHOOTING.md#slow-performance)

### How do I enable GPU acceleration?

### For NVIDIA GPUs

1. Install CUDA Toolkit and cuDNN
2. Install GPU-enabled PyTorch:

   ```bash
   poetry run pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
   ```

3. Restart application
4. Check **Help → System Info** to verify GPU detected

### For Intel GPUs

- OpenVINO automatically uses Intel GPU if available
- No additional configuration needed

### Can I process multiple videos in parallel?

Yes! Use **Batch Processing**:

1. **File → Batch Processing**
2. Add videos to queue
3. Configure shared settings (or use per-video settings)
4. Click **Start Batch**

**Parallel videos**: Controlled by `performance.max_parallel_videos` setting (default: 2)

### What is frame skipping and when should I use it?

**Frame skipping** analyzes every Nth frame instead of all frames.

**Skip 1 (default)**: Analyze every frame
**Skip 2**: Analyze every 2nd frame (50% speed increase)
**Skip 5**: Analyze every 5th frame (5x speed increase)

### Use cases

- ✅ Slow-moving subjects (zebrafish at rest)
- ✅ Long videos (1+ hours)
- ✅ Quick preliminary analysis

### Avoid for

- ❌ Fast movements (may miss behavior)
- ❌ Short videos (minimal time savings)
- ❌ High temporal resolution needed

### How much RAM does ZebTrack-AI use?

### Typical usage

- Application: ~500MB
- Video buffer: ~200MB per minute of 1080p video
- AI model: ~500MB (YOLO) to ~1GB (large models)
- Processing: ~1-2GB temporary data

**Total**: 2-4GB for typical session

**High-resolution videos (4K)**: May use 6-8GB

---

## Advanced Features

### What is Arduino integration?

ZebTrack-AI can send commands to Arduino microcontrollers based on ROI events.

### Use cases

- Trigger LED lights when fish enters zone
- Activate pumps/feeders based on behavior
- Synchronize with external devices
- Closed-loop behavioral experiments

**Setup**: See `docs/ARDUINO_INTEGRATION.md` (coming soon)

### Can I create custom ROI shapes?

Yes! ROI tools support:

- **Rectangle**: Click and drag
- **Polygon**: Click corners to define arbitrary shape
- **Circle**: Center + radius

**Complex shapes**: Use polygon tool with many vertices

### What are ROI templates?

**ROI templates** save ROI configurations for reuse across projects.

### Workflow

1. Configure ROIs in Project Wizard
2. **File → Save ROI Template**
3. In future projects: **File → Load ROI Template**

### Use cases

- Consistent experimental setup
- Multi-day experiments
- Batch processing with same ROIs

### Can I export heatmaps as images?

Yes! Heatmaps are automatically saved as PNG images in results directory:

- `<video_name>_heatmap.png`
- Resolution matches original video
- Color scale: Blue (low) → Red (high)

Or generate manually:

```python
from zebtrack.analysis import generate_heatmap
generate_heatmap("3_CoordMovimento_video.parquet", output="heatmap.png")
```

### How do I automate batch processing with scripts?

Use Python API for automation:

```python
from zebtrack.core import Controller
from zebtrack import load_settings

settings = load_settings()
controller = Controller(settings)

# Process multiple videos
videos = ["video1.mp4", "video2.mp4", "video3.mp4"]
for video in videos:
    controller.load_video(video)
    controller.configure_detection(confidence=0.5)
    controller.run_analysis()
    print(f"Completed: {video}")
```

**More examples**: See `docs/SCRIPTING_GUIDE.md` (coming soon)

---

## Troubleshooting

### Camera not detected - what should I do?

### Quick fixes

1. Check camera is connected (USB)
2. Try different USB port
3. Check camera permissions (Windows: Settings → Privacy → Camera)
4. Restart application
5. Try different camera ID (0, 1, 2 in settings)

**Details**: [Troubleshooting Guide - Camera Not Found](TROUBLESHOOTING.md#camera-not-found)

### Detection accuracy is poor - how to improve?

### Immediate fixes

1. Increase confidence threshold (0.5 → 0.6+)
2. Improve lighting (uniform, bright)
3. Clean tank (remove debris)
4. Try different model (YOLO → OpenVINO or vice versa)

**Details**: [Troubleshooting Guide - Low Detection Accuracy](TROUBLESHOOTING.md#low-detection-accuracy)

### Application crashes during analysis - why?

### Common causes

1. **Insufficient RAM**: Close other applications
2. **Corrupted video file**: Try different video
3. **GPU memory overflow**: Reduce batch size or resolution
4. **Python version mismatch**: Ensure Python 3.12+

### Debugging

- Check logs: `logs/zebtrack.log`
- Run with verbose logging: `poetry run zebtrack --verbose`
- Report bug: [GitHub Issues](https://github.com/MarkSant/ZebTrack-AI/issues)

### Results seem incorrect - what's wrong?

### Check

1. **Calibration**: Is physical unit conversion correct?
2. **ROI definitions**: Are ROIs drawn accurately?
3. **Track IDs**: Are there many ID swaps? (affects per-track metrics)
4. **Video quality**: Is detection accuracy acceptable (>90%)?

### Validation

- Manually inspect annotated video
- Check detection rate in analysis summary
- Compare trajectory plots to expected behavior

### Where can I get help?

### Documentation

- [User Guide](GETTING_STARTED.md)
- [Troubleshooting Guide](TROUBLESHOOTING.md)
- Developer docs: `docs/`

### Community

- [GitHub Issues](https://github.com/MarkSant/ZebTrack-AI/issues)
- [Discussions](https://github.com/MarkSant/ZebTrack-AI/discussions)

### Direct support

- Email: <support@zebtrack.ai>

---

## Contributing and Development

### How can I contribute to ZebTrack-AI?

Contributions welcome! See [Contributing Guide](../../../CONTRIBUTING.md) for:

- Bug reports
- Feature requests
- Code contributions
- Documentation improvements
- Testing and validation

### Where is the source code?

GitHub repository: <https://github.com/MarkSant/ZebTrack-AI>

### Structure

```text
ZebTrack-AI/
├── src/zebtrack/        # Application code
├── tests/               # Test suite
├── docs/                # Documentation
├── config.yaml          # Default settings
└── pyproject.toml       # Dependencies
```

### Can I use ZebTrack-AI for commercial purposes?

Yes! The MIT License allows commercial use with no restrictions.

### Requirements

- Include original copyright notice
- Include MIT License text

**No warranty**: Software provided "as-is"

---

## License and Citation

### What license is ZebTrack-AI released under?

**MIT License** - permissive, open-source

You are free to:

- Use commercially
- Modify and distribute
- Use privately
- Sublicense

See [LICENSE](../../../LICENSE) file for full text.

### How do I cite ZebTrack-AI in publications?

**Temporary citation** (until formal publication):

```text
ZebTrack-AI: DRerio LogAI - Automated Zebrafish Behavioral Tracking System
https://github.com/MarkSant/ZebTrack-AI
Version 2.1 (2025)
```

**Formal citation coming soon** with peer-reviewed publication.

---

**Last Updated**: November 2025
**Version**: 2.1
**For more questions**: [Open an issue](https://github.com/MarkSant/ZebTrack-AI/issues) or email <support@zebtrack.ai>
