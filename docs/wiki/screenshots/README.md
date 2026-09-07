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

## The ten images

Filenames are fixed: `GETTING_STARTED.md` links to exactly these names. Where a
capture also serves a supplementary figure of the platform manuscript, the panel
is noted — one capture session can serve both.

| File | Screen | Manuscript panel |
|---|---|---|
| `main_window.png` | Launcher, with the project-action buttons and the detection-model status panel below them (active weights per function, OpenVINO device and hardware) | Fig. S5a |
| `wizard_step1.png` | Project wizard, **step 1 of 7** — project type | Fig. S5b |
| `wizard_step2_video.png` | Wizard, video/folder selection, with the preview tree summarising the detected structure | — |
| `roi_config.png` | Zone and ROI definition drawn on a real acquired frame, with the arena boundary and the ROI list | Fig. S6b |
| `wizard_step4_detection.png` | Wizard, **step 5 of 7** — detection and tracking: YOLO weights per function, OpenVINO device, ByteTrack association parameters | Fig. S5d |
| `wizard_step5_options.png` | Wizard, **step 3 of 7** — physical calibration (pixels per centimetre from the arena dimensions) with the behavioural-analysis settings | Fig. S5c |
| `analysis_running.png` | Batch panel with pending videos, progress, and the buttons that run processing and generate reports | Fig. S7 |
| `heatmap.png` | Spatial occupancy heat map over the arena, with the ROI overlay | — |
| `live_analysis_dialog.png` | Live analysis dialog: camera, experiment identification, real aquarium width and height, session duration, optional Arduino | Fig. S5e |
| `live_preview.png` | Live session in progress: camera feed with detection overlay, frame counter, measured FPS, session timer | Fig. S6c |

> The wizard is **dynamic**: 7 steps for pre-recorded projects, 6 for live. Step
> numbers above are the pre-recorded branch, matching the manuscript captions.
> The filenames `wizard_step4_*` and `wizard_step5_*` predate that and no longer
> match the step they show — they are kept because `GETTING_STARTED.md` links to
> them, and renaming buys nothing.

## Two extra captures the manuscript needs

Not referenced by the wiki, but part of the same session:

| Screen | Manuscript panel |
|---|---|
| Project overview: sessions, subjects, per-video processing status | Fig. S6a |
| Tracking output rendered on the video, zones and trajectory overlaid, with the run metrics | Fig. S6d |

Twelve captures in total cover both the wiki and Figures S5–S7.

## Technical requirements

- **Format**: PNG, lossless.
- **Resolution**: native. Do not downscale; the manuscript figures are
  assembled from these and are printed.
- **Framing**: the whole window, or a clean rectangular region. No desktop
  clutter, no overlapping windows, nothing cut off.
- **Legibility**: every label readable at 100%.
