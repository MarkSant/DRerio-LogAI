# Zebrafish Behavioral Metrics & Definitions

**Status:** Canonical Reference
**Last Updated:** February 2, 2026
**Category:** Reference (Diátaxis)

## 1. Locomotor Metrics

### 1.1. Distance Traveled (cm)
Calculated as the cumulative Euclidean distance between object centers across all valid frames.
$$ D = \sum \sqrt{(x_2-x_1)^2 + (y_2-y_1)^2} \times \text{pixel\_to\_cm\_ratio} $$

### 1.2. Velocity (cm/s)
Instantaneous speed calculated using the framerate ($FPS$):
$$ V = \frac{\Delta D}{\Delta t} = \Delta D \times FPS $$

- **Mean Speed (`mean_speed_cm_s`):** Average velocity magnitude over the recording.
- **Median Speed (`median_speed_cm_s`):** Median velocity, robust to outliers.
- **Max Speed (`max_speed_cm_s`):** Maximum instantaneous velocity (added v3.2).
- **Std Dev (`std_speed_cm_s`):** Standard deviation of velocity.

### 1.3. Trajectory Smoothing
Savitzky-Golay smoothing is applied to every trajectory before metrics are computed.
- **`window_length`**: Number of frames in each smoothing window (must be odd).
- **`polyorder`**: Polynomial degree used to fit each window.

## 2. Spatial Metrics (Zonal)

### 2.1. Time in Zone (s)
Cumulative duration where the tracked object's center is within a defined polygon.

### 2.2. Thigmotaxis (Center vs Periphery)
Analysis of preference for the tank margins.
- **Periphery:** Usually defined as the outer 2-5cm of the arena.
- **Thigmotaxis Index:** $\frac{\text{Time in Periphery}}{\text{Total Time}}$.
- **Average distance to wall**: Mean distance to the arena boundary.
- **Inner Zone Distance**: Distance traveled within the center area.
- **Zone Latency**: Time elapsed before first entry into the center zone.

### 2.3. Multi-Aquarium Metrics
When processing multiple subjects in the same video:
- **Aquarium Isolation:** Metrics are computed independently for each `aquarium_id`.
- **Thigmotaxis Per Aquarium:** Periphery/Center zones are scaled individually to each detected aquarium's geometry.
- **Combined Reporting:** Summary reports aggregate results but keep columns separated by subject ID.

### 2.4. ROI Inclusion Rules
- `centroid_in`: post-warp pixel containment check.
- `centroid_in_on_buffered_roi`: ROI expanded by a configurable radius (cm).
- `bbox_intersects`: minimum overlap ratio between detection BBox and ROI.

## 3. Geotaxis (Dive Response)
For lateral-view aquariums (`aquarium_perspective: lateral`), geotaxis analysis measures vertical position preference.
- **Zones:** 1-indexed in reports: "Zona 1 - Fundo" (Bottom), "Zona 2" (Middle), etc.
- **Avg Bottom Distance (`geotaxis_avg_bottom_distance_cm`):** Mean distance from tank bottom.
- **Time Near Bottom (`geotaxis_time_near_bottom_pct`):** % of time within threshold of bottom.

## 4. Derived Statistics (Social)

- **Inter-Individual Distance (IID):** Distance between two subjects in the same aquarium.
- **Nearest Neighbor Distance (NND):** For shoaling analysis.

## 5. Freezing and Speed Filters
- `freezing_velocity_threshold`
- `freezing_min_duration_s`
- `sharp_turn_threshold_deg_s`

---
**Data Output:** All metrics are exported in `.parquet` format for raw data and summarized in `.docx`/`.xlsx` reports.
