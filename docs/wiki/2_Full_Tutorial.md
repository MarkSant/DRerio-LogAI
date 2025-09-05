# Full Tutorial: From Video to Results

This tutorial will guide you through a complete analysis workflow in ZebTrack-AI, from setting up a new project to interpreting your final data.

[Screenshot of the main ZebTrack-AI window when first opened]

---

### Step 1: Create a New Project

A "Project" in ZebTrack-AI is a folder that contains your videos and all the results and settings associated with them.

1.  **Start a New Project:**
    *   Click the **"New Project"** button on the main screen.
    *   A dialog box will ask you to select a folder. Choose the folder that contains the video files you want to analyze. It's best to have all videos for one experiment in a single folder.

2.  **Project View:**
    *   After selecting a folder, the application will switch to the "Project View".
    *   On the left, you will see a list of all the video files found in your project folder.
    *   On the right, you will see a panel for defining your experimental setup.

    [Screenshot of the Project View, showing the video list and settings panel]

---

### Step 2: Define Your Arena and Regions of Interest (ROIs)

Before tracking, you must tell ZebTrack-AI where to look for animals and define any specific zones you are interested in.

1.  **Draw the Processing Area:**
    *   Click the **"Draw Processing Area"** button.
    *   Your mouse cursor will change. Click on the corners of the fish tank or arena in the video preview. This tells the software the boundaries of the area where tracking should occur.
    *   Right-click to finish drawing. The area will be highlighted.

2.  **Define a Scale for Calibration:**
    *   Click the **"Set Scale"** button.
    *   Draw a line across a known distance in the video (e.g., the width of the tank).
    *   A dialog will appear asking for the real-world length of this line in centimeters. This step is crucial for converting pixel measurements into meaningful real-world units (cm).

3.  **Draw Regions of Interest (Optional):**
    *   If you want to measure time spent in specific zones (e.g., the center vs. the edges of the tank), click the **"Add ROI"** button.
    *   Draw a rectangle over an area of interest and give it a name when prompted (e.g., "Center Zone"). You can add multiple ROIs.

    [Screenshot showing a video preview with the processing area, scale line, and a few ROIs drawn on it]

---

### Step 3: Run the Analysis

With your project set up, you are ready to run the tracking and analysis.

1.  **Start the Batch Process:**
    *   Click the **"Run Batch Analysis"** button in the main control panel.
    *   ZebTrack-AI will now go through each video in your project list, one by one.
    *   The status bar at the bottom of the window will show the progress.

2.  **Wait for Completion:**
    *   This process may take some time, depending on the number and length of your videos.
    *   Once finished, a "Batch analysis complete!" message will appear.

---

### Step 4: Explore and Interpret Your Results

After the analysis is complete, the "Reports" tab will become active. This is where you can visualize and export your data.

1.  **Select an Experiment:**
    *   Use the dropdown menu at the top of the "Reports" tab to select the specific video (experiment) you want to view.

2.  **View Trajectory and Heatmap:**
    *   Click **"Generate Trajectory Plot"** to see the path the animal took during the trial.
    *   Click **"Generate Heatmap"** to see a visual representation of where the animal spent the most time.

    [Screenshot of the Reports tab, showing a trajectory plot on the left and the control buttons on the right]

3.  **Export Your Data:**
    *   **For a single experiment:** Use the "Export Data" or "Export Visual Report" buttons to save the plots and summary data for the currently selected experiment.
    *   **For the entire project:** In your project folder, you will find a file named **`project_summary.xlsx`**. This Excel file contains all the key behavioral metrics for every video in your project, ready for statistical analysis.

Congratulations! You have successfully completed a full analysis in ZebTrack-AI.
