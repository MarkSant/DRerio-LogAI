#!/bin/bash

# setup.sh - Environment setup script for DRerio LogAI
# This script installs necessary system dependencies, python packages,
# and verifies the installation.

set -e  # Exit immediately if a command exits with a non-zero status.

echo "========================================="
echo "Starting DRerio LogAI Environment Setup"
echo "========================================="

# 1. Install System Dependencies via apt-get
# We need sudo for apt-get. In some environments (like Docker containers running as root),
# sudo might not be needed or available. We check for it.
echo "[1/5] Installing system dependencies..."

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
echo "[2/5] Configuring python tools..."
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
echo "[3/5] Installing Python dependencies with Poetry..."

# Install dependencies
poetry install

# 5. Verify Setup
echo "[4/5] Verifying setup..."
# We run the verification script inside the poetry environment
poetry run python scripts/verify_setup.py

echo "========================================="
echo "✅ Setup Complete! Environment is ready."
echo "========================================="
