"""Tests for class names validation and consistency across plugins.

MELHORIA #5: Test suite to ensure class names are correctly extracted
and validated across Ultralytics and OpenVINO plugins.

Why the model-backed tests resolve their paths instead of naming them
---------------------------------------------------------------------
The three tests that need a real model on disk used to gate on
``Path("best_seg.pt")`` and ``Path("openvino_model_cache/...")`` -- bare
relative paths, resolved against the *current working directory*. Weights have
not lived at the project root for a long time: ``fetch-weights`` writes them
into ``weights/`` and :func:`zebtrack.paths.resolve_weights_dir` is the
canonical resolver. So the first two conditions were false even on a fully
provisioned machine, and the third (CWD-relative) was true only when pytest
happened to be launched from the main checkout -- never from a git worktree.
All three skipped silently, which is indistinguishable from passing.

Anchoring them the way production does (``repo_root()`` + the settings) makes
them run wherever the assets actually are. They still skip when the asset is
genuinely absent: ``best_seg.pt`` is a generalist model that ``fetch-weights``
downloads only with ``--all``, so CI legitimately skips them.
"""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from zebtrack.core.services.detector_service import DetectorService
from zebtrack.core.services.weight_manager import OPENVINO_CACHE_DIR
from zebtrack.paths import repo_root, resolve_weights_dir
from zebtrack.settings import load_settings

#: Name of the generalist segmentation weight these tests inspect. It is a
#: weight NAME (the key ``WeightManager`` registers), not a path -- keep it that
#: way: ``ModelService.inspect_model`` resolves the path itself.
SEG_WEIGHT_NAME = "best_seg.pt"


def _seg_weight_path() -> Path:
    """Absolute path to ``best_seg.pt`` in the configured weights directory.

    Mirrors :class:`~zebtrack.core.services.weight_manager.WeightManager`:
    ``settings.weights.source_dir`` (default ``weights``) anchored at the
    repository root -- never at the working directory.
    """
    return resolve_weights_dir(load_settings()) / SEG_WEIGHT_NAME


def _openvino_seg_model_dir() -> Path:
    """Absolute path to the converted OpenVINO model directory.

    ``WeightManager`` builds this as ``config_dir / OPENVINO_CACHE_DIR``, with
    ``config_dir`` defaulting to :func:`~zebtrack.paths.repo_root`.
    """
    return repo_root() / OPENVINO_CACHE_DIR / "best_seg_openvino_model"


