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
-   `{video_name}_summary.xlsx`: A multi-sheet Excel file with global and ROI-specific metrics.
-   `{video_name}_report.docx`: A full report with metadata, tables, and all generated plots.

For project-wide analysis, you can generate a unified report in `.xlsx`, `.csv`, or `.parquet` format from the "Reporting" tab.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
