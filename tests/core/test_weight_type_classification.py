"""
Tests for new weight type classification and per-type default features.
"""

import os
import tempfile
from unittest.mock import patch

from zebtrack.core.weight_manager import WeightManager


def test_weight_type_classification():
    """Test weight type classification based on filename suffix."""
    with tempfile.TemporaryDirectory() as temp_dir:
        wm = WeightManager(config_dir=temp_dir)

        # Test segmentation model classification
        assert wm._classify_weight_type("best_seg.pt") == "seg"
        assert wm._classify_weight_type("model_seg.pt") == "seg"
        assert wm._classify_weight_type("YOLO_SEG.PT") == "seg"  # Case insensitive

        # Test detection model classification
        assert wm._classify_weight_type("best_oi.pt") == "det"
        assert wm._classify_weight_type("model_oi.pt") == "det"
        assert wm._classify_weight_type("YOLO_OI.PT") == "det"  # Case insensitive

        # Test unclassified models
        assert wm._classify_weight_type("best.pt") is None
        assert wm._classify_weight_type("model.pt") is None
        assert wm._classify_weight_type("random_name.pt") is None


def test_add_weight_with_type_classification():
    """Test adding weights with automatic type classification."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create mock .pt files
        seg_file = os.path.join(temp_dir, "test_seg.pt")
        det_file = os.path.join(temp_dir, "test_oi.pt")
        unknown_file = os.path.join(temp_dir, "test.pt")

        with open(seg_file, "w") as f:
            f.write("mock seg model")
        with open(det_file, "w") as f:
            f.write("mock det model")
        with open(unknown_file, "w") as f:
            f.write("mock unknown model")

        wm = WeightManager(config_dir=temp_dir)

        with patch("zebtrack.core.weight_manager.messagebox"):
            # Test adding seg weight
            wm.add_weight(seg_file, set_as_default=True)
            assert "test_seg.pt" in wm.weights
            assert wm.weights["test_seg.pt"]["type"] == "seg"
            assert wm.weights["test_seg.pt"]["is_default_seg"] is True
            assert wm.weights["test_seg.pt"]["is_default_det"] is False

            # Test adding det weight
            wm.add_weight(det_file, set_as_default=True)
            assert "test_oi.pt" in wm.weights
            assert wm.weights["test_oi.pt"]["type"] == "det"
            assert wm.weights["test_oi.pt"]["is_default_seg"] is False
            assert wm.weights["test_oi.pt"]["is_default_det"] is True

            # Test adding unclassified weight (should default to seg)
            wm.add_weight(unknown_file, set_as_default=False, weight_type="det")
            assert "test.pt" in wm.weights
            assert wm.weights["test.pt"]["type"] == "det"


def test_get_default_by_type():
    """Test getting default weights by type."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create mock .pt files
        seg_file = os.path.join(temp_dir, "best_seg.pt")
        det_file = os.path.join(temp_dir, "best_oi.pt")

        with open(seg_file, "w") as f:
            f.write("mock seg model")
        with open(det_file, "w") as f:
            f.write("mock det model")

        wm = WeightManager(config_dir=temp_dir)

        with patch("zebtrack.core.weight_manager.messagebox"):
            # Add both weights
            wm.add_weight(seg_file, set_as_default=True)
            wm.add_weight(det_file, set_as_default=False)

            # Set det as default for det type
            wm.set_default_weight_by_type("best_oi.pt", "det")

            # Test getting defaults by type
            seg_name, seg_details = wm.get_default_seg_weight()
            assert seg_name == "best_seg.pt"
            assert seg_details["type"] == "seg"

            det_name, det_details = wm.get_default_det_weight()
            assert det_name == "best_oi.pt"
            assert det_details["type"] == "det"


def test_get_weight_path_by_method():
    """Test getting weight path by method."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create mock .pt files
        seg_file = os.path.join(temp_dir, "best_seg.pt")
        det_file = os.path.join(temp_dir, "best_oi.pt")

        with open(seg_file, "w") as f:
            f.write("mock seg model")
        with open(det_file, "w") as f:
            f.write("mock det model")

        # Mock settings to avoid initializing with default weights
        with patch("zebtrack.core.weight_manager.settings") as mock_settings:
            mock_settings.weights.seg_filename = None
            mock_settings.weights.det_filename = None
            mock_settings.yolo_model.path = None

            wm = WeightManager(config_dir=temp_dir)

            with patch("zebtrack.core.weight_manager.messagebox"):
                # Add both weights and set as defaults for their types
                wm.add_weight(seg_file, set_as_default=True)
                wm.add_weight(det_file, set_as_default=False)
                wm.set_default_weight_by_type("best_oi.pt", "det")

                # Test getting paths by method
                seg_path = wm.get_weight_path_by_method("seg", "aquarium")
                assert seg_path == seg_file

                det_path = wm.get_weight_path_by_method("det", "animal")
                assert det_path == det_file

                # Test invalid method
                invalid_path = wm.get_weight_path_by_method("invalid", "task")
                assert invalid_path is None


def test_backward_compatibility_migration():
    """Test migration of old format weights to new format."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create old format weights config
        import json

        old_weights = {
            "best_seg.pt": {
                "path": "best_seg.pt",
                "is_default": True,
                "openvino_path": "",
                "openvino_hash": "",
            }
        }

        config_path = os.path.join(temp_dir, "weights_config.json")
        with open(config_path, "w") as f:
            json.dump(old_weights, f)

        # Load with new WeightManager - should migrate
        wm = WeightManager(config_dir=temp_dir)

        # Check migration occurred
        assert "type" in wm.weights["best_seg.pt"]
        assert wm.weights["best_seg.pt"]["type"] == "seg"
        assert "is_default_seg" in wm.weights["best_seg.pt"]
        assert "is_default_det" in wm.weights["best_seg.pt"]
        assert wm.weights["best_seg.pt"]["is_default_seg"] is True
        assert wm.weights["best_seg.pt"]["is_default_det"] is False
