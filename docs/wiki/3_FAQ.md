# FAQ (Frequently Asked Questions)

Here are answers to some common questions and troubleshooting tips for ZebTrack-AI.

---

### **Q: What should I do if the software is not detecting my animal?**

**A:** This is a common issue that can usually be solved by checking a few things:

1.  **Lighting and Contrast:** The tracking models work best when there is good contrast between the animal and the background. Ensure your arena is well-lit and the background is a uniform color that is different from the animal.
2.  **Processing Area:** Double-check that the Processing Area you drew completely covers the area where the animal is located. If the animal moves outside this boundary, it will not be detected.
3.  **Model Confidence:** In the application settings, you can find a "Confidence Threshold". If this value is too high (e.g., 0.9), the model will only register very certain detections. Try lowering this value slightly (e.g., to 0.7 or 0.6) to see if detection improves. Be careful not to set it too low, as this can lead to false positives.

[Screenshot of the settings panel showing the confidence threshold]

---

### **Q: What is the best video format to use?**

**A:** ZebTrack-AI uses standard video libraries that support a wide range of formats. However, for best results and maximum compatibility, we recommend using **MP4 files with the H.264 codec**. This is a very common format that provides a good balance between file size and quality.

---

### **Q: How does the calibration work? Why is it important?**

**A:** Calibration is the process of teaching the software how to convert measurements from pixels (the dots on your screen) into real-world units like centimeters (cm).

You do this by drawing a line over an object of a known size in your video (like the width of the tank) and telling the software its true length.

This step is **critical** for scientific accuracy. Without it, all your results (distance, velocity, etc.) would be in pixels, which are not comparable across different experiments or camera setups. Proper calibration ensures your data is reliable and reproducible.

---

### **Q: Can I analyze videos that were recorded from an angle?**

**A:** Yes. The software includes a perspective correction feature. When you draw the four corners of your rectangular arena (the "Processing Area"), the software automatically "warps" the image to create a flat, top-down view. This corrects for camera distortion and ensures that measurements are accurate even if the video was filmed from a slight angle.

---

### **Q: I ran my analysis, but the "Reports" tab is empty. What happened?**

**A:** First, check the status bar at the bottom of the main window for any error messages that might have occurred during the analysis. If there are no errors, the most common reason is that you may need to manually load the results.

Click the **"Load Project Results"** button in the main control panel. This will scan your project folder for any completed analysis files and populate the dropdown menu in the "Reports" tab.

---

### **Q: Where are my final data files saved?**

**A:** All of your data is saved inside your Project Folder. For each video you analyze, a new subfolder named `{video_name}_results` is created. Inside, you will find plots and raw data for that specific trial.

For a summary of your entire experiment, look for the **`project_summary.xlsx`** file in the main root of your Project Folder. This single Excel file contains the most important behavioral metrics for all the videos you processed.
