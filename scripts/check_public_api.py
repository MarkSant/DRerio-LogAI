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
    "refresh_project_views",
    "update_zone_listbox",
    "setup_interactive_polygon",
    "show_external_trigger_notice",
    "clear_external_trigger_notice",
    "apply_pending_readiness_snapshot",
    "update_processing_stats",
    "update_social_summary",
    "update_analysis_task_status"
]

def main():
    missing = []
    for method_name in EXPECTED_PUBLIC_API:
        if not hasattr(ApplicationGUI, method_name):
            print(f"❌ Method not found: {method_name}")
            missing.append(method_name)
            continue

        method = getattr(ApplicationGUI, method_name)
        if not hasattr(method, '__public_api__'):
             print(f"❌ Missing @public_api: {method_name}")
             missing.append(method_name)

    if missing:
        print(f"Found {len(missing)} violations.")
        sys.exit(1)

    print("✅ All public API methods verified.")
    sys.exit(0)

if __name__ == "__main__":
    main()
