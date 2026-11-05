# Domain Glossary — DRerio LogAI

Quick definitions of project-specific terms. The goal: skim before reading code,
not read code to learn vocabulary.

## Tracking & detection

**Detector / DetectorService**
The component that runs YOLO/OpenVINO inference on a frame and returns
detections (bounding boxes + confidences + track IDs). Located in
`core/detection/`. Plugins in `plugins/` provide concrete backends.

**DetectorPlugin**
Abstract base in `plugins/base.py`. Concrete plugins (YOLO, OpenVINO) are
registered in `plugins/__init__.py` via the `DETECTOR_PLUGINS` dict.

**ByteTracker**
Multi-object tracker (in `tracker/`) that assigns persistent `track_id`s across
frames using Kalman filtering + matching.

**track_id (convention)**
Persistent ID for one tracked subject across frames.
In **multi-aquarium** mode: `global_id = aquarium_id * 1000 + local_track_id`.
Example: aquarium 0 → IDs 0–999; aquarium 1 → IDs 1000–1999.
**Local IDs MUST stay <1000** to avoid collision overflow.

## Spatial / geometric concepts

**Arena**
The full tracking region inside a video. Defined either by **4 corners**
(quadrilateral) or **center+radius** (circle). The "4 corners OR center" logic
is enforced project-wide.

**Zone**
A user-defined region inside the arena (e.g. top half, corner refuge). Zones
are stored in **reference coordinates** (`camera.desired_width` ×
`camera.desired_height`) and rescaled to actual video dimensions via
`Detector.set_zones()`.

**ROI (Region of Interest)**
A geometric region used to attribute detections to a behavioral context. Four
modes determine when a detection counts as "inside":

- `centroid_in` — center of bbox is inside the polygon.
- `centroid_in_on_buffered_roi` — center inside polygon expanded by a buffer.
- `bbox_intersects` — any part of bbox overlaps the polygon.
- `seg_overlap` — segmentation mask overlaps (when available).

**ROI metric semantics — per-animal vs. `any_track`**
When a trajectory contains more than one `track_id`, "time in the ROI" has two
distinct meanings, and the report carries both:

- **Per animal** (primary calculation) — each animal gets its own presence
  series, its own observed clock, and its own entries and exits. Published under
  `report["analise_roi"]["por_animal"][track_id]`.
- **`any_track` occupancy** (published at the top of `analise_roi`) — the ROI
  counts as occupied while *any* animal is inside. This is the aggregation of
  the per-animal series, and it is the same reading
  `ArduinoEventMapper` uses to fire hardware on ROI enter/exit, so report and
  equipment describe the same event.

Consequences worth stating explicitly:

- Two animals entering together are **one** occupancy entry but **two**
  per-animal entries.
- `tempo_gasto_por_roi.seconds` at the top level is session time, never the sum
  of animal-seconds (which would reach N × the session duration).
- `distancia_por_roi` at the top level *is* a sum across animals — there is no
  "path of the group".
- Tortuosity for multiple animals is the **mean** of the individual
  tortuosities; concatenating subjects into one path would only measure the
  distance between them.
- With a single animal the two semantics coincide and the output is unchanged.

`report["analise_roi"]["semantica"]` records which reading the top-level keys
use, and `n_animais` how many subjects were found. Multi-animal trajectories
also raise a validation warning, surfaced in the report's appendix.

**Calibration**
Maps pixels ↔ centimeters using a known real-world reference (often the arena
edge length). When calibration exists, parquet rows include `x_cm`, `y_cm`.

**Coordinate systems**
See [`COORDINATE_SYSTEMS.md`](COORDINATE_SYSTEMS.md) for the full reference
(video px ↔ canvas px ↔ reference px ↔ cm).

## Multi-aquarium

**Aquarium**
One physical fish tank visible in the video. Multi-aquarium mode supports
**up to 2** independent aquariums per video, each with its own polygon, ROI,
calibration, and outputs.

**AquariumData / MultiAquariumZoneData**
Data classes in `core/detection/`. `AquariumData` holds one aquarium's
`(id, polygon, roi_mode, roi_data)`. `MultiAquariumZoneData` is the container:
`aquariums: list[AquariumData]`, `calibration`, `active_aquarium_id`,
`sequential_processing`.

**`get_zone_data()` vs `get_multi_aquarium_zone_data()`** ⚠️
`get_zone_data()` returns **only aquarium 0** (legacy compatibility shim).
For any multi-aquarium operation (especially **report generation**), always use
`ProjectManager.get_multi_aquarium_zone_data()` with a fallback for
single-aquarium projects.

**Sequential processing**
Boolean flag on `MultiAquariumZoneData`. When `True`, the video is processed
twice (one full pass per aquarium). When `False` (default), both aquariums are
processed in a single pass with partitioned detection. UI toggle lives in
`ui/components/zone_controls.py`.

## Behavior metrics

