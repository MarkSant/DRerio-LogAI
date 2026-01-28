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

echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
echo "  ✅ Jules Setup Complete"
echo "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
