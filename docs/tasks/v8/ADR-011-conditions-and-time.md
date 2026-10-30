# ADR-011: Condition engine, time semantics and the analysis-window artifact

**Status:** Accepted · **Date:** 2026-10-30 · **Version:** 8.0.0

## Context

Users need START/STOP conditions for the analysis (Barnes: start when `start_box` and
`experimenter` are absent and `rat` present for k frames; stop at the first of end-of-video,
`rat` absent for S s, or 240 s after start). The audit ([AUDIT](AUDIT.md) §2) showed that the
current notion of time is unreliable: reports use a global 30 fps, `duracao_video_s` counts rows,
latency starts at the first detection and treats exits as entries, and the live `timestamp` is a
processing clock.

## Decision

### Engine — pure package `core/conditions/`

- `model.py`: Pydantic v2 AST, discriminated by `kind`, two families.
  - **Level** (true/false per frame): `ClassPresence(target={class|role}, present, min_count,
    min_confidence)`, `RoiInside(roi, state)`, `Not`, `AllOfLevel`, `AnyOfLevel`.
  - **Trigger** (fires once, at an instant): `Persist(level, hold=seconds|frames, max_gap_s)`,
    `RoiEdge(roi, edge)`, `TimeReached(clock, at)`, `FrameReached(frame)`,
    `Delay(after="start"|trigger, seconds)`, `External(source=arduino|manual, code)`,
    `EndOfStream`, `FirstOf`, `AllOf` (instant = last child), `Sequence(children, within_s)`.
  - `WindowSpec(version=1, start, stop, on_start_not_met="whole_recording",
    on_stop="mark"|"end_session")`. `start=None` = first processed frame (today's behaviour).
    Validators reject `Delay(after="start")` and `EndOfStream` inside `start`.
- `evaluator.py`: `ConditionEvaluator(spec).step(FrameObservation) -> list[WindowEvent]` and
  `finish()`. Batch mode `evaluate_window(spec, observations)` is a fold over `step` — one
  implementation, so online ≡ batch is a testable property.
- **Persistence** is measured on the event clock in seconds (frames allowed, seconds
  recommended). A run starts at the first true frame `(frame0, t0)`; gaps larger than
  `max_gap_s` (default 3 × median dt) reset it; the fired event is **back-dated to
  `(frame0, t0)`**.
- **Never satisfied.** START never met → `status="start_not_met"`; metrics use the **whole
  recording** with a warning in the report and xlsx (user decision). STOP never met →
  `EndOfStream`, `censored=True`.
- No re-arming in v8: the first window wins. Multi-aquarium: one evaluator per `aquarium_id`.

### Clocks

| Pipeline | Event clock | Frame key |
|---|---|---|
| pre-recorded | PTS (`timestamp = POS_MSEC/1000`) | `frame` (0-based, `i % N == 0`) |
| live | `t_capture_perf − anchor.t0_perf` from `6_FrameLedger` | `pipeline_frame == frame` |

Live `timestamp` (processing clock) is never used to date anything. `retime_from_ledger()`
replaces the index **in memory** for analysis; the Parquet is untouched.

`analysis/time_base.resolve_time_base()` picks fps/duration from, in order: `3c` heartbeat >
ledger > unique trajectory timestamps > `CAP_PROP_FPS` stored on the video entry >
`settings.video_processing.fps` (warned). `duracao_video_s = (t_last − t_first) + median_dt`
over unique timestamps; new `duracao_janela_s`.

### Analysis

- `AnalysisService.run_full_analysis(window=None)`: smoothing, velocity and ROI debounce run on
  the **whole** frame; then `restrict_to_window(t_start, t_end)` cuts with the absolute index
  kept. Denominators become STOP − START. `report["janela_analise"]` always exists
  (`status="none"` without a window) so the unified report schema never mismatches.
- Latency: rising edge `cur & ~prev.shift(fill_value=False)` (fixes the XOR), explicit `t0`.
  - Subject already inside an inner ROI at START → latency 0, `present_at_start=True`; entry
    count only counts real outside→inside transitions after START.
  - The arena never yields entry/latency metrics; "subject in arena" is a condition only.
  - Censored latency → the window duration (e.g. 240 s) plus `latency_censored=True`.
- Freezing episodes cut by a window edge are truncated; `min_duration` applies to what remains.
- The metrics cache key includes `spec_hash` and the window bounds.

### Artifact — `7_AnalysisWindow_<base>.json` (next to the trajectory)

```json
{"schema": "zebtrack.analysis_window/1", "spec": {}, "spec_hash": "sha256:…",
 "clock": "pts|capture_perf", "fps_video": 9.9, "aquarium_id": null,
 "external_events": [{"t_s": 3.2, "source": "arduino", "code": 1}],
 "online": {"start": {}, "stop": {}},
 "offline": {"start": {"frame": 67, "t_s": 6.71},
             "stop": {"frame": 1840, "t_s": 186.0, "reason": "persist|max_duration|end_of_stream"},
             "status": "complete|start_not_met|censored|inputs_missing",
             "inputs": {"trajectory_sha": "…", "objects_sha": "…"}}}
```

`AnalysisWindowService.resolve()` reuses `offline` when `spec_hash` and input hashes match,
otherwise recomputes from `3c` + trajectory + ledger + recorded external events and rewrites
atomically. **`offline` governs analysis**; `online` only drives display and session end. A
divergence > 1 frame becomes a report warning.

### Live integration and the external-trigger gate

`ConditionRuntime` runs in `frame_processing_pipeline.py` just before
`_dispatch_arduino_zone_commands`; Arduino/manual events enter a `SimpleQueue` stamped with
`perf_counter` at read time. `decide_external_trigger` stays the single rule:

| Situation | Decision |
|---|---|
| legacy `external_trigger_mode=True` | `ARM_AND_WAIT` (unchanged) |
| window spec with `External(arduino)` and no `use_arduino` | `REJECT_NO_ARDUINO` |
| same, port offline | `REJECT_ARDUINO_OFFLINE` |
| same, Arduino ready | `PROCEED` — record everything; the code becomes an engine event |
| both configured | invalid |

`on_stop="end_session"` stops through `finish_session_early()` (`keep_data=True`), bypassing the
50 % heuristic; the Arduino exit sweep runs at window STOP.

## Consequences

- Recording is always complete (user decision 1); changing a condition only needs re-analysis.
- Deliberate number changes are listed in [ADR-013](ADR-013-zebrafish-compatibility.md).
