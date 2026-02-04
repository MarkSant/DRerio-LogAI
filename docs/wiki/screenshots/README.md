# Screenshots Directory

This directory contains screenshots referenced in the user documentation guides.

## Required Screenshots

The following screenshots need to be captured from the running application:

### 1. Main Window (`main_window.png`)

**Location**: Main application window after launch
**Content**:

- Menu bar (File, Edit, View, Tools, Help)
- Toolbar with common actions
- Video player area
- Timeline and controls
- Status bar

**How to capture**:

```bash
poetry run zebtrack
# Wait for main window to open
# Take screenshot of entire window
```

### 2. Wizard Step 1 (`wizard_step1.png`)

**Location**: File → New Project → Project Wizard opens
**Content**:

- Project wizard window (1150x550px)
- Step 1: Project Information
- Fields: Project Name, Experiment ID, Description
- Navigation buttons (Next, Cancel)

**How to capture**:

```bash
poetry run zebtrack
# Click File → New Project
# Take screenshot of wizard window (Step 1)
```

### 3. Wizard Step 2 - Video Source (`wizard_step2_video.png`)

**Location**: Project Wizard → Step 2
**Content**:

- Video source selection options
- File browser button
- Camera selection dropdown
- Resolution and frame rate settings

**How to capture**:

```bash
# Continue from wizard Step 1
# Click Next to reach Step 2
# Take screenshot
```

### 4. ROI Configuration (`roi_config.png`)

**Location**: Project Wizard → Step 3 (Arena and ROI Configuration)
**Content**:

- Video frame with drawn ROIs
- ROI list panel
- Drawing tools (rectangle, polygon, circle)
- ROI properties (name, color)
- Arena boundary overlay

**How to capture**:

```bash
# Continue from wizard Step 2
# Click Next to reach Step 3
# Draw 2-3 example ROIs on the video
# Take screenshot showing ROIs overlaid on video
```

### 5. Detection Settings (`wizard_step4_detection.png`)

**Location**: Project Wizard → Step 4
**Content**:

- Model selection (YOLO, OpenVINO)
- Confidence threshold slider
- Multi-subject tracking checkbox
- Track ID assignment options
- Advanced settings panel

**How to capture**:

```bash
# Continue from wizard Step 3
# Click Next to reach Step 4
# Take screenshot of detection configuration
```

### 6. Analysis Options (`wizard_step5_options.png`)

**Location**: Project Wizard → Step 5 (Final step)
**Content**:

- Output options checkboxes (annotated video, heatmap, etc.)
- Export format dropdown
- Performance options
- Advanced settings
- Finish button

**How to capture**:

```bash
# Continue from wizard Step 4
# Click Next to reach Step 5
# Take screenshot
```

### 7. Analysis Progress (`analysis_running.png`)

**Location**: During analysis (after clicking Run Analysis)
**Content**:

- Progress dialog with progress bar
- Frame count (current/total)
- Processing speed (FPS)
- Detection rate
- Estimated time remaining
- Pause/Cancel buttons

**How to capture**:

```bash
# Complete wizard and start analysis
# OR load existing project and click Run Analysis
# Take screenshot while analysis is running (mid-progress, e.g., 50%)
```

### 8. Heatmap Example (`heatmap.png`)

**Location**: Analysis results after completion
**Content**:

- Heatmap visualization overlaid on video frame
- Color scale (blue → green → yellow → red)
- Arena boundary
- ROI overlays
- Clear movement density patterns

**How to capture**:

```bash
# After analysis completes
# Open annotated video or heatmap output
# Take screenshot showing heatmap with visible activity patterns
```

### 9. Live Analysis Dialog (`live_analysis_dialog.png`)

**Location**: File → Analisar Câmera ao Vivo...
**Content**:

- Live Analysis configuration dialog
- Experiment ID field
- Session duration settings
- Camera selection
- Resolution options
- Detection settings
- Output settings
- Start Session button

**How to capture**:

```bash
poetry run zebtrack
# Click File → Analisar Câmera ao Vivo...
# Take screenshot of dialog
```

### 10. Live Preview Window (`live_preview.png`)

**Location**: During live camera session
**Content**:

- Real-time video feed from camera
- Detection overlays (bounding boxes)
- Frame counter
- FPS display
- Session timer
- Control buttons (Pause, Stop)

**How to capture**:

```bash
# From Live Analysis Dialog, click Start Session
# Take screenshot while session is running
# Ensure camera is detecting subjects (bounding boxes visible)
```

## Screenshot Guidelines

### Technical Requirements

- **Format**: PNG (lossless)
- **Resolution**: Native resolution (don't downscale)
- **Quality**: Maximum quality, no compression artifacts
- **Naming**: Use exact filenames as listed above (lowercase, underscores)

### Content Guidelines

- **Clean UI**: Close unnecessary windows, clean desktop background
- **Representative Data**: Use realistic example data (not empty/default states)
- **Visibility**: Ensure all text is readable, no cutoff elements
- **Privacy**: No personal information, real subject IDs, or sensitive data

### Capture Tools

#### Windows

- **Snipping Tool**: Win+Shift+S → Select area → Save as PNG
- **Windows + PrtScn**: Captures full screen to Pictures/Screenshots

#### Linux

- **GNOME Screenshot**: gnome-screenshot -a (area selection)
- **Spectacle**: spectacle -r (rectangular region)

#### macOS

- **Cmd+Shift+4**: Click and drag to capture area
- **Cmd+Shift+4, then Space**: Capture entire window

## Placeholder Images

Until screenshots are captured, the documentation references them by filename. The guides are complete and ready; screenshots will be added when the application is running.

## Contributing Screenshots

If you capture screenshots for this documentation:

1. Follow the naming convention exactly
2. Use PNG format with maximum quality
3. Verify screenshots are readable and clear
4. Place files in this directory (`docs/wiki/screenshots/`)
5. Update this README if adding new screenshots
6. Submit via pull request

---

**Status**: Awaiting screenshot capture (application needs to be launched)
**Last Updated**: November 2025
