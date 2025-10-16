import os
import sys
import warnings
from importlib import util
from unittest.mock import MagicMock

os.environ.setdefault("ZEBTRACK_SUPPRESS_POST_CREATION_GUIDE", "1")
os.environ.setdefault("ZEBTRACK_SUPPRESS_WIZARD_DIALOGS", "1")


def pytest_configure(config):
    """
    Pytest hook to configure warnings before imports.

    Suppresses pkg_resources deprecation warning from docxcompose library.

    Why suppress rather than fix:
    - docxcompose v1.4.0 (latest as of 2025) uses deprecated pkg_resources API
    - docxcompose is an external dependency (required by docxtpl for Word reports)
    - We cannot fix their code, only wait for maintainers to migrate to importlib
    - We pinned setuptools < 81 in pyproject.toml so pkg_resources stays available
    - This suppression hides the warning noise while the upstream fix is pending

    Tracking issue: https://github.com/4teamwork/docxcompose/issues
    Alternative: Migrate from docxtpl to pure python-docx (would lose template features)
    """
    warnings.filterwarnings(
        "ignore",
        category=UserWarning,
        message=".*pkg_resources.*",
    )


import tkinter as tk
import pytest


@pytest.fixture
def tkinter_root():
    """
    Fixture for creating a tkinter root window.
    This is necessary for any UI components that are tested.
    """
    # Create the virtual display
    from pyvirtualdisplay import Display

    display = Display(visible=0, size=(800, 600))
    display.start()

    # Create the tkinter root window
    root = tk.Tk()
    root.withdraw()  # Hide the main window

    yield root

    # Clean up the tkinter window and the virtual display
    root.destroy()
    display.stop()