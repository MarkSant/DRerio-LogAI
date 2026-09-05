import textwrap
import unittest
from pathlib import Path
from unittest.mock import mock_open, patch

from zebtrack.settings import Settings, export_schema, load_settings, reload_settings


class TestSettings(unittest.TestCase):
    def setUp(self):
        """Prepare a generic, valid YAML content for tests."""
        self.mock_yaml_content = """
camera:
  index: 1
  desired_width: 1280
  desired_height: 720
arduino:
  port: 'COM5'
  baud_rate: 9600
recorder:
  flush_interval_seconds: 3.5
  flush_row_threshold: 250
yolo_model:
  path: 'test.pt'
  confidence_threshold: 0.5
  nms_threshold: 0.5
video_processing:
  fps: 30
  processing_interval: 10
  processing_offset: 1
reproducibility:
  seed: 123
roi_inclusion_rule: "bbox_intersects"
roi_buffer_radius_value: 0.5
roi_min_bbox_overlap_ratio: 0.10
trajectory_smoothing:
  window_length: 7
  polyorder: 3
"""

    def test_load_settings_success_without_zones(self):
        """Test that settings load with default empty zones if section is missing."""
        # Simulate only config.yaml existing
        with patch("pathlib.Path.is_file", side_effect=[True, False]) as mock_is_file:
            with patch("builtins.open", mock_open(read_data=self.mock_yaml_content)) as mock_file:
                settings = load_settings()
                self.assertIsInstance(settings, Settings)
                self.assertEqual(settings.camera.index, 1)
                self.assertEqual(settings.yolo_model.path, "test.pt")
                self.assertEqual(settings.recorder.flush_interval_seconds, 3.5)
                self.assertEqual(settings.recorder.flush_row_threshold, 250)
                # ByteTrack defaults: track_threshold=0.1 (very low to catch all),
                # match_threshold=0.95 (strict)
                self.assertAlmostEqual(settings.bytetrack.track_threshold, 0.1)
                self.assertAlmostEqual(settings.bytetrack.match_threshold, 0.95)
                self.assertFalse(settings.tracking.use_single_subject_tracker)
                # Check that default empty values are created
                self.assertEqual(settings.detection_zones.polygon, [])
                self.assertEqual(settings.detection_zones.roi_polygons, [])
                self.assertEqual(settings.detection_zones.roi_names, [])
                self.assertEqual(settings.detection_zones.roi_colors, [])
                # UI feature flags should fall back to defaults when not specified
                # Wizard is now the default (v1.6+)
                self.assertTrue(settings.ui_features.use_wizard_for_project_creation)
                # Event queue is opt-in for staged migration
                self.assertFalse(settings.ui_features.enable_event_queue)
                # Should check for both default and override files
                self.assertEqual(mock_is_file.call_count, 2)
                # Should only open the default file
                mock_file.assert_called_once()

    def test_load_settings_with_zones(self):
        """Test that settings are loaded correctly when zones are present."""
        yaml_with_zones = """
camera:
  index: 1
  desired_width: 1280
  desired_height: 720
arduino:
  port: 'COM5'
  baud_rate: 9600
recorder:
  flush_interval_seconds: 2.0
  flush_row_threshold: 100
yolo_model:
  path: 'test.pt'
  confidence_threshold: 0.5
  nms_threshold: 0.5
video_processing:
  fps: 30
  processing_interval: 10
  processing_offset: 1
detection_zones:
  polygon:
    - [0, 0]
    - [1, 1]
  roi_polygons:
    - [[10, 20], [30, 40], [15, 30]]
  roi_names: ["ROI1"]
  roi_colors:
    - [255, 0, 0]
reproducibility:
  seed: 123
"""
        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=yaml_with_zones)):
                settings = load_settings()
                self.assertEqual(len(settings.detection_zones.polygon), 2)
                self.assertEqual(
                    settings.detection_zones.roi_polygons[0],
                    [[10, 20], [30, 40], [15, 30]],
                )
                self.assertEqual(settings.detection_zones.roi_names[0], "ROI1")
        self.assertEqual(settings.recorder.flush_interval_seconds, 2.0)
        self.assertEqual(settings.recorder.flush_row_threshold, 100)

    def test_load_settings_file_not_found(self):
        """Test that a FileNotFoundError is raised if the default config is missing."""
        with patch("pathlib.Path.is_file", return_value=False):
            with self.assertRaises(FileNotFoundError):
                load_settings()

    def test_load_settings_validation_error(self):
        """Test that a ValueError is raised for invalid config data."""
        invalid_yaml = """
yolo_model:
  path: 'test.pt'
"""  # Missing several required fields
        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=invalid_yaml)):
                with self.assertRaises(ValueError):
                    load_settings()

    def test_load_settings_with_override(self):
        """Test that override config correctly merges with base config."""
        base_yaml = self.mock_yaml_content
        override_yaml = textwrap.dedent(
            """
            camera:
              index: 9
            yolo_model:
              confidence_threshold: 0.8
            recorder:
              flush_interval_seconds: 4.0
            """
        )

        # This mock handles opening either the base or override file
        def mock_open_side_effect(path, *args, **kwargs):
            if "local" in str(path):
                return mock_open(read_data=override_yaml).return_value
            return mock_open(read_data=base_yaml).return_value

        # Simulate both config.yaml and config.local.yaml existing
        with patch("pathlib.Path.is_file", side_effect=[True, True]):
            with patch("builtins.open", side_effect=mock_open_side_effect):
                settings = load_settings()

                # Check that the override value was applied
                self.assertEqual(settings.camera.index, 9)
                # Check that a non-overridden value from the base is still present
                self.assertEqual(settings.arduino.port, "COM5")
                # Check that a nested value was overridden
                self.assertEqual(settings.yolo_model.confidence_threshold, 0.8)
                # Check that another nested value (not in override) is still present
                self.assertEqual(settings.yolo_model.path, "test.pt")
                # Recorder settings should merge correctly
                self.assertEqual(settings.recorder.flush_interval_seconds, 4.0)
                self.assertEqual(settings.recorder.flush_row_threshold, 250)

    def test_bytetrack_override(self):
        base_yaml = self.mock_yaml_content
        override_yaml = textwrap.dedent(
            """
            bytetrack:
              track_threshold: 0.35
              match_threshold: 0.65
            """
        )

        def mock_open_side_effect(path, *args, **kwargs):
            if "local" in str(path):
                return mock_open(read_data=override_yaml)()
            return mock_open(read_data=base_yaml)()

        with patch("pathlib.Path.is_file", side_effect=[True, True]):
            with patch("builtins.open", side_effect=mock_open_side_effect):
                settings = load_settings()

        self.assertAlmostEqual(settings.bytetrack.track_threshold, 0.35)
        self.assertAlmostEqual(settings.bytetrack.match_threshold, 0.65)

    def test_roi_inclusion_settings_defaults(self):
        """Test that ROI inclusion settings have correct defaults."""
        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=self.mock_yaml_content)):
                settings = load_settings()

                # Check default values for ROI inclusion settings
                self.assertEqual(settings.roi_inclusion_rule, "bbox_intersects")
                self.assertEqual(settings.roi_buffer_radius_value, 0.5)
                self.assertEqual(settings.roi_min_bbox_overlap_ratio, 0.10)
                self.assertEqual(settings.trajectory_smoothing.window_length, 7)
                self.assertEqual(settings.trajectory_smoothing.polyorder, 3)

    def test_roi_inclusion_settings_override(self):
        """Test that ROI inclusion settings can be overridden."""
        base_yaml = self.mock_yaml_content
        override_yaml = """
roi_inclusion_rule: "centroid_in"
roi_buffer_radius_value: 1.5
roi_min_bbox_overlap_ratio: 0.25
trajectory_smoothing:
  window_length: 9
  polyorder: 3
"""

        def mock_open_side_effect(path, *args, **kwargs):
            if "local" in str(path):
                return mock_open(read_data=override_yaml)()
            else:
                return mock_open(read_data=base_yaml)()

        with patch("pathlib.Path.is_file", side_effect=[True, True]):
            with patch("builtins.open", side_effect=mock_open_side_effect):
                settings = load_settings()

                # Check overridden values
                self.assertEqual(settings.roi_inclusion_rule, "centroid_in")
                self.assertEqual(settings.roi_buffer_radius_value, 1.5)
                self.assertEqual(settings.roi_min_bbox_overlap_ratio, 0.25)
                self.assertEqual(settings.trajectory_smoothing.window_length, 9)
                self.assertEqual(settings.trajectory_smoothing.polyorder, 3)

    def test_ui_feature_flag_override(self):
        base_yaml = self.mock_yaml_content
        override_yaml = """
ui_features:
  use_wizard_for_project_creation: true
  enable_event_queue: true
"""

        def mock_open_side_effect(path, *args, **kwargs):
            if "local" in str(path):
                return mock_open(read_data=override_yaml)()
            return mock_open(read_data=base_yaml)()

        with patch("pathlib.Path.is_file", side_effect=[True, True]):
            with patch("builtins.open", side_effect=mock_open_side_effect):
                loaded = load_settings()

        self.assertTrue(loaded.ui_features.use_wizard_for_project_creation)
        self.assertTrue(loaded.ui_features.enable_event_queue)

    def test_tracking_settings_override(self):
        base_yaml = self.mock_yaml_content
        override_yaml = """
tracking:
  use_single_subject_tracker: true
"""

        def mock_open_side_effect(path, *args, **kwargs):
            if "local" in str(path):
                return mock_open(read_data=override_yaml)()
            return mock_open(read_data=base_yaml)()

        with patch("pathlib.Path.is_file", side_effect=[True, True]):
            with patch("builtins.open", side_effect=mock_open_side_effect):
                loaded = load_settings()

        self.assertTrue(loaded.tracking.use_single_subject_tracker)

    def test_trajectory_smoothing_validation(self):
        invalid_yaml = (
            self.mock_yaml_content
            + """
trajectory_smoothing:
  window_length: 6
  polyorder: 5
"""
        )

        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=invalid_yaml)):
                with self.assertRaises(ValueError):
                    load_settings()

    def test_processing_offset_must_be_less_than_interval(self):
        invalid_yaml = (
            self.mock_yaml_content
            + """
video_processing:
  fps: 30
  processing_interval: 5
  processing_offset: 5
"""
        )

        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=invalid_yaml)):
                with self.assertRaises(ValueError):
                    load_settings()

    def test_processing_interval_must_be_positive(self):
        invalid_yaml = (
            self.mock_yaml_content
            + """
video_processing:
  fps: 30
  processing_interval: 0
  processing_offset: 0
"""
        )

        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=invalid_yaml)):
                with self.assertRaises(ValueError):
                    load_settings()

    def test_buffer_radius_requires_positive_value_for_buffered_rule(self):
        invalid_yaml = (
            self.mock_yaml_content
            + """
roi_inclusion_rule: "centroid_in_on_buffered_roi"
roi_buffer_radius_value: 0
"""
        )

        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=invalid_yaml)):
                with self.assertRaises(ValueError):
                    load_settings()

    def test_overlap_ratio_bounds_respected(self):
        invalid_yaml = (
            self.mock_yaml_content
            + """
roi_inclusion_rule: "bbox_intersects"
roi_min_bbox_overlap_ratio: 1.5
"""
        )

        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=invalid_yaml)):
                with self.assertRaises(ValueError):
                    load_settings()

    def test_zero_overlap_ratio_accepted_for_bbox_intersects(self):
        """0 é o limiar "qualquer sobreposição real" — a semântica que o nome promete."""
        valid_yaml = (
            self.mock_yaml_content
            + """
roi_inclusion_rule: "bbox_intersects"
roi_min_bbox_overlap_ratio: 0.0
"""
        )

        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=valid_yaml)):
                settings = load_settings()
                self.assertEqual(settings.roi_min_bbox_overlap_ratio, 0.0)

    def test_zero_overlap_ratio_rejected_for_seg_overlap(self):
        """``seg_overlap`` não tem caminho de sobreposição pura implementado."""
        invalid_yaml = (
            self.mock_yaml_content
            + """
roi_inclusion_rule: "seg_overlap"
roi_min_bbox_overlap_ratio: 0.0
"""
        )

        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=invalid_yaml)):
                with self.assertRaises(ValueError):
                    load_settings()

    def test_negative_overlap_ratio_rejected(self):
        invalid_yaml = (
            self.mock_yaml_content
            + """
roi_inclusion_rule: "bbox_intersects"
roi_min_bbox_overlap_ratio: -0.1
"""
        )

        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=invalid_yaml)):
                with self.assertRaises(ValueError):
                    load_settings()

    def test_overlap_basis_defaults_to_bbox(self):
        """Sem configurar nada, a base é a histórica — retrocompatível."""
        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=self.mock_yaml_content)):
                self.assertEqual(load_settings().roi_bbox_overlap_basis, "bbox")

    def test_overlap_basis_accepts_the_three_options(self):
        for basis in ("bbox", "roi", "max"):
            with self.subTest(basis=basis):
                valid_yaml = (
                    self.mock_yaml_content
                    + f"""
roi_bbox_overlap_basis: "{basis}"
"""
                )
                with patch("pathlib.Path.is_file", side_effect=[True, False]):
                    with patch("builtins.open", mock_open(read_data=valid_yaml)):
                        self.assertEqual(load_settings().roi_bbox_overlap_basis, basis)

    def test_overlap_basis_rejects_unknown_value(self):
        invalid_yaml = (
            self.mock_yaml_content
            + """
roi_bbox_overlap_basis: "area"
"""
        )

        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=invalid_yaml)):
                with self.assertRaises(ValueError):
                    load_settings()

    def test_reload_settings(self):
        """Test that reload_settings() works as expected."""
        base_yaml = self.mock_yaml_content
        override_yaml = """
camera:
  index: 8
"""

        def mock_open_side_effect(path, *args, **kwargs):
            if "local" in str(path):
                return mock_open(read_data=override_yaml)()
            return mock_open(read_data=base_yaml)()

        with patch("pathlib.Path.is_file", side_effect=[True, True]):
            with patch("builtins.open", side_effect=mock_open_side_effect):
                settings = reload_settings()
                self.assertEqual(settings.camera.index, 8)

    def test_export_schema(self):
        """Test that export_schema() generates valid JSON Schema."""
        schema = export_schema()

        # Check that basic schema structure exists
        self.assertIn("properties", schema)
        self.assertIn("$defs", schema)
        self.assertIn("camera", schema["properties"])
        self.assertIn("yolo_model", schema["properties"])

        # Check that CameraSettings is defined in $defs
        self.assertIn("CameraSettings", schema["$defs"])
        camera_def = schema["$defs"]["CameraSettings"]
        self.assertIn("properties", camera_def)
        self.assertIn("index", camera_def["properties"])
        self.assertIn("description", camera_def["properties"]["index"])

    def test_export_schema_to_file(self):
        """Test that export_schema() can write to a file."""
        import json
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            temp_path = Path(f.name)

        try:
            schema = export_schema(temp_path)

            # Verify file was created and contains valid JSON
            self.assertTrue(temp_path.exists())
            with open(temp_path) as f:
                loaded_schema = json.load(f)

            # Should match the returned schema
            self.assertEqual(schema, loaded_schema)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_configdict_forbids_extra_fields(self):
        """Test that extra='forbid' in ConfigDict prevents unknown fields."""
        invalid_yaml = (
            self.mock_yaml_content
            + """
camera:
  index: 1
  unknown_field: "should fail"
"""
        )

        with patch("pathlib.Path.is_file", side_effect=[True, False]):
            with patch("builtins.open", mock_open(read_data=invalid_yaml)):
                with self.assertRaises(ValueError) as context:
                    load_settings()
                # Should mention the extra field in the error
                self.assertIn("unknown_field", str(context.exception).lower())

    def test_deep_merge_preserves_nested_values(self):
        """Test that deep merge correctly handles nested dictionaries."""
        base_yaml = self.mock_yaml_content
        # Override only one nested value, others should be preserved
        override_yaml = """
video_processing:
  fps: 60
"""

        def mock_open_side_effect(path, *args, **kwargs):
            if "local" in str(path):
                return mock_open(read_data=override_yaml)()
            return mock_open(read_data=base_yaml)()

        with patch("pathlib.Path.is_file", side_effect=[True, True]):
            with patch("builtins.open", side_effect=mock_open_side_effect):
                settings = load_settings()
                # Overridden value
                self.assertEqual(settings.video_processing.fps, 60)
                # Preserved values from base
                self.assertEqual(settings.video_processing.processing_interval, 10)
                self.assertEqual(settings.video_processing.processing_offset, 1)