**Geotaxis**
Vertical preference behavior. Zones are numbered 1-indexed in user-facing
labels: `geotaxis_zone_0_pct` → "Geotaxis Zona 1 - Fundo (%)" (zone 1 = bottom).
Configured via `behavioral_config["geotaxis_zones"]`.

**Velocity stats**
Calculated in `analysis/behavior.py:get_velocity_stats()` →
`mean_speed_cm_s`, `median_speed_cm_s`, `std_dev_speed_cm_s`,
`max_speed_cm_s`. All persisted in summary parquet/Excel/Word.

**Social proximity**
Inter-subject distance metrics for multi-subject tracking (legacy v1.x).

## Project / organization

**ProjectManager**
Owns all per-project state: video list, ROI templates, zones, parquet outputs,
metadata. Located in `core/project/project_manager.py`. Project files are
JSON-serialized on disk.

**experiment_id**
Identifier scoped to one experiment (often = day or treatment). Used in output
folder naming for live sessions: `live_analysis_sessions/{experiment_id}_{ts}/`.

**Subject**
One tracked individual (one animal). Has `subject_name` (display) and
`subject_id` (stable). In single-subject mode, one subject per aquarium; in
multi-subject mode, multiple per aquarium.

**Group**
Experimental cohort (e.g. control, treated). One group contains many subjects.
`group_id` is the canonical column; `group` (without `_id`) is **deprecated**
and dropped during unified report generation.

**Day**
Experimental day (D1, D2…). Often used as a hierarchy level in tree views.

**Subject hierarchy (tree)**
Group → Day → Subject → Video. Cascade deletion lives in
`ProjectManager.delete_subject()` etc.

## Wizard

**Wizard / WizardService**
Project creation flow. UI lives in `ui/wizard/` (7 steps for a pre-recorded
project, 6 for a live one; see `WizardStepID`). Business logic
lives in `core/services/wizard_service.py` (validation, hardware detection,
30s TTL hardware cache).

**Live project vs Single video vs Multi-aquarium**
Three project types selected at wizard step 1:

- **Single video** — one pre-recorded file, one aquarium.
- **Multi-aquarium** — one pre-recorded file, 2 aquariums.
- **Live** — real-time camera capture into multiple sessions.

## Recording / live

**LiveCameraService**
Owns the live capture pipeline: parallel capture + processing threads, own
session timer, lightweight recording. Decoupled from `RecordingService` since
v2.1. Located in `core/recording/live_camera_service.py`.

**FrameSource / LiveStreamSource / VideoSource**
Frame iterators. `VideoSource` reads from disk; `LiveStreamSource` wraps
`Camera` with a time-limited duration. Both implement the `FrameSource`
protocol so the processing pipeline doesn't care which source it has.

**Recorder / RecorderFactory**
Writes detection rows to parquet. `RecorderFactory` lazily imports
pandas/pyarrow only when analysis starts (saves ~2.9s startup + 150 MB).

## Class roles & analysis window (v8)

**Class role**
What a class of a detection weight *is*, one of four persisted tokens (never
translated): `subject` (tracked and measured; several subject classes share one
`track_id` axis), `arena` (the apparatus, at most one class), `context` (seen and
recorded per frame, never tracked — e.g. `experimenter`, `start_box`) and
`ignored`. Defined in `core/detection/class_roles.py` (ADR-009).

**ClassRoleMap / role source**
The frozen map of roles **by normalised class name** (never by id, so a retrain
that inserts a class shifts nothing). `source` says where it came from:
`project` (`model_overrides.class_roles`, valid only while
`class_roles_weight_sha256` matches the effective weight), `weight` (the
`class_roles` of the `weights_config.json` entry), `aliases` (`class_aliases.py`
name lists; never produce `context`) or `legacy_positional` (ids 0/1, only for a
model without names). Built only by `resolve_class_role_map()`.

**ClassRolesUnresolvedError**
Raised when a weight has class names, three or more classes and none resolvable
as the subject. Live and batch detection refuse such a weight instead of tracking
class 1 by position. Catch it by type, never by message.

**Object sidecar (`3c_Objetos_<base>.parquet`)**
Per-video file next to the trajectory with one **heartbeat** row per processed
frame (`class_id = -1`, `role = "frame"`, no bbox) plus one row per subject and
context detection. The heartbeat is what distinguishes "nothing was detected"
from "the frame was not processed". Written unless
`recorder.persist_object_sidecar` is `False` (`should_capture_objects()`); schema
in [`data_schema.md`](data_schema.md).

**Analysis window / WindowSpec**
The rule that says when the analysis STARTS and STOPS inside a recording
(ADR-011), stored in `project_data["analysis_window"]` (`None` = whole
recording). A `WindowSpec` has a `start` and a `stop` condition,
`on_start_not_met` (`whole_recording` | `empty`) and `on_stop` (`mark` |
`end_session`, live only). The recording is always complete; only the metrics are
cut.

