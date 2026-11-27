# Barnes maze (rats)

User guide for the Barnes-maze protocol introduced in version 8.1 (#633). Technical details live
in [`docs/tasks/v8.1/barnes/`](../../tasks/v8.1/barnes/). Portuguese version:
[Labirinto de Barnes](LABIRINTO_BARNES.md).

## 1. Create the project

1. In the project wizard's first step, open **Experiment Profile** and choose **Animal model:
   Rodent (rat or mouse)** and **Protocol: Barnes maze (rodents)**, or load the built-in
   **Barnes maze (rat)** template.
2. Barnes fixes the top-down view, analyses every frame (`analysis_interval_frames = 1`) and sets
   the analysis window to the Barnes preset v2.
3. In **Calibration**, enter the **Table diameter (cm)** (default 184 cm); it is used for both
   width and height.
4. Pick the rat detection weight. It needs the classes `arena`, `experimenter`, `rat` and
   `start_box` with their roles set (arena, context, subject, context).

For a single video or an ad-hoc live session, the same two fields appear in the configuration
dialog.

## 2. Draw the arena with the Barnes assistant

The **Barnes assistant** button in the **Zones** tab appears only in Barnes projects.

1. **Table:** **Detect table (auto)** uses the weight's `arena` class; otherwise click 5 or more
   points on the table rim.
2. **Escape hole:** click the hole the rat can enter (**Click the escape hole**). The app places
   the holes around the table, snaps each one to the real dark hole and shows a preview.
3. **Hole count:** the assistant tries 18 and 20 and shows "detected: N · project: M". The lab's
   current table has 18. If the detected count differs from the project's, it asks before
   changing it.
4. **Trial type:** **Training** or **Probe**, per video.
5. **Apply.** It creates the arena, the `quadrante_alvo` ROI (the slice with the escape hole and
   two holes on each side), the `toca` ROI and one ROI per decoy hole, named by its distance from
   the escape hole (`buraco_+01`, `buraco_-01`, …, `buraco_oposto`; positive = clockwise).
6. **Apply to other videos…** copies the layout and re-snaps it on each video. For working-memory
   trials, where the escape hole moves daily, click each video's escape hole. A doubtful copy goes
   to manual review, and a video framed differently is not written.

Do not rename these ROIs: the names are what the metrics read.

## 3. How encounter and entry are decided

- **Start:** the start box and the experimenter leave the view and the rat is visible.
- **Encounter (nose poke):** the first frame where the rat covers part of the escape hole's disk.
- **Entry (four paws):** the rat is mostly over the escape hole and visibly smaller than during
  the rest of the trial (part of the body already in the hole) for half a second, or it vanishes
  with its last position in the hole. Without an entry, the latency is 240 s, marked censored.

The analysis window closes at the entry, not at the first touch. A window created before 8.1 (v1)
still works; in the window editor, **Update to Barnes preset v2…** explains what changes before
switching.

## 4. Results

- **Individual report (`.docx`):** the Barnes section lists the latencies (censored ones read
  "≥ 240 s"), primary, total and perseverative errors, the search strategy, the time in the
  target quadrant and, for probe trials, the first-hole score, first-error latency and attempts.
  It includes a hole diagram with the visit order and the numbered trajectory.
- **Spreadsheet (`.xlsx`):** `barnes_*` columns and a `barnes_visits` sheet with the visit
  sequence.
- **Partial and unified reports:** learning curves per group and day (mean ± SEM), strategy
  distribution and probe comparison. Censored latencies are counted separately.
- **Correct the strategy:** right-click the video in the reports tree and pick the strategy. The
  report marks it as "manually corrected"; regenerate the report afterwards.

## 5. Calibrate against manual scoring

The visit and entry thresholds are provisional until they are compared with the lab's manual
scoring. The step-by-step guide, including what to export from the spreadsheets, is
[`VALIDATION.md`](../../tasks/v8.1/barnes/VALIDATION.md). Start with:

```bash
python scripts/barnes_validation.py init-mapping --out mapping.yaml
```

## 6. Known limits

- One trial per video.
- One arena with one animal (multi-aquarium is not supported for Barnes).
- When the detection box includes the tail, the entry may be detected late or not at all.
- The rodent defaults (freezing 2.0 cm/s for 1.0 s) are provisional.