class TestSaveSettingsNeverDestroysTheExistingFile(unittest.TestCase):
    """A failed save must leave the previous configuration untouched.

    ``save_settings`` used to open the target with ``"w"`` and serialize INTO the
    handle, so the file was truncated before anyone knew whether the dump would
    succeed. One unit test calling it with a mocked settings object zeroed the
    real ``config.local.yaml`` in the repo root — camera index, Arduino port,
    weight paths and language, gone — while the suite reported 6492 passing.
    """

    def _existing_config(self, tmp_path):
        from pathlib import Path

        target = Path(tmp_path) / "config.local.yaml"
        target.write_text("camera:\n  index: 7\n", encoding="utf-8")
        return target

    def _save_or_fail(self, settings_like, target):
        """Call ``save_settings``, tolerating whichever error type it raises.

        The assertion that matters is on the FILE, not on the exception class:
        the defect was that the target got truncated before anyone knew the dump
        would work. Pinning an exception type here would only couple the test to
        PyYAML's internals.
        """
        import contextlib

        import zebtrack.settings as settings_module

        with contextlib.suppress(Exception):
            settings_module.save_settings(settings_like, target_path=target)

    def test_unserializable_settings_leave_the_file_intact(self):
        """The exact shape that zeroed the repo's config: a mocked settings object."""
        import tempfile
        from unittest.mock import MagicMock

        with tempfile.TemporaryDirectory() as tmp:
            target = self._existing_config(tmp)
            original = target.read_text(encoding="utf-8")

            self._save_or_fail(MagicMock(), target)

            self.assertEqual(
                target.read_text(encoding="utf-8"),
                original,
                "a failed save must not touch the previous configuration",
            )

    def test_empty_dump_is_refused_rather_than_written(self):
        import tempfile
        from unittest.mock import MagicMock

        with tempfile.TemporaryDirectory() as tmp:
            target = self._existing_config(tmp)
            original = target.read_text(encoding="utf-8")

            empty = MagicMock()
            empty.model_dump.return_value = {}

            self._save_or_fail(empty, target)

            self.assertEqual(target.read_text(encoding="utf-8"), original)

    def test_a_real_settings_object_round_trips(self):
        """A genuine Settings object must still save, and leave no temp file."""
        import tempfile
        from pathlib import Path

        import zebtrack.settings as settings_module

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "config.local.yaml"
            settings = settings_module.load_settings(Path("config.yaml"), Path(tmp) / "absent.yaml")

            settings_module.save_settings(settings, target_path=target)

            self.assertTrue(target.exists())
            self.assertGreater(target.stat().st_size, 0)
            self.assertFalse(
                target.with_name(f"{target.name}.tmp").exists(),
                "the temp file must not survive a successful write",
            )


