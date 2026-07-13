# Installation Guide

DRerio LogAI currently ships as a Poetry project. The recommended way to run the application is to clone the repository, install the dependencies with Poetry, and launch the GUI from the virtual environment.

## Prerequisites

- Python 3.12 (64-bit)
- [Poetry](https://python-poetry.org/docs/#installation) available on your `PATH`
- Git (to clone the repository)
- GPU with CUDA (optional) or Intel OpenVINO runtime (optional) for accelerated inference

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
| GUI does not open and no error appears      | Confirm you ran `poetry run zebtrack` from inside the project folder; check `poetry env info` to ensure the virtual environment is created.  |
| Models are slow on CPU                      | Convert weights to OpenVINO (`python -m zebtrack.core.weight_manager`) or run on a CUDA-capable GPU.                                         |
| Wizard disabled unexpectedly                | Delete `config.local.yaml` or set `ui_features.use_wizard_for_project_creation: true`.                                                       |

For additional help, open an issue on GitHub or consult the reference documentation in `docs/`.
