# ZebTrack-AI: High-Throughput Animal Tracking and Behavioral Analysis

ZebTrack-AI is a user-friendly desktop application designed for researchers to perform high-throughput tracking and behavioral analysis of animals in video recordings. Built for scientific rigor, it provides a complete workflow from video processing to data analysis and visualization, all within an intuitive graphical interface. Whether you are studying zebrafish larvae or other organisms, ZebTrack-AI helps you extract meaningful data with ease and precision.

[Placeholder for a GIF or screenshot of the ZebTrack-AI interface in action]

## Key Features

*   **Multi-Animal Tracking:** Utilizes state-of-the-art models (YOLOv8) to reliably track multiple animals simultaneously.
*   **Automated Behavioral Analysis:** Automatically calculates a wide range of behavioral metrics, including:
    *   Total distance traveled and velocity
    *   Freezing episodes (time spent immobile)
    *   Thigmotaxis (wall-hugging behavior)
    *   Tortuosity (path complexity)
*   **Interactive ROI Definition:** Easily define custom regions of interest (ROIs) to analyze location-specific behaviors.
*   **User-Friendly Interface:** A simple, point-and-click interface that guides you through creating projects, running analyses, and exploring results. No programming required.
*   **Comprehensive Data Export:** Exports all data into easy-to-use formats like Excel (`.xlsx`) and Parquet (`.parquet`), along with high-quality plots for publication.

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
    *   Click on **"New Project"** and select the folder containing your video files.

4.  **Run the Analysis:**
    *   Once your project is loaded, click **"Run Batch Analysis"** to process all videos and generate your results. It's that simple!

---

## Data Output

When you run an analysis, ZebTrack-AI organizes the results into a subfolder for each video. The primary data file is `3_CoordMovimento_{video_name}.parquet`, which contains the core tracking data for each detected animal, including its timestamp, frame number, track ID, and bounding box coordinates.

All summary data is aggregated into a `project_summary.xlsx` file at the root of your project, which is perfect for importing into statistical software like R, SPSS, or Prism.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
