"""
Integration test that simulates the exact issue scenario mentioned in the problem
statement. This test validates that the "det" method for animal detection now
works correctly.
"""

import os
import tempfile
from unittest.mock import MagicMock, patch

from zebtrack.core.weight_manager import WeightManager


def test_animal_detection_det_method_issue():
    """
    Test the specific issue: 'Falha ao iniciar o detector de "animal" no fluxo de
    Vídeo Único' when animal_method is "det" and weights.get_path.not_found is
    logged.

    This reproduces the exact scenario from the problem statement and validates the
    fix.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # Simulate the config.yaml setup where:
        # - animal_method = "det" (this was failing)
        # - seg_filename = "best_seg.pt"
        # - det_filename = "best_oi.pt" (this file should exist for "det" method)

        # Create both weight files as they would exist in a real setup
        seg_file = os.path.join(temp_dir, "best_seg.pt")
        det_file = os.path.join(temp_dir, "best_oi.pt")

        with open(seg_file, "w") as f:
            f.write("mock segmentation model")
        with open(det_file, "w") as f:
            f.write("mock detection model")

        # Mock settings to match the problematic configuration
        mock_settings = MagicMock()
        mock_settings.weights.seg_filename = seg_file
        mock_settings.weights.det_filename = det_file
        mock_settings.yolo_model.path = seg_file  # Legacy config points to seg

        with patch("zebtrack.core.weight_manager.settings", mock_settings):
            # Initialize WeightManager (this is what happens in
            # controller.setup_detector())
            wm = WeightManager(config_dir=temp_dir)

            # This is the critical call that was failing:
            # controller.setup_detector() calls get_weight_path_by_method("det",
            # "animal") when animal_method = "det"
            det_path = wm.get_weight_path_by_method("det", "animal")

            # Before the fix, this would return None and log
            # "weights.get_path.not_found". After the fix, it should return the
            # path to the detection weight.
            assert det_path is not None, "Detection weight path should not be None!"
            assert det_path == det_file, f"Expected {det_file}, got {det_path}"

            # Verify that both weights are properly initialized
            assert len(wm.weights) == 2, "Both seg and det weights should be initialized"
            assert "best_seg.pt" in wm.weights
            assert "best_oi.pt" in wm.weights

            # Verify the detection weight has correct type and default settings
            det_details = wm.weights["best_oi.pt"]
            assert det_details["type"] == "det"
            assert det_details["is_default_det"] is True
            assert det_details["is_default_seg"] is False

            # Verify segmentation still works too
            seg_path = wm.get_weight_path_by_method("seg", "aquarium")
            assert seg_path == seg_file


def test_controller_setup_detector_scenario():
    """
    Test that simulates the exact controller.setup_detector() flow that was failing.
    This demonstrates that the issue is fixed at the application level.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create weight files
        seg_file = os.path.join(temp_dir, "best_seg.pt")
        det_file = os.path.join(temp_dir, "best_oi.pt")

        with open(seg_file, "w") as f:
            f.write("segmentation model")
        with open(det_file, "w") as f:
            f.write("detection model")

        # Mock settings with animal_method = "det" (the failing scenario)
        mock_settings = MagicMock()
        mock_settings.model_selection.animal_method = "det"  # This was the issue!
        mock_settings.weights.seg_filename = seg_file
        mock_settings.weights.det_filename = det_file
        mock_settings.yolo_model.path = seg_file

        with patch("zebtrack.core.weight_manager.settings", mock_settings):
            # Simulate the controller.setup_detector() logic
            weight_manager = WeightManager(config_dir=temp_dir)

            # This is the exact call that was failing in setup_detector():
            animal_method = mock_settings.model_selection.animal_method  # "det"
            model_path = weight_manager.get_weight_path_by_method(animal_method, "animal")

            # Before fix: model_path would be None, causing setup_detector to fail
            # After fix: model_path should be the path to the detection model
            assert model_path is not None, "Model path should not be None!"
            assert model_path == det_file

            # Verify the fix prevents the original error condition Original error:
            # "Nenhum modelo det está disponível para detecção de animais." This
            # should not happen anymore because we found the detection model


def test_backwards_compatibility_maintained():
    """
    Ensure that the fix maintains backward compatibility with existing setups.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # Old setup: only yolo_model.path specified, new weight settings not used
        old_weight_file = os.path.join(temp_dir, "old_model.pt")
        with open(old_weight_file, "w") as f:
            f.write("old model")

        mock_settings = MagicMock()
        mock_settings.yolo_model.path = old_weight_file
        mock_settings.weights.seg_filename = "nonexistent_seg.pt"
        mock_settings.weights.det_filename = "nonexistent_det.pt"

        with patch("zebtrack.core.weight_manager.settings", mock_settings):
            wm = WeightManager(config_dir=temp_dir)

            # Should still work for legacy setups
            assert len(wm.weights) == 1
            assert "old_model.pt" in wm.weights

            # Should classify as seg since no specific suffix
            assert wm.weights["old_model.pt"]["type"] == "seg"
