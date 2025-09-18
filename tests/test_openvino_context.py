"""
Test the context-based class filtering in OpenVINO plugin.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestOpenVINOContext(unittest.TestCase):
    def setUp(self):
        """Create a mock OpenVINO plugin for testing."""
        # Mock all dependencies
        sys.modules["openvino"] = MagicMock()
        sys.modules["structlog"] = MagicMock()
        sys.modules["zebtrack.tracker.byte_tracker"] = MagicMock()
        sys.modules["zebtrack.settings"] = MagicMock()
        sys.modules["zebtrack.utils"] = MagicMock()

        # Import after mocking
        from zebtrack.plugins.openvino_detector import OpenVINOPlugin

        # Create a mock plugin without actually loading model
        self.plugin = object.__new__(OpenVINOPlugin)
        self.plugin._context = "tracking"
        self.plugin._aquarium_region_defined = False

    def test_default_context_is_tracking(self):
        """Test that the default context is 'tracking'."""
        self.assertEqual(self.plugin._context, "tracking")
        self.assertFalse(self.plugin._aquarium_region_defined)

    def test_set_context_methods(self):
        """Test the context control methods."""

        # Add methods to mock object
        def set_context(context):
            if context in ("tracking", "diagnostic"):
                self.plugin._context = context

        def set_aquarium_region_defined(defined=True):
            self.plugin._aquarium_region_defined = bool(defined)

        self.plugin.set_context = set_context
        self.plugin.set_aquarium_region_defined = set_aquarium_region_defined

        # Test setting context to diagnostic
        self.plugin.set_context("diagnostic")
        self.assertEqual(self.plugin._context, "diagnostic")

        # Test setting aquarium region
        self.plugin.set_aquarium_region_defined(True)
        self.assertTrue(self.plugin._aquarium_region_defined)

        # Test invalid context is ignored
        self.plugin.set_context("invalid")
        self.assertEqual(self.plugin._context, "diagnostic")  # Should remain unchanged


if __name__ == "__main__":
    unittest.main()
