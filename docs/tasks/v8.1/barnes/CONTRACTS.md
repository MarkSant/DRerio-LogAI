# Barnes v8.1 — contracts every front codes against

**Owner:** the hub session. **Status:** frozen for stage 1 (2026-11-19). **Issue:** #633.
**Decision record:** [ADR-014](../ADR-014-experiment-profile-and-protocols.md). **Plan:**
[PLAN.md](PLAN.md).

This file is the single source of truth for names, types, units, defaults and semantics shared by
more than one front. The code that already implements a contract is named next to it; where a
front still has to implement something, its owner is named. **Only the hub changes this file.** A
front that needs a different contract stops, writes the problem in its report, and waits.

All paths are relative to `src/zebtrack/` unless they start with `tests/`, `docs/` or `scripts/`.

## 1. Experiment profile (done in stage 0)

Module: `core/services/experiment_profile.py`. Reader: `resolve_experiment_profile(project_data=None,
behavioral_config=None) -> ExperimentProfile`. Reading the keys anywhere else fails
`tests/quality/test_single_source_rules.py` (rule c).

| `behavioral_config` key | Type | Values | Default |
|---|---|---|---|
| `animal_model` | `str` | `zebrafish`, `rodent`, `other` (`AnimalModel`) | `zebrafish` |
| `protocol` | `str` | `generic`, `barnes` (`ProtocolId`) | `generic` |
| `protocol_params` | `dict[str, dict]` | `{<protocol>: {...}}`, e.g. `{"barnes": {"n_holes": 20}}` | absent |

- Precedence, **per key**: the run's `behavioral_config` > `project_data["behavioral_config"]`
  (or the legacy `behavioral_analysis` block when `behavioral_config` is absent) > default. A key
  whose value is `None` is undeclared.
- Tokens are normalised (`strip().lower()`).
- **Degrade, never raise.** Unknown model → `other` + warning. Unknown protocol → `GENERIC` with
  `declared_protocol` set + warning; `is_generic` is then `False` and the report says
  `unknown_protocol`. A non-mapping `protocol_params` (or its own block) → `{}` + warning.
- `forced_animal_model(ProtocolId.BARNES) is AnimalModel.RODENT`: a declared model that differs is
  replaced with a warning; an undeclared one is replaced silently.
