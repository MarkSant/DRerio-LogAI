import os
import platform
import tkinter as tk
import warnings

import pytest

os.environ.setdefault("ZEBTRACK_SUPPRESS_POST_CREATION_GUIDE", "1")
os.environ.setdefault("ZEBTRACK_SUPPRESS_WIZARD_DIALOGS", "1")


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

    tk.Variable.__del__ = safe_del
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
    import threading
    import gc
    import time

    # 1. Force garbage collection
    gc.collect()

    # 2. Wait for non-daemon threads with timeout
    timeout = 5.0  # 5 second timeout
    start = time.time()

    print("\n=== PYTEST SESSION CLEANUP ===")
    non_daemon_threads = [
        t for t in threading.enumerate()
        if not t.daemon and t is not threading.current_thread()
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
        root = tk._default_root
        if root:
            # Cancel ALL pending after() callbacks
            try:
                after_ids = root.tk.call('after', 'info')
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

    # Only use virtual display on Linux/Unix systems
    if platform.system() == "Linux":
        try:
            from pyvirtualdisplay import Display  # type: ignore[attr-defined]

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
        # CRITICAL: Cancel ALL pending after() callbacks BEFORE destroy
        # This prevents Tkinter callbacks from persisting after root.destroy()
        # which can cause pytest to hang on Windows
        try:
            after_ids = root.tk.call('after', 'info')
            if after_ids:
                print(f"[tkinter_session_root] Canceling {len(after_ids)} pending after() callback(s)")
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
                stacklevel=2
            )


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
        # CRITICAL: Cancel after() callbacks for this window BEFORE destroy
        # This prevents Toplevel callbacks from persisting which can cause
        # pytest to hang on Windows
        try:
            after_ids = test_window.tk.call('after', 'info')
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

        # Destroy the test window
        test_window.update_idletasks()
        test_window.destroy()
    except tk.TclError:
        pass
    except Exception:
        pass
