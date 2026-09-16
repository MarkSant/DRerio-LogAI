# Installation and Setup

This page assumes **no previous experience** with programming, terminals or GitHub. Every term it
uses is explained where it first appears, and every step says how to tell whether it worked.

If you have installed Python projects before, the short version is: install Python 3.12, download
and extract the source ZIP, double-click `install.bat`. Everything else on this page is detail for
when something does not go that way.

Developers: jump to [Installing to develop it](#installing-to-develop-it).

## Contents

- [Before you start](#before-you-start)
- [Step 1 — Install Python](#step-1--install-python)
- [Step 2 — Download DRerio LogAI](#step-2--download-drerio-logai)
- [Step 3 — Extract the ZIP somewhere permanent](#step-3--extract-the-zip-somewhere-permanent)
- [Step 4 — Run the installer](#step-4--run-the-installer)
- [Step 5 — Start the application](#step-5--start-the-application)
- [What if I need the terminal?](#what-if-i-need-the-terminal)
- [Updating to a new version](#updating-to-a-new-version)
- [If `fetch-weights` says there is no module named zebtrack](#if-fetch-weights-says-there-is-no-module-named-zebtrack)
- [Troubleshooting](#troubleshooting)
- [macOS and Linux](#macos-and-linux)
- [Using Git instead of the ZIP](#using-git-instead-of-the-zip)
- [Installing to develop it](#installing-to-develop-it)
- [Local configuration overrides](#local-configuration-overrides)

## Before you start

**Check your computer has room.** The installation needs about **3 GB of free disk space** — most
of it is the scientific libraries (PyTorch, OpenVINO, OpenCV) and about 240 MB of trained models.
8 GB of RAM is the minimum, 16 GB is comfortable.

To see how much space you have on Windows: open **File Explorer** (the yellow folder icon in the
taskbar), click **This PC** on the left, and read the bar under drive C:.

**You do not need a special graphics card.** No NVIDIA card is required. On Intel machines the
analysis is accelerated through OpenVINO instead.

**Allow 15–30 minutes**, most of it unattended downloading.

## Step 1 — Install Python

**What Python is:** the programming language DRerio LogAI is written in. Installing it installs the
engine that runs the application. You will never have to write any Python.

**Which version:** **3.12** (3.13 also works). **Not 3.14** — one of the libraries the application
depends on has no ready-made build for 3.14, and the installation fails in a way that blames the
wrong thing.

1. Open <https://www.python.org/downloads/release/python-3129/>.
2. Scroll to the bottom, to the table titled **Files**.
3. Click **Windows installer (64-bit)**. A file named something like `python-3.12.9-amd64.exe`
   downloads.
4. Open the downloaded file (it is usually in your **Downloads** folder, and your browser shows it
   at the bottom of the window or under the ⤓ icon).
5. **On the first screen of the installer, tick the box "Add python.exe to PATH"** at the bottom,
   *before* clicking anything else.

   > **Why this box matters.** "PATH" is the list of folders Windows searches when a program asks
   > for another program by name. Without the tick, Python is installed but invisible to everything
   > that needs it, and the error messages that follow never mention Python. This is the single
   > most common reason this installation fails.

6. Click **Install Now** and wait. When it finishes, click **Close**.

**How to tell it worked:** the installer's last screen says "Setup was successful". If you want to
be sure, the check is in [What if I need the terminal?](#what-if-i-need-the-terminal).

> **You can skip this step.** The installer in step 4 offers to install Python 3.12 for you, if
> your computer has Windows' own app installer (`winget`, present on Windows 11 and up-to-date
> Windows 10). Doing it yourself first is more predictable, which is why it is step 1.

## Step 2 — Download DRerio LogAI

**What GitHub is:** the website where the software's source code and its official downloads live.
You do not need an account.

1. Open the releases page:
   <https://github.com/MarkSant/DRerio-LogAI/releases>

   A "release" is a published version. The newest one is at the top, marked **Latest**.

2. Under that release, find the section called **Assets** (you may have to click the word
   **Assets** to expand it).

3. Click **Source code (zip)**.

   > **What that file is.** "Source code" sounds like something only a programmer would want, but
   > it is simply the complete application, compressed into one file. This is the normal way to
   > download DRerio LogAI. Do not pick `Source code (tar.gz)` — that is the same thing in a format
   > Windows does not open on its own.
   >
   > The `.pt` files also listed under Assets are the trained models. **You do not need to download
   > them by hand**; the installer fetches them.

The file — `DRerio-LogAI-7.1.0.zip` or similar — lands in your **Downloads** folder.

## Step 3 — Extract the ZIP somewhere permanent

A ZIP is a folder in a box. Windows can look inside without unpacking it, which is a trap: programs
run from inside a ZIP misbehave, so it has to be extracted first.

1. Open **File Explorer** and go to **Downloads**.
2. **Right-click** the downloaded ZIP file and choose **Extract All...**.
3. In the box that appears, replace the suggested destination with something short and permanent,
   for example:

   ```text
   C:\DRerio-LogAI
   ```

4. Click **Extract** and wait.

**Choose that folder carefully.** It becomes the application's home: the models, the settings, the
OpenVINO cache and — unless you choose otherwise — your projects live inside it.

- **Not** `Downloads`, which people empty.
- **Not** a folder synchronised by OneDrive, Google Drive or Dropbox if you can avoid it: they can
  lock or partially download files while the application is using them.
- Avoid accented characters and spaces in the path where you can.

**How to tell it worked:** open the extracted folder. You should see files named `install.bat`,
`pyproject.toml`, `README.md` and a folder called `src`. If instead you see a single folder with a
long name, open it — the real files are one level down, and that inner folder is the one to treat
as the application's home.

## Step 4 — Run the installer

1. In the extracted folder, find **`install.bat`** and **double-click** it.

   > File Explorer may hide the `.bat` ending. Look for the file named `install` with an icon like
   > a small gear or window.

2. **Windows may show a blue box: "Windows protected your PC".** This appears because the file was
   downloaded from the internet, not because anything is wrong with it. Click **More info**, then
   **Run anyway**.

3. A black window opens and reports what it is doing, in four steps:

   ```text
   [1/4] Checking Python
   [2/4] Checking Poetry
   [3/4] Installing dependencies (this takes several minutes)
   [4/4] Downloading detector models (~250 MB)
   ```

4. **It may ask you one or two questions**, and the answer to both is yes — press `Y` and Enter:

   - *"Install Python 3.12 now?"* — only if step 1 was skipped or did not take effect.
   - *"Install Poetry now?"* — **Poetry** is the tool that downloads the ~1.7 GB of libraries the
     application needs. The installer fetches it from its official site and puts it where Windows
     can find it, which is work you would otherwise have to do by hand.

5. Wait. Step 3 takes several minutes and shows little; step 4 downloads about 240 MB. The window
   finishes with:

   ```text
   Setup complete.
   Start the application from the "DRerio LogAI" icon on your Desktop.
   ```

6. Press a key to close the window.

**If it stops early**, the last message is in yellow and says what to do about it. The installer
stops at the first failing step on purpose — see [Troubleshooting](#troubleshooting) below. Run
`install.bat` again after fixing the cause: it continues rather than starting over.

## Step 5 — Start the application

Double-click the **DRerio LogAI** icon on your Desktop (there is one in the Start Menu too).

The first launch:

1. Asks which language you want. Your answer is saved; change it later in
   **Settings → Language...**.
2. Shows a splash screen while it measures your hardware and picks the fastest way to run the
   models. **This is the slowest launch you will have** — the result is cached.
3. Opens the main window, and then a **Getting started** window explaining the detector models and
   whether OpenVINO is worth enabling on your machine.

What to do next: [Getting started with your first project](user-guide/GETTING_STARTED.md).

## What if I need the terminal?

Most people never need it. It is worth knowing anyway, because troubleshooting instructions are
written as commands.

**What the terminal is:** a window where you type commands instead of clicking. On Windows the one
this project uses is called **PowerShell**.

**To open it in the right folder** (this matters — commands act on the folder you are in):

1. Open the application's folder in File Explorer (`C:\DRerio-LogAI`).
2. Click the address bar at the top, type `powershell` over the path, and press Enter.

A blue or black window opens, showing the folder path and a `>` prompt.

**To run a command:** type it (or right-click to paste) and press Enter. The command is finished
when the `>` prompt returns. Some commands take minutes and print nothing meanwhile — that is
normal.

Useful checks:

```powershell
python --version
```

Prints e.g. `Python 3.12.9`. If it prints nothing, opens the Microsoft Store, or reports a version
starting with 3.14, that is the problem to fix first.

```powershell
poetry run zebtrack
```

Starts the application, printing any error that the desktop shortcut would have hidden.

```powershell
poetry run fetch-weights --check
```

Verifies the trained models without downloading anything.

> **"Open a new terminal"** appears in some instructions. It means: close the window and open
> another one. A terminal reads the PATH once, when it opens, so a program installed after that
> is invisible to it until then.

## Updating to a new version

1. Download and extract the new ZIP, as in steps 2 and 3, into a **new** folder.
2. From the old folder, copy across:
   - `config.local.yaml` — your settings, including the language and camera;
   - the `weights/` folder — so the models are not downloaded again;
   - any project folders you kept inside the application folder.
3. Double-click `install.bat` in the new folder.
4. Delete the old folder once the new one works.

**Re-run `install.bat` after moving the folder**, too. The desktop shortcut stores an absolute path,
so moving the folder leaves it pointing at nothing. (It only recreates the shortcut; nothing is
downloaded again.)

## If `fetch-weights` says there is no module named zebtrack

```text
ModuleNotFoundError: No module named 'zebtrack'
```

The message names the symptom, not the cause. It means the installation did not finish putting the
application itself in place, so its commands point at something that is not there. Two things
produce it:

**The environment is on the wrong Python.** Check:

```powershell
poetry env info --path
poetry run python -V
```

Anything other than 3.12 or 3.13 explains it: the pinned NumPy publishes no build above 3.13, so on
3.14 the install tries to compile it from source, fails, and leaves the project uninstalled. Rebuild
on 3.12:

```powershell
poetry env use 3.12
poetry install
```

**Or the environment predates the command.** `fetch-weights` arrived in 7.0.0. An environment
created from an earlier checkout has no such command; re-running `poetry install` after the upgrade
creates it.

## Troubleshooting

| Symptom | What it means and what to do |
| --- | --- |
| The installer says "No supported Python found" | Python is missing, or was installed without "Add python.exe to PATH". Reinstall it with the box ticked (step 1), then run `install.bat` again |
| It says Poetry could not be installed | Usually no internet, or a proxy/firewall blocking `install.python-poetry.org`. Try again on another connection, or install Poetry by hand: <https://python-poetry.org/docs/#installation> |
| `poetry install` failed | Nothing here needs a compiler. The usual causes are a dropped connection or too little free disk (~1.7 GB needed). Fix and re-run `install.bat` |
| "Windows protected your PC" | The file came from the internet. **More info → Run anyway** |
| Double-clicking `install.ps1` opens Notepad | That is expected — Windows does not run `.ps1` files on double-click. Use `install.bat`, which exists for exactly this reason |
| The desktop icon does nothing | The folder was moved or renamed. Re-run `install.bat`, or `scripts\install_shortcut.ps1`. Check `logs/analysis.log` for what the application itself reported |
| The application opens but refuses to track | The models are missing: `poetry run fetch-weights` |
| `ModuleNotFoundError: No module named 'zebtrack'` | [See above](#if-fetch-weights-says-there-is-no-module-named-zebtrack) |
| Analysis is very slow | Enable OpenVINO in **Settings → Model settings...** and convert the weights you use; raise the analysis interval |
| The wizard does not appear | Delete `config.local.yaml`, or set `ui_features.use_wizard_for_project_creation: true` |

More: [Troubleshooting guide](user-guide/TROUBLESHOOTING.md) · [FAQ](3_FAQ.md).

## macOS and Linux

### Debian / Ubuntu

```bash
git clone https://github.com/MarkSant/DRerio-LogAI.git
cd DRerio-LogAI
./setup.sh
```

`setup.sh` installs the system packages (including the Tk bindings), Poetry through pipx, the
Python dependencies and the models, and creates a `.desktop` launcher. Flags: `--skip-weights`,
`--skip-launcher`.

On other distributions, install Python 3.12, `python3.12-tk` (or your distribution's equivalent)
and [Poetry](https://python-poetry.org/docs/#installation), then follow the macOS commands below.

### macOS

```bash
brew install python@3.12        # or the installer from python.org
curl -sSL https://install.python-poetry.org | python3 -
git clone https://github.com/MarkSant/DRerio-LogAI.git
cd DRerio-LogAI
poetry install
poetry run fetch-weights
poetry run zebtrack
```

The Tkinter window appears in the Dock. There is no launcher script for macOS yet; start it with
`poetry run zebtrack`.

## Using Git instead of the ZIP

**Git** is a tool that downloads the code and keeps it updatable with one command. It is optional
— the ZIP gives you exactly the same files — but if you plan to update often, it saves the copying
described under [Updating](#updating-to-a-new-version).

Install it from <https://git-scm.com/download/win> (accept every default), then, in a terminal:

```powershell
git clone https://github.com/MarkSant/DRerio-LogAI.git
cd DRerio-LogAI
powershell -ExecutionPolicy Bypass -File install.ps1
```

To update later:

```powershell
git pull
powershell -ExecutionPolicy Bypass -File install.ps1
```

## Installing to develop it

The same steps with the development dependency group, and no launcher:

```powershell
git clone https://github.com/MarkSant/DRerio-LogAI.git
cd DRerio-LogAI
poetry install --with dev
poetry run pre-commit install
poetry run fetch-weights
poetry run pytest -q
```

`install.ps1 -Dev` does all of that on Windows, plus the shortcut. Other flags: `-SkipWeights`,
`-SkipShortcut`, `-Yes` (accept every prerequisite offer, for unattended runs).

**About the detector weights.** The trained YOLO models are not stored in the repository because of
their size. `fetch-weights` downloads all six from the release named in `weights_manifest.json` and
verifies every file against a recorded SHA-256; an interrupted or corrupt download is discarded
rather than kept. `--check` validates an existing installation without downloading.

Four of the six are the perspective specialists (`seg` and `det`, lateral and top-down) and are
pre-assigned as defaults. The other two — `best_oi.pt` and `best_seg.pt` — are 3-class generalists
carrying a `zup-aqua` class the specialists lack; they are registered by
`WeightManager.discover_weights()` and appear in the model panel, but claim no default slot.
(Before v7.1.0 they sat behind an `--all` flag and matched no discovery glob, so they were
invisible even when downloaded. The flag is still accepted and now changes nothing.)

### Managing the shortcut

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_shortcut.ps1            # create or repair
powershell -ExecutionPolicy Bypass -File scripts\install_shortcut.ps1 -NoDesktop # Start Menu only
powershell -ExecutionPolicy Bypass -File scripts\install_shortcut.ps1 -Remove    # delete
```

The shortcut targets `.venv\Scripts\pythonw.exe -m zebtrack`: `pythonw` so no console window sits
behind the application (closing that console would kill a running analysis), and `-m zebtrack`
because the console script Poetry generates is a launcher that reintroduces one. Diagnostics go to
`logs/analysis.log` regardless of how the application was started.

The script refuses to write a shortcut whose environment cannot import `zebtrack`, so a broken
install is reported now rather than as a window that opens and vanishes.

## Local configuration overrides

**There is no setup step here.** `config.local.yaml` is created for you on first run — answering the
language question is what writes it — and the settings an operator needs are all reachable from the
interface:

| Setting | Where it is chosen |
| --- | --- |
| Interface language | **Settings → Language...** |
| Detector models, roles, OpenVINO | **Settings → Model settings...** |
| Camera | Project wizard (live projects); later, the session detail dialog |
| Arduino port | The Arduino panel, which lists the ports it detects |
| Detector thresholds, ROI rule | The wizard's model step, the configuration editor and the analysis panel |

**Camera and Arduino port live in the project, and the project's value wins.** `ProjectInitializer`
reads `project_data["arduino_port"]` first and only falls back to `settings.arduino.port`, so
setting them globally by hand has no effect on a project that carries its own — which is every
project the wizard creates. Use the global file for a genuinely machine-wide default, not to
configure a study.

To override something the interface does not expose, put in the file *only* the keys you are
changing:

```yaml
ui_features:
  use_wizard_for_project_creation: true # default
```

> Do **not** copy the whole `config.yaml` into it. The two are merged recursively, so a full copy
> freezes every current default onto this machine and silently shadows every later correction.

Other overrides (detector thresholds, event bus) are documented in
`docs/reference/operational_reference.md` and `docs/guides/developer/wizard.md`.
