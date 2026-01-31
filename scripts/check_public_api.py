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
EXPECTED_PUBLIC_API = [
    "setup_interactive_polygon",
    "refresh_project_views",
    "update_weights_dropdown",
    "_on_analyze_single_video_clicked",
    "setup_zone_definition_for_single_video",
    "set_status",
    "show_progress_bar",
    "update_progress",
    "update_idletasks",
    "hide_progress_bar",
    "show_error",
    "show_warning",
    "show_info",
    "show_pending_videos_dialog",
    "ask_ok_cancel",
    "ask_string",
    "ask_directory",
    "ask_open_filenames",
    "ask_save_filename",
    "update_button_state",
    "ask_recording_details_unified",
    "ask_missing_metadata",
    "publish_event",
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