- `ExperimentProfile` fields: `animal_model`, `protocol`, `protocol_params` (read-only mapping of
  the effective protocol's block), `declared_protocol`, `warnings` (translated);
  property `is_generic`.
- Writers (UI) put the keys in the dicts they already produce (`behavioral_analysis` /
  `behavioral_config`); building a dict literal is not a "read". `resolve_behavioral_config`
  already passes unknown keys through (`config.update(project_block)`), so no plumbing is needed
  for the analysis to see them.

## 2. Protocol layer (done in stage 0)

Package: `analysis/protocols/` (`base.py` types, `registry.py` registry and dispatch).

### 2.1 `report["protocol_metrics"]`

Always present (key `PROTOCOL_METRICS_KEY`). Written by `AnalysisService._attach_protocol_metrics`
at the very end of `run_full_analysis` (both return paths), after every generic metric, with the
analysers already restricted to the window.

| `status` | Meaning | Other keys |
|---|---|---|
| `none` | generic project | none: the dict is exactly `{"status": "none"}` |
| `ok` | computed | `protocol`, `version`, `reason=None`, protocol keys |
| `unavailable` | asked for, cannot compute | `protocol`, `version` (may be `None`), `reason` |
| `error` | `compute_metrics` raised or returned garbage | `protocol`, `version=None`, `reason="exception"`, `error` |

`reason` tokens (`UnavailableReason`): `unknown_protocol`, `unregistered`, `no_rois`,
`layout_unresolved`, `multi_animal`, `no_trajectory`, `exception`. Build them with
`unavailable_metrics(protocol, reason, version=..., status=..., error=...)`.

### 2.2 `ProtocolSpec`

```python
@dataclass(frozen=True, slots=True)
class ProtocolSpec:
    protocol: ProtocolId
    display_name: Callable[[], str]                     # _() at call time
    compute_metrics: Callable[[ProtocolContext], dict]  # returns status/protocol/version at least
    tidy_columns: Callable[[Mapping[str, Any]], tuple[str, ...]] = lambda params: ()
    suppressed_report_sections: frozenset[GenericReportSection] = frozenset()
    window_preset: Callable[[Mapping[str, Any]], WindowSpec] | None = None
    zone_assistant: str | None = None
```

- `GenericReportSection`: `thigmotaxis`, `geotaxis` (extend through the hub).
- Registration: add the spec to `analysis/protocols/registry.py::_builtin_specs()`; the registry is
  built lazily on first use. `generic` has no spec.
- Dispatch: `compute_protocol_metrics(context)` never raises; generic → `{"status": "none"}`
  without calling anything.

### 2.3 `ProtocolContext`

Every field shares ONE coordinate space: the space `run_full_analysis` was called in (arena-local
raw pixels for `4_Relatorio`; the homography's warped space for the `_summary.parquet` that feeds
the unified report). Never mix in `ZoneData` coordinates.

| Field | Type | Notes |
|---|---|---|
| `profile` | `ExperimentProfile` | `profile.protocol_params` = raw params of this protocol |
| `trajectory` | `pd.DataFrame` | after `screen_subjects`; the WHOLE recording, NOT cut; columns as recorded (`timestamp`, `frame`, `track_id`, `x1..y2`, `confidence`, optional `x_center_px`/`y_center_px`); `timestamp` = event clock |
| `rois` | `tuple[ROI, ...]` | stored order; `ROI.name`, `ROI.geometry` (shapely) |
| `arena_polygon_px` | `tuple[tuple[float, float], ...]` | |
| `pixelcm_x`, `pixelcm_y` | `float` | px per cm |
| `window` | `WindowResolution \| None` | `window.cut` on the `timestamp` clock; `window.stop.reason`; `window.spec` (JSON) |
| `time_base` | `TimeBase` | |
| `behavioral_config` | `Mapping` | read-only |
| `inputs` | `Mapping` | `protocol_inputs[<protocol>]`, `{}` when none |
| `behavioral_analyzer` | `ConcreteBehavioralAnalyzer` | already restricted; read-only |
| `roi_analyzer` | `ROIAnalyzer \| None` | report's rule, already restricted; read-only |
| `warnings` | `list[str]` | the SAME list as `report["validacao"]["avisos"]`; append only |

### 2.4 Per-video inputs

- Stored in `video_entry["protocol_inputs"][<protocol>]` (key `PROTOCOL_INPUTS_KEY`). Read with
  `protocol_inputs_of_entry(entry)` / `protocol_inputs_for(inputs, protocol)`; write with
  `set_protocol_input(entry, protocol, key, value)` / `clear_protocol_input(...)`, then save the
  project. Any other read fails rule c.
- Plumbed (stage 0) as `run_full_analysis(..., protocol_inputs=...)` /
  `run_full_analysis_as_dto(..., protocol_inputs=...)` / `ReporterContext(..., protocol_inputs=...)`
  from: the individual report (`ReportGenerationCoordinator._generate_standard_report`), the
  single-arena summary (`_process_standard_summary_video`), the pre-recorded pipeline
  (`AnalysisPipelineRunnerMixin._video_protocol_inputs`), "Generate summaries"
  (`AnalysisControlViewModel`) and the live post-analysis.
- **Live:** a session has no video entry; `LiveAnalysisPostProcessorMixin` reads
  `protocol_inputs_of_entry(self._analysis_params)`, i.e. the session's analysis params carry
  `{"protocol_inputs": {"barnes": {...}}}` under the same key.
- Multi-aquarium paths pass nothing: no protocol supports more than one arena per video.

## 3. Barnes conventions (done in stage 0)

Module: `analysis/protocols/barnes/contract.py`.

- **Offsets are relative to the target (the escape hole).** `0` = target; `+k` = `k` holes
  **clockwise as seen on screen** (image coordinates, y down, so `atan2(y - cy, x - cx)` grows
  clockwise); `-k` counter-clockwise. With an even `n_holes` the opposite hole is `+n/2`, never
  negative. `circular_offset(abs_index, target_abs_index, n_holes)` returns `(-n/2, n/2]`.
- **Distance** = `abs(offset)`, `0..n_holes // 2` (`max_offset`).
- **Probe score** = `probe_score(offset, cap) = min(abs(offset) + 1, cap)`; `cap = 10` by default,
  so with 20 holes target = 1 … opposite and its neighbours = 10 (to be confirmed by the lab).

### 3.1 ROI names (contract: names, not metadata)

| Name | Constant | Meaning |
|---|---|---|
| `toca` | `TARGET_ROI` (= `core/conditions/presets.BARNES_BURROW_ROI`) | the escape hole |
| `quadrante_alvo` | `QUADRANT_ROI` | target sector |
| `buraco_+01` … `buraco_+09`, `buraco_-01` … `buraco_-09` | `hole_roi_name(offset, n)` | decoys, sign always written, two digits |
| `buraco_oposto` | `OPPOSITE_HOLE_ROI` | opposite hole (even `n` only) |

- Stored order = `expected_roi_names(n_holes)`: `quadrante_alvo`, `toca`, `+01..+k`, `-01..-k`,
  `buraco_oposto`. The quadrant comes first so the holes win `ROIAnalyzer`'s single `stable_roi`
  column where they overlap it. Non-Barnes ROIs the user drew may coexist (after the Barnes ones).
- `parse_barnes_roi_name(name, n_holes) -> BarnesRoiName | None` is exact and case-sensitive.
- Geometry rules (written by `barnes-arena`, relied on by `barnes-metrics`), all raw pixels of the
  frame the zones were drawn on:
  - arena = the table ellipse as a polygon of 64 vertices;
  - hole ROI = circle of radius `min(radius_px * hole_roi_dilation, 0.45 * min_adjacent_spacing)`
    as 32 vertices, centred on the hole (hole ROIs never overlap);
  - `quadrante_alvo` = sector from the ring-ellipse centre, bounded by the rays through the
    mid-points between hole `±quadrant_half_holes` and hole `±(quadrant_half_holes + 1)` (in the
    ring's parametric angle), closed by the table ellipse; at least one vertex per 3°.

### 3.2 `BarnesParams` — `behavioral_config["protocol_params"]["barnes"]`

Read only with `parse_barnes_params(raw) -> (BarnesParams, warnings)`: a bad field falls back to
its default with a warning; unknown keys are ignored.

| Field | Default | Unit / range | Used by |
|---|---|---|---|
| `n_holes` | 20 | 3–99 | all |
| `table_diameter_cm` | 184.0 | cm, > 0 | wizard (mirrors it into `aquarium_width_cm`/`aquarium_height_cm`), sanity checks |
| `quadrant_half_holes` | 2 | ≥ 0, `2k+1 ≤ n_holes` | arena, metrics |
| `hole_roi_dilation` | 1.25 | 1–3 | arena |
| `center_radius_ratio` | 0.5 | (0, 1), of the hole-ring radius | metrics (strategy) |
| `max_trial_s` | 240.0 | s | entry preset, metrics (censoring) |
| `default_trial_type` | `training` | `training` / `probe` | metrics |
| `probe_score_cap` | 10 | ≥ 1 | metrics |
| `visit_min_cover` | 0.3 | (0, 1], fraction of the hole DISK | metrics |
| `visit_enter_frames` | 2 | processed frames | metrics |
| `visit_exit_frames` | 3 | processed frames | metrics |
| `visit_max_speed_cm_s` | `None` | cm/s; `None` = filter off | metrics |
| `entry_min_cover` | 0.5 | (0, 1], fraction of the subject BBOX | entry |
| `entry_max_visible_fraction` | 0.35 | (0, 1) | entry |
| `entry_hold_s` | 0.5 | s | entry |
| `entry_absent_s` | 3.0 | s | entry |
| `entry_min_reference_frames` | 10 | detected frames since START | entry |
| `strategy_direct_max_errors` | 3 | | metrics |
| `strategy_serial_min_adjacent_fraction` | 2/3 | (0, 1] | metrics |
| `strategy_serial_max_center_crossings` | 1 | | metrics |
| `strategy_adjacent_max_step` | 2 | holes (circular) | metrics |

### 3.3 `BarnesVideoInputs` — `video_entry["protocol_inputs"]["barnes"]`

`{"trial_type": "training" | "probe" | None, "strategy_override": "direct" | "serial" | "random" |
None}`, read with `parse_barnes_video_inputs(raw)`. `None`/absent = undeclared: the trial type
falls back to `BarnesParams.default_trial_type`, the strategy is the automatic one. Written by the
arena assistant (trial type) and the report UI (strategy override) through `set_protocol_input`.

### 3.4 Layout cache — `ZoneData.metadata["barnes_layout"]`

`BarnesLayout.to_metadata()` / `BarnesLayout.from_metadata(raw) -> BarnesLayout | None` (invalid →
`None`, logged). It is lost by the `2_AreasOfInterest` parquet, ROI templates and `apply_template`,
so nothing may REQUIRE it: the metrics rebuild the layout from names + polygons.

```json
{
  "schema": 1,
  "n_holes": 20,
  "target_abs_index": 3,
  "source": "snapped",
  "table": {"center_px": [320.0, 214.0], "semi_axes_px": [238.0, 212.0], "angle_deg": 0.0},
  "ring":  {"center_px": [320.0, 214.0], "semi_axes_px": [200.0, 180.0], "angle_deg": 0.0},
  "holes": [
    {"offset": -3, "abs_index": 0, "center_px": [520.0, 214.0], "radius_px": 14.0,
     "snapped": true, "residual_px": 1.5}
  ]
}
```

`holes` has exactly `n_holes` entries sorted by `abs_index` (0 = the assistant's chosen origin,
clockwise); each `offset` must equal `circular_offset(abs_index, target_abs_index, n_holes)`;
`source ∈ {auto, click, snapped, reconstructed}`; ellipses use OpenCV's `fitEllipse` convention.

## 4. Front `barnes-arena` — what it must write

- Visible only when `resolve_experiment_profile(project_data).protocol is ProtocolId.BARNES`. Do
  not compare against `get_protocol(...).zone_assistant` (the spec is registered by another front).
- Writes, for the current video: the arena polygon (`set_main_arena_polygon`), then every name of
  `expected_roi_names(n_holes)` in that order (`add_roi_polygon`), replacing existing Barnes ROIs
  (names that `parse_barnes_roi_name` recognises) and keeping the user's other ROIs; the layout
  cache under `metadata["barnes_layout"]`; the trial type with
  `set_protocol_input(entry, ProtocolId.BARNES, "trial_type", ...)`; then saves the project.
- Clicks go through `CanvasManager._canvas_to_video`; coordinates are raw pixels of the frame shown
  (video or live camera snapshot).
- Pure geometry in `core/detection/barnes_geometry.py` (no Tk), testable on synthetic images.

## 5. Front `barnes-entry` — conditions engine

All in `core/conditions/` plus the two observation builders; one evaluator (ADR-011).

- **`FrameObservation`** gains two fields with defaults (existing constructors keep working):
  - `subject_area_px: float | None = None` — area (px²) of the subject bbox chosen for this frame;
    `None` when no subject detection.
  - `subject_cover: Mapping[str, float] = {}` — for each ROI with non-zero overlap,
    `area(bbox ∩ roi) / area(bbox)` in `(0, 1]`; a missing name means `0.0`.
- **`core/conditions/subject_geometry.py`** (no `analysis/` import: core must not depend on it):

  ```python
  @dataclass(frozen=True, slots=True)
  class SubjectGeometry:
      area_px: float | None
      cover: Mapping[str, float]

  def pick_subject_bbox(
      boxes: Sequence[tuple[float, float, float, float, float]],  # x1, y1, x2, y2, confidence
  ) -> tuple[float, float, float, float] | None: ...  # highest confidence; tie -> larger area

  def observe_subject(
      bbox: tuple[float, float, float, float] | None,
      rois: Sequence[tuple[str, BaseGeometry]],  # (name, shapely geometry), same space as bbox
  ) -> SubjectGeometry: ...
  ```

  Used by BOTH `analysis/window_observations.build_window_observations` and
  `core/recording/condition_runtime.py`, from the same detection that sets `subject_rois`.
- **Level nodes** (`model.py`, compiled in `evaluator._compile_level`):

  | Node (`kind`) | Params | True when |
  |---|---|---|
  | `SubjectOverRoi` (`subject_over_roi`) | `roi: str`, `min_cover: float = 0.5` (0, 1] | `subject_cover.get(roi, 0) >= min_cover` |
  | `SubjectVisibleFraction` (`subject_visible_fraction`) | `max_fraction: float` (0, 1), `min_reference_frames: int = 10` | START has fired, `subject_area_px` is not `None`, at least `min_reference_frames` detected frames since START precede this one, and `subject_area_px <= max_fraction * median(areas of those frames)` (running median, `_RunningMedian`; the current frame joins the reference AFTER the test) |
  | `LastSeenIn` (`last_seen_in`) | `roi: str`, `min_cover: float = 0.5` | `subject_area_px is None` on this frame AND the last frame with a detection had `subject_cover.get(roi, 0) >= min_cover` |

- **Trigger node `BurrowEntry`** (`kind="burrow_entry"`): `roi="toca"`, `min_cover=0.5`,
  `max_visible_fraction=0.35`, `hold=Hold(seconds=0.5)`, `absent_s=3.0`,
  `min_reference_frames=10`, `max_gap_s=None`. Fires on the first of
  `Persist(AllOfLevel(SubjectOverRoi(roi, min_cover), SubjectVisibleFraction(max_visible_fraction,
  min_reference_frames)), hold)` and `Persist(LastSeenIn(roi, min_cover), Hold(seconds=absent_s))`,
  back-dated to the first frame of that run, with reason **`burrow_entry`**
  (`contract.STOP_REASON_BURROW_ENTRY`, added to `WindowReason`). It is refused inside START.
- **Preset v2** in `core/conditions/presets.py` (keyword arguments, NOT `BarnesParams`:
  `contract.py` imports `presets.py`, so the reverse import would be circular):

  ```python
  def barnes_maze_preset_v2(
      *, k_frames: int = 5, max_s: float = 240.0, burrow_roi: str = BARNES_BURROW_ROI,
      entry_min_cover: float = 0.5, entry_max_visible_fraction: float = 0.35,
      entry_hold_s: float = 0.5, entry_absent_s: float = 3.0,
      entry_min_reference_frames: int = 10,
  ) -> WindowSpec
  ```

  START identical to v1; STOP `FirstOf(EndOfStream(), BurrowEntry(...), Delay(after="start",
  seconds=max_s))` (in this order). `barnes_maze_preset` (v1) stays as is; existing specs keep
  their hash. The editor renders, edits and round-trips the new nodes, and offers "update to v2"
  explicitly for a Barnes project whose window is the v1 preset.

## 6. Front `barnes-metrics` — semantics of the Barnes metrics

Files: `analysis/protocols/barnes/{layout,visits,metrics,strategy,spec}.py`, plus the
registration of `BARNES_SPEC` in `registry._builtin_specs()`.

- **Spec:** `protocol=BARNES`, `display_name=lambda: _("Barnes maze")`, `compute_metrics`,
  `tidy_columns=lambda raw: barnes_tidy_columns(parse_barnes_params(raw)[0].n_holes)`,
  `suppressed_report_sections={THIGMOTAXIS, GEOTAXIS}`, `zone_assistant=ASSISTANT_ID`,
  `window_preset=None` until `barnes-entry` is merged; the hub then asks this front to wire it to
  `barnes_maze_preset_v2` with `BarnesParams` mapped to its keyword arguments.
- **Inputs:** `parse_barnes_params(profile.protocol_params)`,
  `parse_barnes_video_inputs(context.inputs)`; their warnings go to `context.warnings`.
  `trial_type = inputs.trial_type or params.default_trial_type`.
- **Unavailable cases** (in this order): no ROIs → `no_rois`; layout not rebuildable (missing
  `toca` or any decoy name of `expected_roi_names(n_holes)`, warning names the missing ones) →
  `layout_unresolved`; `count_subjects(trajectory) > 1` → `multi_animal`; nothing to measure
  (empty trajectory, or empty window) → `no_trajectory`. `quadrante_alvo` is optional: without it
  the quadrant metrics are `None` with a warning.
- **Layout rebuild:** hole centres = ROI polygon centroids; ring ellipse = `cv2.fitEllipse` of the
  hole centres; centre disk = the ring ellipse scaled by `center_radius_ratio` about its centre.
- **t0** (`t_start_s`, absolute on the `timestamp` clock): `window.start.t_s` when the window
  started (`start_source="window"`); else the first trajectory timestamp
  (`start_source="recording"`) plus a warning. **Trial end** = `min(window stop t_s or last
  timestamp, t0 + max_trial_s)`.
- **Visits:** per hole, from the subject bbox per processed frame: cover = `area(bbox ∩ hole ROI)
  / area(hole ROI)`. A visit opens after `visit_enter_frames` consecutive frames with cover ≥
  `visit_min_cover` and closes after `visit_exit_frames` consecutive frames below it, both
  back-dated; a frame without a detection counts as below. With `visit_max_speed_cm_s` set, a
  visit also needs one covered frame below that speed. A visit already open at t0 starts at t0.
  Only visits that start in `[t0, trial end)` count.
- **Encounter:** first visit to `toca`. `encounter_latency_s` = its start − t0; none →
  `max_trial_s` with `encounter_censored=True`.
- **Entry** (training only; never re-detected in the metrics, ADR-011):
  - `window.stop.reason == "burrow_entry"` → `entry_latency_s = stop.t_s - t0`,
    `entry_censored=False`, `entry_source="window"`;
  - else, if `window.spec` contains a node of kind `burrow_entry` → `max_trial_s`,
    `entry_censored=True`, `entry_source="censored"`;
  - else → `None`, `entry_censored=None`, `entry_source="unavailable"` plus a warning;
  - probe → `None`, `None`, `"not_applicable"`.
- **Errors:** `primary_errors` = decoy visits that start before the encounter (all decoy visits of
  the trial when there is no encounter); `total_errors` = decoy visits that start before the entry
  (training with an entry) or before the trial end; `perseverative_errors` = decoy visits to a hole
  already visited earlier in the trial (subset of `total_errors`).
- **Paths:** `primary_path_length_cm` (t0 → encounter) and `entry_path_length_cm` (t0 → entry),
  from the subject centre (`x_center_px`/`y_center_px`, else bbox centre) with `pixelcm_x/y`, not
  counting jumps across gaps longer than `behavioral_analyzer.gap_threshold_s` (same rule as
  `distancia_total_cm`); `None` when the event did not happen.
- **Quadrant:** `target_quadrant_time_s` = `roi_analyzer.get_time_spent_in_rois()["quadrante_alvo"]
  ["seconds"]` (the report's rule, already window-restricted; it matches the generic ROI table);
  `target_quadrant_time_pct` = that / (trial end − t0) × 100.
- **Sequence and histogram:** `visit_sequence` lists every counted visit in time order with
  `VISIT_FIELDS` (times relative to t0; `t_exit_s`/`dwell_s` `None` when still open at the trial
  end); `visits_by_distance` = `{d: count}` for every `d` in `0..n/2` (all keys present, ints).
- **Strategy** (visits up to and including the first target visit; all of the trial's visits
  without an encounter):
  - `errors_before_target` = `primary_errors`;
  - `n_transitions` = visits − 1; `adjacent_transition_fraction` = share of transitions whose
    CIRCULAR offset step `min(|a-b|, n-|a-b|)` ≤ `strategy_adjacent_max_step` (`None` with no
    transition);
  - `center_crossings` = outside → inside entries of the subject centre into the centre disk
    after t0 (leaving the start box at the centre is not a crossing);
  - **direct** if there is an encounter, `errors_before_target ≤ strategy_direct_max_errors` and
    no crossing; else **serial** if `n_transitions ≥ 1`, the adjacent fraction ≥
    `strategy_serial_min_adjacent_fraction` and crossings ≤ `strategy_serial_max_center_crossings`;
    else **random**; `None` when the trial has no visit;
  - `strategy_auto` is always the automatic result; with `inputs.strategy_override`, `strategy` is
    the override and `strategy_source="manual"`, otherwise `strategy = strategy_auto`,
    `strategy_source="auto"` (`None` when `strategy` is `None`).
- **Probe** (`trial_type == "probe"`): first counted visit → `probe_first_hole_offset`,
  `probe_first_hole_score = probe_score(offset, probe_score_cap)`;
  `probe_first_error_latency_s` = first visit's start − t0 when it is a decoy, `None` when it is
  the target; `probe_attempts_to_target` = visits up to and including the first target visit,
  `None` when never. All four are `None` in training.

## 7. `report["protocol_metrics"]` for Barnes (status `ok`)

Keys in order: `contract.METRICS_KEYS` (30 keys); visit entries: `contract.VISIT_FIELDS`.

```json
{
  "status": "ok", "protocol": "barnes", "version": 1, "reason": null,
  "trial_type": "training", "n_holes": 20, "t_start_s": 12.4, "start_source": "window",
  "encounter_latency_s": 38.1, "encounter_censored": false,
  "entry_latency_s": 41.7, "entry_censored": false, "entry_source": "window",
  "primary_errors": 2, "total_errors": 3, "perseverative_errors": 1,
  "primary_path_length_cm": 412.0, "entry_path_length_cm": 430.5,
  "target_quadrant_time_s": 11.2, "target_quadrant_time_pct": 26.9,
  "visits_by_distance": {"0": 1, "1": 1, "2": 1, "3": 1, "4": 0, "5": 0, "6": 0,
                         "7": 0, "8": 0, "9": 0, "10": 0},
  "visit_sequence": [
    {"order": 1, "roi": "buraco_+03", "offset": 3, "distance": 3, "t_enter_s": 20.0,
     "t_exit_s": 21.2, "dwell_s": 1.2, "is_target": false, "is_perseverative": false,
     "before_encounter": true}
  ],
  "strategy": "serial", "strategy_source": "auto", "strategy_auto": "serial",
  "strategy_features": {"errors_before_target": 2, "center_crossings": 0,
                        "adjacent_transition_fraction": 1.0, "n_transitions": 2},
  "probe_first_hole_offset": null, "probe_first_hole_score": null,
  "probe_first_error_latency_s": null, "probe_attempts_to_target": null
}
```

(JSON shows `visits_by_distance` keys as strings; in Python they are `int`.)

## 8. Front `barnes-reports` — outputs

- **Tidy:** when `profile.protocol is BARNES`, append `spec.tidy_columns(profile.protocol_params)`
  AFTER the `window_*` columns. Values: `tidy_column_source(column)` gives the dotted path into
  `report["protocol_metrics"]` (`strategy_features.center_crossings`, `visits_by_distance.7`).
  When `status != "ok"`, only `barnes_status` (and `barnes_trial_type` when known) are filled.
  Generic projects get no `barnes_*` column.
- **Excel:** sheet `barnes_visits` (`EXCEL_VISITS_SHEET`) with `EXCEL_VISIT_COLUMNS`, one row per
  `visit_sequence` entry; written only for Barnes, even when empty (header only).
- **Word:** a Barnes section after "Metrics Summary"; sections in
  `spec.suppressed_report_sections` are omitted.
- **Partial / unified:** learning curves (group × day, mean ± SEM of latencies and errors),
  strategy distribution, probe comparison; censored latencies stated as such.
- **Strategy correction UI:** writes `strategy_override` through `set_protocol_input`, saves the
  project, and the next report regenerates with `strategy_source="manual"`.

## 9. Front `exp-profile` — persistence and UI

- Discovery step and `BehavioralConfigWidget` produce `animal_model`, `protocol` and (for Barnes)
  `protocol_params.barnes` inside the `behavioral_analysis` dict they already return;
  `BehavioralAnalysisData` (`ui/wizard/models.py`) gets them as real fields.
  `project_lifecycle_manager._persist_project_data` already copies that dict into
  `project_data["behavioral_config"]`.
- Choosing Barnes: animal model locked to rodent, perspective `top_down`,
  `analysis_interval_frames = 1`, the window preset from `get_protocol(BARNES).window_preset`
  when it is not `None` (the spec is registered by `barnes-metrics`; handle `None`), and the
  Calibration step shows one "Table diameter (cm)" field that writes `aquarium_width_cm`,
  `aquarium_height_cm` and `protocol_params.barnes.table_diameter_cm` with the same value.
- Live ad-hoc dialog: for Barnes, a trial-type selector whose value travels in the session's
  analysis params as `{"protocol_inputs": {"barnes": {"trial_type": ...}}}`.
- Built-in template `resources/wizard_templates/barnes_maze.json`.
- Per-animal defaults (speed ceiling, freezing, thigmotaxis) in `analysis/behavioral_policy.py`;
  `zebrafish` keeps today's numbers.

## 10. Shared artefacts (supersedes the plan's i18n rule)

- **i18n.** `tests/i18n/test_pot_in_sync.py` fails on any `_()` msgid missing from the committed
  `.pot`, and `test_pairs_not_orphaned.py` on any pair whose msgid is missing from the `.po`, so a
  front MUST add its own catalogue entries. Do it by hand, never with
  `scripts/update_translations.py` (it reflows ~2600 unrelated lines):
  1. append the entries at the END of `locales/zebtrack.pot` (or `locales/reporter.pot` for
     strings under `analysis/reporters/`);
  2. insert the translated entries just BEFORE the first obsolete `#~` entry of
     `locales/pt_BR/LC_MESSAGES/zebtrack.po` (`reporter.po`: at the end);
  3. record the pairs in `locales/_pairs/barnes-<session>.json`;
  4. `python scripts/compile_translations.py`.

  Two fronts appending at the same spot conflict at merge; the hub keeps both blocks and
  recompiles the `.mo` (binary: never merge it, recompile).
- **Mutation catalogue.** Append your blocks at the end of `scripts/mutation_catalog.yaml` under a
  `# --- Barnes v8.1 <session> ---` comment. Run
  `python scripts/mutation_check.py --changed-since claude/barnes-maze-arena-automation-68f138
  --jobs 2`. An edit next to an OLD block's `find` text makes that block report "found 0" (it
  shows as a survivor): update that block's `find`/`replace` to the new text, never delete it.
- **Dead-code guard.** `tests/quality/test_no_dead_code.py` runs vulture over `src/` (tests do not
  count as callers). The stage-0 contract published ahead of its callers sits in the
  `[contract-ahead]` section of `tests/quality/vulture_whitelist.txt`; when your front starts
  calling one of those names the guard reports the entry as stale: delete it in your branch. A
  new definition of yours that only tests use fails the guard: call it from production code or
  delete it; never add an entry without asking the hub.
- **Hub only:** `CHANGELOG.md`, `docs/testing/TEST_MAP.md`, `docs/testing/COVERAGE_BASELINE.md`,
  `.copilot-impact-map.yaml`, `docs/reference/system_integration.md`, `docs/wiki/`,
  `docs/tasks/active/ROLLING_TASK_LOG.md`, this file. List what you need there in your report.
- **Persistence tokens** never translated: everything in sections 1, 2.4, 3 and 7. Barnes ROI names
  contain no accent, so the i18n scanner does not flag them; do not add them to
  `scripts/i18n_allowlist.txt` unless the scanner does.
