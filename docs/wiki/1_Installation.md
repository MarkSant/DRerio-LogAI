# Installation Guide

DRerio LogAI currently ships as a Poetry project. The recommended way to run the application is to clone the repository, install the dependencies with Poetry, and launch the GUI from the virtual environment.

## Prerequisites

- Python 3.12 (64-bit). Not 3.11, and not 3.14+ — `pyproject.toml` requires
  `>=3.12,<3.14`, and Poetry refuses to resolve outside that range.

  **If 3.14 is your default `python`, this matters even when 3.12 is also
  installed.** Poetry builds the environment from the interpreter it finds
  first. Point it at 3.12 explicitly before installing:

  ```powershell
  poetry env use 3.12          # or the full path to python.exe
  ```

- [Poetry](https://python-poetry.org/docs/#installation) available on your `PATH`
- Git (to clone the repository)
- **A C compiler.** One dependency (`cython-bbox`) is published only as a source
  distribution, so `poetry install` builds an extension module on every platform:
  Visual Studio Build Tools with the "Desktop development with C++" workload on
  Windows, `build-essential` on Debian/Ubuntu, Xcode Command Line Tools on macOS.
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

## Clone the repository

```powershell
git clone https://github.com/MarkSant/DRerio-LogAI.git
cd DRerio-LogAI
```

> 💡 On Windows, use **PowerShell** (the default shell in the project). On Linux/macOS, any POSIX-compatible shell works.

## Install dependencies with Poetry

```powershell
poetry install
```

The first run may take a few minutes while Poetry resolves and downloads all packages. The command creates an isolated virtual environment that will be reused in subsequent runs.

## Download the detector weights

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

## If `fetch-weights` says there is no module named `zebtrack`

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

```powershell
poetry run zebtrack
```

This command opens the Tkinter GUI. The project creation wizard (5 steps) is enabled by default.

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

## Optional: local configuration overrides

Create `config.local.yaml` in the project root to override specific settings (e.g., to enable experimental features):

```yaml
ui_features:
  use_wizard_for_project_creation: true # padrão
```

Other overrides (detector thresholds, Arduino port, event bus) are documented in `docs/reference/operational_reference.md` and `docs/guides/developer/wizard.md`.

## Troubleshooting

| Symptom                                     | Suggested fix                                                                                                                                |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `poetry install` fails with compiler errors | Ensure you have build tools installed (Visual Studio Build Tools on Windows, `build-essential` on Linux, Xcode Command Line Tools on macOS). |
| GUI does not open and no error appears      | Check `poetry env info` to confirm the virtual environment exists. The launch directory no longer matters: configuration and weights are resolved against the repository root. |
| Models are slow on CPU                      | Convert the active weight to OpenVINO from the model panel in the app (Advanced Settings → Convert to OpenVINO). There is no command-line entry point for this.                |
| Wizard disabled unexpectedly                | Delete `config.local.yaml` or set `ui_features.use_wizard_for_project_creation: true`.                                                       |

For additional help, open an issue on GitHub or consult the reference documentation in `docs/`.
