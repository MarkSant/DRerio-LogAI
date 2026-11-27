# Plan — Barnes maze end to end (#633) and the experiment profile

**Approved:** 2026-11-19 by the maintainer · **Contracts:** [CONTRACTS.md](CONTRACTS.md) ·
**Decision record:** [ADR-014](../ADR-014-experiment-profile-and-protocols.md).

Where this plan and `CONTRACTS.md` differ, `CONTRACTS.md` wins: it was written after reading the
code and records three deliberate refinements (see "Deviations" at the end).

## Context

DRerio LogAI was born for zebrafish in aquariums. Since v8 it runs any YOLO weight through class
roles, but the transition is incomplete.

**What already exists for the Barnes maze:**

- the analysis-window preset `barnes_maze_preset` (`core/conditions/presets.py`);
- a `toca` ROI drawn by hand;
- the generic trajectory and ROI metrics.

**What issue #633 asks** (protocol of the FMB-UNESP lab):

- **encounter** latency (nose poke) × **entry** latency (four paws in);
- primary and total errors;
- search strategy (direct / serial / random);
- probe metrics;
- a hole template.

**Findings:**

- No species or protocol concept exists in `project_data`.
- A ROI is only a polygon in raw pixels, with no attributes; `ZoneData.metadata` is lost by the
  parquet, templates and `apply_template`.
- The current preset closes the window at the first TOUCH of the escape hole (`RoiEdge` with
  `bbox_intersects`), so the encounter → entry interval falls outside the window.
- The rat weight (`best_det_topdown_rat_v2`: `arena, experimenter, rat, start_box`) is
  detection-only; the videos are ~640×428 at ~9.9 fps, variable frame rate.
- `run_full_analysis` is the single funnel of the analysis entry points; `behavioral_config`
  already reaches all of them. There is no reporter registry.
- 169 UI msgids mention aquarium/fish; the `aquarium_*` keys are persistence contracts (ADR-012).

**User decisions:**

- **20 holes** evenly spaced on the rim; after the click on the escape hole, the target quadrant is
  the escape hole ± 2 holes on each side (5 holes, 90°).
- **Two fields** at creation time: animal model + protocol.
- Entry detection: **bbox heuristic now, a pose weight later**.
- Search strategy: **automatic, with manual correction**.
- **Execution delegated to sub-sessions in worktrees**, with the originating conversation as hub.

## Part I — Architecture

### 0. Experiment profile

- New keys in `behavioral_config`: `animal_model ∈ {zebrafish, rodent, other}`,
  `protocol ∈ {generic, barnes}`, `protocol_params.barnes` (`BarnesParams`). Absent keys =
  `generic` + `zebrafish`: legacy outputs unchanged.
- One reader: `core/services/experiment_profile.resolve_experiment_profile()`.
- Protocol registry `analysis/protocols/` (`ProtocolSpec`): forced animal model, zone assistant,
  window preset factory, `compute_metrics`, tidy columns, report sections, suppressed generic
  sections. `generic` is a no-op. `report["protocol_metrics"]` is always present
  (`{"status": "none"}` for generic).
- UI: Discovery step of the wizard and `BehavioralConfigWidget` (shared by the Calibration step,
  `LiveAnalysisDialog` and `SingleVideoConfigDialog`). Barnes locks rodent, top-down,
  `analysis_interval_frames=1`, the Barnes preset, and turns Calibration into one "Table diameter
  (cm)" field. `BehavioralAnalysisData` gains real fields. New template
  `resources/wizard_templates/barnes_maze.json`. Per-animal defaults in `behavioral_policy`.

### 1. Barnes arena assistant

- Pure geometry in `core/detection/barnes_geometry.py`:
  - **table ellipse** from the `arena` class box (existing auto-detection) or from 5+ rim clicks
    fitted with `cv2.fitEllipse`;
  - **hole ring**: the click on the escape hole sets the ring radius and phase; 20 holes every
    18° in the ellipse's unit-circle frame;
  - **snapping**: on the median of ~30 frames (rat and experimenter vanish), find the dark blob
    nearest each predicted hole, then refit the ellipse through the 20 snapped centres (corrects
    the perspective); per-hole residual and "not found" flag.
- ROIs as dense polygons in raw pixels: elliptical arena, `quadrante_alvo` (90° sector), `toca`,
  19 decoys named by their offset from the escape hole (clockwise positive), so columns compare
  across days when the escape hole moves (working-memory protocol). Quadrant first, holes after;
  dilation below half the spacing; `metadata["barnes_layout"]` is only a cache.
