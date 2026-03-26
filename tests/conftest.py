import logging
import os
import platform
import tkinter as tk
import warnings
from typing import Any

import pytest
import structlog

os.environ.setdefault("ZEBTRACK_SUPPRESS_POST_CREATION_GUIDE", "1")
os.environ.setdefault("ZEBTRACK_SUPPRESS_WIZARD_DIALOGS", "1")
# Suppress console logs during tests - this env var is checked by logging_config.py
os.environ["ZEBTRACK_SUPPRESS_CONSOLE_LOGS"] = "1"
HEADLESS_TESTS = os.environ.get("ZEBTRACK_HEADLESS_TESTS", "0") == "1"


def _can_initialize_tk() -> bool:
    try:
        root = tk.Tk()
        root.withdraw()
        root.destroy()
    except tk.TclError:
        return False
    return True


if not HEADLESS_TESTS:
    # Skip GUI tests when Tk cannot initialize (missing Tcl/Tk or no display).
    HEADLESS_TESTS = not _can_initialize_tk()


class _NullHandler(logging.Handler):
    """A handler that does nothing - discards all logs."""

    def emit(self, record):
        pass


def _configure_silent_logging():
    """Configure logging to be silent during tests.

    This must run BEFORE any ZebTrack modules are imported to prevent
    console output from structlog loggers created at module level.
    """
    # Configure root logger with NullHandler only
    root_logger = logging.getLogger()

    # Remove any existing handlers (especially StreamHandlers)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add only a NullHandler - this prevents "No handlers" warnings
    # and ensures no output to console
    root_logger.addHandler(_NullHandler())
    root_logger.setLevel(logging.DEBUG)

    # Configure structlog to NOT output anything to console
    # Use a simple processor chain that goes nowhere
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,  # Don't cache to allow reconfiguration
    )


def _create_mock_tk_root():
    from unittest.mock import MagicMock

    root = MagicMock()
    root._w = "."
    root.children = {}
    root.tk = MagicMock()
    root.tk.call = MagicMock(return_value=())
    root.winfo_id = MagicMock(return_value=12345)
    root.destroy = MagicMock()
    root.quit = MagicMock()
    root.update_idletasks = MagicMock()
    root.after = MagicMock()
    root.after_cancel = MagicMock()
    return root


# Run IMMEDIATELY at import time, BEFORE any other imports
_configure_silent_logging()


@pytest.fixture(scope="session", autouse=True)
def suppress_tk_variable_finalizer_errors():
    """Prevent noisy Tkinter RuntimeError when Variable objects are GC'd post-tests."""
    original_del = getattr(tk.Variable, "__del__", None)

    def safe_del(self, *args, **kwargs):
        if not original_del:
            return
        try:
            original_del(self, *args, **kwargs)
        except RuntimeError as exc:
            if "main thread is not in main loop" in str(exc):
                return
            raise

    tk.Variable.__del__ = safe_del  # type: ignore[method-assign]
    yield


