# Project Wizard Walkthrough: Your First Tracking Run

**Last updated:** 2026-08-15

## Overview

The Project Creation Wizard is the smart, multi-step assistant that automates
project creation in DRerio LogAI. It is the standard experience (the
`ui_features.use_wizard_for_project_creation` flag should stay enabled). It
detects the experimental design automatically, imports zones from existing
Parquet files, and configures a processing strategy for every video.

The wizard window targets **1050×780 px**, is resizable down to **900×650 px**,
and centers itself on the screen while leaving room for the taskbar.

### Benefits

- ✅ **Automatic Design Detection** — identifies groups, days, and experimental structure
- ✅ **Smart Parquet Import** — reuses arenas, ROIs, and trajectories already processed
- ✅ **Granular Configuration** — per-video control over what to import
- ✅ **Time Savings** — avoids unnecessary reprocessing
- ✅ **Smart Validation** — catches errors before project creation

## The steps differ by project type

The wizard shows a different sequence of steps depending on what you picked in
Discovery:

- **Pre-recorded (Experimental / Exploratory)** — 7 steps: Discovery → File
  Selection → Physical Calibration → Automatic Design Detection → Models and
  Weights → Import Configuration → Project Confirmation and Creation.
- **Live** — 6 steps: Discovery → Experimental Design → Live Recording
  Configuration → Physical Calibration → Models and Weights → Project
  Confirmation and Creation. There is no folder scan, so File Selection,
  Automatic Design Detection, and Import Configuration are skipped; camera and
  optional Arduino setup replace them. See
  [`arduino-bindings.md`](../guides/user/arduino-bindings.md) and
  [`external-trigger.md`](../guides/user/external-trigger.md) for that path.

This tutorial walks through the **pre-recorded** flow, which covers the common
case of tracking videos you already have on disk.

---

## Step 1 · Discovery

**Goal:** Define the project type and import intentions.

### 1. Project Type

- **Experimental (pre-recorded videos with groups, days, subjects)** — studies
  with treatment groups, controls, a time design
  - Example: comparing drug effect across Control vs. Treatment groups over 5 days
- **Exploratory (pre-recorded videos, free-form analysis)** — open-ended
  analyses, quick tests, projects with no formal design
  - Example: testing camera setup, validating detection parameters
- **Live (record straight from the camera in real time)** — recording
  experiments live using a camera connected to the computer

### 2. Folder Organization (experimental projects only)

- **Yes - folders represent the experimental structure (e.g. Group/Day/)**
- **Yes - but only for organization (arbitrary names)**
- **No - every video is in a single directory**

### 3. Existing Parquet Files

- **No - start from scratch** — process everything from zero
- **Yes - I want to import only the arena**
- **Yes - I want to import zones (arena and ROIs)** — import arena/ROIs, regenerate trajectories
- **Yes - I want to import everything (zones + trajectory)**

