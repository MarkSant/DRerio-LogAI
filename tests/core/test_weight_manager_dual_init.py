import os
import tempfile
from unittest.mock import MagicMock, patch

from zebtrack.core.weight_manager import WeightManager


def test_initialize_both_seg_and_det_weights():
    """Test initialization with both seg and det weights available."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create mock weight files
        seg_file = os.path.join(temp_dir, "best_seg.pt")
        det_file = os.path.join(temp_dir, "best_oi.pt")

        with open(seg_file, 'w') as f:
            f.write("mock seg model")
        with open(det_file, 'w') as f:
            f.write("mock det model")

        # Mock settings
        mock_settings = MagicMock()
        mock_settings.weights.seg_filename = seg_file
        mock_settings.weights.det_filename = det_file
        mock_settings.yolo_model.path = seg_file  # Legacy path

        with patch('zebtrack.core.weight_manager.settings', mock_settings):
            wm = WeightManager(config_dir=temp_dir)

            # Both weights should be initialized
            assert len(wm.weights) == 2
            assert "best_seg.pt" in wm.weights
            assert "best_oi.pt" in wm.weights

            # Check segmentation weight
            seg_details = wm.weights["best_seg.pt"]
            assert seg_details["type"] == "seg"
            assert seg_details["is_default_seg"] is True
            assert seg_details["is_default_det"] is False
            assert seg_details["path"] == seg_file

            # Check detection weight
            det_details = wm.weights["best_oi.pt"]
            assert det_details["type"] == "det"
            assert det_details["is_default_seg"] is False
            assert det_details["is_default_det"] is True
            assert det_details["path"] == det_file

            # Test get_weight_path_by_method for both types
            seg_path = wm.get_weight_path_by_method("seg", "animal")
            assert seg_path == seg_file

            det_path = wm.get_weight_path_by_method("det", "animal")
            assert det_path == det_file


def test_initialize_only_seg_weight():
    """Test initialization with only segmentation weight available."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create only seg weight file
        seg_file = os.path.join(temp_dir, "best_seg.pt")
        det_file = os.path.join(temp_dir, "best_oi.pt")  # This won't exist

        with open(seg_file, 'w') as f:
            f.write("mock seg model")

        # Mock settings
        mock_settings = MagicMock()
        mock_settings.weights.seg_filename = seg_file
        mock_settings.weights.det_filename = det_file  # Points to non-existent file
        mock_settings.yolo_model.path = seg_file

        with patch('zebtrack.core.weight_manager.settings', mock_settings):
            wm = WeightManager(config_dir=temp_dir)

            # Only seg weight should be initialized
            assert len(wm.weights) == 1
            assert "best_seg.pt" in wm.weights
            assert "best_oi.pt" not in wm.weights

            # Check segmentation weight
            seg_details = wm.weights["best_seg.pt"]
            assert seg_details["type"] == "seg"
            assert seg_details["is_default_seg"] is True
            assert seg_details["is_default_det"] is False

            # Test get_weight_path_by_method
            seg_path = wm.get_weight_path_by_method("seg", "animal")
            assert seg_path == seg_file

            det_path = wm.get_weight_path_by_method("det", "animal")
            assert det_path is None  # Should return None since no det weight available


def test_initialize_only_det_weight():
    """Test initialization with only detection weight available."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create only det weight file
        seg_file = os.path.join(temp_dir, "best_seg.pt")  # This won't exist
        det_file = os.path.join(temp_dir, "best_oi.pt")

        with open(det_file, 'w') as f:
            f.write("mock det model")

        # Mock settings
        mock_settings = MagicMock()
        mock_settings.weights.seg_filename = seg_file  # Points to non-existent file
        mock_settings.weights.det_filename = det_file
        mock_settings.yolo_model.path = det_file

        with patch('zebtrack.core.weight_manager.settings', mock_settings):
            wm = WeightManager(config_dir=temp_dir)

            # Only det weight should be initialized
            assert len(wm.weights) == 1
            assert "best_oi.pt" in wm.weights
            assert "best_seg.pt" not in wm.weights

            # Check detection weight
            det_details = wm.weights["best_oi.pt"]
            assert det_details["type"] == "det"
            assert det_details["is_default_seg"] is False
            assert det_details["is_default_det"] is True

            # Test get_weight_path_by_method
            det_path = wm.get_weight_path_by_method("det", "animal")
            assert det_path == det_file

            seg_path = wm.get_weight_path_by_method("seg", "animal")
            assert seg_path is None  # Should return None since no seg weight available


def test_initialize_no_weights():
    """Test initialization when no weights are available."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # No weight files exist
        seg_file = os.path.join(temp_dir, "best_seg.pt")
        det_file = os.path.join(temp_dir, "best_oi.pt")

        # Mock settings
        mock_settings = MagicMock()
        mock_settings.weights.seg_filename = seg_file
        mock_settings.weights.det_filename = det_file
        mock_settings.yolo_model.path = seg_file

        with patch('zebtrack.core.weight_manager.settings', mock_settings):
            wm = WeightManager(config_dir=temp_dir)

            # No weights should be initialized
            assert len(wm.weights) == 0

            # Both methods should return None
            seg_path = wm.get_weight_path_by_method("seg", "animal")
            assert seg_path is None

            det_path = wm.get_weight_path_by_method("det", "animal")
            assert det_path is None