@pytest.fixture(autouse=True)
def mock_tkinter_dialogs(request):
    """
    Automatically mock tkinter messagebox and filedialog for GUI tests.

    This prevents modal dialogs from blocking test execution on Windows.
    Only applies to tests marked with @pytest.mark.gui.

    The mocks return sensible defaults:
    - messagebox functions return True/False as appropriate
    - filedialog functions return empty string (cancelled dialog)
    """
    from unittest.mock import MagicMock, patch

    # Only apply to tests marked with 'gui'
    if "gui" not in [marker.name for marker in request.node.iter_markers()]:
        yield
        return

    # Create mock functions with appropriate return values
    mock_messagebox = MagicMock()
    mock_messagebox.showinfo = MagicMock(return_value=None)
    mock_messagebox.showwarning = MagicMock(return_value=None)
    mock_messagebox.showerror = MagicMock(return_value=None)
    mock_messagebox.askokcancel = MagicMock(return_value=True)
    mock_messagebox.askyesno = MagicMock(return_value=True)
    mock_messagebox.askyesnocancel = MagicMock(return_value=True)
    mock_messagebox.askquestion = MagicMock(return_value="yes")
    mock_messagebox.askretrycancel = MagicMock(return_value=True)

    mock_filedialog = MagicMock()
    mock_filedialog.askdirectory = MagicMock(return_value="")
    mock_filedialog.askopenfilename = MagicMock(return_value="")
    mock_filedialog.askopenfilenames = MagicMock(return_value=())
    mock_filedialog.asksaveasfilename = MagicMock(return_value="")

    # Patch at all the specific module locations where messagebox/filedialog are imported
    with (
        # Core tkinter modules
        patch("tkinter.messagebox.showinfo", mock_messagebox.showinfo),
        patch("tkinter.messagebox.showwarning", mock_messagebox.showwarning),
        patch("tkinter.messagebox.showerror", mock_messagebox.showerror),
        patch("tkinter.messagebox.askokcancel", mock_messagebox.askokcancel),
        patch("tkinter.messagebox.askyesno", mock_messagebox.askyesno),
        patch("tkinter.messagebox.askyesnocancel", mock_messagebox.askyesnocancel),
        patch("tkinter.messagebox.askquestion", mock_messagebox.askquestion),
        patch("tkinter.messagebox.askretrycancel", mock_messagebox.askretrycancel),
        patch("tkinter.filedialog.askdirectory", mock_filedialog.askdirectory),
        patch("tkinter.filedialog.askopenfilename", mock_filedialog.askopenfilename),
        patch("tkinter.filedialog.askopenfilenames", mock_filedialog.askopenfilenames),
        patch("tkinter.filedialog.asksaveasfilename", mock_filedialog.asksaveasfilename),
        # Dialog manager specific patches
        patch("zebtrack.ui.components.dialog_manager.messagebox", mock_messagebox),
        patch("zebtrack.ui.components.dialog_manager.filedialog", mock_filedialog),
        # GUI specific patches
        patch("zebtrack.ui.gui.messagebox", mock_messagebox, create=True),
        # Widget factory patches
        patch("zebtrack.ui.components.widget_factory.messagebox", mock_messagebox, create=True),
        # Validation manager patches
        patch("zebtrack.ui.components.validation_manager.messagebox", mock_messagebox, create=True),
        # Live camera service patches
        patch(
            "zebtrack.core.recording.live_camera_service.messagebox",
            mock_messagebox,
            create=True,
        ),
        # UI scheduler patches
        patch("zebtrack.core.ui_scheduler.messagebox", mock_messagebox, create=True),
    ):
        yield


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


def pytest_collection_modifyitems(config, items):
    if not HEADLESS_TESTS:
        return

    skip_gui = pytest.mark.skip(reason="GUI tests disabled in headless mode")
    for item in items:
        if "gui" in item.keywords:
            item.add_marker(skip_gui)