Use **📂 Load Template...** at the top of the step to reload a previously
saved wizard template (see [Templates](#templates) below) instead of
answering these questions from scratch.

💡 **Tip:** if you already processed videos before, pick a Parquet import
option to save time.

---

## Step 2 · File Selection

**Goal:** Select the videos and/or folders for the project.

- **📁 Add Files...** — pick individual `.mp4`, `.avi`, or `.mov` files (supports multi-select)
- **📂 Add Folder...** — pick a root folder; the scan is recursive and finds videos in subfolders automatically
- **❌ Remove Selected** — removes the item currently selected in the list
- **🗑️ Clear All** — removes every selected video and folder
- The **Selection Summary** panel shows a running count of files/folders selected
- The **Selected Items** list and the **Structure Preview** tree (columns
  **Folder / File** and **Summary**) show the first folders/files detected —
  useful to confirm you picked the right root before advancing. Loose files
  are grouped under **Individual Files**.

### Example structure

```text
Experimento_Canabidiol/
├── Control/
│   ├── Day01/
│   │   ├── Subject01.mp4
│   │   └── Subject02.mp4
│   └── Day02/
│       └── Subject01.mp4
└── Treatment/
    ├── Day01/
    │   └── Subject01.mp4
    └── Day02/
        └── Subject02.mp4
```

💡 **Tip:** for folder-structured projects, use **📂 Add Folder...** on the
experiment root — the preview tree shows the hierarchy and the wizard detects
the design automatically in the next steps.

---

## Step 3 · Physical Calibration

**Goal:** Set the physical dimensions of the arena to convert pixels into
centimetres, and the detection/tracking cadence.

- **Video and Animal Configuration**: **Number of aquariums (videos)** and **Animals per aquarium**
- **Physical Aquarium Dimensions**: **Width (cm)** and **Height (cm)**
- **⚙️ Advanced Settings**: **Analysis interval (frames)** — how often detection runs
- **🧠 Behavioural Analysis** section for related settings

See [`COORDINATE_SYSTEMS.md`](../reference/COORDINATE_SYSTEMS.md) for how
these values map onto the arena/ROI coordinate system.

---

## Step 4 · Automatic Design Detection

**Goal:** Analyze videos and existing Parquet files, and detect the
experimental design automatically (skipped for Exploratory projects).

The **Detection Results** panel reports:

- **📊 Videos found**
- **📦 Existing Parquet Files** — counts for Arena, ROIs, Trajectory, and videos that are Complete (all three)
- **🎯 Experimental Design Detected** — Groups, Days, subjects per group, the pattern used, and a **Confidence** percentage (higher is more reliable; treat values below ~70% with caution)
- **⚙️ Current Detector Configuration** — aquarium/animal method and weight, OpenVINO status

Actions available in this step:

- **🔄 Re-analyze** — rerun detection (e.g. after changing files)
- **✏️ Edit Design** — manually correct groups/days/subjects when detection gets it wrong
- **🔧 Custom Regex** — supply your own group/day/subject patterns; the preview updates live as you type, and errors show inline instead of as interruptive pop-ups

The wizard recognizes folder-based patterns (groups and/or days as folders,
mixed folder layouts) as well as filename-based patterns
(`Control_Day01_Subject01.mp4`-style names).

---

## Step 5 · Models and Weights

**Goal:** Choose detection methods, weights, and tracking parameters — this
step did not exist in older wizard versions and is new since the OpenVINO
integration.

- **Methods and Weights per Role**: separate **Aquarium (arena detection)**
  and **Animals (tracking)** roles, each with its own method
  (**Segmentation (seg)** / **Detection (det)**) and weight file
- **Acceleration / OpenVINO**: **Use OpenVINO (requires converting the weight)** toggle plus an **OpenVINO device** selector
- **Detection Parameters (YOLO)**: **Minimum confidence (0-1)** and **NMS (overlap, 0-1)**
- **Tracking Parameters (ByteTrack)**: **Use ByteTrack (Recommended)**, **Track Threshold (0-1)**, **Match Threshold (0-1)**, **Track Buffer (frames)**, **Max distance (px)**, **IoU Threshold (0-1)**
- **🔄 Restore Recommended Defaults** resets all of the above

💡 **Tip shown in the app:** adjust ONE parameter at a time (±0.05) and test.

---

## Step 6 · Import Configuration

**Goal:** Define the per-video processing strategy.

### Bulk actions

- **Import All Arenas**
- **Import All ROIs**
- **Import All Trajectories**
- **Import Everything**

### Videos and Strategies table

Columns: **Video**, **Arena**, **ROIs**, **Trajectory**, **Action**. Double-click
a cell to toggle it; the **Action** column recomputes automatically:

| Arena | ROIs | Trajectory | Action (internal code)        | Label shown             |
| ----- | ---- | ---------- | ------------------------------ | ------------------------ |
| ✅    | ✅   | ✅         | `SKIP`                          | Skip (complete data)     |
| ✅    | ✅   | ❌         | `IMPORT_ZONES`                  | Import Zones + track     |
| ✅    | ❌   | ❌         | `PARTIAL`                       | Partial (arena only)     |
| ❌/✅ | ❌/✅| ❌/✅      | `FULL`                          | Full (from scratch)      |

- **🏟 Arena \| 🎯 ROIs \| 🧭 Trajectory** legend: **✓** import, **⏸** do not import, **✗** unavailable (no Parquet found)
- **ROI Strategy** for conflicts between imported and newly drawn ROIs:
  **Replace (overwrite)**, **Merge (keep both ROIs)** (conflicts are renamed),
  or **Manual (ask)** (ask for each conflict)

💡 **Tip:** use Skip for already-processed videos and Import Zones + track to
reuse drawn zones while regenerating trajectories.

---

## Step 7 · Project Confirmation and Creation

**Goal:** Review every setting and create the project.

The **Project Summary** panel reflects everything chosen in the previous
steps: project type, detected design (groups/days/confidence), hardware
(camera/Arduino, for live projects), calibration, detector configuration,
folder structure preview, processing plan (estimated at **~5 minutes per
video** to process; Skip is instant), and existing/imported Parquet counts.

Final fields:

- **Project Name:** — auto-suggested (e.g. `Experiment_Control` for the
  first detected group, or `Experimental_Project` / `Exploratory_Project`
  otherwise); editable
- **Location:** — defaults to `Documents`; use **Browse...** to change it
- **💾 Save as Template** — stores every answer from this run (see
  [Templates](#templates) below) so a future project can start from the same
  configuration

The wizard validates the project name and location before letting you finish
— it will not allow an empty name, special characters, a non-writable
location, or a duplicate project name in the same location.

---

## Templates

Two independent template mechanisms exist:

- **Curated baseline templates** shipped with the repo under
  `resources/wizard_templates/*.json`, packaged by `scripts/build_templates.py`
  into `dist/wizard_templates.zip` in CI. Use `scripts/compile_translations.py`
  to make sure Word/Excel reports generated by the wizard use the up-to-date
  `pt_BR` catalog.
- **User-saved templates**, created with **💾 Save as Template** on the
  Confirmation step and reloaded with **📂 Load Template...** on the
  Discovery step (file filter: **Wizard Templates** `*.json`). Loading one
  pre-fills every step; review each step before continuing.

Any wizard change should update this documentation, run the `tests/test_wizard*.py`
suite, and review the developer guide at
[`docs/guides/developer/wizard.md`](../guides/developer/wizard.md).

---

## Recommended Flow by Scenario

### Scenario 1: New Project (no Parquets)

1. **Discovery**: Experimental + "folders represent the experimental structure" + "start from scratch"
2. **File Selection**: Add Folder... (experiment root)
3. **Automatic Design Detection**: verify the detected design (groups and days)
4. **Import Configuration**: all videos default to `FULL` (process from scratch)
5. **Confirmation**: confirm and create

**Result:** project created with the detected design; every video gets processed.

---

### Scenario 2: Import Zones from a Previous Project

1. **Discovery**: Experimental + folder structure + **"Yes - I want to import zones (arena and ROIs)"**
2. **File Selection**: add videos with adjacent `*_arena.parquet` and `*_rois.parquet` files
3. **Automatic Design Detection**: the wizard detects the existing arenas/ROIs
4. **Import Configuration**: videos with arena+ROIs → `IMPORT_ZONES` (track again)
5. **Confirmation**: confirm

**Result:** arena and ROIs imported; new trajectories generated without redrawing zones.

---

### Scenario 3: Reuse a Fully Processed Run

1. **Discovery**: Experimental + **"Yes - I want to import everything (zones + trajectory)"**
2. **File Selection**: add videos with adjacent `*_trajectory.parquet` files
3. **Automatic Design Detection**: the wizard detects complete data
4. **Import Configuration**: complete videos → `SKIP`; new videos → `FULL`
5. **Confirmation**: confirm

**Result:** already-processed videos are skipped; only new videos are processed.

---

### Scenario 4: Quick Exploratory Project

1. **Discovery**: **Exploratory** + "start from scratch"
2. **File Selection**: add one or two test videos
3. **Automatic Design Detection**: skipped (exploratory projects don't detect a design)
4. **Import Configuration**: `FULL` for everything
5. **Confirmation**: the project name auto-suggests `Exploratory_Project`

**Result:** a simple project created quickly for testing.

---

## Frequently Asked Questions

### 1. What happens if I have no folder structure?

The wizard still works, but it won't auto-detect a design. Configure each
video's action manually in Import Configuration.

### 2. Can I edit the detected design?

Yes. Use **✏️ Edit Design** on the Automatic Design Detection step to correct
groups/days/subjects by hand, or **🔧 Custom Regex** to supply your own
detection patterns. If confidence is low (below ~70%), consider reorganizing
folders/filenames first.

### 3. What is detection "Confidence"?

A percentage reflecting how consistent the detected pattern is across your
videos. Higher values are more reliable; treat anything clearly below 70%
with caution and double-check the detected design before continuing.

### 4. Can I go back to previous steps?

Yes — the **< Back** button is available at any time; your data is preserved.

### 5. Can I cancel the wizard?

Yes. Click **Cancel** at any time.

### 6. What if I choose Skip but the video is missing data?

The wizard won't allow `SKIP` without complete data — Import Configuration
only allows it when arena + ROIs + trajectory all exist.

### 7. How long does processing take?

Estimate: **~5 minutes per video** for `FULL` processing. `IMPORT_ZONES` is
faster (only trajectory generation runs). `SKIP` is instant.

### 8. Do the Parquet files need to be in the same folder as the videos?

Yes. The wizard looks for `{video_name}_arena.parquet`,
`{video_name}_rois.parquet`, and `{video_name}_trajectory.parquet` next to
the matching video:

```text
/Videos/
├── Subject01.mp4
├── Subject01_arena.parquet
├── Subject01_rois.parquet
└── Subject01_trajectory.parquet
```

---

## Troubleshooting

### "No design detected" despite a folder structure

**Cause:** the structure doesn't follow one of the recognized patterns.

**Solution:**

1. Check that folders/names follow a consistent pattern.
2. Use recognizable keywords: Control, Treatment, Day, D, Subject, S.
3. Try **🔧 Custom Regex** to describe your own naming pattern, or reorganize
   into an Exploratory project.

---

### The wizard doesn't find existing Parquet files

**Cause:** files don't follow the naming convention.

**Solution:**

1. Rename Parquets to `{video_name}_arena.parquet`, etc.
2. Make sure they sit in the same folder as the video.
3. Check the extension is `.parquet` (not `.pq` or `.parq`).

---

### Detection confidence is very low

**Cause:** inconsistent folder/name structure.

**Solution:**

1. Review the structure and identify outliers (videos that don't fit the pattern).
2. Rename folders/files to follow a consistent pattern.
3. Or switch to an Exploratory project and configure manually.

---

### "Project already exists" when creating

**Cause:** a folder with the same name already exists at that location.

**Solution:**

1. Choose a different name.
2. Or pick a different location.
3. Or remove/rename the existing project.

---

## Glossary

- **Arena**: the experimental tank's coordinates
- **ROI**: Region of Interest (zones inside the tank)
- **Trajectory**: tracking data (animal positions over time)
- **Parquet**: the columnar file format used to store tracking data
- **SKIP** (`Skip (complete data)`): skip processing — complete data already exists
- **IMPORT_ZONES** (`Import Zones + track`): import arena and ROIs, generate a new trajectory
- **PARTIAL** (`Partial (arena only)`): import only the arena
- **FULL** (`Full (from scratch)`): process everything from zero (no import)
- **Experimental Design**: the study's formal structure (groups, days, subjects)
- **Detection Confidence**: percentage reflecting how certain the automatic design detection is

---

## Support

To report problems or suggest improvements:

- GitHub Issues: <https://github.com/MarkSant/DRerio-LogAI/issues>
- Complementary developer docs: `docs/guides/developer/wizard.md`
- Architecture: `docs/explanation/architecture.md`
