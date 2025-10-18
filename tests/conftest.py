import os
import platform
import tkinter as tk
import warnings

import pytest

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


@pytest.fixture
def tkinter_root():
    """
    Fixture for creating a tkinter root window.
    Platform-aware: uses virtual display on Linux, native window on Windows.

    This fixture is necessary for any UI components that are tested.
    """
    display = None

    # Only use virtual display on Linux/Unix systems
    # Windows and macOS can run Tkinter natively during tests
    if platform.system() == "Linux":
        try:
            from pyvirtualdisplay import Display

            display = Display(visible=0, size=(800, 600))
            display.start()
        except ImportError:
            # pyvirtualdisplay not available, try to run without it
            # This will fail in headless environments but works in CI with X11
            pass
        except Exception as e:
            # Failed to start display, continue without it
            warnings.warn(f"Could not start virtual display: {e}", stacklevel=2)

    # Create the tkinter root window
    root = tk.Tk()
    root.withdraw()  # Hide the main window

    # Process pending events to ensure window is fully initialized
    root.update_idletasks()

    yield root

    # Clean up the tkinter window
    try:
        root.destroy()
    except tk.TclError:
        # Window already destroyed, ignore
        pass

    # Clean up the virtual display (if it was created)
    if display is not None:
        try:
            display.stop()
        except Exception:
            # Ignore errors during cleanup
            pass
