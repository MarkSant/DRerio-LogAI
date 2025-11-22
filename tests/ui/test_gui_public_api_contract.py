"""
Tests for Public API Contract.

Task 1.3 / 3.3: Ensure public API integrity and decorator usage.
"""

from zebtrack.ui.gui import ApplicationGUI

# List of methods that MUST have @public_api decorator according to API_STABILITY.md
# We only list the ones currently marked or intended to be marked.
EXPECTED_PUBLIC_API = [
    "refresh_project_views",
    "update_zone_listbox",
    "setup_interactive_polygon",
    "show_external_trigger_notice",
    "clear_external_trigger_notice",
    "apply_pending_readiness_snapshot",
    "update_processing_stats",
    "update_social_summary",
    "update_analysis_task_status",
]


class TestGUIPublicAPIContract:
    def test_public_methods_exist(self):
        """Ensure all expected public API methods exist on the class."""
        for method_name in EXPECTED_PUBLIC_API:
            assert hasattr(ApplicationGUI, method_name), f"Missing public API method: {method_name}"

    def test_public_methods_have_decorator(self):
        """Ensure all expected public methods have the @public_api decorator."""
        for method_name in EXPECTED_PUBLIC_API:
            method = getattr(ApplicationGUI, method_name)
            # The decorator sets __public_api__ = True on the wrapper or function
            assert hasattr(method, "__public_api__"), (
                f"Method {method_name} is missing @public_api decorator"
            )
            assert method.__public_api__ is True