- UI: `ui/dialogs/barnes_layout_dialog.py`, opened from `zone_controls.py` only for Barnes:
  1. adjust the ellipse;
  2. click the escape hole;
  3. check the preview with snapping;
  4. adjust (drag a hole, rotate the ring);
  5. choose `training` or `probe` per video;
  6. apply.

  Written through `set_main_arena_polygon` / `add_roi_polygon`; "apply to other videos" re-snaps
  on each video.

### 2. Encounter × entry (heuristic)

- **Visit (nose poke):** the bbox covers ≥ `c` of the hole disk (0.3) for ≥ 2 frames; ends after
  ≥ 3 frames below; optional slowdown filter.
- **Encounter:** first visit to `toca`.
- **Entry**, back-dated, whichever happens first:
  - **(a) over the hole and small:** for ≥ 0.5 s, ≥ 50 % of the visible bbox is inside the
    dilated `toca` AND its area is ≤ θ = 0.35 of the rat's running median area since START;
  - **(b) vanished into the hole:** the rat disappears for `absent_s` with its last position in
    `toca`.

  No entry → 240 s, censored. Risk: the tail inflating the bbox (#651); confidence drop as an
  auxiliary cue; thresholds calibrated in section 5.
- Engine changes, one evaluator (ADR-011): `FrameObservation` gains `subject_area_px` and
  `subject_cover` from one helper `core/conditions/subject_geometry.py` used by both observation
  builders; new levels `SubjectOverRoi`, `SubjectVisibleFraction`, `LastSeenIn`; preset v2 STOP
  `FirstOf(EndOfStream, entry, Delay 240 s)` with reason `burrow_entry`; preset v1 stays, the
  editor offers the update explicitly.

### 3. Barnes metrics

Package `analysis/protocols/barnes/` (`layout`, `visits`, `metrics`, `strategy`). Layout rebuilt
from ROI names and centroids.

- **Training:** encounter and entry latencies (censoring), primary / total / perseverative errors,
  path lengths, time in the target quadrant, visit sequence, visits per distance (0–10).
- **Probe:** offset and score of the first hole (`min(d+1, 10)`, to confirm with the lab), latency
  of the first error, attempts until the target.
- **Strategy** (explainable, features exposed): direct (≤ 3 errors before the target, no centre
  crossing); serial (≥ ⅔ adjacent transitions, |Δ| ≤ 2, ≤ 1 crossing); random otherwise. Manual
  correction per video; the report says automatic or corrected.
- Multi-aquarium refused with a warning; one trial per video.

### 4. Reports

- Tidy `barnes_*` columns appended after `window_*` (English names); generic projects unchanged.
- Individual Word: Barnes section, polar diagram of the 20 holes, trajectory with numbered visits;
  fish figures suppressed via `ProtocolSpec`. Excel: one sheet with the visit sequence.
- Partial and unified: learning curves (group × day, mean ± SEM), strategy distribution, probe
  comparison. `project_reporter.py` gets its metric list from the `ProtocolSpec`.

### 5. Validation against the lab

`scripts/barnes_validation.py` compares the lab's exported sheets (latencies, strategy, probe) with
the unified report: Bland–Altman and ICC for latencies, agreement for errors, Cohen's κ for
strategy; calibrates `c`, `θ`, `h` and the centre radius on a subset and reports on held-out
videos; checks START against the manual marks.

### 6. Interface vocabulary per animal

`ui/terminology.py` with `term(key, animal_model)`, resolved at call time; no persisted key
changes; precedent `global_model_configuration_panel.py:31`.

### Future (out of this delivery)

A pose weight as `animal_method="pose"`: the nose marks the encounter, the tail base the entry.

## Part II — Orchestration: hub + sub-sessions

### Hub role

The hub (the originating conversation) writes no product code. It:

- launches the sessions and receives their reports;
- reviews each diff: a `pr-review-toolkit:code-reviewer` subagent (Sonnet), the
  `git diff <hub>...<branch> --stat` against the session's owned files, and the session's tests
  run in the hub worktree after `source scripts/wt-env.sh`;
- asks the user before every merge into the integration branch and merges;
- releases the dependents and keeps the progress board;
- alone changes `CONTRACTS.md`: a session that needs a contract change stops and reports; the hub
  decides and tells the affected sessions with `SendMessage`.

### Branches and worktrees

- Integration branch: `claude/barnes-maze-arena-automation-68f138`. Each session starts with
  `use_worktree: true` and `source_branch` = that branch (the default would be `main`, without
  the contracts), on its own branch.
- Inside a session: commits on its own branch only. Never push, PR, merge, `--no-verify` or an
  untagged `git stash`. `source scripts/wt-env.sh` before any gate.
- At the end, one PR from the integration branch to `main`, opened by the hub with the user's
  approval (split per stage if the mutation check cannot cope with the diff).

### Shared artefacts

See `CONTRACTS.md` §10. In short: each session appends its own i18n entries to the `.pot`/`.po`
by hand and recompiles the `.mo` (never `update_translations.py`); mutation blocks at the end of
the catalogue under its own header; hub-only files listed there. Four concurrent sessions: run the
domain's tests first, the fast suite once at the end, the mutation check with `--jobs 2`.

### Stages and sessions

| Stage | Session (`name` / branch) | Model · effort | Depends on | Owns (exclusively) |
|---|---|---|---|---|
| 0 | `barnes-contracts` (fork of the hub) | Opus 5.5 | — | this PLAN, `CONTRACTS.md`, ADR-014, `core/services/experiment_profile.py`, `analysis/protocols/{__init__,base,registry}.py`, `analysis/protocols/barnes/{__init__,contract}.py`, the `protocol_metrics` hook and the `protocol_inputs` plumbing, their tests, the rule-c scan |
| 1 | `exp-profile` | Sonnet 5.5 · high | 0 | `ui/wizard/{discovery_step,calibration_step,models,templates}.py`; `ui/components/behavioral_config_widget.py`; `ui/dialogs/{live_analysis_dialog,single_video_config_dialog}.py` (field wiring only); `analysis/behavioral_policy.py`; `core/project/project_lifecycle_manager.py` (persistence); `resources/wizard_templates/barnes_maze.json` |
| 1 | `barnes-arena` | Opus 5.5 · high | 0 | `core/detection/barnes_geometry.py`; `ui/dialogs/barnes_layout_dialog.py`; `ui/components/zone_controls.py`; `ui/event_bus_v2.py`; `ui/components/event_dispatcher.py`; wiring in `coordinators/multi_aquarium_coordinator.py` if needed |
| 1 | `barnes-entry` | Opus 5.5 · high | 0 | `core/conditions/{evaluator,model,presets,subject_geometry,artifact}.py`; `analysis/window_observations.py`; `core/recording/condition_runtime.py`; `ui/components/analysis_window_panel.py` (new nodes, "update preset") |
| 1 | `barnes-metrics` | Opus 5.5 · high | 0 | `analysis/protocols/barnes/{layout,visits,metrics,strategy,spec}.py`; the Barnes line in `registry._builtin_specs()`; scripted-trajectory tests |
| 2 | `barnes-reports` | Sonnet 5.5 · high | `metrics` and `arena` merged | `analysis/data_transformer.py`; `analysis/reporters/*`; `analysis/visualization_generator.py`; `coordinators/_unified_report_mixin.py`; `ui/dialogs/block_detail_dialog.py`; strategy-correction UI (`ui/components/project_views/report_tree_builder.py` + new event) |
| 2 | `barnes-validation` | Sonnet 5.5 · medium | `metrics` merged | `scripts/barnes_validation.py`; `tests/scripts/test_barnes_validation.py`; `docs/tasks/v8.1/barnes/VALIDATION.md` |
| 3 | `animal-terms` | Sonnet 5.5 · medium | `exp-profile`, `arena`, `reports` merged | `ui/terminology.py` and the label changes in UI and report files (sequential: touches earlier stages' files) |
| 4 | hub | — | all | i18n regeneration if needed, TEST_MAP, CHANGELOG, docs/wiki, full gates, real video, PR to `main`, update #633 |

**Why stage 1 is safe in parallel:**

- the file sets are disjoint;
- everyone imports the same names and types from stage 0's `contract.py`;
- nobody but stage 0 touches `analysis_service.py`;
- `barnes-metrics` tests against synthetic `WindowResolution`s with the `burrow_entry` reason from
  the contract, so it does not wait for `barnes-entry`.

**Integration hooks:**

- `barnes-reports` may start against the `protocol_metrics` schema before `metrics` merges, but
  merges after it.
- After `barnes-entry` merges, the hub asks `barnes-metrics` to wire `BARNES_SPEC.window_preset`
  to `barnes_maze_preset_v2`.

### Session brief template (`fresh` context)

Each session's prompt contains:

1. **The front's goal** and the matching section of Part I.
2. **Required reading first:** this file and `CONTRACTS.md`.
3. **The owned files.** Anything else is off limits; if needed, stop and report.
4. **Repository protocol:**
   - `source scripts/wt-env.sh`;
   - `python scripts/impact_analyzer.py` before each change;
   - English strings wrapped in `_()`;
   - no placeholders.
5. **Done means:**
   - new tests for the domain;
   - fast suite green;
   - `pytest -m gui -n0` when there is UI;
   - `ruff`;
   - `mypy .`;
   - `mutation_check.py --changed-since <hub-branch> --jobs 2` with no survivors;
   - the four `test_flow_e2e_*` and the v7.2 golden green.
6. **Final report** (what reaches the hub):
   - branch and commits;
   - files touched;
   - every test command with its result;
   - deviations from the contract;
   - open questions;
   - what the hub must add to TEST_MAP, CHANGELOG or docs.

`background` summarises the user's decisions and the map of the other fronts, so each session
knows what is NOT its job.

### Hub loop

1. **Stage 0:** fork `barnes-contracts`; review; ask to merge; merge.
2. **Stage 1:** start the four sessions together (`user_asked`, `fresh`,
   `source_branch` = hub branch).
3. **On each report:**
   - check the report against the diff;
   - run the review;
   - answer with `SendMessage` (fixes) or ask the user to merge.
4. **Stage-1 merges** in the order `metrics`, `arena`, `entry`, `exp-profile`; expected conflicts
   only in the catalogue/i18n appends; fast suite in the hub after each merge.
5. **Stage 2:** `barnes-reports` and `barnes-validation`. The user provides the three exported
   sheets and the reference videos.
6. **Stage 3:** `animal-terms`.
7. **Stage 4:** final integration in the hub.

**Pending on the user:**

- approve each merge;
- export the lab's sheets (latencies, strategy, probe) with the matching videos;
- confirm the probe-score formula with the lab.

## Verification (stage 4, in the hub)

- **Gates:** `pytest -q`; `pytest -m gui -n0`; `mutation_check.py --changed-since origin/main`;
  `ruff`, `mypy .`, `bandit`, `run_pip_audit.py`.
- **Regression:** the four `tests/integration/test_flow_e2e_*`; v7.2 golden and the
  `project_7_2_0` fixture; `test_no_orphan_ui_events`; the import-time translation test.
- **Synthetic end to end:** extend `tests/helpers/prerecorded_pipeline.py` and
  `tests/integration/test_barnes_window_e2e.py` with the 20-hole layout and a scripted rat (+3,
  +2, `toca`, shrinks, vanishes); assert latencies, errors, strategy, `barnes_*` columns, the
  `.docx` section and the visits sheet.
- **Real video:** `Desktop/Anchieta_ratos/VideosNovos` with the v2 weight; check snapping and
  events by eye, then `barnes_validation.py` against the sheets.

## Deviations (recorded in CONTRACTS.md)

1. **Per-video data** lives in `video_entry["protocol_inputs"]["barnes"]` (`trial_type`,
   `strategy_override`) instead of `video_entry["barnes_overrides"]["strategy"]`: one generic,
   protocol-keyed place, read and written through `analysis/protocols/base.py`, plumbed into
   `run_full_analysis(protocol_inputs=...)` in stage 0.
2. **The visits sheet** is `barnes_visits` (English, ADR-012) instead of `barnes_visitas`. The ROI
   names stay Portuguese (`toca` precedent, lab-facing data).
3. **i18n rule:** the plan said sessions would not touch the catalogue; the repository's tests
   require every new msgid in the `.pot` and every pair in the `.po`, so each session appends its
   own entries by hand (`CONTRACTS.md` §10).
4. **Dead-code guard:** the contract is published before its callers, which vulture reads as
   dead code. Those names sit in a temporary `[contract-ahead]` section of
   `tests/quality/vulture_whitelist.txt` that empties itself: each entry goes stale, and must be
   deleted, when the front that calls it lands (`CONTRACTS.md` §10).