class TestClassNamesConsistency:
    """Test class names are correctly extracted from models."""

    @pytest.mark.skipif(
        not _seg_weight_path().exists(),
        reason=f"{SEG_WEIGHT_NAME} not found in the configured weights directory",
    )
    def test_ultralytics_plugin_extracts_class_names(self):
        """Verify UltralyticsDetectorPlugin extracts class names from model."""
        from zebtrack.plugins.ultralytics_detector import UltralyticsDetectorPlugin

        plugin = UltralyticsDetectorPlugin(_seg_weight_path())

        # Plugin should have class_names attribute
        assert hasattr(plugin, "class_names"), "Plugin missing class_names attribute"

        # Class names should be a dict
        assert isinstance(plugin.class_names, dict), (
            f"class_names should be dict, got {type(plugin.class_names)}"
        )

        # Should have at least 2 classes for segmentation model
        assert len(plugin.class_names) >= 2, (
            f"Expected at least 2 classes, got {len(plugin.class_names)}"
        )

        # Class IDs should be integers
        for class_id in plugin.class_names.keys():
            assert isinstance(class_id, int), f"Class ID {class_id} should be int"

        # Class names should be strings
        for class_name in plugin.class_names.values():
            assert isinstance(class_name, str), f"Class name {class_name} should be str"

        print(f"✓ Extracted class names: {plugin.class_names}")

    @pytest.mark.skipif(
        not _openvino_seg_model_dir().exists(),
        reason="converted OpenVINO model not found in the repository cache",
    )
    def test_openvino_plugin_loads_metadata(self):
        """Verify OpenVINOPlugin loads class names from metadata.json.

        The names must come from the sidecar, not from the generic fallback.
        Counting classes cannot show that: the fallback infers its count from
        the output shape and lands on the same number, so ``len() >= 2`` holds
        either way. What separates the two branches is the NAMES -- the
        fallback can only synthesise ``class_<i>`` placeholders (pinned by
        :meth:`test_openvino_plugin_fallback_without_metadata`), while
        metadata.json carries the real taxonomy.
        """
        from zebtrack.plugins.openvino_detector import OpenVINOPlugin

        model_dir = _openvino_seg_model_dir()
        metadata = json.loads((model_dir / "metadata.json").read_text(encoding="utf-8"))
        expected = {int(k): v for k, v in metadata["class_names"].items()}

        plugin = OpenVINOPlugin(model_dir)

        # Plugin should have class_names attribute
        assert hasattr(plugin, "class_names"), "OpenVINO plugin missing class_names"

        # Should have loaded from metadata.json
        assert len(plugin.class_names) >= 2, (
            f"Expected at least 2 classes, got {len(plugin.class_names)}"
        )

        # Exactly the sidecar's mapping, with int keys -- not the fallback's.
        assert plugin.class_names == expected
        assert not any(name.startswith("class_") for name in plugin.class_names.values()), (
            f"Generic names mean the fallback ran, not metadata.json: {plugin.class_names}"
        )

    def test_openvino_plugin_fallback_without_metadata(self):
        """Verify OpenVINOPlugin gracefully handles missing metadata."""
        from zebtrack.plugins.openvino_detector import OpenVINOPlugin

        # Create a mock model directory without metadata.json
        with patch("os.path.exists") as mock_exists:
            # metadata.json doesn't exist, but .xml file does
            def side_effect(path):
                if "metadata.json" in str(path):
                    return False
                if path.endswith(".xml"):
                    return True
                return True

            mock_exists.side_effect = side_effect

            with patch("glob.glob") as mock_glob:
                mock_glob.return_value = ["mock_model.xml"]

                with patch("zebtrack.plugins.openvino_detector.ov") as mock_ov:
                    # Mock OpenVINO core and model
                    mock_core = Mock()
                    mock_model = Mock()
                    mock_compiled = Mock()

                    # Mock output structure
                    mock_output_det = Mock()
                    mock_output_det.partial_shape = [1, 38, 8400]  # 2 classes seg model
                    mock_output_proto = Mock()
                    mock_output_proto.partial_shape = [1, 32, 160, 160]

                    mock_compiled.outputs = [mock_output_det, mock_output_proto]
                    mock_compiled.output = (
                        lambda idx: mock_output_det if idx == 0 else mock_output_proto
                    )

                    mock_input = Mock()
                    mock_input.shape = [1, 3, 640, 640]
                    mock_compiled.input = lambda idx: mock_input

                    mock_compiled.create_infer_request = Mock()

                    mock_core.read_model.return_value = mock_model
                    mock_core.compile_model.return_value = mock_compiled
                    mock_ov.Core.return_value = mock_core

                    # Initialize plugin
                    plugin = OpenVINOPlugin("mock_model_dir")

                    # Should have fallback class names
                    assert hasattr(plugin, "class_names")
                    assert isinstance(plugin.class_names, dict)

                    # With segmentation model (38 channels), should infer 2 classes
                    # 38 = 4 (bbox) + 2 (classes) + 32 (masks)
                    assert len(plugin.class_names) == 2

                    # Names should be generic
                    assert plugin.class_names[0].startswith("class_")
                    assert plugin.class_names[1].startswith("class_")

                    print(f"✓ Fallback class names: {plugin.class_names}")


