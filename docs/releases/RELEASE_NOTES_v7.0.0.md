# DRerio LogAI v7.0.0

Citable snapshot prepared for permanent archiving on Zenodo, in support of the
manuscripts describing the platform (validation study) and the multi-method
tracking benchmark.

## Relation to the published results — read this first

The validation and benchmark results reported in the associated manuscripts were
produced with release **4.0.0**, which remains available as tag `v4.0.0` and is
the version to check out for exact reproduction of the reported numbers.

Releases 5, 6 and 7 are **subsequent work on the codebase** and were not used to
generate any reported result. This snapshot is archived as the citable state of
the software; the manuscripts cite tag `v4.0.0` as the version under test and
this release as the archived platform.

## Installing this release

Three steps, and the second one is new:

```bash
git clone https://github.com/MarkSant/DRerio-LogAI.git && cd DRerio-LogAI
poetry install
poetry run fetch-weights     # ~200 MB of trained models, required
poetry run zebtrack
```

`fetch-weights` downloads the four trained detector models from this release's
assets and verifies every file against a SHA-256 recorded in
`weights_manifest.json`. They are not in the repository because of their size,
and **the application does not start without them**.

Six models are attached. The four installed by default are the perspective
pair -- one segmentation and one detection model for the lateral view and for
the top-down view -- and they are the ones the weight catalogue discovers by
filename. `--all` adds `best_oi.pt` and `best_seg.pt`, 3-class generalists
that carry a `zup-aqua` class the perspective models do not; they match no
discovery glob and are registered through **Add Weight...**.

A C compiler is required: one dependency (`cython-bbox`) ships only as a source
distribution. Budget about 3 GB of free disk for the virtual environment and the
models together. Full prerequisites in the README.

## Changes since v6.0.0

### Installation and first run — the reason this is a major version

- The trained models are now obtainable. They were git-ignored and no
  instruction anywhere said how to get them, so a fresh clone installed, passed
  the whole test suite — which mocks them — and then failed to open.
  `poetry run fetch-weights` closes that, with checksum verification and a
  download that is discarded rather than kept when it does not verify.
- Starting without models now says which models, in which folder, and which
  command installs them. It previously ran a full hardware benchmark, drew the
  splash to ~95%, and reported only "a fatal error occurred".
- `config.yaml`, `weights/`, `weights_config.json` and the OpenVINO cache are
  resolved against the repository root instead of the working directory, so the
  launch directory no longer decides whether the application finds its own
  configuration.
- `--reset`, `--reset-weights` and `--reset-all` now delete what they promise.
  Run from any other directory they matched nothing, deleted nothing, and still
  printed "Reset complete".
- The installation documentation stopped describing things that do not work: a
  troubleshooting entry invented a configuration key that fails validation and
  prevents the application from opening; both READMEs advised copying the whole
  `config.yaml` into the local override, which permanently shadows later
  defaults; three separate places claimed the models download automatically.

### Live-camera workflow

- Real aquarium width and height can be entered in the live dialog. They were
  validated and used to derive the pixel/cm ratio of every distance, speed and
  cm-based metric, but no widget exposed them — a maze declared square produced
  95.8 px/cm on one axis against 60.1 on the other.
- Live post-analysis uses the project's settings snapshot instead of the shared
  settings object, so a project session is no longer analysed with the
  thresholds left behind by the last ad-hoc run.
- `seg_overlap` no longer degrades unconditionally in live sessions: the mask
  sidecar is written when the rule requires it.
- Re-detecting the arena no longer erases the ROIs.
- A thread lock timeout no longer surfaces as "session cancelled" and removes
  the session from the project.
- Standalone live sessions appear in the Reports tab; the chosen perspective
  reaches the arena detector; real aquarium shape is selectable without editing
  YAML.

### Pre-recorded workflow

- Single-video: "1 animal" reaches the worker, so an artefact no longer becomes
  a second tracked object.
- Aquarium auto-detection honours segmentation, real shape and perspective;
  segmentation no longer returns the whole frame as the arena.
- 15.7 ms per frame of dead waiting removed from the pre-recorded worker.
- Imported arenas reappear in the Zones tab and the ROI button works again.
- Single-video thresholds and properties no longer leak into an open project's
  reports.

### Reporting correctness

- Zones stopped disappearing from the summary, and with it from the unified
  report.
- A basename repeated across days no longer overwrites the summary and loses
  half the animals.
- The sharp-turn threshold now reaches the number it configures.
- The animal bounding box no longer blows up when the fish leaves the frame.
- The Parquet coordinate space is documented.

### Interface and infrastructure

- A destroyed panel no longer raises `TclError` on project rebind; event-bus
  subscriptions no longer outlive the widget that made them.
- Input fields that froze, vanished, or stored a different value than shown.
- Coverage locked to a ratchet, hollow tests removed, the `_extendedN` test
  files consolidated.
- A cross-flow regression net so the pre-recorded pipeline keeps computing the
  numbers it was signed off on.

## Earlier in this line

- **v6.0.0** — English as the default interface language with a pt-BR locale and
  a CI scanner against untranslated strings; closed-loop logger now records the
  frame rate **measured** from capture timestamps in `fps`, with the configured
  value kept separately in `fps_configured` (the camera can exceed the
  configured rate, and in the reported sessions it did); repository curated for
  archiving; `.zenodo.json` added and `CITATION.cff` completed.
- **v5.0.0-rc1** — detector parameter error boundary, UI cleanups, worktree
  tooling.

See `CHANGELOG.md` for the full history.

## Licensing

Original source code: MIT, copyright Universidade Estadual Paulista (UNESP).
**The application as distributed is effectively AGPL-3.0-or-later**, because it
packages and requires Ultralytics YOLO (AGPL-3.0).

The trained YOLOv11 weights attached to this release are Ultralytics derivatives
and are likewise effectively AGPL-3.0. Their training imagery derives from the
ZebraFish-Detection dataset (Roboflow Universe), CC BY 4.0, **attribution
required** — and that obligation travels with the weights, including to anyone
who redistributes the files downloaded from this release.

Companion hardware designs: CERN-OHL-S v2. See `LICENSE` and `NOTICE`.

## Intellectual property

Registered with the Brazilian National Institute of Industrial Property (INPI),
process **BR 51 2026 005215-7**. Patrimonial rights held by UNESP; moral rights
by the authors. A copyright deposit under Brazilian Law 9.609/98, it does not
restrict the open-source licensing above. Public release authorised by the UNESP
technology transfer office (AUIN).

## Requirements

Python ≥ 3.12, < 3.15 · Ultralytics YOLO ≥ 8.3.179 · Intel OpenVINO ~2026.0 ·
PyTorch ≥ 2.8 · NumPy ~2.2 · OpenCV ~4.13. Runs GPU-free on integrated graphics.
Validated on Windows 11. Full dependency pins in `pyproject.toml` /
`poetry.lock`.

## Funding and ethics

FAPESP grant 2023/14200-3. Animal procedures approved by the UNESP Animal Use
Ethics Committee (CEUA), protocol 4806060624.
