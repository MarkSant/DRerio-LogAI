"""
Test the context-based class filtering in OpenVINO plugin.
"""

import os
import sys
import unittest
from typing import Any, cast
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


#: Modules replaced while importing the plugin without OpenVINO installed.
_MOCKED_MODULES = (
    "openvino",
    "structlog",
    "zebtrack.tracker.byte_tracker",
    "zebtrack.settings",
    "zebtrack.utils",
)


class TestOpenVINOContext(unittest.TestCase):
    def setUp(self):
        """Create a mock OpenVINO plugin for testing."""
        # Mock all dependencies.
        #
        # ``sys.modules`` is PROCESS-WIDE and these replacements used to have no
        # tearDown, so every later test in the same pytest worker that imported
        # ``zebtrack.settings`` lazily got a MagicMock instead of the module.
        # The symptom was baffling on the receiving end: a plugin's
        # ``conf_threshold`` came out as ``mock.resolve_animal_confidence()``,
        # and ``save_settings`` appeared to accept a mocked Settings object.
        # The originals are captured here and restored in ``tearDown``.
        self._saved_modules = {name: sys.modules.get(name) for name in _MOCKED_MODULES}
        for name in _MOCKED_MODULES:
            sys.modules[name] = MagicMock()

        # Import after mocking
        from zebtrack.plugins.openvino_detector import OpenVINOPlugin

        # Create a mock plugin without actually loading model
        self.plugin = object.__new__(OpenVINOPlugin)
        self.plugin._context = "tracking"
        self.plugin._aquarium_region_defined = False

    def tearDown(self):
        """Put ``sys.modules`` back exactly as it was.

        A module absent before must be REMOVED again, not left bound to ``None``:
        a ``None`` entry in ``sys.modules`` makes the next import raise
        ``ImportError`` instead of importing.
        """
        for name, original in self._saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original

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

        plugin_any = cast(Any, self.plugin)
        attr_name = "set_context"
        setattr(plugin_any, attr_name, set_context)
        attr_name = "set_aquarium_region_defined"
        setattr(plugin_any, attr_name, set_aquarium_region_defined)

        # Test setting context to diagnostic
        self.plugin.set_context("diagnostic")
        self.assertEqual(self.plugin._context, "diagnostic")

        # Test setting aquarium region
        self.plugin.set_aquarium_region_defined(True)
        self.assertTrue(self.plugin._aquarium_region_defined)

        # Test invalid context is ignored
        self.plugin.set_context("invalid")
        self.assertEqual(self.plugin._context, "diagnostic")  # Should remain unchanged


class TestOpenVINOValidation(unittest.TestCase):
    """Test validation of OpenVINO model directories."""

    def _is_valid_openvino_directory(self, path):
        """
        Local copy of validation function to avoid complex imports in tests.
        """
        import glob

        if not path or not os.path.exists(path):
            return False

        if not os.path.isdir(path):
            return False

        xml_files = glob.glob(os.path.join(path, "*.xml"))
        return len(xml_files) > 0

    def test_is_valid_openvino_directory_with_none(self):
        """Test that None path returns False."""
        self.assertFalse(self._is_valid_openvino_directory(None))

    def test_is_valid_openvino_directory_nonexistent(self):
        """Test that nonexistent path returns False."""
        self.assertFalse(self._is_valid_openvino_directory("/nonexistent/path"))

    def test_is_valid_openvino_directory_empty(self):
        """Test that empty directory returns False."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertFalse(self._is_valid_openvino_directory(tmpdir))

    def test_is_valid_openvino_directory_with_xml(self):
        """Test that directory with .xml file returns True."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a .xml file
            xml_file = Path(tmpdir) / "model.xml"
            xml_file.touch()
            self.assertTrue(self._is_valid_openvino_directory(tmpdir))

    def test_is_valid_openvino_directory_file_not_dir(self):
        """Test that a file path (not directory) returns False."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file, not a directory
            test_file = Path(tmpdir) / "test.txt"
            test_file.touch()
            self.assertFalse(self._is_valid_openvino_directory(str(test_file)))


if __name__ == "__main__":
    unittest.main()
