# Zebrafish Behavioral Metrics & Definitions

**Status:** Canonical Reference
**Last Updated:** June 2026
**Category:** Reference (Diátaxis)

## 1. Locomotor Metrics

### 1.1. Distance Traveled (cm)

Calculated as the cumulative Euclidean distance between smoothed object centers across all valid frames.

$$D = \sum_{i=1}^{N-1} \sqrt{(x_{i+1}-x_i)^2 + (y_{i+1}-y_i)^2}$$

Where coordinates are in centimeters (converted from pixels via `pixelcm_x`, `pixelcm_y`).

| Column | Description |
| --- | --- |
| `total_distance_cm` | Cumulative path length over the entire recording |

### 1.2. Velocity (cm/s)

Instantaneous speed calculated using the framerate ($FPS$):

$$v_i = \frac{\sqrt{(x_{i+1}-x_i)^2 + (y_{i+1}-y_i)^2}}{1 / FPS}$$

| Column | Description |
| --- | --- |
| `mean_speed_cm_s` | Average velocity magnitude over the recording |
| `median_speed_cm_s` | Median velocity, robust to outliers |
| `max_speed_cm_s` | Maximum instantaneous velocity (added v3.2) |
| `std_speed_cm_s` | Standard deviation of velocity |

### 1.3. Trajectory Smoothing

Savitzky-Golay smoothing is applied to every trajectory before metrics are computed.

- **`window_length`**: Number of frames in each smoothing window (must be odd).
- **`polyorder`**: Polynomial degree used to fit each window.

### 1.4. Tortuosity

Ratio of actual path length to straight-line (net) displacement. Values ≥ 1.0; a perfectly straight path yields 1.0.

$$\text{Tortuosity} = \frac{D_{\text{path}}}{D_{\text{net}}}$$

Where $D_{\text{path}}$ is the cumulative distance and $D_{\text{net}} = \sqrt{(x_N-x_1)^2 + (y_N-y_1)^2}$.

| Column | Description |
| --- | --- |
| `tortuosity` | Path tortuosity ratio (≥ 1.0) |

### 1.5. Angular Velocity (°/s)

Rate of heading change between consecutive displacement vectors. Computed on smoothed coordinates; stationary frames (displacement < `min_displacement_threshold_cm`) are excluded (NaN).

$$\omega_i = \frac{\theta_i}{\Delta t}$$

Where $\theta_i = \arctan2(\vec{v}_i \times \vec{v}_{i-1},\; \vec{v}_i \cdot \vec{v}_{i-1})$ is the signed angle between consecutive displacement vectors.

Summary statistics use absolute values (direction-agnostic magnitude).

| Column | Description |
| --- | --- |
| `mean_angular_velocity_deg_s` | Mean \|ω\| over the recording |
| `max_angular_velocity_deg_s` | Maximum \|ω\| |
| `angular_velocity_std_dev_deg_s` | Std dev of \|ω\| |

**Configuration** (in `settings.angular_velocity`):

- `min_displacement_threshold_cm`: Minimum displacement to compute angle (default 0.5 cm).
- `angle_calculation_window`: Frame window for angle computation.
- `angular_velocity_smoothing_window`: Rolling mean window for smoothing.

### 1.6. Sharp Turns

A sharp turn is detected when the instantaneous angular velocity exceeds a configurable threshold.

| Column | Description |
| --- | --- |
| `sharp_turns_count` | Number of sharp turns detected |
| `sharp_turns_per_minute` | Sharp turns normalized to per-minute rate |

**Configuration:** `sharp_turn_threshold_deg_s` (default 200.0 °/s).

### 1.7. Speed Bursts

Episodes where velocity exceeds a threshold continuously for at least a minimum duration.

| Column | Description |
| --- | --- |
| `speed_bursts_count` | Number of burst episodes |
| `speed_bursts_total_duration_s` | Total time in burst episodes |
| `speed_bursts_threshold_cm_s` | Threshold used for detection |

### 1.8. Inactivity Periods

Episodes where velocity stays below a threshold continuously for a minimum duration.

| Column | Description |
| --- | --- |
| `inactivity_count` | Number of inactivity episodes |
| `inactivity_total_duration_s` | Total time in inactivity |
| `inactivity_percentage_of_recording` | Percentage of total recording time |
| `inactivity_threshold_cm_s` | Threshold used for detection |

## 2. Spatial Metrics (Zonal)

### 2.1. Time in Zone (s)

Cumulative duration where the tracked object's center is within a defined polygon.

### 2.2. Thigmotaxis (Center vs Periphery)

Analysis of preference for the tank margins.

- **Periphery:** Usually defined as the outer 2-5 cm of the arena.
- **Thigmotaxis Index:** $\frac{\text{Time in Periphery}}{\text{Total Time}}$.
- **Average distance to wall**: Mean distance to the arena boundary.
- **Inner Zone Distance**: Distance traveled within the center area.
- **Zone Latency**: Time elapsed before first entry into the center zone.

| Column | Description |
| --- | --- |
| `thigmotaxis_time_near_wall_pct` | Percentage of time near wall |
| `thigmotaxis_avg_wall_distance_cm` | Mean distance to nearest boundary |

