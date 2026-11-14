# DRerio LogAI v8.0.0

The any-weight, any-protocol release. Up to 7.2 the program assumed what a
zebrafish experiment looks like: a weight with exactly two classes, an aquarium
and a fish, and an analysis that starts on the first frame where the fish is
seen. v8 drops both assumptions. Any YOLOv8/v11 detection weight works once you
say what each of its classes is, and each recording can have its own **start and
end of analysis**, defined by conditions instead of by the first detection.

The case that drove the release is the **Barnes maze**: a top-down video of a rat
recorded at about 9.9 frames per second with a variable frame interval, where the
experimenter is still in the picture when the recording starts and the rat must
only be measured after the start box is lifted. Every piece of this release was
tested end to end against that case.

> **Version DOI of 8.0.0:**
> [`10.5281/zenodo.24226429`](https://doi.org/10.5281/zenodo.24226429). To cite the
> software in general, use the all-versions DOI
> [`10.5281/zenodo.22650404`](https://doi.org/10.5281/zenodo.22650404).

## Relation to the published results

Unchanged. The validation and benchmark results reported in the associated
manuscripts were produced with release **4.0.0**, available as tag `v4.0.0`,
which remains the version to check out for exact reproduction.

**Some numbers do change in v8**, on purpose, when a report is generated again.
Each change fixes a defect; they are listed in [What changes in the
numbers](#what-changes-in-the-numbers) below.

## Installing this release

Nothing changed in the installation. On Windows, download the source ZIP from
this page, extract it somewhere permanent and double-click `install.bat`. From a
terminal:

```bash
git clone https://github.com/MarkSant/DRerio-LogAI.git && cd DRerio-LogAI
poetry install
poetry run fetch-weights     # trained models, required
poetry run zebtrack
```

**Projects created with 7.2 open as they are.** Nothing you saved is renamed; the
new settings are added with values that reproduce the 7.2 behaviour, and a frozen
7.2.0 project is part of the test suite.

**`fetch-weights` installs the zebrafish weights, as before.** The six weights of
`v7.0.0` are still the ones distributed with the program. A weight for another
species, such as a rat weight for the Barnes maze, is yours: add it to the weight
catalogue (*Global Model Configuration*) and say what each of its classes is, as
described below.

## What changed

### Use a weight with other classes: class roles

Every class of a weight now has a **role**:

| Role | Meaning |
| --- | --- |
| Subject | the animal that is tracked and measured |
| Arena | the apparatus (tank, box, maze); at most one class |
| Context | seen and recorded, never tracked — e.g. the experimenter or a start box |
| Ignored | dropped |

Roles are stored by **class name**, so retraining a weight with one more class
does not shift them. Where you set them:

- **For a weight**, in *Global Model Configuration* → weight catalogue →
  **Class roles…**. Every project that uses the weight gets these roles.
- **For one project**, in the **AI Model Config.** tab. The project's roles are
  tied to the exact weight file; if the weight is replaced or retrained, they are
  ignored and the panel says so.
- **While creating a project**, in the optional *Class roles* section of the
  models step of the wizard.

You rarely have to. A weight whose classes are named like the usual ones
(`fish`, `zebrafish`, `rat`, `mouse`, `animal`, `subject`, `arena`, `tank`,
`maze`…) is resolved automatically, and a zebrafish weight behaves exactly as in
7.2. What changed is the failure mode: **a weight with three or more named
classes and none recognisable as the animal is now refused with a message**,
instead of tracking whatever class sat in position 1. On the Barnes weight
(`arena`, `experimenter`, `rat`, `start_box`), that position was the
experimenter.

Context classes are written, frame by frame, to a new file next to the
trajectory, `3c_Objetos_<video>.parquet`, together with one "heartbeat" row per
processed frame. That is what lets a condition ask "was the experimenter visible
here?" — and lets you change the condition later without detecting again.

The batch worker now loads **the project's** weight. Until 7.2 it always loaded
the default from the settings, so a project set up with a rat weight was
processed with the zebrafish one.

The detection overlay is drawn with the roles **the detector actually used**,
published together with the detections, so what you see on screen is what was
measured. **Wizard templates keep the roles** too, by class name and tied to the
weight they were set for. Applying a template with another weight re-checks the
names, fills in the ones that match and lists the rest; it never falls back to
class positions.

### Define the start and end of the analysis: the analysis window

In the **Zone Configuration** tab, the *Analysis Window (Optional)* panel shows,
in plain words, when the analysis starts and when it stops. **Edit conditions…**
opens an editor where each of the two blocks is a list of lines:

- a class is present or absent (by name, or any class of a role), optionally
  *held for* a number of seconds or frames;
- the subject enters or leaves one of the project's ROIs;
- the video reaches a time or a frame number;
- a number of seconds after the start (stop only);
- an Arduino code, or the manual **Mark start/stop** button of a live session;
- the end of the video (stop only).

Lines are combined with *all of*, *any of (the first one wins)* or *in sequence*.
Two more choices complete the rule: what to do if the start never happens (use
the whole recording, with a warning, or leave the metrics empty) and, in live
sessions, whether the stop only marks the end or also ends the recording.

**The Barnes maze preset** fills in the protocol of the motivating study: the
analysis starts when the start box and the experimenter are gone and the rat is
visible for 5 frames in a row, and stops at the first of end of video, rat absent
for 3 s, **the rat entering the `toca` (escape hole) ROI**, or 240 s after the
start. In the real videos the rat stays visible until the last frame, so without
the escape-hole condition the end was always censored at the end of the video.
If the project has no ROI with that name, the editor warns when the preset is
loaded and when the rule is saved.

How the window is applied:

- **The video is always recorded in full.** Only the metrics are restricted to
  the window, so changing a condition only needs a new analysis.
- Conditions are measured on **the recording's own clock** — the video's
  timestamps for pre-recorded files, the capture instant for live sessions — and
  an event is dated at the **first** frame of the run that satisfied it.
- Rates and percentages use the window's duration. The latency to each ROI is
  counted from the start; an animal already inside at the start gets latency 0
  and is flagged *present at start*; an animal that never enters gets the
  window's duration as a ceiling and is flagged *censored*.
- The computed start and stop are saved next to the trajectory in
  `7_AnalysisWindow_<video>.json` and reused while neither the rule nor the input
  files change.
- The Word report gains an **Analysis Window** section with the cut, the rule,
  the status and the censoring caveat; the `.xlsx` summary gains `window_*`
  columns and, per ROI, `latency_censored_<roi>` and
  `latency_present_at_start_<roi>`, all at the end so no existing column moves.

A project without a window analyses the whole recording, exactly as before.

### Live sessions

The window is evaluated during the session, on the capture clock, and the panel
shows "waiting for the start condition", "window open since X s" or "window
finished at X s". With a window that waits for the Arduino, everything is
recorded from the start and the code only marks where the analysis begins.
Turning on the legacy *External Trigger Mode* together with such a window is
refused with an explanation, because the two read the same signal differently.

Per-ROI Arduino commands are only sent inside the window. And **Arduino code 0
now stops a session started from the Progress grid**; until 7.2 it was routed to
a coordinator that had no recording and was ignored.

The **ad hoc live analysis dialog** (live camera without a project) now has the
same start/end editor, in a compact form and with the Barnes preset. The rule
goes to that session only and never touches the shared settings. A rule that
waits for the Arduino is refused there, with the reason, when no Arduino is
enabled and connected.

**Live sessions with two aquariums** now work end to end. They used to record
no trajectory rows at all. A two-aquarium session now writes one full-frame
video and one frame ledger in the session folder, and one trajectory per
`aquarium_N/`. Each aquarium has its own analysis window, its own ROI commands
and its own overlay. A per-ROI Arduino binding can be limited to one aquarium,
chosen in a new *Aquarium* column of the bindings panel, which only appears when
there are two or more aquariums. Bindings saved in a newly created project are
no longer lost.

**The live timeline is the camera's.** Each sensor frame enters the pipeline
once, with the instant it was read; the analysed frames follow a single cadence;
the MP4 is written at the measured frame rate, not 30. Stopping a session first
writes the frames still queued, and whatever is left is recorded in the ledger
as `dropped_on_stop` instead of disappearing.

### Rodents: behaviour defaults

Behaviour defaults no longer assume a fish in a side-view tank:

- Geotaxis (distance to the bottom) is never computed in a top-down view.
- The thigmotaxis band accepts up to 50 cm; a rat open field uses 10–20 cm.
- The plausible-speed ceiling used by the trajectory validator is a project
  setting, with a new *Maximum speed (cm/s)* field in the wizard, the dialogs and
  the advanced settings tab.
- A built-in wizard template, **Rodent, top view**, fills all three: top-down,
  no geotaxis, a 15 cm thigmotaxis band and a 100 cm/s ceiling. It carries no
  class roles, because no rodent weight ships with the program.

### Tracking

- The tracker uses the recording's real frame rate, and a lost track lives for a
  number of **seconds** on the recording's clock, whatever the frame rate, the
  analysis interval or the frames dropped on the way. Lost tracks found again are
  emitted again, and expired ones leave the association pool.
- Tracker settings changed in the panel, restored from a project or reset to
  factory defaults now reach the tracker; they used to be ignored once the
  detector existed. The Kalman filter predicts with the real detection cadence.
- In multi-aquarium projects, an aquarium with no detection still advances its
  tracker, and each track is recorded with the detection's box, as in
  single-aquarium projects.
- Only the tracks the tracker confirms are recorded. A one-rat Barnes video used
  to come out as a three-animal report; very short glitch tracks next to a longer
  one are now left out of the analysis, with a warning.

### Faster start

torch, Ultralytics and OpenVINO are loaded the first time they are needed instead
of when the program starts; importing the detection package dropped from about
4.5 s to 1 s.

### Removed

The interactive HTML report and the R/Python script export were removed. No
screen or setting ever produced them, and they had defects nobody could see. The
Word report and the Excel summary are unchanged.

### The interface talks about animals and arenas

Model, calibration and dialog texts no longer assume a fish in a tank: "Animal
AI", "Arena AI", calibration examples for zebrafish, rodent open fields and the
Barnes maze. Saved keys and folder names (`aquarium_N/`, `num_aquariums`, the
weight targets) did not change.

The Portuguese catalogue is complete again, and a new test fails whenever a
translatable text is added without being catalogued.

## What changes in the numbers

These are corrections, and each one moves results when a report is generated
again:

| Change | What you will see |
| --- | --- |
| **ROI latency** uses the moment the animal goes from outside to inside | An animal that starts inside an ROI gets latency `0.0` (flagged *present at start*), not an empty value next to an entry count of 1. ROIs entered from outside do not change. |
| **Recording duration** (`video_duration_s`) is measured from the timestamps | It used to count rows: doubled with two tracks, divided by N when processing every N-th frame. Anyone normalising by this column gets different values. |
| **Frame rate** is the recording's own, not the global 30 fps | Every time-based metric of variable-rate or non-30 fps videos changes. On the Barnes videos (~9.9 fps) the error reached 125 s. When no rate can be measured, the configured one is used and the report says so. |
| **Live re-analysis** uses the capture instant from the frame ledger | Times of re-analysed live sessions reflect when each frame was captured, not when it was processed. |
| **Tracking gaps** cut episodes, smoothing, distance and speed | Freezing, inactivity and bursts no longer run across a gap, the hidden time leaves the duration, and the first row after a gap has no speed (a rat hidden for 3 s that reappears 50 cm away no longer counts as moving at 16.7 cm/s). Recordings without gaps do not change. |
| **Frames analysed and temporal coverage** count frames, not rows | With two animals the frame count no longer doubles and coverage no longer exceeds 100 %; with an analysis interval of 10, a recording with no losses has 100 % coverage, not 10 %. |
| **Episodes with more than one animal** are found per animal | Two animals visible at the same time used to break every freezing or burst episode into one-frame pieces. |
| **Rows without a track ID** are not an animal | A multi-animal project no longer gains an extra animal from unconfirmed detections; a one-rat Barnes video is reported as one animal. |
| **Geotaxis in top-down views** is off | Top-down projects no longer report a distance to a "bottom" that does not exist. |
| **The automatic pre-recorded report** reads the project's behaviour settings | It used to ignore them, so the same project produced two different `.xlsx` files. Side-view projects gain filled geotaxis columns and per-zone geotaxis columns; top-down projects report `top_down` and their own thigmotaxis band, and lose the geotaxis plots in the `.docx`. |
| **`processing_offset`** is applied, with the same phase in both flows | With the shipped `config.yaml` (offset 1, interval 10), pre-recorded analysis moves from frames 0, 10, 20… to 1, 11, 21…, and live analysis uses the same phase. Projects that analyse every frame do not change. |
| **Segmentation masks and the standard summary** are measured in the same space as the ROIs | With the `seg_overlap` rule and an arena away from the image origin, time in ROI no longer comes out as 0 s; the standard summary measures ROIs, thigmotaxis and geotaxis against the right arena. |
| **Tracker defaults** come from `config.yaml` | New projects created by the wizard and *Restore factory defaults* use the shipped tracker settings (maximum centre distance 400 px, IoU 0.05, match 0.95). **Existing projects keep the values they saved.** |
| **Multi-aquarium trajectories** record the detection, not the tracker's filtered box | Small changes in distance, speed and ROI membership where the filtered box lagged behind the animal. |
| New report keys and `.xlsx` columns, always present | Extra columns at the end of the table; nothing moves. |
| New `3c_Objetos_` file per video | One more file in each output folder. |

## Known limitations

- **Only zebrafish weights are distributed.** A rodent weight is loaded by hand,
  and its class roles are set by hand. The *Rodent, top view* template therefore
  carries no roles.
- **No Barnes-specific metrics yet**: errors, search strategy and the hole
  template are planned for 8.1 (issue #633). The generic metrics (latency to an
  ROI, counted from the start of the window, time in ROI, distance) already apply.
- **The start rule of the Barnes preset** has not yet been compared with the
  laboratory's manual marks. On the two reference videos the computed start falls
  about 1.5–1.8 s after them.
- **A rat's tail moves the bounding box while the animal is still**, which can
  inflate distance and speed and hide freezing (issue #651, under investigation).

## Full changelog

See [`CHANGELOG.md`](../../CHANGELOG.md) for the complete list with the reasoning
behind each change.