def pytest_sessionfinish(session, exitstatus):
    """
    Force cleanup of all resources before pytest exits.

    CRITICAL for Windows: Ensures threads, Tkinter, and queues are cleaned up
    even if individual tests failed without proper teardown.

    This hook addresses the Windows-specific issue where:
    1. Non-daemon threads block Python shutdown
    2. Tkinter root.after() callbacks persist after root.destroy()
    3. VSCode and system can freeze waiting for pytest to exit

    Resolution:
    - Force garbage collection
    - Wait for non-daemon threads with timeout (5 seconds)
    - Cancel ALL pending Tkinter after() callbacks
    - Log remaining threads for debugging
    """
    import gc
    import threading
    import time

    # 1. Force garbage collection
    gc.collect()

    # 1.5. Shutdown ThreadPoolExecutors
    from concurrent.futures import ThreadPoolExecutor

    # Find all ThreadPoolExecutor instances and shutdown
    all_objects = gc.get_objects()
    executors_shutdown = 0
    for obj in all_objects:
        try:
            if isinstance(obj, ThreadPoolExecutor):
                obj.shutdown(wait=False)
                executors_shutdown += 1
        except (Exception, ReferenceError):
            pass

    if executors_shutdown > 0:
        print("\n=== PYTEST SESSION CLEANUP ===")
        print(f"Shutdown {executors_shutdown} ThreadPoolExecutor(s)")
    else:
        print("\n=== PYTEST SESSION CLEANUP ===")

    # 2. Wait for non-daemon threads with timeout
    timeout = 5.0  # 5 second timeout
    start = time.time()

    non_daemon_threads = [
        t for t in threading.enumerate() if not t.daemon and t is not threading.current_thread()
    ]

    if non_daemon_threads:
        print(f"Found {len(non_daemon_threads)} non-daemon thread(s) to cleanup:")
        for thread in non_daemon_threads:
            print(f"  - {thread.name} (alive={thread.is_alive()})")

    for thread in non_daemon_threads:
        remaining = timeout - (time.time() - start)
        if remaining <= 0:
            print(f"WARNING: Thread {thread.name} did not finish in time")
            continue

        thread.join(timeout=remaining)
        if thread.is_alive():
            print(f"WARNING: Thread {thread.name} still alive after join(timeout={remaining:.1f}s)")

    # 3. Cleanup Tkinter if exists
    try:
        import tkinter as tk

        root = tk._default_root  # type: ignore[attr-defined]
        if root:
            # Cancel ALL pending after() callbacks
            try:
                after_ids = root.tk.call("after", "info")
                if after_ids:
                    print(f"Canceling {len(after_ids)} pending Tkinter after() callback(s)")
                    for after_id in after_ids:
                        try:
                            root.after_cancel(after_id)
                        except Exception:
                            pass
            except Exception as e:
                print(f"WARNING: Failed to cancel after callbacks: {e}")

            # Destroy root
            try:
                root.quit()
                root.update_idletasks()
                root.destroy()
            except Exception as e:
                print(f"WARNING: Failed to destroy Tkinter root: {e}")
    except Exception:
        pass

    # 4. Final thread status
    remaining_threads = threading.enumerate()
    print(f"\nRemaining threads at session end: {len(remaining_threads)}")
    for thread in remaining_threads:
        print(f"  - {thread.name}: daemon={thread.daemon}, alive={thread.is_alive()}")
    print("==============================\n")


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
    use_mock = HEADLESS_TESTS

    # Only use virtual display on Linux/Unix systems
    if platform.system() == "Linux" and not use_mock:
        try:
            from pyvirtualdisplay import Display  # type: ignore[attr-defined]

            display = Display(visible=False, size=(800, 600))
            display.start()
        except ImportError:
            pass
        except Exception as e:
            warnings.warn(f"Could not start virtual display: {e}", stacklevel=2)

    # Create the tkinter root window (once per session)
    if not use_mock:
        try:
            root = tk.Tk()
            root.withdraw()
            root.update_idletasks()
        except tk.TclError:
            warnings.warn(
                "Headless environment detected. Using Mock for Tkinter root.",
                stacklevel=2,
            )
            root = _create_mock_tk_root()
    else:
        warnings.warn("Headless test mode enabled. Using Mock for Tkinter root.", stacklevel=2)
        root = _create_mock_tk_root()

    yield root

    # Clean up at end of session
    try:
        # CRITICAL: Cancel ALL pending after() callbacks BEFORE destroy
        # This prevents Tkinter callbacks from persisting after root.destroy()
        # which can cause pytest to hang on Windows
        try:
            after_ids = root.tk.call("after", "info")
            if after_ids:
                print(
                    f"[tkinter_session_root] Canceling {len(after_ids)} pending after() callback(s)"
                )
                for after_id in after_ids:
                    try:
                        root.after_cancel(after_id)
                    except Exception:
                        pass
        except Exception as e:
            print(f"[tkinter_session_root] WARNING: Failed to cancel after callbacks: {e}")

        # Now safe to destroy
        root.quit()
        root.update_idletasks()  # Process any pending events
        root.destroy()
        root.update_idletasks()  # Final cleanup

    except Exception as e:
        print(f"[tkinter_session_root] ERROR in cleanup: {e}")
        import traceback

        traceback.print_exc()

    if display is not None:
        try:
            display.stop()
        except Exception as e:
            print(f"[tkinter_session_root] WARNING: Failed to stop virtual display: {e}")


@pytest.fixture(scope="session", autouse=True)
def configure_test_logging():
    """
    Configure logging for tests to prevent MagicMock comparison errors.

    Issue: When tests use Mock() for settings objects, the logging system
    tries to compare handler.level (a MagicMock) with an int in background
    threads (ProcessingWorker), causing:
    TypeError: '>=' not supported between instances of 'int' and 'MagicMock'

    Solution: Disable logging entirely during tests to prevent threading issues
    and Mock comparison errors. Tests should focus on business logic, not logs.
    """
    import logging

    # Disable all logging during tests to prevent Mock comparison errors
    # in background threads (e.g., ProcessingWorker)
    logging.disable(logging.CRITICAL)

    yield

    # Re-enable logging after tests (if needed for debugging)
    logging.disable(logging.NOTSET)