if __name__ == "__main__":
    unittest.main()


class TestAnimalConfidenceResolution(unittest.TestCase):
    """The animal threshold is separate from the arena's, and falls back to it.

    A permissive floor is right for finding a tank ONCE per video and wrong for
    accepting a fish on every frame: at 0.05 a static artifact just outside the
    arena was recorded on 263 frames of a real run (2026-09-05), 22.7% of the
    trajectory.
    """

    def test_falls_back_to_the_arena_threshold_when_unset(self):
        from types import SimpleNamespace

        from zebtrack.settings import resolve_animal_confidence

        yolo = SimpleNamespace(confidence_threshold=0.05, animal_confidence_threshold=None)

        self.assertEqual(resolve_animal_confidence(yolo), 0.05)

    def test_explicit_value_wins(self):
        from types import SimpleNamespace

        from zebtrack.settings import resolve_animal_confidence

        yolo = SimpleNamespace(confidence_threshold=0.05, animal_confidence_threshold=0.35)

        self.assertEqual(resolve_animal_confidence(yolo), 0.35)

    def test_mock_settings_fall_back_instead_of_returning_a_mock(self):
        """A MagicMock answers every attribute; trusting getattr returns an object.

        The plugins compare this value against detection scores, so a mock here
        would not raise — it would silently accept or reject everything.
        """
        from unittest.mock import MagicMock

        from zebtrack.settings import resolve_animal_confidence

        yolo = MagicMock()
        yolo.confidence_threshold = 0.6

        self.assertEqual(resolve_animal_confidence(yolo), 0.6)

    def test_out_of_range_override_is_ignored(self):
        from types import SimpleNamespace

        from zebtrack.settings import resolve_animal_confidence

        for bad in (0, 1, -0.2, 1.5, True):
            yolo = SimpleNamespace(confidence_threshold=0.05, animal_confidence_threshold=bad)
            self.assertEqual(resolve_animal_confidence(yolo), 0.05, f"bad={bad!r}")

    def test_real_settings_expose_the_same_answer_as_the_property(self):
        from zebtrack.settings import load_settings, resolve_animal_confidence

        settings = load_settings()

        self.assertEqual(
            settings.yolo_model.effective_animal_confidence,
            resolve_animal_confidence(settings.yolo_model),
        )