> **Arbitrary polygon geometry (any number of sides).** The distance to the wall
> is computed as the exact Euclidean distance from each trajectory point to the
> *nearest edge* of the arena polygon, via Shapely
> (`shapely.distance(point, arena_polygon.boundary)` in
> `analysis/behavior.py::get_thigmotaxis_timeseries`). This is **geometry-agnostic**:
> it is correct for arenas with any number of vertices (≥3), convex or concave —
> not only 4-corner rectangles. Aquariums automatically segmented as 6-, 8- or
> more-sided polygons are measured against their true outline. The center vs.
> periphery split is likewise geometric: the center zone is the polygon inset by
> `buffer(-distance)` (or scaled by `sqrt(area_ratio)` around its centroid in
> `analysis/roi.py::analyze_center_vs_periphery`), so the periphery follows the
> real shape of the wall. **The thigmotaxis plot in the Word report is therefore
> reliable for non-rectangular, many-sided aquariums.**

### 2.3. ROI-Specific Metrics

For each user-defined ROI (named polygon), the following per-ROI columns are generated:

| Column Pattern | Description |
| --- | --- |
| `time_in_{roi}_s` | Cumulative time inside ROI (seconds) |
| `time_percentage_in_{roi}` | Percentage of total recording time |
| `entries_in_{roi}` | Number of entries into ROI |
| `exits_from_{roi}` | Number of exits from ROI |
| `latency_to_{roi}_s` | Time to first entry (seconds) |
| `distance_in_{roi}_cm` | Distance traveled inside ROI |
| `mean_speed_in_{roi}_cm_s` | Mean speed inside ROI |
| `freezing_count_in_{roi}` | Number of freezing episodes inside ROI |
| `freezing_duration_in_{roi}_s` | Total freezing duration inside ROI |
| `roi_color_{roi}` | Color assigned to ROI (human name) |

### 2.4. Multi-Aquarium Metrics

When processing multiple subjects in the same video:

- **Aquarium Isolation:** Metrics are computed independently for each `aquarium_id`.
- **Thigmotaxis Per Aquarium:** Periphery/Center zones are scaled individually to each detected aquarium's geometry.
- **Combined Reporting:** Summary reports aggregate results but keep columns separated by subject ID.

### 2.5. ROI Inclusion Rules

- `centroid_in`: post-warp pixel containment check.
- `centroid_in_on_buffered_roi`: ROI expanded by a configurable radius (cm).
- `bbox_intersects`: minimum overlap ratio between detection BBox and ROI.

## 3. Geotaxis (Dive Response)

For lateral-view aquariums (`aquarium_perspective: lateral`), geotaxis analysis measures vertical position preference.

- **Zones:** 1-indexed in reports: "Zona 1 - Fundo" (Bottom), "Zona 2" (Middle), etc.
- **Avg Bottom Distance (`geotaxis_avg_bottom_distance_cm`):** Mean distance from tank bottom.
- **Time Near Bottom (`geotaxis_time_near_bottom_pct`):** % of time within threshold of bottom.

| Column Pattern | Description |
| --- | --- |
| `geotaxis_zone_{i}_pct` | Percentage of time in vertical zone *i* (0-indexed internally, 1-indexed in display) |
| `geotaxis_avg_bottom_distance_cm` | Mean distance from tank bottom |
| `geotaxis_time_near_bottom_pct` | % of time within threshold of bottom |

> **Caveat — bottom defined by the bounding box, not the polygon edge.** Unlike
> thigmotaxis (which uses the full polygon outline), the geotaxis "distance to
> bottom" is measured against the *minimum Y of the arena polygon's bounding box*
> (`arena_polygon_cm.bounds[1]` in `analysis/behavior.py::get_geotaxis_timeseries`).
> This is accurate for lateral-view tanks whose floor is approximately horizontal
> (the common case). For strongly irregular or tilted polygons it measures the
> distance to the bounding-box floor rather than to the true bottom edge, so the
> absolute bottom-distance value may be slightly biased even though the relative
> vertical-zone occupancy stays consistent. This is intentional for the supported
> lateral-tank use case.

## 4. Derived Statistics (Social)

- **Inter-Individual Distance (IID):** Distance between two subjects in the same aquarium.
- **Nearest Neighbor Distance (NND):** For shoaling analysis.

## 5. Freezing and Speed Filters

| Parameter | Description |
| --- | --- |
| `freezing_velocity_threshold` | Velocity below which the animal is considered "frozen" (cm/s) |
| `freezing_min_duration_s` | Minimum continuous duration to qualify as a freezing episode (s) |
| `sharp_turn_threshold_deg_s` | Angular velocity threshold for sharp turn detection (°/s) |

## 6. Video/Session Metadata

| Column | Description |
| --- | --- |
| `experiment_id` | Unique identifier for the video/experiment |
| `group_id` | Experimental group assignment |
| `day` | Experimental day |
| `subject` | Subject identifier |
| `aquarium_id` | Aquarium number (multi-aquarium mode) |
| `video_duration_s` | Total video duration in seconds (added v4.0) |
| `total_frames_analyzed` | Number of frames processed (added v4.0) |

---

**Data Output:** All metrics are exported in `.parquet` format for raw data and summarized in `.docx`/`.xlsx` reports. Unified reports additionally include `.csv` export and descriptive statistics pivot tables.