@pytest.fixture(autouse=True)
def cleanup_threads():
    """
    Autouse fixture to ensure threads are cleaned up after each test.

    CRITICAL for threading tests that create non-daemon threads.

    This fixture:
    1. Records threads before test execution
    2. After test completes, identifies new threads
    3. Waits for non-daemon threads to finish (with timeout)
    4. Warns if threads persist after cleanup

    Prevents thread leakage that can cause pytest to hang on Windows.
    """
    import threading

    # Get threads before test
    threads_before = set(threading.enumerate())

    yield  # Run test

    # Get threads after test
    threads_after = set(threading.enumerate())
    new_threads = threads_after - threads_before

    if not new_threads:
        return  # No new threads, nothing to cleanup

    # Wait for new non-daemon threads to finish
    for thread in new_threads:
        if thread.daemon:
            continue
        if not thread.is_alive():
            continue

        # Try to join with timeout
        thread.join(timeout=2.0)

        if thread.is_alive():
            import warnings

            warnings.warn(
                f"Thread {thread.name} still alive after test cleanup (timeout=2.0s)",
                ResourceWarning,
                stacklevel=2,
            )


@pytest.fixture
def tkinter_root(tkinter_session_root):
    """
    Function-scoped fixture that reuses the session root.

    Creates a Toplevel window for each test to ensure isolation,
    avoiding the Tkinter multi-instance bug on Windows.
    """
    # Create a Toplevel window for this test (not a new Tk instance)
    from unittest.mock import MagicMock

    if isinstance(tkinter_session_root, MagicMock):
        test_window: Any = MagicMock()
        test_window.master = tkinter_session_root
        test_window.tk = tkinter_session_root.tk
        test_window._w = f"{tkinter_session_root._w}.toplevel"
        test_window.children = {}
        test_window.winfo_id = MagicMock(return_value=67890)
        test_window.destroy = MagicMock()
        test_window.update_idletasks = MagicMock()
        test_window.winfo_children = MagicMock(return_value=[])
    else:
        test_window = tk.Toplevel(tkinter_session_root)
        test_window.withdraw()
        # CRITICAL: Do NOT call update_idletasks() during setup
        # It causes Windows access violations with threading

    yield test_window

    # Clean up only this test's window
    try:
        # CRITICAL: Cancel after() callbacks for this window BEFORE destroy
        # This prevents Toplevel callbacks from persisting which can cause
        # pytest to hang on Windows
        try:
            after_ids = test_window.tk.call("after", "info")
            if after_ids:
                for after_id in after_ids:
                    try:
                        test_window.after_cancel(after_id)
                    except Exception:
                        pass
        except Exception:
            pass

        # Destroy all child widgets
        for widget in test_window.winfo_children():
            try:
                widget.destroy()
            except Exception:
                pass

        # Destroy the test window WITHOUT update_idletasks to avoid access violations
        try:
            test_window.destroy()
        except Exception:
            pass
    except tk.TclError:
        pass
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Multi-Aquarium Fixtures (Phase 14)
# -----------------------------------------------------------------------------


@pytest.fixture
def single_aquarium_zone_data():
    """
    ZoneData for single-aquarium tests (backward compatibility).

    Returns a MultiAquariumZoneData with a single aquarium covering
    the entire frame. Use this fixture when testing single-subject
    workflows that should work with the new data model.
    """
    from zebtrack.core.detection import AquariumData, MultiAquariumZoneData

    return MultiAquariumZoneData(
        aquariums=[
            AquariumData(
                id=0,
                polygon=[[0, 0], [1280, 0], [1280, 720], [0, 720]],
                roi_polygons=[],
                roi_names=[],
                roi_colors=[],
                group="Default",
                subject_id="S01",
                day=1,
            )
        ],
        video_width=1280,
        video_height=720,
    )


@pytest.fixture
def multi_aquarium_zone_data():
    """
    MultiAquariumZoneData for dual-aquarium tests.

    Returns zone data with two non-overlapping aquariums:
    - Aquarium 0 (left): x=0-600, group="Controle", subject="S01"
    - Aquarium 1 (right): x=680-1280, group="Tratamento", subject="S02"

    Use this fixture for testing multi-aquarium workflows.
    """
    from zebtrack.core.detection import AquariumData, MultiAquariumZoneData

    return MultiAquariumZoneData(
        aquariums=[
            AquariumData(
                id=0,
                polygon=[[0, 0], [600, 0], [600, 720], [0, 720]],
                roi_polygons=[],
                roi_names=[],
                roi_colors=[],
                group="Controle",
                subject_id="S01",
                day=1,
            ),
            AquariumData(
                id=1,
                polygon=[[680, 0], [1280, 0], [1280, 720], [680, 720]],
                roi_polygons=[],
                roi_names=[],
                roi_colors=[],
                group="Tratamento",
                subject_id="S02",
                day=1,
            ),
        ],
        video_width=1280,
        video_height=720,
    )


