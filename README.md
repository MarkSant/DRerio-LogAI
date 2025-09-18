# ZebTrack-AI: High-Throughput Animal Tracking and Behavioral Analysis

ZebTrack-AI is a user-friendly desktop application designed for researchers to perform high-throughput tracking and behavioral analysis of animals in video recordings. Built for scientific rigor, it provides a complete workflow from video processing to data analysis and visualization, all within an intuitive graphical interface. Whether you are studying zebrafish larvae or other organisms, ZebTrack-AI helps you extract meaningful data with ease and precision.

[Placeholder for a GIF or screenshot of the ZebTrack-AI interface in action]

## Key Features

*   **Multi-Animal Tracking:** Utilizes state-of-the-art models (YOLOv8) to reliably track multiple animals simultaneously.
*   **Automated Behavioral Analysis:** Automatically calculates a wide range of behavioral metrics, including:
    *   **Core Metrics:** Total distance traveled, velocity statistics (mean, median, std dev), and path tortuosity.
    *   **Sharp Turns:** Identifies and counts rapid changes in direction using a configurable angular velocity threshold (default: 90°/s).
    *   **Freezing Episodes:** Detects periods of immobility based on velocity and duration thresholds.
    *   **Thigmotaxis:** Calculates wall-hugging behavior.
*   **Advanced ROI Analysis:**
    *   **Interactive ROI Definition:** Easily draw custom polygonal regions of interest (ROIs) directly on a frame from your video.
    *   **Configurable Inclusion Rules:** Choose how animals are considered "inside" an ROI:
        *   **`centroid_in`:** Simple centroid-based inclusion (legacy behavior) - fast but may miss partial entries
        *   **`centroid_in_on_buffered_roi`:** Uses buffered (dilated) ROI for more sensitive detection of partial entries
        *   **`bbox_intersects` (default):** Considers animals inside when their bounding box overlaps the ROI by a configurable threshold
        *   **`seg_overlap`:** Uses segmentation masks for most accurate but computationally intensive detection
    *   **Intra-ROI Metrics:** Get detailed statistics for behavior *within* each defined region, including distance traveled, velocity, freezing episodes, entry/exit counts, and time spent.
    *   **ROI Reference Map:** Automatically generate a numbered and colored map of your ROIs in reports for easy reference.
*   **Flexible Live Recording:**
    *   **Countdown Timer:** An optional on-screen countdown to ensure experiments start precisely when you're ready.
    *   **Timed Recording:** Set a specific duration for your live recordings.
*   **Rich Visualizations:**
    *   **Advanced Plotting Suite:** Generates a comprehensive set of plots for each experiment:
        *   Trajectory plot (with optional video frame background)
        *   Positional Heatmap
        *   Position (X/Y) vs. Time
        *   Cumulative Distance vs. Time
        *   Angular Velocity vs. Time (with sharp turns highlighted)
*   **Comprehensive Data Export:**
    *   **Multiple Formats:** Export aggregated project data into tidy formats ready for analysis in R, Python, or SPSS: **Excel (`.xlsx`)**, **CSV (`,csv`)**, and **Apache Parquet (`.parquet`)**.
    *   **Structured Excel Reports:** Exports a comprehensive Excel file with all global and ROI-specific metrics in a single, tidy sheet.
    *   **Detailed Word Reports:** Generates detailed `.docx` reports for individual experiments and unified project summaries, complete with summary tables, all generated plots, and an event log.

---

## How to Get Started (Quick Start)

Getting your research underway with ZebTrack-AI is simple.

1.  **Download the Application:**
    *   [Link to Windows Executable (coming soon)]
    *   [Link to macOS Application (coming soon)]
    *   [Link to Linux Executable (coming soon)]

2.  **Launch the Program:**
    *   Open the downloaded application. You will be greeted by the main project window.

3.  **Create a New Project:**
    *   Click on **"New Project"** and select the folder where your project will be saved.
    *   For pre-recorded analysis, select your video files.

4.  **Run the Analysis:**
    *   Once your project is loaded, click **"Add and Process New Videos/Folders"** to start the analysis.

---

## Data Output

When you run an analysis, ZebTrack-AI organizes the results into a subfolder for each video (e.g., `MyVideo_results/`). This folder contains:

-   `3_CoordMovimento_{video_name}.parquet`: The core trajectory data.
    -   **Note:** This specific naming convention is important. The analysis modules expect the trajectory data file to start with `3_CoordMovimento_` and end with the experiment name (derived from the video's filename) and the `.parquet` extension.
-   `{video_name}_summary.xlsx`: A multi-sheet Excel file with global and ROI-specific metrics.
-   `{video_name}_report.docx`: A full report with metadata, tables, and all generated plots.

For project-wide analysis, you can generate a unified report in `.xlsx`, `.csv`, or `.parquet` format from the "Reporting" tab.

## ROI Inclusion Rules

ZebTrack-AI offers four configurable rules for determining when an animal is considered "inside" a Region of Interest (ROI):

### 1. `centroid_in` (Simple Centroid)
- **Method:** Animal is inside when its centroid falls within the ROI polygon
- **Pros:** Fast and simple
- **Cons:** May miss partial entries (e.g., when only the head enters first)
- **Best for:** When precision is less critical and performance is important

### 2. `centroid_in_on_buffered_roi` (Buffered Centroid)
- **Method:** Uses a dilated ROI with configurable buffer radius `r`
- **Parameters:** Buffer radius `r` (interpreted in cm if calibration available, otherwise pixels)
- **Pros:** Catches partial entries while remaining computationally efficient
- **Cons:** May over-detect at boundaries
- **Best for:** Detecting early entries while maintaining good performance

### 3. `bbox_intersects` (Bounding Box Intersection) - **Default**
- **Method:** Animal is inside when its bounding box overlaps the ROI by at least the specified fraction
- **Parameters:** Minimum overlap ratio (0.0-1.0, default: 0.10)
- **Pros:** Good balance of accuracy and performance, captures partial entries
- **Cons:** Requires bounding box data; may overestimate at ROI edges
- **Best for:** Most general use cases where you want to detect partial entries

### 4. `seg_overlap` (Segmentation Overlap)
- **Method:** Uses pixel-level segmentation masks for most precise detection
- **Parameters:** Minimum area overlap ratio (0.0-1.0)
- **Pros:** Most accurate detection method
- **Cons:** Requires segmentation data (not currently stored); computationally intensive
- **Best for:** When maximum precision is needed and segmentation data is available

### Configuration

ROI inclusion rules can be configured in the GUI under "Regra de Inclusão em ROI" or by modifying the settings:

```yaml
roi_inclusion_rule: "bbox_intersects"
roi_buffer_radius_value: 0.5
roi_min_bbox_overlap_ratio: 0.10
```

The settings are automatically saved to your project and will be preserved for future analyses.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
