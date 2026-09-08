# DRerio LogAI v7.1.0

The first-run release. v7.0.0 made the software citable; the work since then has
been about the interval between double-clicking the icon and starting the first
analysis — the part a researcher meets before any of the science.

This release supersedes the unreleased 7.0.1 entry in the changelog: v7.0.0 is
the only tag published so far, so everything below has accumulated since it.

## Relation to the published results

Unchanged from v7.0.0. The validation and benchmark results reported in the
associated manuscripts were produced with release **4.0.0**, available as tag
`v4.0.0`, which remains the version to check out for exact reproduction. Releases
5 through 7 are subsequent work on the codebase and were not used to generate any
reported result.

## Installing this release

On Windows, download the source ZIP from this page and double-click
`install.bat`. It checks Python, checks Poetry, pins the environment to a
supported interpreter, installs the dependencies, downloads the models and
creates a **DRerio LogAI** icon on the Desktop and in the Start Menu.

From a terminal, on any platform:

```bash
git clone https://github.com/MarkSant/DRerio-LogAI.git && cd DRerio-LogAI
poetry install
poetry run fetch-weights     # ~240 MiB of trained models, required
poetry run zebtrack
```

No C compiler is needed any more — every dependency installs from a prebuilt
wheel. Budget about 3 GB of free disk for the virtual environment and the models
together. Python 3.12 or 3.13; **not** 3.14, where the pinned numpy has no wheel.

### All six models are now installed

`fetch-weights` downloads **all six** trained models and verifies every file
against a SHA-256 recorded in `weights_manifest.json`. Previously it installed
four and left the two generalists — `best_oi.pt` and `best_seg.pt` — behind an
`--all` flag.

The reason they were excluded turned out to be circular. They were skipped
*because* the weight catalogue could not discover them: discovery globbed only
`best_*_lateral.pt` and `best_*_topdown.pt`, so a downloaded generalist landed in
`weights/` and never appeared in the model panel. Fetching a file nothing could
select was pointless. The discovery gap was the real defect; with it fixed, the
download no longer has to model it. `--all` is still accepted and now changes
nothing.

The four specialists remain the defaults. They are trained for a specific camera
angle — a lateral model on a top-down scene returns nothing — so a generalist is
registered but never claims a default slot; it is something you opt into from the
model panel.

**The model assets for this release are the same files published on `v7.0.0`,
byte for byte**, and `weights_manifest.json` still points there. That is
deliberate: the manifest names a published release, so `fetch-weights` works
immediately rather than depending on this page.

## What changed

### The icon no longer looks dead for four seconds

The splash screen was created *after* the import block that builds the
coordinator graph, so the window only appeared once the heavy loading had already
finished. Under the desktop shortcut the app runs through `pythonw.exe` with no
console, so there was nothing at all to see: no window, no cursor change, no
taskbar entry.

Two costs sat in front of it, both looking like ordinary import lines —
`zebtrack.utils` imports torch in its module body (~1.1 s), and the DI
registration block pulls ultralytics, cv2 and matplotlib on top of it (~3 s).
The splash is now built before both, and the heavy loading runs under a progress
message.

### The first-run benchmark now measures something

Its inference steps are guarded on an OpenVINO model existing, and on a fresh
install nothing has been converted yet — so every measurement step was skipped.
The whole benchmark finished in 0.2 seconds and recommended CPU at 0.0 FPS. That
result was then cached and never recomputed, leaving the machine configured from
a measurement that never happened.

It now converts one model to OpenVINO before measuring. This is not added
overhead: it is work the application pays anyway the first time OpenVINO is used
for real, moved out of your first analysis and into a moment where the splash can
explain the wait. A run that still measures nothing is marked inconclusive and is
**not** cached, so it retries on the next launch instead of freezing a guess.

The seven benchmark steps are also legible now. They were always sent to the
splash, but several finish in milliseconds and were overwritten within a single
frame, so the sequence existed only in the log.

### A getting-started window, and a menu entry that should have existed

Opening the application for the first time gave you a complete interface and no
indication of what to do first — in particular, no hint that the six models need
assigning to roles. Worse, the model configuration panel had **no menu entry at
all**: it was reachable only from a button inside a project view.

There is now a getting-started window after the main window opens, explaining the
models, the four roles they fill, and whether OpenVINO is worth enabling on
*your* machine — it reads the detected hardware and names the devices rather than
offering generic advice. It is reachable afterwards from **Help → Getting
Started**, and the panel itself from **Settings → Model settings**.

### Installing and launching without a terminal (from the unreleased 7.0.1 work)

- `install.ps1` / `install.bat` and `setup.sh`: guided installation that stops at
  the first failing step and says what to do about it.
- A desktop and Start Menu shortcut targeting `pythonw.exe -m zebtrack`.
- **Logging died on every record without a console.** `StreamHandler(sys.stdout)`
  under `pythonw` got `None`, and the fallback to `sys.stderr` is `None` too —
  every record raised inside `emit`, silently.
- **Camera detection needed a stderr to silence.** A failed redirect closed the
  process's real stderr; the wizard then listed no cameras at all.
- **The very first launch hung on a window that was never drawn.** The language
  chooser called `transient()` on a withdrawn root, and a transient inherits its
  master's withdrawn state — so `wait_window` blocked forever on a window nobody
  could see, focus or close.
- **A failure before Tk existed vanished without trace.** Startup errors now
  reach a message box instead of a `sys.stderr` that does not exist.

## Full changelog

See [`CHANGELOG.md`](../../CHANGELOG.md) for the complete list with the reasoning
behind each change.
