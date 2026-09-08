#!/bin/bash

# setup.sh - Environment setup script for DRerio LogAI (Debian/Ubuntu)
# This script installs necessary system dependencies, python packages, the
# detector weights, and a desktop launcher, then verifies the installation.
#
# The Windows equivalent is install.ps1 (or install.bat for a double-click).
#
# Options:
#   --skip-weights   do not download the detector models
#   --skip-launcher  do not create the .desktop entry

set -e  # Exit immediately if a command exits with a non-zero status.

SKIP_WEIGHTS=0
SKIP_LAUNCHER=0
for arg in "$@"; do
    case "$arg" in
        --skip-weights) SKIP_WEIGHTS=1 ;;
        --skip-launcher) SKIP_LAUNCHER=1 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================="
echo "Starting DRerio LogAI Environment Setup"
echo "========================================="

# 1. Install System Dependencies via apt-get
# We need sudo for apt-get. In some environments (like Docker containers running as root),
# sudo might not be needed or available. We check for it.
echo "[1/6] Installing system dependencies..."

SUDO=""
if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
fi

# Update package lists
$SUDO apt-get update

# Install libraries required for OpenCV (headless), Tkinter, and general build tools
# - python3-tk: Required for Tkinter
# - libgl1, libsm6, libxext6: Standard OpenCV dependencies on Linux
# - xvfb: Virtual Framebuffer for headless UI testing
# - ffmpeg: Video processing support
$SUDO apt-get install -y \
    python3-tk \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    xvfb \
    ffmpeg

# 2. Install pipx if not present (it usually is in many dev images, but good to ensure)
echo "[2/6] Configuring python tools..."
if ! command -v pipx >/dev/null 2>&1; then
    python3 -m pip install --user pipx
    export PATH="$HOME/.local/bin:$PATH"
fi

# 3. Install Poetry via pipx (Isolated)
# We use pipx to install tools in isolation, which is the PEP 668 compliant way.
if ! command -v poetry >/dev/null 2>&1; then
    echo "Installing Poetry via pipx..."
    # Ensure pipx path is available for this session
    export PATH="$HOME/.local/bin:$PATH"
    pipx install poetry

    # Ensure poetry is on path immediately
    export PATH="$HOME/.local/bin:$PATH"
else
    echo "Poetry is already installed."
fi

# 4. Install Project Dependencies
echo "[3/6] Installing Python dependencies with Poetry..."

# Install dependencies
poetry install

# Poetry reports success for a run that resolved every dependency and still
# left the project itself uninstalled -- the state that surfaces one command
# later as "No module named 'zebtrack'", naming the wrong cause. Check here,
# where the fix is still obvious.
if ! poetry run python -c "import zebtrack" >/dev/null 2>&1; then
    echo "" >&2
    echo "Dependencies installed, but the 'zebtrack' package did not." >&2
    echo "Check the interpreter with 'poetry run python -V' -- it must report" >&2
    echo "3.12 or 3.13. If not, remove .venv and run this script again." >&2
    exit 1
fi

# 5. Download detector weights
echo "[4/6] Downloading detector models (~200 MB)..."
if [ "$SKIP_WEIGHTS" -eq 1 ]; then
    echo "Skipped (--skip-weights)."
else
    # Required, not optional: the application refuses to start without them.
    poetry run fetch-weights
fi

# 6. Desktop launcher
echo "[5/6] Creating desktop launcher..."
if [ "$SKIP_LAUNCHER" -eq 1 ]; then
    echo "Skipped (--skip-launcher)."
else
    # Exec points at the venv interpreter directly rather than at `poetry run`:
    # a desktop launcher has no shell, so it has neither poetry on PATH nor the
    # working directory poetry expects. zebtrack.paths anchors config and
    # weights to the repository root, so launching from anywhere is fine.
    VENV_PYTHON="$(poetry env info --executable 2>/dev/null || true)"
    ICON="$REPO_ROOT/src/zebtrack/ui/assets/drerio_logai.ico"
    APPS_DIR="$HOME/.local/share/applications"
    if [ -z "$VENV_PYTHON" ] || [ ! -x "$VENV_PYTHON" ]; then
        echo "Could not locate the virtualenv interpreter; skipping the launcher." >&2
        echo "Start the application with: poetry run zebtrack" >&2
    else
        mkdir -p "$APPS_DIR"
        cat > "$APPS_DIR/drerio-logai.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=DRerio LogAI
Comment=Zebrafish tracking and behavioral analysis
Exec=$VENV_PYTHON -m zebtrack
Path=$REPO_ROOT
Icon=$ICON
Terminal=false
Categories=Science;Education;
EOF
        chmod +x "$APPS_DIR/drerio-logai.desktop"
        # Best-effort: without a database refresh some desktops only show the
        # entry after the next login.
        command -v update-desktop-database >/dev/null 2>&1 &&
            update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
        echo "Launcher created: $APPS_DIR/drerio-logai.desktop"
    fi
fi

# 7. Verify Setup
echo "[6/6] Verifying setup..."
# We run the verification script inside the poetry environment
poetry run python scripts/verify_setup.py

echo "========================================="
echo "✅ Setup Complete! Environment is ready."
echo "========================================="
echo "Start it from your applications menu (\"DRerio LogAI\"),"
echo "or with: poetry run zebtrack"
