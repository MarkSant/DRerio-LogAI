# FAQ (Frequently Asked Questions)

Common answers and troubleshooting tips for ZebTrack-AI users.

---

## Q: The wizard is missing. How do I enable it?

**A:** Since v1.6 the project creation wizard is enabled by default. If you disabled it previously, add the following to `config.local.yaml`:

```yaml
ui_features:
  use_wizard_for_project_creation: true
```

Restart the application and the 5-step wizard will appear when you click **Create Project**.

---

## Q: Detections are flaky or the animal disappears. What should I check?

1. **Lighting & Contrast:** Ensure the arena background contrasts with the animal. Avoid reflections or strong shadows.
2. **Processing Area:** Confirm the arena polygon fully covers the region where the animal moves. With the new clamping logic, the snap indicator stays inside the arena — if you cannot place a point, the arena is probably too small.
3. **Confidence / NMS:** Lower the detector confidence threshold (e.g., from 0.85 to 0.65) or tweak NMS in the advanced configuration tab.
4. **Single-subject mode:** Calibration and diagnostics force single-subject tracking. The overlay shows the active mode; make sure the correct mode is being used for your experiment.

---

## Q: What's the recommended video format?

**A:** MP4 (H.264) at 25-30 fps offers the best balance between size and quality. Higher bitrates improve detection, but ensure your storage and GPU can keep up. Other formats (AVI, MOV) work as long as OpenCV can decode them.

---

## Q: How do ROI templates work?

**A:** Draw the arena/ROIs once, then use **💾 Salvar Zonas Atuais** to store the layout in `templates/`. Later projects can:

- Select a saved template from **Templates salvos** and click **Aplicar**.
- Import external JSON files via **📂 Importar e Aplicar Arquivo...** (applies immediately and saves to the library).

Templates include arena, ROI polygons, names, and colors. The wizard also reuses templates when you import Parquet files containing zones.

---

## Q: Do I still need to calibrate?

**A:** Yes. Calibration translates pixels into centimeters. Without it, distances and velocities are expressed in pixels. Use the calibration dialog (or wizard Step 4 for live projects) to record real-world dimensions. Once the calibration is saved, Recorder adds `x_cm`/`y_cm` columns and reports show metrics in centimeters.

---

## Q: Can ZebTrack-AI handle videos recorded from an angle?

**A:** Yes. Draw the arena corners in the zone editor; ZebTrack-AI computes a homography that warps coordinates into a normalized top-down plane. Metrics and ROI checks operate in this warped space, so moderate perspective skew is fine.

---

## Q: Reports tab is empty even after processing. How do I refresh it?

**A:** The GUI automatically refreshes after each processing batch. If you still see an empty list:

1. Check the status bar for errors while processing.
2. Click **Atualizar** in the Reports tab to rescan the project folder.
3. Confirm that the `<video>_results/` folder exists and that `3_CoordMovimento_*.parquet` was written (absence indicates processing failed earlier).

---

## Q: What do the new metrics (Sharp Turns, Social Proximity, etc.) mean?

- **Sharp Turns:** Counts how often angular velocity exceeds the configured threshold (default 90°/s).
- **Speed bursts / inactivity:** Duration and counts for periods above/below configurable thresholds.
- **Intra-ROI metrics:** Distance, average speed, freezing, and transitions calculated solely within each ROI.
- **Social proximity:** Percentage of time individuals remain inside dynamically computed proximity clusters (requires multi-animal tracking and calibration).

See `docs/reference/operational_reference.md` Section 5 for formulas and exact definitions.

---

## Q: Where are the outputs stored?

**A:** Each video produces a `<video_name>_results/` folder containing:

- `1_ProcessingArea_*.parquet` (arena), `2_AreasOfInterest_*.parquet` (ROIs), `3_CoordMovimento_*.parquet` (trajectory)
- Optional MP4 with overlays if recording was enabled
- `{video}_summary.xlsx`, `{video}_report.docx`, plus optional CSV/Parquet exports

Project-wide exports created from the **Relatórios** tab are saved wherever you point the file dialog. The wizard also keeps metadata in `project_config.json` and `config_snapshot.yaml` for reproducibility.

---

## Q: How do I report a bug or request a feature?

Open an issue on GitHub describing your environment (OS, Python version, GPU), attach logs (`logs/` folder if present) and, if possible, include the wizard summary exported as JSON. Contributions and pull requests are welcome — read `CONTRIBUTING.md` for guidelines.

---

## Q: What are the velocity metrics in reports? (v3.2+)

**A:** Reports now include enhanced velocity statistics:

| Metric                  | Description                          |
| ----------------------- | ------------------------------------ |
| **Mean Speed (cm/s)**   | Average swimming velocity            |
| **Max Speed (cm/s)**    | Maximum instantaneous velocity       |
| **Median Speed (cm/s)** | Median velocity (robust to outliers) |
| **Std Speed (cm/s)**    | Standard deviation of velocity       |

Max Speed was added in v3.2 to help identify burst swimming behavior.

---

## Q: What are Geotaxis metrics? How do zone names work?

**A:** Geotaxis analysis measures vertical position preference in lateral-view aquariums:

- **Geotaxis Zona 1 - Fundo (%)** - Time in bottom zone (zone 0 internally)
- **Geotaxis Zona 2 (%)** - Time in middle zone
- **Geotaxis Zona 3 (%)** - Time in top zone (if 3 zones configured)

Zone names are 1-indexed for user display (Zona 1, 2, 3...) but stored as 0-indexed internally (zone_0, zone_1, zone_2...).

**Configuration**: Set `geotaxis_num_zones` in behavioral analysis settings (default: 3).

---

## Q: My unified report is missing geotaxis data or subject identification. What happened?

**A:** This was fixed in v3.2 (Dec 2025). If you're seeing empty cells:

1. **Update to v3.2+** - Earlier versions had a bug where `behavioral_config` wasn't properly passed during summary generation.
2. **Re-process summaries** - Go to Reports tab and regenerate the unified report.

Unified reports now include:

- Subject columns (group, subject, day, experiment_id) appearing first
- All geotaxis zone percentages properly populated
- Proper column names with units