@pytest.fixture
def multi_aquarium_zone_data_with_rois():
    """
    MultiAquariumZoneData with ROIs defined for each aquarium.

    Extends multi_aquarium_zone_data with sample ROI polygons
    for testing ROI-based analysis in multi-aquarium mode.
    """
    from zebtrack.core.detection import AquariumData, MultiAquariumZoneData

    return MultiAquariumZoneData(
        aquariums=[
            AquariumData(
                id=0,
                polygon=[[0, 0], [600, 0], [600, 720], [0, 720]],
                roi_polygons=[
                    [[50, 50], [200, 50], [200, 200], [50, 200]],  # Top-left ROI
                    [[50, 520], [200, 520], [200, 670], [50, 670]],  # Bottom-left ROI
                ],
                roi_names=["Top", "Bottom"],
                roi_colors=[(0, 255, 0), (255, 0, 0)],
                group="Controle",
                subject_id="S01",
                day=1,
            ),
            AquariumData(
                id=1,
                polygon=[[680, 0], [1280, 0], [1280, 720], [680, 720]],
                roi_polygons=[
                    [[730, 50], [880, 50], [880, 200], [730, 200]],  # Top ROI
                ],
                roi_names=["Top"],
                roi_colors=[(0, 255, 0)],
                group="Tratamento",
                subject_id="S02",
                day=1,
            ),
        ],
        video_width=1280,
        video_height=720,
    )


@pytest.fixture
def sample_trajectory_df():
    """
    Sample trajectory DataFrame for testing analysis.

    Returns a DataFrame with the standard tracking schema:
    timestamp, frame, track_id, x1, y1, x2, y2, confidence, center_x, center_y
    """
    import numpy as np
    import pandas as pd

    n_frames = 100
    return pd.DataFrame(
        {
            "timestamp": np.linspace(0, 3.33, n_frames),  # ~30 fps
            "frame": range(n_frames),
            "track_id": [1] * n_frames,
            "x1": np.linspace(100, 500, n_frames) + np.random.normal(0, 2, n_frames),
            "y1": np.linspace(200, 400, n_frames) + np.random.normal(0, 2, n_frames),
            "x2": np.linspace(130, 530, n_frames) + np.random.normal(0, 2, n_frames),
            "y2": np.linspace(230, 430, n_frames) + np.random.normal(0, 2, n_frames),
            "confidence": np.random.uniform(0.85, 0.99, n_frames),
            "center_x": np.linspace(115, 515, n_frames) + np.random.normal(0, 2, n_frames),
            "center_y": np.linspace(215, 415, n_frames) + np.random.normal(0, 2, n_frames),
        }
    )


@pytest.fixture
def sample_multi_aquarium_trajectories(sample_trajectory_df):
    """
    Sample trajectories for multi-aquarium testing.

    Returns a dict mapping aquarium_id to (trajectory_df, AquariumData).
    Uses track ID offset convention: aquarium_id * 1000 + local_id.
    """
    from zebtrack.core.detection import AquariumData

    # Aquarium 0: original trajectory
    df_aq0 = sample_trajectory_df.copy()
    aq0 = AquariumData(
        id=0,
        polygon=[[0, 0], [600, 0], [600, 720], [0, 720]],
        group="Controle",
        subject_id="S01",
    )

    # Aquarium 1: shifted trajectory with offset track IDs
    df_aq1 = sample_trajectory_df.copy()
    df_aq1["track_id"] = df_aq1["track_id"] + 1000  # Offset for aquarium 1
    df_aq1["x1"] = df_aq1["x1"] + 680  # Shift to right aquarium
    df_aq1["x2"] = df_aq1["x2"] + 680
    df_aq1["center_x"] = df_aq1["center_x"] + 680
    aq1 = AquariumData(
        id=1,
        polygon=[[680, 0], [1280, 0], [1280, 720], [680, 720]],
        group="Tratamento",
        subject_id="S02",
    )

    return {
        0: (df_aq0, aq0),
        1: (df_aq1, aq1),
    }