class TestClassValidation:
    """Test class validation in DetectorService."""

    def test_validate_model_classes_success(self):
        """Test validation passes with correct class names."""
        # Mock plugin with valid class names
        mock_plugin = Mock()
        mock_plugin.class_names = {0: "aqua", 1: "zebrafish"}

        # Mock dependencies
        mock_state_manager = Mock()
        mock_project_manager = Mock()
        mock_weight_manager = Mock()
        mock_model_service = Mock()
        mock_settings = Mock()

        service = DetectorService(
            state_manager=mock_state_manager,
            project_manager=mock_project_manager,
            weight_manager=mock_weight_manager,
            model_service=mock_model_service,
            settings_obj=mock_settings,
        )

        # Should not raise exception
        service._validate_model_classes(mock_plugin, "test_model.pt")

    def test_validate_model_classes_alternative_names(self):
        """Test validation accepts alternative class names."""
        # Mock plugin with alternative names
        mock_plugin = Mock()
        mock_plugin.class_names = {0: "aquarium", 1: "fish"}

        mock_state_manager = Mock()
        mock_project_manager = Mock()
        mock_weight_manager = Mock()
        mock_model_service = Mock()
        mock_settings = Mock()

        service = DetectorService(
            state_manager=mock_state_manager,
            project_manager=mock_project_manager,
            weight_manager=mock_weight_manager,
            model_service=mock_model_service,
            settings_obj=mock_settings,
        )

        # Should not raise exception (warning logged but not raised)
        service._validate_model_classes(mock_plugin, "test_model.pt")

    def test_validate_model_classes_missing_animal_class_warns(self):
        """Test validation warns (but doesn't fail) with missing animal class.

        The validation was changed to be non-blocking to support custom models
        that may use different class names or have only aquarium segmentation.
        Missing classes now generate warnings instead of raising exceptions.
        """
        # Mock plugin missing class 1 (zebrafish)
        mock_plugin = Mock()
        mock_plugin.class_names = {0: "aqua"}  # Only aquarium, no zebrafish

        mock_state_manager = Mock()
        mock_project_manager = Mock()
        mock_weight_manager = Mock()
        mock_model_service = Mock()
        mock_settings = Mock()

        service = DetectorService(
            state_manager=mock_state_manager,
            project_manager=mock_project_manager,
            weight_manager=mock_weight_manager,
            model_service=mock_model_service,
            settings_obj=mock_settings,
        )

        # Should NOT raise ValueError - just warns and continues
        # This allows using custom models with different class configurations
        service._validate_model_classes(mock_plugin, "aquarium_only_model.pt")
        # Test passes if no exception is raised

    def test_validate_model_classes_no_classes_attribute(self):
        """Test validation handles plugins without class_names."""
        # Mock plugin without class_names attribute
        mock_plugin = Mock(spec=[])  # Empty spec, no attributes

        mock_state_manager = Mock()
        mock_project_manager = Mock()
        mock_weight_manager = Mock()
        mock_model_service = Mock()
        mock_settings = Mock()

        service = DetectorService(
            state_manager=mock_state_manager,
            project_manager=mock_project_manager,
            weight_manager=mock_weight_manager,
            model_service=mock_model_service,
            settings_obj=mock_settings,
        )

        # Should not raise exception (warning logged, validation skipped)
        service._validate_model_classes(mock_plugin, "legacy_model.pt")


class TestModelInspection:
    """Test model inspection functionality."""

    @pytest.mark.skipif(
        not _seg_weight_path().exists(),
        reason=f"{SEG_WEIGHT_NAME} not found in the configured weights directory",
    )
    def test_inspect_model_success(self):
        """Test model inspection returns correct information."""
        from zebtrack.core.services.model_service import ModelService
        from zebtrack.core.services.weight_manager import WeightManager
        from zebtrack.settings import load_settings

        settings = load_settings()
        weight_manager = WeightManager(settings_obj=settings)
        model_service = ModelService(weight_manager)

        # Inspect by weight NAME; WeightManager resolves the path.
        info = model_service.inspect_model(SEG_WEIGHT_NAME)

        # Verify structure
        assert "weight_name" in info
        assert "weight_type" in info
        assert "model_task" in info
        assert "class_names" in info
        assert "num_classes" in info
        assert "input_shape" in info
        assert "model_path" in info
        assert "is_available" in info

        # Verify values
        assert info["weight_name"] == SEG_WEIGHT_NAME
        assert info["weight_type"] == "seg"
        assert info["model_task"] == "segment"
        assert info["is_available"] is True
        assert isinstance(info["class_names"], dict)
        assert info["num_classes"] >= 2

        print(f"✓ Model inspection successful: {info}")

    def test_inspect_model_not_found(self):
        """Test inspection handles missing models gracefully."""
        from zebtrack.core.services.model_service import ModelService
        from zebtrack.core.services.weight_manager import WeightManager
        from zebtrack.settings import load_settings

        settings = load_settings()
        weight_manager = WeightManager(settings_obj=settings)
        model_service = ModelService(weight_manager)

        # Try to inspect non-existent model
        with pytest.raises(ValueError, match="not found in the configuration"):
            model_service.inspect_model("nonexistent.pt")


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])
