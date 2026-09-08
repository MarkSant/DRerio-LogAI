# Installation Guide

DRerio LogAI ships as a Poetry project. There are two ways in, and they are not
variations of the same thing:

- **[The guided installer](#the-guided-installer-recommended)** — one script,
  then a desktop icon. Written for whoever runs experiments with the software.
  Skip the rest of this page unless it fails.
- **[Step by step](#step-by-step)** — the same operations spelled out, for
  anyone modifying the code or working on a machine where the script cannot run.

## The guided installer (recommended)

Install [Python 3.12](https://www.python.org/downloads/release/python-3129/)
(tick **"Add python.exe to PATH"** on the installer's first screen) and
[Poetry](https://python-poetry.org/docs/#installation), download the repository
— [**Source code (zip)**](https://github.com/MarkSant/DRerio-LogAI/releases)
extracted somewhere permanent, or `git clone` — then:

```powershell
# Windows: double-click install.bat, or from a terminal:
powershell -ExecutionPolicy Bypass -File install.ps1
```

```bash
# Debian/Ubuntu:
./setup.sh
```

It installs the dependencies, downloads the ~200 MB of detector models, verifies
that the package actually imports, and creates a **DRerio LogAI** launcher on the
desktop and in the applications menu. Double-click that to start the app.

Flags: `-Dev` adds the development group and the pre-commit hooks;
`-SkipWeights` and `-SkipShortcut` skip those steps (`--skip-weights` and
`--skip-launcher` on `setup.sh`).

> **Why `install.bat` and not just the `.ps1`?** Windows does not run a `.ps1`
> on double-click — Explorer opens it in an editor — and the default execution
> policy on a client OS refuses scripts outright. A script extracted from a
> downloaded ZIP is blocked even at `RemoteSigned`, because it carries the Mark
> of the Web. `install.bat` is one line that launches PowerShell with the policy
> bypassed **for that process only**; it changes nothing on the machine.

## Step by step

### Prerequisites

- Python 3.12 (64-bit). Not 3.11, and not 3.14+ — `pyproject.toml` requires
  `>=3.12,<3.14`, and Poetry refuses to resolve outside that range.

  **If 3.14 is your default `python`, this matters even when 3.12 is also
  installed.** Poetry builds the environment from the interpreter it finds
  first. Point it at 3.12 explicitly before installing:

  ```powershell
  poetry env use 3.12          # or the full path to python.exe
  ```

- [Poetry](https://python-poetry.org/docs/#installation) available on your `PATH`
- Git, if you clone rather than download the ZIP
- **No C compiler.** Every dependency installs from a prebuilt wheel. Earlier
  releases needed a toolchain for `cython-bbox`; that IoU routine is NumPy now,
  so nothing is compiled during installation.
- **About 3 GB of free disk.** The virtual environment lands around 1.7 GB
  (PyTorch, OpenVINO, OpenCV and SciPy dominate it) and the detector weights add
  another ~200 MB.
- An Intel Core Ultra NPU is optional and used through OpenVINO when present.

Confirm the versions:

```powershell
python --version
poetry --version
git --version
```

### Clone the repository

```powershell
git clone https://github.com/MarkSant/DRerio-LogAI.git
cd DRerio-LogAI
```

> 💡 On Windows, use **PowerShell** (the default shell in the project). On Linux/macOS, any POSIX-compatible shell works.

### Install dependencies with Poetry

```powershell
poetry install
```

The first run may take a few minutes while Poetry resolves and downloads all packages. The command creates an isolated virtual environment that will be reused in subsequent runs.

### Download the detector weights

```powershell
poetry run fetch-weights
```

**This step is required.** The trained YOLO models are roughly 200 MB and are not
stored in git, so a fresh clone has none of them and the application refuses to
start until they are present. The command downloads them from the project's
GitHub release and checks every file against a SHA-256 recorded in
`weights_manifest.json`; a corrupt or interrupted download is discarded rather
than kept.

Useful variants:

```powershell
poetry run fetch-weights --check   # verify what is installed, download nothing
poetry run fetch-weights --all     # also fetch the two generalist models
```

The release carries six models and installs four by default. The four are the
perspective pair (`seg` + `det`, lateral and top-down), which
`WeightManager.discover_perspective_weights()` finds by filename. The two
behind `--all` -- `best_oi.pt` and `best_seg.pt` -- are 3-class generalists,
carrying a `zup-aqua` class the perspective models lack. They match no
discovery glob, so register them with **Add Weight...** in the model
configuration panel once downloaded.

### If `fetch-weights` says there is no module named `zebtrack`

```text
ModuleNotFoundError: No module named 'zebtrack'
```

The message names the symptom, not the cause. It means `poetry install` did not
finish installing the project, so the console scripts point at a package that is
not there. Two things produce it:

**The environment is on the wrong Python.** Check first:

```powershell
poetry env info --path
poetry run python -V
```

Anything other than 3.12 or 3.13 explains it: the pinned NumPy publishes no
wheel above cp313, so on 3.14 the install tries to compile NumPy from source and
fails, leaving the project uninstalled. Rebuild the environment on 3.12:

```powershell
poetry env use 3.12
poetry install
```

**Or the environment predates the command.** `fetch-weights` arrived in 7.0.0.
An environment created from an earlier checkout has no such script, and Poetry
warns that it is "an entry point defined in pyproject.toml, but it's not
installed as a script". Re-running `poetry install` after the upgrade creates it.

## Launch the application

Double-click the **DRerio LogAI** icon the installer created on the desktop, or
from a terminal in the repository folder:

```powershell
poetry run zebtrack
```

Either opens the Tkinter GUI. The project creation wizard (5 steps) is enabled
by default.

The shortcut targets `.venv\Scripts\pythonw.exe -m zebtrack`, which is why no
console window sits behind the application. Diagnostics go to
`logs/analysis.log` regardless of how it was launched.

### Managing the shortcut

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_shortcut.ps1            # create or repair
powershell -ExecutionPolicy Bypass -File scripts\install_shortcut.ps1 -NoDesktop # Start Menu only
powershell -ExecutionPolicy Bypass -File scripts\install_shortcut.ps1 -Remove    # delete
```

**Re-run it after moving the repository folder.** A `.lnk` stores an absolute
path, so a move leaves it pointing at an interpreter that is no longer there.
The script refuses to write a shortcut whose environment cannot import
`zebtrack`, so a stale or broken install is reported now rather than as a window
that opens and vanishes.

### Useful commands

```powershell
# Inspect CLI options
poetry run python -m zebtrack --help

# Run the automated test suite
poetry run pytest -q

# Run Ruff static checks
poetry run ruff check .
```

## Platform notes

### Windows

- If you have multiple Python versions installed, ensure `python` maps to the 3.12 interpreter.
- When Poetry prompts to install in the system-wide location, answer "Yes".
- To keep dependencies isolated, prefer `poetry run ...` instead of manually activating the virtual environment.

### macOS

- Install Python 3.12 via [Homebrew](https://brew.sh/) (`brew install python@3.12`) or the official installer.
- Install Poetry with `curl -sSL https://install.python-poetry.org | python3 -` (see Poetry docs for alternatives).
- Launch the app with `poetry run zebtrack` from Terminal; the Tkinter window will appear in the Dock.

### Linux

- Ensure system packages for Tkinter are installed (e.g., `sudo apt install python3.12-tk` on Ubuntu-based distributions).
- Make sure your user can access the GPU driver (if using CUDA).

## Local configuration overrides

**There is no setup step here.** `config.local.yaml` is created for you on first
run — answering the language prompt is what writes it — and the settings an
operator needs are all reachable from the interface:

| Setting                   | Where it is chosen                                                |
| ------------------------- | ----------------------------------------------------------------- |
| Interface language        | **Settings → Language**                                            |
| Camera                    | Project Wizard (live projects); later, the session detail dialog   |
| Arduino port              | The Arduino panel, which lists the ports it detects                |
| Detector thresholds, ROI  | The configuration editor and the analysis panel                    |

**Camera and Arduino port live in the project, and the project's value wins.**
`ProjectInitializer` reads `project_data["arduino_port"]` first and only falls
back to `settings.arduino.port`, so setting them globally by hand has no effect
on a project that carries its own — which is every project the wizard creates.
Use the global file for a genuinely machine-wide default, not to configure a
study.

To override something the UI does not expose, put in the file _only_ the keys
you are changing:

```yaml
ui_features:
  use_wizard_for_project_creation: true # default
```

> Do **not** copy the whole `config.yaml` into it. The two are merged
> recursively, so a full copy freezes every current default onto this machine
> and silently shadows every later correction.

Other overrides (detector thresholds, event bus) are documented in
`docs/reference/operational_reference.md` and `docs/guides/developer/wizard.md`.

## Troubleshooting

| Symptom                                     | Suggested fix                                                                                                                                |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `poetry install` fails                      | Nothing here needs a compiler — every dependency ships as a wheel. Check the interpreter (`poetry run python -V`, must be 3.12 or 3.13), the network, and free disk (~1.7 GB). |
| The desktop icon does nothing               | Re-run `scripts\install_shortcut.ps1`; a moved repository folder leaves the shortcut pointing at a path that no longer exists. Check `logs/analysis.log` for what the app itself reported. |
| GUI does not open and no error appears      | Check `poetry env info` to confirm the virtual environment exists. The launch directory no longer matters: configuration and weights are resolved against the repository root. |
| Models are slow on CPU                      | Convert the active weight to OpenVINO from the model panel in the app (Advanced Settings → Convert to OpenVINO). There is no command-line entry point for this.                |
| Wizard disabled unexpectedly                | Delete `config.local.yaml` or set `ui_features.use_wizard_for_project_creation: true`.                                                       |

For additional help, open an issue on GitHub or consult the reference documentation in `docs/`.
