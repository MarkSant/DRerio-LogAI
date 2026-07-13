# Getting Started with DRerio LogAI

## Welcome

DRerio LogAI is a comprehensive application for zebrafish behavioral tracking and analysis. This guide will help you get started with your first project, from installation to analyzing results.

## Table of Contents

<!-- markdownlint-disable MD051 --><!-- justification: TOC anchors validated by renderer -->

1. [Installation](#installation)
2. [System Requirements](#system-requirements)
3. [First Launch](#first-launch)
4. [Creating Your First Project](#creating-your-first-project)
5. [Understanding the Project Wizard](#understanding-the-project-wizard)
6. [Running Analysis](#running-analysis)
7. [Understanding Results](#understanding-results)
8. [Live Camera Analysis](#live-camera-analysis)
9. [Keyboard Shortcuts](#keyboard-shortcuts)
10. [Next Steps](#next-steps)

<!-- markdownlint-enable MD051 -->

---

## Installation

### Prerequisites

Before installing DRerio LogAI, ensure your system meets these requirements:

- **Operating System**: Windows 10/11, Linux, or macOS
- **Python**: Version 3.12 or higher
- **Hardware**:
  - Minimum 8GB RAM (16GB recommended)
  - Webcam or video files for analysis
  - GPU recommended for real-time processing (NVIDIA with CUDA support)

### Install via Poetry (Recommended)

Poetry is the recommended installation method for both users and developers.

```bash
# 1. Clone the repository
git clone https://github.com/MarkSant/DRerio-LogAI.git
cd DRerio-LogAI

# 2. Install dependencies
poetry install

# 3. Run the application
poetry run zebtrack
```

### Alternative: Install from Release

Pre-built executable releases are coming soon. Check the [Releases page](https://github.com/MarkSant/DRerio-LogAI/releases) for availability.

---

## System Requirements

### Minimum Requirements

- **CPU**: Dual-core processor, 2.0 GHz
- **RAM**: 8GB
- **Storage**: 5GB free space (for application and temporary files)
- **Graphics**: Integrated graphics card
- **Camera**: USB webcam (for live analysis)

### Recommended Requirements

- **CPU**: Quad-core processor, 3.0 GHz or higher
- **RAM**: 16GB or more
- **Storage**: 20GB free space (for video storage and results)
- **Graphics**: NVIDIA GPU with CUDA support (GTX 1060 or better)
- **Camera**: HD webcam (1080p) with good low-light performance

### Supported Video Formats

- MP4 (recommended)
- AVI
- MOV
- MKV
- Any format supported by OpenCV

---

## First Launch

### Starting the Application

After installation, launch the application:

```bash
poetry run zebtrack
```

### Main Window Overview

When the application starts, you'll see the main window with the following components:

![Main Window](../screenshots/main_window.png)

**Key Components**:

1. **Menu Bar**: Access to File, Edit, View, Tools, and Help menus
2. **Toolbar**: Quick access to common actions (New, Open, Save, Run Analysis)
3. **Video Player**: Central area for video playback and visualization
4. **Timeline**: Scrub through video frames
5. **Control Panel**: Play, pause, frame advance controls
6. **Status Bar**: Current frame, FPS, processing status

---

## Creating Your First Project

### Project Creation Flow

DRerio LogAI uses a **Project Wizard** as the primary method for creating new projects. The wizard guides you through 5 essential steps.

### Step 1: Start New Project

1. Click **File → New Project** (or press `Ctrl+N`)
2. The Project Wizard opens

![Project Wizard Start](../screenshots/wizard_step1.png)

### Alternative: Traditional Flow

For advanced users, you can use the traditional flow:

- **File → Load Video**: Load video first, then configure settings

---

## Understanding the Project Wizard

The wizard consists of 5 steps with a consistent layout (1150x550px window):

### Wizard Step 1: Project Information

**Required Information**:

- **Project Name**: Unique identifier for your project
- **Experiment ID**: Experiment identifier (used for grouping)
- **Description**: Optional notes about the experiment

**Tips**:

- Use descriptive names (e.g., "Zebrafish_Locomotion_Trial1")
- Keep experiment IDs consistent across related projects
- Document experimental conditions in the description

![Wizard Step 1](../screenshots/wizard_step1.png)

### Wizard Step 2: Video Source

Choose your video source:

#### Option A: Pre-recorded Video

- Click **Browse** to select video file
- Supported formats: MP4, AVI, MOV, MKV
- Resolution: Up to 4K (1080p recommended)

#### Option B: Live Camera

- Select camera from dropdown
- Configure resolution and frame rate
- Test camera feed before proceeding

![Wizard Step 2 - Video Source](../screenshots/wizard_step2_video.png)

**Tips**:

- For best results, use 1080p resolution at 30 FPS
- Ensure consistent lighting across video
- Minimize camera movement and vibrations

### Wizard Step 3: Arena and ROI Configuration

Define the analysis arena and regions of interest (ROI).

**Arena Configuration**:

- **Center Point**: Click to set arena center
- **Four Corners**: Click four corners to define arena boundary
- Arena defines the analysis boundary

**ROI Configuration**:

- Click **Add ROI** to create new regions
- Draw rectangle or polygon on video
- Name each ROI (e.g., "Zone A", "Zone B", "Center")
- ROIs are used for behavioral metrics (time spent, entries/exits)

![ROI Configuration](../screenshots/roi_config.png)

**Tips**:

- Draw ROIs on a representative frame
- Use clear, descriptive names
- Save ROI templates for reuse (**File → Save ROI Template**)

### Wizard Step 4: Detection Settings

Configure the AI detection model and tracking parameters.

**Model Selection**:

- **YOLO (Recommended)**: Fast, accurate, general-purpose
- **OpenVINO**: Optimized for Intel CPUs
- **Custom Model**: Load your own trained model

**Detection Parameters**:

- **Confidence Threshold**: 0.5 (default)
  - Lower values: More detections, more false positives
  - Higher values: Fewer detections, more misses
- **Multi-Subject Tracking**: Enable for multiple fish
- **Track ID Assignment**: Enable to maintain consistent IDs

![Detection Settings](../screenshots/wizard_step4_detection.png)

**Tips**:

- Start with default confidence (0.5)
- Enable GPU acceleration if available
- Test detection on a few frames before full analysis

### Wizard Step 5: Analysis Options

Final configuration before running analysis.

**Output Options**:

- **Save Annotated Video**: Include bounding boxes and tracks
- **Generate Heatmap**: Visualize movement density
- **Export Format**: Parquet (default), CSV, JSON

**Performance Options**:

- **Frame Skipping**: Analyze every N frames (default: 1)
- **Parallel Processing**: Enable multi-threading
- **GPU Acceleration**: Use CUDA if available

**Advanced Options**:

- **Analysis Interval**: Detection frequency (default: 10 frames)
- **Display Interval**: Overlay update frequency (default: 10 frames)
- **Calibration**: Physical units (cm) conversion

![Wizard Step 5 - Analysis Options](../screenshots/wizard_step5_options.png)

**Tips**:

- Enable all output options for comprehensive results
- Frame skipping speeds up processing but reduces temporal resolution
- Calibration enables distance/speed metrics in cm and cm/s

### Completing the Wizard

1. Review all settings in Step 5
2. Click **Finish** to create the project
3. Project is saved and ready for analysis

---

## Running Analysis

### Starting Analysis

After creating a project:

1. Click **Run Analysis** button (or press `Ctrl+R`)
2. Progress dialog appears showing:
   - Total frames
   - Processed frames
   - Detected frames
   - Estimated time remaining

![Analysis Progress](../screenshots/analysis_running.png)

### Monitoring Progress

The progress dialog displays:

- **Progress Bar**: Overall completion percentage
- **Frame Count**: Current frame / Total frames
- **Detection Rate**: Frames with successful detections
- **Processing Speed**: FPS (frames per second)
- **Time Remaining**: Estimated time to completion

### Analysis Stages

The analysis pipeline consists of:

1. **Video Loading**: Reading video file and metadata
2. **Detection**: AI model identifies subjects in each frame
3. **Tracking**: Assigns consistent IDs across frames
4. **Zone Analysis**: Calculates time in ROIs, entries/exits
5. **Metric Calculation**: Distance, speed, behavioral metrics
6. **Output Generation**: Parquet files, annotated video, reports

### Typical Processing Times

| Video Length | Resolution | Speed (with GPU) | Speed (CPU only) |
| ------------ | ---------- | ---------------- | ---------------- |
| 1 minute     | 1080p      | ~10 seconds      | ~30 seconds      |
| 5 minutes    | 1080p      | ~50 seconds      | ~2.5 minutes     |
| 30 minutes   | 1080p      | ~5 minutes       | ~15 minutes      |
| 1 hour       | 4K         | ~20 minutes      | ~1 hour          |

### Pausing and Canceling

- **Pause**: Click **Pause** button to temporarily stop
- **Resume**: Click **Resume** to continue from current frame
- **Cancel**: Click **Cancel** to abort analysis (partial results saved)

---

## Understanding Results

### Output Structure

After analysis completes, results are saved in `<video_name>_results/` directory:

```text
my_video_results/
├── 1_ArenaROI_my_video.parquet         # Arena and ROI definitions
├── 2_Zones_my_video.parquet            # Zone metadata
├── 3_CoordMovimento_my_video.parquet   # Frame-by-frame tracking data
├── my_video_summary.xlsx               # Summary metrics per ROI
├── my_video_report.docx                # Word report with plots
└── my_video_annotated.mp4              # Annotated video (optional)
```

### Key Output Files

#### 1. Tracking Data (`3_CoordMovimento_*.parquet`)

**Parquet Schema** (fixed, immutable):

```text
timestamp, frame, track_id, x1, y1, x2, y2, confidence, [x_center_px, y_center_px, x_cm, y_cm]*
```

**Columns**:

- `timestamp`: Video timestamp (seconds)
- `frame`: Frame number
- `track_id`: Unique ID for each tracked subject
- `x1, y1, x2, y2`: Bounding box coordinates (pixels)
- `confidence`: Detection confidence (0.0-1.0)
- `x_center_px, y_center_px`: Centroid coordinates (pixels)
- `x_cm, y_cm`: Centroid coordinates (cm, if calibrated)

**Reading in Python**:

```python
import pandas as pd

# Load tracking data
df = pd.read_parquet("my_video_results/3_CoordMovimento_my_video.parquet")

# Filter by track ID
track_1 = df[df['track_id'] == 1]

# Calculate total distance
distance = track_1[['x_cm', 'y_cm']].diff().pow(2).sum(axis=1).pow(0.5).sum()
print(f"Total distance: {distance:.2f} cm")
```

#### 2. Summary Report (`*_summary.xlsx`)

Excel file with multiple sheets:

##### Sheet 1: Overall Statistics

| Metric            | Value | Unit    |
| ----------------- | ----- | ------- |
| Total Time        | 120.5 | seconds |
| Total Frames      | 3615  | frames  |
| Detection Rate    | 98.3  | %       |
| Distance Traveled | 345.2 | cm      |
| Average Speed     | 2.86  | cm/s    |
| Max Speed         | 12.4  | cm/s    |

##### Sheet 2: ROI Metrics

| ROI Name | Time (s) | Entries | Exits | % Time |
| -------- | -------- | ------- | ----- | ------ |
| Zone A   | 45.3     | 12      | 12    | 37.6   |
| Zone B   | 32.1     | 8       | 8     | 26.6   |
| Center   | 43.1     | 15      | 14    | 35.8   |

##### Sheet 3: Track-by-Track Analysis (if multi-subject)

Per-track metrics for each detected subject.

#### 3. Word Report (`*_report.docx`)

Comprehensive report including:

- Experiment metadata
- Summary statistics
- Trajectory plots
- Heatmaps
- ROI time distribution charts
- Speed over time graphs

### Visualizing Results

#### Heatmap

Heatmaps show movement density (warmer colors = more time spent):

![Heatmap Example](../screenshots/heatmap.png)

**Interpreting Heatmaps**:

- **Red zones**: High activity, preferred locations
- **Blue zones**: Low activity, avoided locations
- **Green zones**: Moderate activity

#### Trajectory Plot

Line plot showing subject's path over time:

- **Color gradient**: Time progression (blue → red)
- **Line thickness**: Speed (thicker = faster)

#### Speed Over Time

Graph showing speed variations:

- **Peaks**: Bursts of activity
- **Valleys**: Resting periods
- **Average line**: Mean speed across session

### Exporting Results

#### Export Formats

**Parquet (Default)**:

- Binary format, efficient storage
- Best for Python analysis (pandas)
- Preserves data types and schema

**CSV**:

- Text format, universal compatibility
- Excel-compatible
- Larger file size

**JSON**:

- Structured text format
- Web application friendly
- Human-readable

#### Changing Export Format

1. Before analysis: **Wizard Step 5 → Export Format**
2. After analysis: **File → Export Results → Choose Format**

---

## Live Camera Analysis

### Overview

Live Camera Analysis allows real-time tracking and recording from connected cameras.

### Launching Live Analysis

1. **File → Analisar Câmera ao Vivo...** (or press `Ctrl+L`)
2. Live Analysis Dialog opens

![Live Analysis Dialog](../screenshots/live_analysis_dialog.png)

### Configuration

**Basic Settings**:

- **Experiment ID**: Identifier for live session
- **Session Duration**: Time limit (seconds, minutes, or hours)
- **Camera**: Select connected camera
- **Resolution**: Camera resolution (720p, 1080p)

**Detection Settings**:

- **Model**: Choose detection model
- **Confidence**: Detection threshold
- **ROIs**: Define analysis regions

**Output Settings**:

- **Save Video**: Record annotated video
- **Save Tracking Data**: Export Parquet file
- **Output Directory**: `live_analysis_sessions/`

### Running Live Session

1. Click **Start Session**
2. Live preview window opens showing:
   - Real-time video feed
   - Detection overlays
   - Frame counter and FPS
3. Session runs for configured duration
4. Results saved automatically to `live_analysis_sessions/{experiment_id}_{timestamp}/`

![Live Preview Window](../screenshots/live_preview.png)

### Live Session Controls

- **Pause**: Temporarily pause recording (timer continues)
- **Resume**: Continue recording
- **Stop**: End session early
- **Snapshot**: Capture current frame

### Live Analysis Output

Same structure as pre-recorded analysis:

```text
live_analysis_sessions/
└── exp_001_20251110_143022/
    ├── 3_CoordMovimento_live_session.parquet
    ├── live_session_summary.xlsx
    ├── live_session_report.docx
    └── live_session_annotated.mp4 (optional)
```

---

## Keyboard Shortcuts

### Global Shortcuts

| Shortcut | Action                    |
| -------- | ------------------------- |
| `Ctrl+N` | New Project (open wizard) |
| `Ctrl+O` | Open Project              |
| `Ctrl+S` | Save Project              |
| `Ctrl+L` | Live Camera Analysis      |
| `Ctrl+Q` | Quit Application          |

### Video Playback

| Shortcut    | Action                  |
| ----------- | ----------------------- |
| `Space`     | Play/Pause              |
| `→`         | Next Frame              |
| `←`         | Previous Frame          |
| `Page Down` | Jump Forward 10 Frames  |
| `Page Up`   | Jump Backward 10 Frames |
| `Home`      | Go to First Frame       |
| `End`       | Go to Last Frame        |

### Analysis

| Shortcut | Action                 |
| -------- | ---------------------- |
| `Ctrl+R` | Run Analysis           |
| `Ctrl+P` | Pause Analysis         |
| `Ctrl+T` | Toggle Track Overlays  |
| `Ctrl+H` | Toggle Heatmap Overlay |

### ROI Management

| Shortcut       | Action              |
| -------------- | ------------------- |
| `Ctrl+Shift+A` | Add ROI             |
| `Ctrl+Shift+D` | Delete Selected ROI |
| `Ctrl+Shift+E` | Edit ROI Properties |
| `Ctrl+Shift+T` | Save ROI Template   |

---

## Next Steps

### Tutorial Videos

Watch video tutorials on our [YouTube channel](https://youtube.com/zebtrack) (coming soon):

- Basic project workflow
- Advanced ROI configuration
- Multi-subject tracking
- Custom model training

### Advanced Features

Explore advanced capabilities:

- **Batch Processing**: Analyze multiple videos automatically ([see FAQ](FAQ.md#batch-processing))
- **Custom Models**: Train detection models on your data
- **Arduino Integration**: Trigger external devices based on ROI events
- **Plugin System**: Extend functionality with custom plugins

### Community and Support

- **Documentation Hub**: [DRerio LogAI docs (GitHub)](https://github.com/MarkSant/DRerio-LogAI/tree/main/docs)
- **GitHub Issues**: [Report bugs and request features](https://github.com/MarkSant/DRerio-LogAI/issues)
- **Discussions**: [Community forum](https://github.com/MarkSant/DRerio-LogAI/discussions)
- **Email Support**: <marco.sant@unesp.br>

### Contributing

Interested in contributing? See our [Contributing Guide](../../../CONTRIBUTING.md) for:

- Code contribution guidelines
- Development setup
- Testing requirements
- Documentation standards

---

## Troubleshooting

For common issues and solutions, see the [Troubleshooting Guide](TROUBLESHOOTING.md).

**Quick Links**:

- [Camera Not Found](TROUBLESHOOTING.md#camera-not-found)
- [Low Detection Accuracy](TROUBLESHOOTING.md#low-detection-accuracy)
- [Slow Performance](TROUBLESHOOTING.md#slow-performance)
- [GPU Not Detected](TROUBLESHOOTING.md#gpu-not-detected)

---

## Glossary

**Arena**: The physical space where subjects are tracked (e.g., fish tank)

**ROI (Region of Interest)**: Defined area within arena for behavioral analysis

**Confidence Threshold**: Minimum score for accepting a detection (0.0-1.0)

**Track ID**: Unique identifier assigned to each subject across frames

**Parquet**: Efficient binary format for storing tabular data

**Heatmap**: Visualization showing spatial density of movement

**FPS (Frames Per Second)**: Processing or playback speed

**Calibration**: Conversion from pixels to physical units (cm)

---

**Version**: 2.1
**Last Updated**: November 2025
**License**: MIT
