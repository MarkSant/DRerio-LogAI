# Screenshots

Capture specification for the images referenced by
[`user-guide/GETTING_STARTED.md`](../user-guide/GETTING_STARTED.md).

This file is a note for maintainers and is deliberately **not** published to the
wiki (see `NOT_WIKI_PAGES` in `scripts/build_wiki.py`): as a wiki page it showed
up in the sidebar as "README", next to the user guides.

## Before capturing

**Set the interface to English.** The wiki is written in English, and the
project's own captures so far are in Portuguese:

```bash
ZEBTRACK_LANGUAGE=en poetry run zebtrack
```

`ui.language: en` in `config.local.yaml` does the same thing permanently.

**Use a real project with real data.** Empty and default states make poor
documentation, and several of these panels only exist once a project has
sessions and completed analyses.

**Do not show identifying data.** No real subject IDs from ongoing work, no
paths revealing unpublished directories.

## What is here

Captured 2026-09-07 with the interface in English. Filenames are fixed where
`GETTING_STARTED.md` links to them. "Manuscript" is the panel of the platform
paper's supplementary figures that the same capture serves.

| File | Screen | Manuscript |
|---|---|---|
| `main_window.png` | Launcher: project actions and the detection-model status panel (weights per role, OpenVINO device, hardware) | Fig. S5a |
| `wizard_step1.png` | Project wizard, step **1/7** — project type, folder organisation, existing Parquet files | Fig. S5b |
| `wizard_step2_video.png` | Wizard — video and folder selection | — |
| `wizard_step5_options.png` | Wizard, step **3/7** — physical calibration px→cm, thigmotaxis and geotaxis settings | Fig. S5c |
| `wizard_step4_detection.png` | Wizard, step **5/7** — models and weights per role, OpenVINO device, YOLO and ByteTrack parameters | Fig. S5d |
| `roi_config.png` | Zone Configuration on a pre-recorded project: arena polygon and four ROIs over a real frame, with the inclusion rule | Fig. S6b |
| `analysis_running.png` | Video Analysis mid-run: frame counter, detections, elapsed and estimated time, live overlay with track ID and confidence | Fig. S7-adjacent |
| `heatmap.png` | Occupancy heat map in centimetres, with the density scale | — |
| `trajectory_output.png` | Reconstructed swim trajectory over the arena frame, with the four ROIs | — |
| `project_overview.png` | Project overview: group / day / subject hierarchy with per-video status and metadata | Fig. S6a |
| `live_analysis_dialog.png` | Live wizard, step **3/6** — camera detection, Arduino synchronisation, external trigger, timed recording | Fig. S5e |
| `live_wizard_experimental_design.png` | Live wizard, step 2/6 — experimental design | — |
| `live_session_control.png` | Live session runner: one card per animal, day/group progress, camera and quick actions | Fig. S6c |
| `live_experiment_progress.png` | Experiment Progress grid: day × group, sessions completed per cell | — |
| `roi_config_live_arduino.png` | Zone Configuration on a live project, with the per-zone Arduino binding panel | — |

## Still missing

**A capture of the live preview window itself** — the camera feed with detection
overlay, frame counter and session timer, while a live session records. The
guide's live section currently shows the session runner instead, captioned for
what it is.

**Fig. S6d** as specified ("tracking output rendered on the video with overlaid
zones and trajectory, *alongside run metrics*"): `analysis_running.png` has the
overlay and the metrics but is mid-run on a pre-recorded video, and
`trajectory_output.png` is the generated plot rather than the application.

## Technical requirements

- **Format**: PNG, lossless.
- **Resolution**: native. Do not downscale; the manuscript figures are
  assembled from these and are printed.
- **Framing**: the whole window, or a clean rectangular region. No desktop
  clutter, no overlapping windows, nothing cut off.
- **Legibility**: every label readable at 100%.
