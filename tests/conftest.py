import os
import platform
import tkinter as tk
import warnings

import pytest

os.environ.setdefault("ZEBTRACK_SUPPRESS_POST_CREATION_GUIDE", "1")
os.environ.setdefault("ZEBTRACK_SUPPRESS_WIZARD_DIALOGS", "1")


def pytest_configure(config):
    """
    Pytest hook to configure warnings and test execution settings.

    1. Suppresses pkg_resources deprecation warning from docxcompose library.

    Why suppress rather than fix:
    - docxcompose v1.4.0 (latest as of 2025) uses deprecated pkg_resources API
    - docxcompose is an external dependency (required by docxtpl for Word reports)
    - We cannot fix their code, only wait for maintainers to migrate to importlib
    - We pinned setuptools < 81 in pyproject.toml so pkg_resources stays available
    - This suppression hides the warning noise while the upstream fix is pending

    Tracking issue: https://github.com/4teamwork/docxcompose/issues
    Alternative: Migrate from docxtpl to pure python-docx (would lose template features)

    Note: GUI test serial execution enforcement was moved to pytest_cmdline_main
    hook because it must run before xdist spawns workers.
    """
    warnings.filterwarnings(
        "ignore",
        category=UserWarning,
        message=".*pkg_resources.*",
    )


@pytest.fixture(scope="session")
def test_settings():
    """
    Fixture for loading settings in tests.

    This fixture loads the configuration from config.yaml once per test session
    and provides a Settings instance for dependency injection in tests.

    Usage:
        def test_something(test_settings):
            manager = WeightManager(settings_obj=test_settings)
            assert manager is not None
    """
    from zebtrack.settings import load_settings

    return load_settings()


@pytest.fixture(scope="session")
def tkinter_session_root():
    """
    Session-scoped fixture for a shared tkinter root window.

    This avoids the Tkinter bug on Windows where multiple Tk() instances
    can corrupt the Tcl/Tk library paths.
    """
    display = None

    # Only use virtual display on Linux/Unix systems
    if platform.system() == "Linux":
        try:
            from pyvirtualdisplay import Display

            display = Display(visible=False, size=(800, 600))
            display.start()
        except ImportError:
            pass
        except Exception as e:
            warnings.warn(f"Could not start virtual display: {e}", stacklevel=2)

    # Create the tkinter root window (once per session)
    root = tk.Tk()
    root.withdraw()
    root.update_idletasks()

    yield root

    # Clean up at end of session
    try:
        root.quit()
        root.destroy()
    except Exception:
        pass

    if display is not None:
        try:
            display.stop()
        except Exception:
            pass


@pytest.fixture
def tkinter_root(tkinter_session_root):
    """
    Function-scoped fixture that reuses the session root.

    Creates a Toplevel window for each test to ensure isolation,
    avoiding the Tkinter multi-instance bug on Windows.
    """
    # Create a Toplevel window for this test (not a new Tk instance)
    test_window = tk.Toplevel(tkinter_session_root)
    test_window.withdraw()
    test_window.update_idletasks()

    yield test_window

    # Clean up only this test's window
    try:
        # Destroy all child widgets
        for widget in test_window.winfo_children():
            try:
                widget.destroy()
            except Exception:
                pass

        # Destroy the test window
        test_window.update_idletasks()
        test_window.destroy()
    except tk.TclError:
        pass
    except Exception:
        pass
