"""
CI Script to verify public API decorators.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / "src"))

try:
    from zebtrack.ui.gui import ApplicationGUI
except ImportError as e:
    print(f"Could not import ApplicationGUI: {e}")
    sys.exit(1)

# This list should theoretically come from a central source of truth or be parsed from MD.
# For now, we mirror the test expectation.
# Updated 2026-03-01: Methods moved to coordinators/components during Phase 2 decomposition
# are no longer on ApplicationGUI.
EXPECTED_PUBLIC_API = [
    "ask_missing_metadata",
    "ask_recording_details_unified",
    "hide_progress_bar",
    "set_status",
    "show_progress_bar",
    "update_button_state",
    "update_idletasks",
    "update_progress",
]


def main():
    missing = []
    for method_name in EXPECTED_PUBLIC_API:
        if not hasattr(ApplicationGUI, method_name):
            print(f"[FAIL] Method not found: {method_name}")
            missing.append(method_name)
            continue

        method = getattr(ApplicationGUI, method_name)
        if not hasattr(method, "__public_api__"):
            print(f"[FAIL] Missing @public_api: {method_name}")
            missing.append(method_name)

    if missing:
        print(f"Found {len(missing)} violations.")
        sys.exit(1)

    print("[OK] All public API methods verified.")
    sys.exit(0)


if __name__ == "__main__":
    main()
