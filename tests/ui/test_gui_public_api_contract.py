import inspect

from zebtrack.ui.gui import ApplicationGUI

# List of expected public API methods (Total: 11 after dialog helpers added)
# Most methods moved to component managers (CanvasManager, DialogManager, etc.)
EXPECTED_PUBLIC_API = [
    # 1. Core UI API (Status & Progress)
    "set_status",
    "show_progress_bar",
    "update_progress",
    "update_idletasks",
    "hide_progress_bar",
    "update_button_state",
    # 2. Dialog entry points (still on ApplicationGUI)
    "ask_recording_details_unified",
    "ask_missing_metadata",
    # 3. Simple message dialogs
    "show_info",
    "show_warning",
    "show_error",
]


def test_public_api_methods_exist():
    """Ensure all documented public API methods exist in ApplicationGUI."""
    missing_methods = []
    for method_name in EXPECTED_PUBLIC_API:
        if not hasattr(ApplicationGUI, method_name):
            missing_methods.append(method_name)

    assert not missing_methods, (
        f"Missing {len(missing_methods)} public API methods: {missing_methods}"
    )


def test_public_api_has_decorator():
    """Ensure all public methods have @public_api decorator."""
    missing_decorator = []
    for method_name in EXPECTED_PUBLIC_API:
        if not hasattr(ApplicationGUI, method_name):
            continue

        method = getattr(ApplicationGUI, method_name)
        # Check if the method has the __public_api__ attribute set by the decorator
        if not getattr(method, "__public_api__", False):
            missing_decorator.append(method_name)

    assert not missing_decorator, (
        f"Missing @public_api decorator on {len(missing_decorator)} methods: {missing_decorator}"
    )


def test_total_public_api_count():
    """Ensure we haven't accidentally marked too many methods as public."""
    count = 0
    for name, method in inspect.getmembers(ApplicationGUI, predicate=inspect.isfunction):
        if getattr(method, "__public_api__", False):
            count += 1

    # We expect exactly the number of methods in our list to be marked
    assert count == len(EXPECTED_PUBLIC_API), (
        f"Expected {len(EXPECTED_PUBLIC_API)} public methods, found {count}"
    )
