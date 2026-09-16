# What's new, version by version

Highlights per release, newest first. This page exists so the README can stay about what the
software *does*; the complete, per-change history is in [`CHANGELOG.md`](../../CHANGELOG.md), and
the text published on each GitHub release is in `RELEASE_NOTES_v<version>.md` next to this file.

| Version | Date | In one line |
| --- | --- | --- |
| [7.1.0](#710--the-first-run-release) | 2026-09-08 | Install and open the program without a terminal; a getting-started window |
| [7.0.0](#700--first-public-release) | 2026-09-07 | First public and citable release; the models became obtainable |
| [6.0.0](#600--archival-snapshot) | 2026-08-15 | Citable archival snapshot, closed-loop logger correctness, English README |
| [5.0.0](#500--roi-overhaul-closed-loop-and-english-ui) | 2026-08 | ROI overhaul, closed-loop stimulation, English as the source language |
| [4.0.0](#400--the-architectural-rewrite) | 2026-03-29 | Event-driven rewrite, multi-aquarium v2, NPU support |
| [v1–v3](#v1v3--earlier-milestones) | 2025 | Wizard, live projects, the unified `LiveCameraService` |

---

## 7.1.0 — the first-run release

v7.0.0 made the software citable; this release is about the interval between double-clicking the
icon and starting the first analysis.

- **📥 Installing and launching without a terminal.** `install.bat` / `install.ps1` and `setup.sh`
  check the prerequisites, install the dependencies, download the models and create a **DRerio
  LogAI** icon on the Desktop and in the Start Menu. The shortcut targets
  `pythonw.exe -m zebtrack`, so no console window sits behind the application.
- **🧭 A getting-started window**, shown once the main window is up. It explains the models, the
  four roles they fill and whether OpenVINO is worth enabling **on your machine** — it reads the
  detected hardware and names the devices instead of giving generic advice.
- **📋 Menu entries that should have existed.** The model configuration panel had **no menu entry
  at all**: the one screen an operator needs before their first analysis was the one they could not
  find. It is now **Settings → Model settings...**, and the welcome window returns from
  **Help → Getting Started...**.
- **📦 All six models are installed.** `fetch-weights` used to install four and hide the two
  generalists behind `--all` — because weight discovery could not find them anyway. The discovery
  gap was the real defect; with it fixed, all six appear in the model panel. `--all` is still
  accepted and now does nothing.
- **⏳ The icon no longer looks dead for four seconds.** The splash screen was created *after* the
  import block that builds the coordinator graph, so it only appeared once the heavy loading had
  finished. Under `pythonw` there was nothing at all to see.
- **📊 The first-run benchmark now measures something.** Its inference steps were guarded on an
  OpenVINO model existing, and on a fresh install nothing has been converted — so every step was
  skipped, the benchmark finished in 0.2 s and recommended CPU at 0.0 FPS, and that result was
  cached forever. It now converts one model first, and a run that still measures nothing is marked
  inconclusive and **not** cached.
- **🪵 Logging died on every record without a console.** `StreamHandler(sys.stdout)` under
  `pythonw` got `None`, and the fallback to `sys.stderr` is `None` too.
- **📷 Camera detection needed a stderr to silence.** A failed redirect closed the process's real
  stderr, and the wizard then listed no cameras at all.
- **🈳 The very first launch hung on a window that was never drawn.** The language chooser called
  `transient()` on a withdrawn root, and a transient inherits its master's withdrawn state.

Full notes: [`RELEASE_NOTES_v7.1.0.md`](RELEASE_NOTES_v7.1.0.md).

## 7.0.0 — first public release

The first **public** release, and the first citable one: this is the tag the Zenodo DOI was minted
from.

- **📥 The trained models became obtainable.** They are git-ignored, and until then nothing said
  how to get them — a fresh clone installed, passed the whole test suite (which mocks them), and
  then failed to open. `fetch-weights` downloads them from the release assets and verifies each
  against a SHA-256 in `weights_manifest.json`.
- **🧭 Starting without models says so** — which models, in which folder, and which command
  installs them, instead of running a full hardware benchmark, drawing the splash to 95% and
  reporting "a fatal error occurred".
- **📂 The launch directory stopped mattering.** `config.yaml`, `weights/`, `weights_config.json`
  and the OpenVINO cache resolve against the repository root. `--reset` and friends now delete what
  they promise; run from another folder they used to match nothing and still print "Reset complete".
- **📐 Real aquarium dimensions in the live dialog.** They drove the pixel/cm ratio behind every
  distance, speed and cm-based metric, but no widget exposed them — a maze declared square produced
  95.8 px/cm on one axis against 60.1 on the other.
- **🎥 Live and pre-recorded correctness.** Live post-analysis uses the project's settings snapshot
  instead of whatever the last ad-hoc run left behind; `seg_overlap` no longer degrades
  unconditionally; re-detecting the arena no longer erases the ROIs; single-video respects "1
  animal"; arena auto-detection honours segmentation, real shape and perspective.
- **📊 Reports.** Zones stopped disappearing from the summary — and with them from the unified
  report; a basename repeated across days no longer overwrites the summary and loses half the
  animals.
- **🧵 No C compiler.** The tracker pulled `cython-bbox`, published only as a source distribution,
  so `poetry install` compiled a C extension and failed outright on a machine without a toolchain.
  That IoU routine is plain NumPy now.

Full notes: [`RELEASE_NOTES_v7.0.0.md`](RELEASE_NOTES_v7.0.0.md).

## 6.0.0 — archival snapshot

Citable archival snapshot prepared for permanent deposit on Zenodo, in support of the manuscripts
describing the platform's validation and a multi-method tracking benchmark.

- **📡 Closed-loop logger correctness.** `fps` and `sampling_interval_ms` in
  `5_ClosedLoop_<base>.csv` now hold the frame rate **measured** from capture timestamps, not the
  value configured in settings — a USB camera routinely exceeds its configured rate. The nominal
  value is kept separately in `fps_configured` / `sampling_interval_ms_configured`.
- **📦 Archival readiness.** `.zenodo.json` with complete metadata (authors, ORCID, licence, INPI
  registration, funding); `CITATION.cff` updated; internal grant-agency material curated out of the
  publicly archived tree.
- **🌐 i18n and docs polish.** `README.md` split into an English source plus a Portuguese
  translation; stale UI-label references fixed after the i18n migration.

## 5.0.0 — ROI overhaul, closed loop, and English UI

Roughly 4.5 months of work between the `v4.0.0` rewrite and the `v6.0.0` archival snapshot.

### Region of interest

- **🎯 One canonical inclusion rule.** A single resolver (project → global → default) backs report
  generation, live Arduino triggers and the UI alike, replacing divergent per-consumer logic.
  Modes: `centroid_in`, `centroid_in_on_buffered_roi`, `bbox_intersects`, `seg_overlap`.
- **🔬 Multi-animal ROI.** `(timestamp, track_id)` aggregation ends the "ghost centroid" bug;
  per-animal (`por_animal`) and any-track group semantics; track-aware smoothing and episode
  detection.
- **🎭 Real segmentation-overlap ROI.** `seg_overlap` reads recorded masks and degrades gracefully
  — never raises — to `bbox_intersects`, with a warning that reaches the report.

### Closed-loop stimulation and hardware

- **⚡ Per-zone Arduino command bindings**: edge-triggered `on_enter` / `on_exit` tokens per ROI,
  with conflict detection and ACK-based inversion detection (the firmware's own reply proves
  whether a binding is wired backwards).
- **📊 Closed-loop latency logging**: software-only characterisation of the ROI-trigger →
  actuation pipeline, plus a non-blocking reference firmware.
- **🗂️ Frame ledger**: `6_FrameLedger_<base>` maps pipeline frame ↔ real MP4 frame ↔ capture
  instant, recording every frame-loss mode.
- **🔌 External trigger mode**: Arduino-gated recording start reaches both the legacy panel and the
  Progress-grid live flow through one decision gate.

### Sessions and internationalisation

- **⏱️ Per-subject recording duration** (subject override → block default → project default → 300 s
  fallback), with a heterogeneous-duration warning on partial and batch reports.
- **🐟 Multi-aquarium and live-session fixes**: zone-reuse detection, "Mark Batch as Complete" now
  generates real reports, OpenVINO global-setting inheritance, corrected processing-tab counters.
- **🌐 English as the interface source language**, with a full pt-BR catalogue, translations
  resolved at call time rather than import time, and a CI scanner preventing regressions.

## 4.0.0 — the architectural rewrite

A fundamental rewrite focused on stability, maintainability and performance. It remains the
architectural foundation of every version above.

- **🏗️ Event-driven architecture**: `EventBus` for asynchronous communication, a mediator
  (`UICoordinator`) for UI orchestration, and the removal of 90+ lines of legacy thread code.
- **🎨 Unified "Processing and Reports" tab**: 50% less memory during rendering, no more UI-update
  race conditions, real-time preview through `LivePreviewWindow`.
- **⚡ Performance**: 67% faster startup (6.0 s → 2.0 s) through lazy loading, `RecorderFactory` for
  on-demand pandas/pyarrow, hardware cache with a 30 s TTL.
- **🔒 Reliability**: ~3700 tests, E2E coverage of critical flows, automatic timeouts to prevent
  hangs.
- **🐛 Live-camera fixes**: correct `camera_index` in live projects, configured analysis intervals
  respected, one unified `LiveCameraService` for both contexts.
- **💡 Contextual help**: the information-icon (ⓘ) system with detailed tooltips for every AI and
  calibration parameter.

### Multi-aquarium v2

Parallel detection (`ThreadPoolExecutor`, ~30–40% speedup), batch inference, per-aquarium ROI
cropping, `uncertainty` and `bbox_iou` quality columns, per-aquarium thigmotaxis, configuration
validation, gap detection, automatic fallback when one aquarium fails, R/Python export scripts,
side-by-side preview and per-aquarium Word/Excel reports.

### Behavioural analysis and hardware

- **🧠 Geotaxis (novel tank test)**: native support for lateral perspective with vertical zones
  (bottom / middle / surface), automatic zone lines on plots, perspective-aware report columns.
- **🔌 Intel NPU** support on Core Ultra processors through OpenVINO, `standard` / `lite` / `nano`
  model variants selected by hardware, an automatic throughput benchmark across CPU, GPU and NPU,
  and a smart fallback when the detected hardware is insufficient.

## v1–v3 — earlier milestones

- **3.0.0** (2025-01-11) — the legacy thread system for live projects removed; the live camera flow
  goes exclusively through `LiveCameraService`.
- **2.1.0** — live projects migrated to the unified `LiveCameraService`; `camera_index` respected
  (it used to force camera 0); analysis and display intervals respected; threads down from 4 to 2.
- **2.0.0** — the wizard service layer with testable, centralised business logic; Pydantic models
  for typed validation; dialogs extracted from `gui.py` into `zebtrack.ui.dialogs/`; hardware
  detection cache; Express/Advanced wizard modes, external trigger, templates and ROI rules.
- **1.6.0** — project creation through the wizard, live projects with camera and Arduino,
  experimental-design fields (groups/days/subjects) and template persistence.