**Condition (level / trigger)**
Nodes of a `WindowSpec`, discriminated by a persisted `kind`. A **level** is true
or false on each frame (`ClassPresence`, `RoiInside`, `Not`, `AllOfLevel`,
`AnyOfLevel`); a **trigger** fires once, at an instant (`Persist`, `RoiEdge`,
`TimeReached`, `FrameReached`, `Delay`, `External`, `EndOfStream`, `FirstOf`,
`AllOf`, `Sequence`). One evaluator (`core/conditions/evaluator.py`) serves live
(`step` per frame) and analysis (`evaluate_window`, a fold over `step`).

**Event clock**
The clock conditions and the window are measured on: the video's PTS
(`timestamp = POS_MSEC / 1000`) for pre-recorded files, the capture instant
(`t_capture_perf − t0_perf` from the `6_FrameLedger`) for live sessions. The live
`timestamp` column of `3_CoordMovimento` is a processing clock and never dates an
event; `time_base.retime_from_ledger()` re-dates a live trajectory in memory.

**Back-dating**
A held condition ("rat visible for 5 frames") fires at the FIRST frame of the run
that satisfied it, not at the frame that confirmed it. `WindowEvent` carries both
(`frame`/`t_s` and `confirmed_frame`/`confirmed_t_s`): live acts at the
confirmation, analysis cuts at the instant.

**Censored (window / latency)**
A window whose STOP was never met ends at the end of the recording with
`censored = True` (reason `end_of_stream`). A subject that never enters an ROI
inside a window gets the window duration as its latency, with
`latency_censored[roi] = True` — a ceiling, not a measured value. Without a
window, a never-entered ROI keeps latency `None` (legacy).

**Present at start**
`latency_present_at_start[roi] = True` when the subject is already inside the ROI
at the window START (or at `t0` without a window): latency is `0.0` and the entry
count only counts real outside→inside transitions afterwards.

**`7_AnalysisWindow_<base>.json`**
The resolved window next to the trajectory: `spec` and `spec_hash`, `clock`,
`external_events` (Arduino/manual events recorded live), `online` (what the live
runtime decided) and `offline` (what the analysis computed, with input hashes).
`offline` governs the metrics; a divergence of more than one frame from `online`
becomes a report warning. Reused while the rule and the inputs do not change
(`AnalysisWindowService.resolve()`).

**Time base**
fps and duration of a recording, from `analysis/time_base.resolve_time_base()`:
3c heartbeat > frame ledger > unique trajectory timestamps >
`settings.video_processing.fps` (with a report warning). `duracao_video_s` is
`(t_last − t_first) + median_dt` over unique timestamps, not a row count.

## Parquet schema (immutable)

Standard column order in `3_CoordMovimento_*.parquet`:

```text
timestamp, frame, track_id, x1, y1, x2, y2, confidence,
[x_center_px, y_center_px, x_cm, y_cm]?, [uncertainty, bbox_iou]?
```

Calibration columns appear only when calibration exists. Multi-aquarium adds
`uncertainty` (1 - confidence) and `bbox_iou` (tracking stability).

## Architecture

**MVVM-S + DI**
The architectural pattern. Model = state + project + detection; View = Tkinter
UI; ViewModel = `MainViewModel` (orchestrator); Services = business logic;
**S**ervices layer is the addition vs vanilla MVVM.

**EventBusV2 / UIEvents**
The single event bus. `UIEvents` enum in `ui/event_bus_v2.py` lists all events
(~200). Naming convention: `DOMAIN_ACTION_RESULT` (e.g.
`ZONE_AQUARIUM_SELECTED`, `PROCESSING_COMPLETED`).

**StateManager**
Centralized observable state, thread-safe. UI subscribes; ViewModel mutates.

**Coordinator**
A class that owns one cross-cutting concern (video processing, report
generation, multi-aquarium, calibration, …). Decomposed from a former "super
coordinator" — see `coordinators/` (23 files).

**DependencyContainer / LazyRef**
DI container in `core/dependency_container.py`. `LazyRef[T]` resolves circular
references between coordinators that need each other.

**Composition root**
`__main__.py` → `ApplicationBootstrapper` (in `core/application_bootstrapper.py`)
wires every service and coordinator into the `DependencyContainer`. The
**only** place where construction happens; everything else gets dependencies
injected.

## Settings & configuration

**`analysis_interval_frames`**
How often the detector runs (default: 10 → every 10th frame). Lower = more
detections, higher CPU cost.

**`display_interval_frames`**
How often the UI overlay updates (default: 10). Independent from
`analysis_interval_frames`.

**Settings hierarchy**
`config.yaml` (defaults, committed) → `config.local.yaml` (per-machine,
git-ignored) → `ProjectManager.project_data` (per-project overrides).
Pydantic v2 with `extra="forbid"`. **Never import the singleton** — always use
DI: `load_settings()` then inject `settings_obj`.
