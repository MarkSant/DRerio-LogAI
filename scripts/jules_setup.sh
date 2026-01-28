#!/bin/bash

# jules_setup.sh - Non-interactive setup script for Google Jules Agent
# Wraps the standard setup.sh with necessary environment flags for automation.

set -e

# Ensure non-interactive mode for apt-get
export DEBIAN_FRONTEND=noninteractive

echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
echo "  🚀 Starting Jules Agent Environment Setup"
echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"

# Define environment variables useful for CI/Agent environments
export CI=true
export DISPLAY=:99  # Setup for Xvfb (Virtual Framebuffer)

# Force Poetry to create a virtualenv, overriding any local poetry.toml settings (create=false)
# This prevents PEP 668 "externally-managed-environment" errors in the agent environment.
export POETRY_VIRTUALENVS_CREATE=true
export POETRY_VIRTUALENVS_IN_PROJECT=true

# Check if we are in a Jules environment (or similar CI)
# We can proceed to run the main setup script.
# The main setup script handles apt-get, pipx, poetry, and dependencies.

if [ -f "./setup.sh" ]; then
    chmod +x ./setup.sh
    ./setup.sh
else
    echo "❌ Error: ./setup.sh not found!"
    exit 1
fi

# Ensure the git working tree is clean (discarding permission changes or other artifacts)
# This satisfies Jules' verification requirement.
git checkout .

echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
echo "  ✅ Jules Setup Complete"
echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
exit 0
