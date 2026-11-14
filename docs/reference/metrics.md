# Behavioral Metrics & Definitions

**Status:** Canonical Reference
**Last Updated:** November 2026 (v8.0.0)
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
| `time_percentage_in_{roi}` | Percentage of observed time (inside the analysis window when there is one, §7) |
| `entries_in_{roi}` | Number of entries into ROI |
| `exits_from_{roi}` | Number of exits from ROI |
| `latency_to_{roi}_s` | Time to the first outside→inside transition, from the first row or from START (§7.3) |
| `latency_censored_{roi}` | `True` when the latency is the window-duration ceiling (never entered) |
| `latency_present_at_start_{roi}` | `True` when the subject was already inside at START (latency `0.0`) |
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

For lateral-view aquariums (`aquarium_perspective: lateral`), geotaxis analysis measures vertical position preference. It is a zebrafish measure (dive response); on a top-down recording of rodents set the perspective to top-down, since the default is still lateral.

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
| `video_duration_s` | Recording duration from timestamps, `(t_last − t_first) + median_dt` (v8; was rows / fps) |
| `total_frames_analyzed` | Number of rows analysed (inside the window when there is one) |
| `window_status`, `window_start_s`, `window_stop_s`, `window_duration_s`, `window_reason` | Analysis window (v8, §7); empty without one |

## 7. Time Base and Analysis Window (v8)

### 7.1. Time base

Every time-based metric uses the recording's own clock, resolved by
`analysis/time_base.resolve_time_base()`: the `3c_Objetos_` heartbeat, then the
live frame ledger, then the trajectory's unique timestamps (PTS). The configured
`video_processing.fps` is only the last resort, and when it is used the report
carries a warning. Live sessions are re-dated by the capture instant
(`retime_from_ledger`) before any metric is computed.

- `video_duration_s` (`duracao_video_s`) = `(t_last − t_first) + median_dt` over
  the unique timestamps. Before v8 it was `rows / fps`, which doubled with two
  tracks and divided by N when processing every N-th frame.
- `validacao.estatisticas.duration_s` sits next to `total_frames` (which stays a
  row count).

### 7.2. Analysis window

With `project_data["analysis_window"]` set, the metrics read only
**[START, STOP]**. The cut is hybrid: validation, smoothing, velocity and ROI
presence (with its debounce) run on the WHOLE recording, so the first sample
inside the window keeps its real neighbour; only then do the metrics read the
window, with the absolute time index preserved.

| Quantity | With a window |
| --- | --- |
| Denominator of rates and percentages (sharp turns per minute, inactivity %, `percentage_of_recording`) | `STOP − START` (`window_duration_s`) |
| ROI time percentage | observed time inside the window (sum of capped `dt`), clipped to [START, STOP]; the row that straddles START is credited only with its part after START |
| `latency_to_{roi}_s` | measured from START |
| Entries / exits | only real transitions after START |
| Freezing episode cut by START or STOP | truncated at the edge; `freezing_min_duration_s` applies to what remains |
| `total_frames_analyzed` | rows inside the window |
| Time axes of plots and the `.docx` event log | start at START; the event log keeps the absolute time and adds a column relative to START |

**START never met.** `on_start_not_met = "whole_recording"` (default) analyses the
whole recording and adds a warning to the report and the `.xlsx`; `"empty"` leaves
the window metrics empty.

**STOP never met.** The window closes at the end of the recording with
`censored = True` (reason `end_of_stream`).

### 7.3. Latency flags

Each ROI latency carries two booleans, in the report (`latency_censored`,
`latency_present_at_start`, `{roi: bool}`, also per animal under
`analise_roi.por_animal`) and in the `.xlsx` (`latency_censored_<roi>`,
`latency_present_at_start_<roi>`):

- **Present at start** — the subject is already inside the ROI at START (or at the
  first row without a window): latency `0.0`, flag `True`. The entry count does
  not count this as an entry. Before v8, `bool.diff()` (an XOR) took the first
  EXIT for the first entry and the latency came out `None` next to 1 entry.
- **Censored** — the subject never enters the ROI inside the window: latency =
  the window duration (e.g. 240 s on Barnes), flag `True`. This is a ceiling, not a
  measurement; analyse it as right-censored (e.g. survival methods), never as an
  observed latency. Without a window a never-entered ROI keeps latency `None`.

### 7.4. Summary columns

The `.xlsx` always has `window_status`, `window_start_s`, `window_stop_s`,
`window_duration_s` and `window_reason` (empty without a window), and the per-ROI
latency flags, all appended at the END so no existing column moves. The report
dict always has `analysis_window` (`{"status": "none"}` without a window), so the
unified report never sees a schema mismatch between projects with and without a
window.

### 7.5. Known limitations

- Freezing uses `fillna(0)` on the first velocity sample (row 0 can look frozen)
  and its blocks span tracking gaps.
- Total distance sums the jump across a tracking gap.
- Multi-aquarium live sessions have no analysis window in v8.

---

**Data Output:** All metrics are exported in `.parquet` format for raw data and summarized in `.docx`/`.xlsx` reports. Unified reports additionally include `.csv` export and descriptive statistics pivot tables.
