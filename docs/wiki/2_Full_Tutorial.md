# Full Tutorial: From Video to Results

This tutorial will guide you through a complete analysis workflow in ZebTrack-AI, from setting up a new project to interpreting your final data.

[Screenshot of the main ZebTrack-AI window when first opened]

---

### Step 1: Create a New Project

A "Project" in ZebTrack-AI is a folder that contains your videos, configuration, and all generated results.

1.  **Start a New Project:**
    *   Click the **"Create New Project"** button on the main screen.
    *   The project creation dialog will appear.

2.  **Configure Your Project:**
    *   **Project Name & Folder:** Give your project a name and select a parent directory where the project folder will be created.
    *   **Project Type:**
        *   **Pre-recorded:** Choose this if you have existing video files to analyze.
        *   **Live:** Choose this for real-time tracking and recording from a camera.
    *   **Calibration:** Enter the real-world width and height of your arena in centimeters. This is crucial for accurate measurements.
    *   **Live Options (for Live projects):**
        *   **Timed Recording:** Set a fixed duration for your recordings.
        *   **Countdown:** Enable a countdown timer that will appear on screen before a recording starts, ensuring you are ready.
    *   **Experimental Design (for Live projects):** Define the structure of your experiment by specifying the number of days, groups, and subjects per group.

    [Screenshot of the new Create Project Dialog]

3.  **Load the Project:**
    *   Once created, the project will load, and you will be taken to the main control view.

---

### Step 2: Define Detection Zones

Before analysis, you must tell ZebTrack-AI where to look for animals (the main processing area) and define any specific Regions of Interest (ROIs).

1.  **Navigate to the "Configuração de Zonas" Tab.**
2.  **Define the Main Arena:**
    *   Click **"Detectar Aquário (Auto)"** to let the AI find the main arena boundary automatically.
    *   Alternatively, manually draw the boundary using the **"Desenhar Polígono Principal"** button. Click to add points and right-click to finish.
3.  **Define Regions of Interest (ROIs):**
    *   Click **"Desenhar Área de Interesse"** to draw rectangular ROIs inside your main arena. These are the zones for which detailed intra-ROI metrics will be calculated.
    *   Give each ROI a unique name and assign it a color.

    [Screenshot showing the Zone Configuration tab with a video, a main polygon, and several colored ROIs.]

---

### Step 3: Process Videos and Generate Reports

1.  **Add and Process Videos (for Pre-recorded projects):**
    *   In the "Main Control" tab, click **"Add and Process New Videos/Folders..."**.
    *   Select your video files. The application will first run detection and tracking, and then immediately perform the behavioral analysis.

2.  **Start Recording (for Live projects):**
    *   Go to the "Progresso do Experimento" tab to see your experimental grid.
    *   Click on a cell to select a specific subject for a session.
    *   Click **"Start Recording"** in the "Main Control" tab. If you enabled the countdown, it will appear now.
    *   After recording, the analysis is run automatically.

---

### Step 4: Explore and Interpret Your Results

The "Reporting" tab is your hub for results.

1.  **View Processed Videos:**
    *   The list shows all videos that have been processed. You can select one or more videos to include in a report.

2.  **Generate Reports:**
    *   **Generate Report for Selected:** Creates a report for only the videos you have highlighted in the list.
    *   **Generate Unified Report (All):** Creates a single report containing data from all videos in the project.

3.  **Export Formats:**
    *   When saving, you can choose from several formats:
        *   **Excel (`.xlsx`):** A tidy spreadsheet with all calculated metrics.
        *   **CSV (`,csv`):** A simple comma-separated file for maximum compatibility.
        *   **Parquet (`.parquet`):** A highly efficient, column-oriented format ideal for large datasets and analysis in Python or R.
    *   A detailed **Word (`.docx`)** report is also generated alongside Excel/CSV exports, containing summary tables, plots, and an **Event Appendix**—a chronological log of every time the animal entered or exited an ROI.

4.  **New Metrics to Explore:**
    *   **Sharp Turns:** The number of times the animal exceeded a turning-rate threshold (e.g., 90 degrees/sec). Useful for measuring anxiety or startle responses.
    *   **Intra-ROI Metrics:** For each ROI you defined, you now get specific metrics like distance traveled, average velocity, and time spent freezing *only within that zone*.

Congratulations! You have successfully completed a full analysis in ZebTrack-AI.
