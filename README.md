<div align="center">
  <img src="src/zebtrack/ui/assets/logo_readme.png" alt="DRerio LogAI Logo" width="400"/>

# DRerio LogAI

**Intelligent Tracking and Behavioral Analysis Platform for _Danio rerio_ (Zebrafish)**

![Version](https://img.shields.io/badge/version-7.1.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.12%2B-yellow.svg)
![License](https://img.shields.io/badge/license-MIT%20%2B%20AGPL--3.0--or--later%20effective-lightgrey.svg)
![INPI](https://img.shields.io/badge/INPI-BR%2051%202026%20005215--7-blueviolet.svg)
<!-- DOI badge is a static shields.io image on purpose. zenodo.org/badge/... is rate-limited
     (120 req/min) and sent with no-cache, so GitHub's shared image proxy intermittently gets
     HTTP 429 and renders a broken icon. The DOI text never changes, so nothing is lost. -->
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.22650404-1682D4.svg)](https://doi.org/10.5281/zenodo.22650404)
[![CI](https://github.com/MarkSant/DRerio-LogAI/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/MarkSant/DRerio-LogAI/actions/workflows/ci.yml)
[![Codecov](https://codecov.io/gh/MarkSant/DRerio-LogAI/branch/main/graph/badge.svg?token=XH937YKEOU)](https://codecov.io/gh/MarkSant/DRerio-LogAI)

**🇧🇷 [Ler em Português](README.pt-BR.md)**

[Install](#-installation) · [First run](#-first-run-what-you-will-see) ·
[Your first project](#-your-first-project) · [Documentation](docs/INDEX.md) ·
[What's new](docs/releases/INDEX.md)

</div>

---

## Contents

- [What it is](#-what-it-is)
- [What it does](#-what-it-does)
- [What it looks like](#-what-it-looks-like)
- [Who uses it](#-who-uses-it)
- [Installation](#-installation)
- [First run: what you will see](#-first-run-what-you-will-see)
- [Detector models and OpenVINO](#-detector-models-and-openvino)
- [Your first project](#-your-first-project)
- [The project window, tab by tab](#-the-project-window-tab-by-tab)
- [Settings and parameters](#-settings-and-parameters)
- [What you get out](#-what-you-get-out)
- [Behavioural metrics](#-behavioural-metrics)
- [When something goes wrong](#-when-something-goes-wrong)
- [What's new](#-whats-new)
- [Citation](#-citation)
- [Ownership, registration and licence](#-ownership-registration-and-licence)
- [For developers](#-for-developers)

## 📋 What it is

**DRerio LogAI** is a complete, open-source application for automated behavioural analysis of
zebrafish (_Danio rerio_). It detects and tracks the animals in a video — or live, straight from a
camera — and turns their movement into the measurements a behavioural experiment actually reports:
distance travelled, speed, time in each region of the aquarium, immobility, thigmotaxis, geotaxis.

It is a **desktop application with a graphical interface**. Nothing here is programmed, scripted or
typed into a terminal: projects, zones, models and parameters are all chosen in windows and dialogs.

Zebrafish are used across neuroscience, pharmacology and toxicology, and analysing their behaviour
by hand is slow (hours of work per minutes of video), subjective (observers disagree) and limited
(a person cannot follow several animals at once). This platform replaces that with an automated,
objective and repeatable measurement, keeping every parameter alongside the data so a result can be
reproduced later.

**It runs on an ordinary computer.** There is no requirement for an NVIDIA graphics card: on Intel
machines the models run through OpenVINO, on the CPU, the integrated graphics or the NPU.

## ✨ What it does

- **🤖 Detection and tracking** — Ultralytics YOLO models (bounding boxes or segmentation masks),
  with multi-object tracking through ByteTrack and ID retention across brief occlusions.
- **🐟 One animal or many**, in one aquarium or several filmed side by side in the same video
  (multi-aquarium), analysed in parallel or one at a time.
- **📹 Pre-recorded video and live camera.** A live project records and analyses the session at the
  same time, per animal, per day, per group.
- **🎯 Arenas and regions of interest** drawn on a real frame of your own recording, with four
  inclusion rules, templates for reuse, and automatic arena detection.
- **📏 Real-world units.** Aquarium dimensions in centimetres turn pixels into cm, so distances and
  speeds are reported in cm and cm/s.
- **📊 Scientific metrics** — locomotion, angular velocity, behavioural episodes, thigmotaxis,
  geotaxis (novel tank test), ROI occupancy and per-animal tables.
- **🔌 Closed-loop hardware.** An Arduino can be triggered by ROI entry and exit, or can itself
  trigger the start of a recording, with the frame→actuation latency logged.
- **📦 Standard outputs** — Parquet (raw trajectories), Excel (metrics) and Word (illustrated
  report), plus a unified report across the whole project.
- **🔬 Reproducibility.** Every configuration is stored with the data, the trajectory schema is
  immutable, and the release is archived with a DOI.

## 📸 What it looks like

The launcher reports which detection weights are loaded and whether OpenVINO is active, before any
analysis runs:

![DRerio LogAI launcher, with the detection-model status panel](docs/wiki/screenshots/main_window.png)

Zones and regions of interest are drawn directly on a frame from the real recording, so the
analysis geometry is set against the actual arena:

![Zone and ROI configuration over an acquired frame](docs/wiki/screenshots/roi_config.png)

Every session yields a reconstructed trajectory and an occupancy heat map in centimetres, with no
manual post-processing:

![Swim trajectory with the four operator-defined ROIs](docs/wiki/screenshots/trajectory_output.png)

More screens, step by step, in the [user guide](docs/wiki/user-guide/GETTING_STARTED.md).

## 🎓 Who uses it

- **Pharmacology** — drug screening (cannabidiol, anxiolytics, antidepressants), dose–response
  designs across groups and days.
- **Toxicology** — environmental toxicity, behavioural endpoints after exposure.
- **Neuroscience** — anxiety-like behaviour (novel tank test, light/dark), memory and learning.
- **Genetics** — phenotyping of mutants and transgenics.
- **Methods work** — closed-loop stimulation, latency characterisation, multi-animal tracking.

## 📥 Installation

### What your computer needs

| Component | Minimum                  | Recommended                           |
| --------- | ------------------------ | ------------------------------------- |
| Python    | 3.12                     | 3.12 (3.13 works; **3.14 does not**)  |
| Disk      | 3 GB free                | 5 GB+                                 |
| RAM       | 8 GB                     | 16 GB+                                |
| CPU       | Dual-core                | Quad-core+ (Intel Core Ultra for NPU) |
| GPU       | Not required             | Intel Core Ultra NPU via OpenVINO     |
| OS        | Windows 10, Linux, macOS | Windows 11 (where it is validated)    |

**No compiler is needed** — every dependency installs from a prebuilt wheel.

**Disk space is the requirement that surprises people.** PyTorch, OpenVINO, OpenCV and SciPy
account for most of a ~1.7 GB virtual environment, and the detector models add another ~240 MB.

### Install it in five steps (Windows)

This is the whole procedure for running the software. It needs no Git, no terminal and no
programming. Each step is explained click by click, with what to do when it fails, in
**[the full installation guide](docs/wiki/1_Installation.md)** — read that one if anything here
is unfamiliar.

1. **Install Python 3.12** from
   [python.org](https://www.python.org/downloads/release/python-3129/) — the button labelled
   "Windows installer (64-bit)". On the **first** screen of that installer, tick
   **"Add python.exe to PATH"** before clicking Install.

   _Python is the engine the application runs on. If you skip this step, the installer in step 4
   offers to do it for you._

2. **Download DRerio LogAI**: open the
   [releases page](https://github.com/MarkSant/DRerio-LogAI/releases), and under **Assets** of the
   newest release click **Source code (zip)**.

3. **Extract the ZIP** somewhere permanent: right-click the downloaded file → **Extract all**.
   Choose a simple folder such as `C:\DRerio-LogAI`. **Not** the Downloads folder — this folder
   becomes the application's home, holding the models, the settings and (by default) your projects.

4. **Double-click `install.bat`** inside the extracted folder. Windows may warn that it protected
   your PC; choose **More info → Run anyway** (the file is a one-line script, and the warning only
   means the file came from the internet).

   It checks Python, checks Poetry, **offers to install whichever is missing**, installs the
   libraries, downloads the ~240 MB of detector models, and puts a **DRerio LogAI** icon on your
   Desktop and in the Start Menu. Expect several minutes. Answer `Y` to anything it asks.

5. **Start it** by double-clicking the **DRerio LogAI** icon.

That is all. The application asks for a language, measures the hardware, creates its folders and
opens. Camera, Arduino port and every other setting are chosen inside the interface — there is no
configuration file to write by hand.

### Linux and macOS

```bash
git clone https://github.com/MarkSant/DRerio-LogAI.git
cd DRerio-LogAI
./setup.sh          # Debian/Ubuntu: dependencies, models and a .desktop launcher
```

On macOS, and on distributions where `setup.sh` does not apply, install
[Python 3.12](https://www.python.org/downloads/) and
[Poetry](https://python-poetry.org/docs/#installation), then:

```bash
poetry install
poetry run fetch-weights     # ~240 MB of trained models, required
poetry run zebtrack
```

Linux also needs the Tk bindings: `sudo apt install python3.12-tk` on Ubuntu-based systems.

### Updating to a newer version

Download and extract the new ZIP, copy `config.local.yaml`, the `weights/` folder and any projects
stored inside the old folder across, then run `install.bat` again. With Git, `git pull` followed by
`install.bat` does the same. Re-run the installer after **moving** the folder too: the desktop
shortcut stores an absolute path.

## 🚀 First run: what you will see

In order, on the very first launch:

1. **A language question.** Your answer is written to `config.local.yaml`. The operating system's
   language is deliberately **not** consulted — before v5.0.0 a Brazilian machine produced
   Portuguese reports without anyone asking. Change it later in **Settings → Language...**.

2. **A splash screen running a hardware benchmark.** It converts one model to OpenVINO and measures
   inference on the devices it finds, to pick a backend. This is the slowest launch you will have:
   the result is cached and later launches skip it. A run that measures nothing is marked
   inconclusive and retried next time rather than cached as a guess.

3. **The main window**, with **Create New Project**, **Open Existing Project**, **Analyze Single
   Video** and **Analyze Live Camera**, plus a panel reporting the active weights and OpenVINO
   state.

4. **The Getting started window**, explaining the detector models, the four roles they fill and
   whether OpenVINO is worth enabling **on your machine** — it reads the hardware it found and
   names the devices, rather than giving generic advice. Its button opens the model panel directly.

   Dismissing it permanently is safe: it comes back from **Help → Getting Started...**, and the
   panel it points to lives in **Settings → Model settings...**.

The detector models are **not** downloaded here. They are fetched once, ahead of time, by
`fetch-weights`, which the installer runs for you. Without them the application starts and then
refuses to track, naming the missing files.

## 🧠 Detector models and OpenVINO

This is the one thing worth setting up before your first analysis.

### The six models

`fetch-weights` installs six trained YOLO models into `weights/` and verifies each against a
SHA-256 recorded in `weights_manifest.json`.

| Model | Type | Camera angle | Use it when |
| --- | --- | --- | --- |
| `best_det_lateral.pt` | detection (box) | lateral (side view) | Novel tank test, geotaxis, tanks filmed from the side |
| `best_seg_lateral.pt` | segmentation (mask) | lateral | Same, when precision at ROI edges matters |
| `best_det_topdown.pt` | detection (box) | top-down | Open field, light/dark, plates and arenas filmed from above |
| `best_seg_topdown.pt` | segmentation (mask) | top-down | Same, when precision at ROI edges matters |
| `best_oi.pt` | detection (box) | any | Setups the specialists do not fit; adds a `zup-aqua` class |
| `best_seg.pt` | segmentation (mask) | any | Same, with masks |

**A model trained for one angle returns nothing on the other.** A lateral model on a top-down
recording does not detect a fish that is plainly visible — so the first thing to get right is
matching the model to how your camera is mounted.

The four specialists are pre-assigned as defaults. The two generalists are registered but claim no
slot: they are something you opt into.

### The four roles

In **Settings → Model settings...**, under **Default weights per slot**, a model is assigned to
each of four roles:

| Role | What it finds |
| --- | --- |
| 🐠 **Aquarium (Detection)** | The arena, as a rectangle |
| 🐠 **Aquarium (Segmentation)** | The arena, as its real shape |
| 🐟 **Animal (Detection)** | Each fish, as a box |
| 🐟 **Animal (Segmentation)** | Each fish, as a mask |

Which pair is used in a given analysis depends on the method chosen for that project in the
wizard's **Models and Weights** step.

**Detection or segmentation?**

- **Detection (`det`)** is lighter and enough when approximate position is what you need.
- **Segmentation (`seg`)** is the better choice when the analysis depends on spatial precision —
  small ROIs, edges, several animals close together — and it is **required** by the `seg_overlap`
  ROI rule, which needs recorded masks.

### OpenVINO

OpenVINO is Intel's inference accelerator. Whether it is worth enabling depends on your machine,
and the Getting started window answers that for the machine in front of you:

| Your hardware | What to do |
| --- | --- |
| NVIDIA graphics card | Leave OpenVINO **off**; PyTorch with CUDA is normally faster |
| Intel CPU, integrated graphics or NPU, no NVIDIA card | Turn OpenVINO **on** — it is the fast path here (3–5× on Intel CPUs) |
| Neither | It still runs, on the CPU, just slower |

In **Settings → Model settings...**: tick **Optimise with OpenVINO (for Intel hardware)**, pick the
**OpenVINO device** (CPU, GPU or NPU), then use **Convert to OpenVINO** on the weights you plan to
use. **Conversion happens once** and is cached in `openvino_model_cache/`; the panel shows each
weight as ✓ Ready, ⏳ Converting or ✗ Failed.

The same panel holds **Add Weight...** (register a model you trained yourself), **Validate Paths**,
**Rescan Weights Folder**, cache maintenance and **Re-run Hardware Benchmark**.

### Checking or repairing the models

```bash
poetry run fetch-weights --check    # verify what is installed, download nothing
poetry run fetch-weights            # download whatever is missing or corrupt
```

## 🚀 Your first project

### The short version, end to end

1. **Create New Project** on the main window opens the wizard.
2. Answer the wizard (7 steps for pre-recorded video, 6 for live — detailed below).
3. In **Zone Configuration**, draw the arena and the regions of interest on a real frame, then
   **✅ Finish and Save Project**.
4. In **Main Control** (pre-recorded) press **Analyse Selected Video(s)** or **Process Pending
   Videos...**; in a live project press **▶️ Start Recording**.
5. In **Processing and Reports**, generate the partial and unified reports.
6. Open the `.xlsx` and the `.docx` written next to each video.

### The wizard, step by step

Both flows start from **Create New Project**. The wizard is 1150×550 px and shows its own step
counter.

#### Pre-recorded project — 7 steps

| # | Step | What you do |
| --- | --- | --- |
| 1 | **Discovery** | Project type (experimental / live), whether folders carry experimental meaning, and what to do with `.parquet` files found next to the videos |
| 2 | **Video Selection** | **📁 Add Files...** or **📂 Add Folder...**; a preview shows the structure that was understood |
| 3 | **Physical Calibration** | Aquarium **Width (cm)** and **Height (cm)**, number of aquariums per video, animals per aquarium, analysis interval, behavioural options |
| 4 | **Automatic Design Detection** | The folder structure is read into Groups / Days / Subjects. Review it; fix it with **✏️ Edit Design** or **🔧 Custom Regex** |
| 5 | **Models and Weights** | Method and weight per role, OpenVINO, YOLO confidence/NMS and the ByteTrack parameters |
| 6 | **Import Configuration** | Per video: import the arena, the ROIs, the trajectory — and the merge strategy when ROIs already exist |
| 7 | **Confirmation** | Project name and location, a summary of everything above, optional **💾 Save as Template** |

#### Live project — 6 steps

| # | Step | What you do |
| --- | --- | --- |
| 1 | **Discovery** | Project type: live |
| 2 | **Experimental Design** | Days, groups, group names, animals per group — the wizard shows the resulting number of recordings |
| 3 | **Live Recording Configuration** | **🔍 Detect Cameras** and pick one; optional Arduino port with **🔌 Test**; external trigger mode; timed recording and countdown |
| 4 | **Physical Calibration** | As above |
| 5 | **Models and Weights** | As above |
| 6 | **Confirmation** | As above |

**Organising the video folders.** When folders carry experimental meaning, a layout like
`Group_CBD/Day_1/Subject_4/CECT_4.mp4` is detected automatically into groups, days and subjects.
The same file name may repeat across days — a longitudinal design records the same subject daily —
because a video is identified by its **path**, never by its name alone.

> **External trigger mode** (the Arduino starts the recording) is opt-in and ships disabled. It
> requires a sketch that sends `1`/`0` over serial; the repository's reference sketch does **not**.
> See [`docs/guides/user/external-trigger.md`](docs/guides/user/external-trigger.md).

### Drawing the arena and the ROIs

In the **Zone Configuration** tab, on a frame loaded from your own video:

- **Detect Aquarium (Auto)** proposes the arena; **Smoothing (frames)** reduces noise in that
  detection. Or draw it yourself with **Main Polygon**.
- **Region of Interest (ROI)** draws each region — polygons, rectangles and circles are supported.
  Name them; the metrics are reported per ROI under those names.
- **ROI Templates** save a set of regions for reuse across videos and projects.
- Undo and redo are available throughout (`Ctrl+Z` / `Ctrl+Y`).
- With several aquariums in one video, **Processing Mode** chooses **Simultaneous** (one pass) or
  **Sequential** (one aquarium at a time).

Zones are stored per video. A video with none of its own falls back to the project default.

## 🧩 The project window, tab by tab

- **Main Control** — actions for the project type (live: start/stop recording; pre-recorded: add
  and process videos), the group/day/subject/video tree, and the **Detection Model Status** panel.
- **Zone Configuration** — arena and ROIs, inclusion rule, stabilisation, templates.
- **Video Analysis** — follow a running analysis and select which `track_id`s to consider.
- **Processing and Reports** — trajectory generation, summary export, partial and unified reports,
  with a per-video status tree; double-click opens the file.
- **AI Model Config.** / **AI Model Diagnostics** — the model panel for this project, and a
  diagnostic run against a sample frame.
- **Advanced Settings** — an in-app editor for the configuration, persisted to `config.local.yaml`.
- **Experiment Progress** (live projects) — the day × group grid of completed sessions.

Live projects also expose the **Arduino Dashboard** for connection status, commands and re-checking
ports.

## 🔩 Settings and parameters

**There is nothing to write by hand.** `config.local.yaml` is created for you — answering the
language question is what writes it — and everything an operator needs is reachable from the
interface.

### What to adjust, and when

| Parameter | Where | Default | Raise it when | Lower it when |
| --- | --- | --- | --- | --- |
| **Minimum confidence** | Wizard → Models and Weights; Advanced Settings | 0.05 | False detections (reflections, shadows, the heater) | The animal is missed, or disappears in dark frames |
| **NMS (overlap)** | Same | 0.5 | The same fish is detected twice | Two fish close together merge into one |
| **Track Threshold** | Same (ByteTrack) | 0.25 | IDs appear on noise | Tracks break up |
| **Match Threshold** | Same | 0.95 (permissive) | Tracks break up between analysed frames | IDs jump between animals |
| **Track Buffer (frames)** | Same | 150 | The animal is often occluded and returns | Identity must not survive a long absence |
| **Max distance (px)** | Same | 400 | The animal swims fast relative to the analysis interval | IDs are swapped between neighbours |
| **Analysis interval (frames)** | Wizard → Calibration; Advanced Settings | 10 | Processing is too slow | You need finer temporal resolution |
| **ROI inclusion rule** | Zone Configuration | `bbox_intersects` | — | See below |
| **Number of animals** | Wizard → Calibration | 1 | — | Must match reality; "1 animal" is respected |
| **Recording duration** | Wizard → Live config, per block or per subject | 300 s | — | — |

The confidence default is deliberately low because it is the floor for finding the **aquarium**,
once. The animal threshold is separate (`animal_confidence_threshold`) and inherits it until you
set it: accepting a tank once and accepting a fish on every frame are different questions.

> **Adjust one parameter at a time, in steps of ±0.05, and re-test.** The interface says the same
> thing, for the same reason: moving two at once makes the result impossible to attribute.

**ROI inclusion rules** decide what counts as "the animal is inside the region":

| Rule | Counts as inside when |
| --- | --- |
| `bbox_intersects` (default) | The bounding box overlaps the region by at least `roi_min_bbox_overlap_ratio` (0.10) |
| `centroid_in` | The centre of the animal is inside the region |
| `centroid_in_on_buffered_roi` | Same, on a region expanded or contracted by a buffer |
| `seg_overlap` | The segmentation **mask** overlaps the region beyond a fraction (default 0.3) |

`seg_overlap` needs masks that only exist if they were recorded — segmentation method, mask
persistence enabled, and that rule in force. When they are missing the analysis **degrades to
`bbox_intersects` with a warning in the report** rather than failing.

**Camera and Arduino port are stored per project, and the project's value wins over the global
one.** Setting them globally by hand therefore does nothing for a project that has its own — which
is every project the wizard creates.

If you do edit `config.local.yaml` directly, put in it _only_ the keys you are overriding:

```yaml
camera:
  index: 0
```

> Do **not** copy the whole `config.yaml` into it. The two files are merged recursively, so a full
> copy freezes every current default onto your machine and silently shadows every later correction.

## 📁 What you get out

Each processed video produces a results folder next to it:

```text
<video>_results/
├── 1_ArenaROI_<video>.parquet       # Arena/ROI definitions
├── 2_Zones_<video>.parquet          # Zone metadata
├── 3_CoordMovimento_<video>.parquet # Trajectory (immutable schema)
├── 3b_Mascaras_<video>.parquet      # Segmentation masks (only when recorded)
├── <video>_summary.xlsx             # Metrics per ROI + per-animal table
└── <video>_report.docx              # Word report with plots
```

Multi-aquarium adds `aquarium_0/`, `aquarium_1/` subfolders mirroring this layout. Live sessions add
a frame ledger (`6_FrameLedger_*`) that maps each analysed frame to its real capture instant, and,
with Arduino bindings, a closed-loop latency log (`5_ClosedLoop_*`).

The project-wide report collects every video:

```text
<project>/unified_reports/
├── project_summary_<run_id>.parquet   # Raw data
├── project_summary_<run_id>.xlsx      # "Data" + "Descriptive Stats" sheets
├── project_summary_<run_id>.csv       # Same as the Data sheet
├── project_summary_<run_id>.docx      # Comparative boxplots + descriptive table
└── project_summary_<run_id>.json      # Manifest with run metadata
```

The trajectory schema is fixed and will not change between versions:

```text
timestamp, frame, track_id, x1, y1, x2, y2, confidence
[x_center_px, y_center_px, x_cm, y_cm]*   — when calibration is available
```

## 📊 Behavioural metrics

Per video, per animal and per ROI:

| Family | Reported |
| --- | --- |
| **Locomotion** | Total distance (cm), mean / max / SD of speed (cm/s), tortuosity |
| **Angular** | Mean / max / SD of angular velocity (°/s), sharp turns, turns per minute |
| **Episodes** | Speed bursts (count and duration), inactivity (count, duration, % of recording) |
| **Spatial** | Thigmotaxis (% time near the wall, mean wall distance), geotaxis occupancy per vertical zone |
| **Per ROI** | Time, entries, exits, latency to first entry, distance and speed inside the region |
| **Session** | Experiment, group, day, video duration, frames analysed |

Wall distance is the exact Euclidean distance to the nearest edge of the aquarium polygon, valid for
any number of sides, convex or concave — the thigmotaxis chart is meaningful for an 8-sided tank,
not only a rectangle.

**Full reference, with every column name and formula:**
[`docs/reference/metrics.md`](docs/reference/metrics.md).

> **Comparing absolute metrics across recordings of different lengths is invalid** (total distance,
> entry counts, time in ROI). The application warns before generating a partial or batch report and
> stamps the caveat inside the `.docx`; the `video_duration_s` column is in the `.xlsx` precisely so
> you can normalise.

## 🔧 When something goes wrong

| Symptom | What to do |
| --- | --- |
| The installer stops with a yellow message | It names the cause and the fix; the commonest is an unsupported Python (3.14) |
| `ModuleNotFoundError: No module named 'zebtrack'` | The environment was built on the wrong Python. [Installation guide § fetch-weights](docs/wiki/1_Installation.md#if-fetch-weights-says-there-is-no-module-named-zebtrack) |
| The desktop icon does nothing | Re-run the installer; a moved folder leaves the shortcut pointing nowhere. Check `logs/analysis.log` |
| The application starts but refuses to track | The models are missing: `poetry run fetch-weights` |
| The fish is not detected | Wrong model for the camera angle (lateral vs top-down), or confidence too high |
| Tracking is slow | Enable OpenVINO on Intel hardware and convert the weight; raise the analysis interval |
| No camera is listed | Close whatever else is using it, then **🔍 Detect Cameras** again |
| The Reports tab is empty | Process the videos first; the tree refreshes on demand |

Longer lists: [Troubleshooting](docs/wiki/user-guide/TROUBLESHOOTING.md),
[FAQ](docs/wiki/3_FAQ.md), [Known issues](docs/reference/KNOWN_ISSUES.md).

## 🆕 What's new

**Version 7.1.0** — the first-run release: a guided installer and a desktop shortcut (no terminal
needed), a getting-started window explaining the models, a splash screen that appears immediately,
a first-run benchmark that actually measures something, and all six models installed and
selectable.

**Full history:** [what's new, version by version](docs/releases/INDEX.md) ·
[CHANGELOG](CHANGELOG.md).

## 📖 Citation

If you use DRerio LogAI in research, please cite it using the metadata in
[CITATION.cff](CITATION.cff) (recognised by GitHub as "Cite this repository").

The software is archived on Zenodo:

| DOI | Resolves to |
| --- | --- |
| [`10.5281/zenodo.22650404`](https://doi.org/10.5281/zenodo.22650404) | **All versions.** Cite this one unless you need to pin a specific release. |
| [`10.5281/zenodo.22650405`](https://doi.org/10.5281/zenodo.22650405) | Release **7.0.0** specifically. |

> **Reproducing the published results.** The validation and benchmark numbers reported in the
> associated manuscripts were produced with release **4.0.0** (tag
> [`v4.0.0`](https://github.com/MarkSant/DRerio-LogAI/tree/v4.0.0)), not with this one. Check out
> that tag for exact reproduction; cite the DOI above for the archived platform.

## 📜 Ownership, registration and licence

**DRerio LogAI** has a **Computer Program Registration granted by INPI** (Brazil), under Law
9.609/98 (software copyright — **not** a patent): process **BR 51 2026 005215-7**, petition
870260066857, filed 07/07/2026, declared creation date 22/10/2025.

The **holder** of the economic rights is the **Universidade Estadual Paulista "Júlio de Mesquita
Filho" (UNESP)**, CNPJ 48.031.918/0001-24. The **authors** (moral rights) are:

- **Marco Antônio Sant'Ana Camargos** — São Paulo State University (UNESP), Botucatu, Brazil
- **Percília Cardoso Giaquinto** — São Paulo State University (UNESP), Botucatu, Brazil

The original source code is licensed under the **MIT License** ([LICENSE](LICENSE)).

⚠️ **Effective distribution licence.** This project depends on
[Ultralytics YOLO](https://github.com/ultralytics/ultralytics), licensed under
**AGPL-3.0-or-later**. Because of that copyleft, the distributed combined work (this code plus
`ultralytics`) is subject to AGPL-3.0-or-later unless a commercial licence from Ultralytics is
obtained. MIT covers UNESP's original code; it does not by itself cover the distributed package as
a whole. [NOTICE](NOTICE) has the full dependency survey.

> **Do not confuse with PyZebArdYolo.** That is a sibling repository, simpler in scope, focused on a
> real-time acquisition unit (webcam + YOLO11 + Arduino) used in a separate hardware paper. It is
> not covered by the INPI registration above and does not carry the UNESP ownership requirement.
> The two projects are independent.

## 👨‍💻 For developers

```bash
git clone https://github.com/MarkSant/DRerio-LogAI.git
cd DRerio-LogAI
poetry install --with dev
poetry run pre-commit install
poetry run fetch-weights
poetry run pytest -q
```

`install.ps1 -Dev` does the same on Windows, plus the shortcut.

The application is Python 3.12+, Tkinter, MVVM-S with dependency injection and an event bus
(`EventBusV2`); ~3700 tests run in 6–7 minutes.

| Topic | Document |
| --- | --- |
| **Contributing** | [CONTRIBUTING.md](CONTRIBUTING.md) |
| **Architecture** | [docs/explanation/architecture.md](docs/explanation/architecture.md) |
| **Developer onboarding** | [docs/guides/developer/getting_started.md](docs/guides/developer/getting_started.md) |
| **Source → tests map** | [docs/testing/TEST_MAP.md](docs/testing/TEST_MAP.md) |
| **Coordinate systems** | [docs/reference/COORDINATE_SYSTEMS.md](docs/reference/COORDINATE_SYSTEMS.md) |
| **Events** | [docs/reference/events.md](docs/reference/events.md) |
| **Performance / NPU** | [docs/guides/developer/performance-tuning.md](docs/guides/developer/performance-tuning.md) · [docs/performance/HARDWARE_OPTIMIZATION_GUIDE.md](docs/performance/HARDWARE_OPTIMIZATION_GUIDE.md) |
| **VS Code setup** | [docs/guides/developer/VSCODE.md](docs/guides/developer/VSCODE.md) |
| **Cutting a release** | [docs/guides/developer/RELEASE.md](docs/guides/developer/RELEASE.md) |
| **Everything else** | [docs/INDEX.md](docs/INDEX.md) |

Contributions are welcome — bug fixes from [KNOWN_ISSUES.md](docs/reference/KNOWN_ISSUES.md),
documentation and translations, test coverage, UI improvements, new detector plugins.

## 🙏 Acknowledgments

**UNESP** — Universidade Estadual Paulista, and the **Fish Physiology and Behavior Laboratory**
(Dept. of Physiology — IBB/UNESP).

Built on [Ultralytics YOLO](https://github.com/ultralytics/ultralytics),
[OpenVINO](https://github.com/openvinotoolkit/openvino),
[BYTETracker](https://github.com/ifzhang/ByteTrack),
[Tkinter](https://docs.python.org/3/library/tkinter.html),
[Poetry](https://python-poetry.org/), [Pydantic](https://pydantic.dev/) and
[structlog](https://www.structlog.org/) — and on the open source community around them.

---

<div align="center">

<h4>Built with ❤️ for scientific research</h4>

<h4>UNESP - Fish Physiology and Behavior Laboratory (Dept. of Physiology - IBB/UNESP)</h4>

[⬆ Back to top](#drerio-logai)

</div>
