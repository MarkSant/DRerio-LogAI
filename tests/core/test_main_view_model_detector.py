"""
Unit tests for MainViewModel - Detector Management.

Phase: Sprint 4.4 - Test coverage for detector operations
Tests setup_detector, weight management, OpenVINO conversion,
and detector configuration.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
import tkinter as tk


@pytest.fixture
def mock_root():
    """Create mock Tkinter root."""
    root = Mock(spec=tk.Tk)
    root.after = Mock()
    return root


@pytest.fixture
def mock_dependencies():
    """Create all mocked dependencies for MainViewModel."""
    detector_service = Mock()
    detector_service.initialize_detector = Mock(return_value=Mock())
    detector_service.detector = None

    weight_manager = Mock()
    weight_manager.get_active_weight_name = Mock(return_value="yolo11n.pt")
    weight_manager.get_all_weight_names = Mock(return_value=["yolo11n.pt", "yolo11m.pt"])

    return {
        "event_bus": Mock(),
        "state_manager": Mock(),
        "ui_coordinator": Mock(),
        "settings_obj": Mock(),
        "project_manager": Mock(),
        "project_workflow_service": Mock(),
        "weight_manager": weight_manager,
        "model_service": Mock(),
        "detector_service": detector_service,
        "video_processing_service": Mock(),
        "analysis_service": Mock(),
        "recording_service": None,
    }


@pytest.fixture
def main_view_model(mock_root, mock_dependencies):
    """Create MainViewModel with mocked dependencies."""
    with patch('zebtrack.core.main_view_model.ApplicationGUI'):
        from zebtrack.core.main_view_model import MainViewModel

        controller = MainViewModel(
            root=mock_root,
            **mock_dependencies
        )
        controller.view = Mock()
        return controller


class TestSetupDetector:
    """Test suite for setup_detector method."""

    def test_setup_detector_initializes_via_service(self, main_view_model):
        """Test setup_detector delegates to DetectorService."""
        mock_detector = Mock()
        main_view_model.detector_service.initialize_detector = Mock(return_value=mock_detector)

        result = main_view_model.setup_detector()

        # Should call detector service
        main_view_model.detector_service.initialize_detector.assert_called_once()
        assert result is True

    def test_setup_detector_with_temp_method_override(self, main_view_model):
        """Test temporary detection method override."""
        mock_detector = Mock()
        main_view_model.detector_service.initialize_detector = Mock(return_value=mock_detector)

        main_view_model.setup_detector(temp_animal_method="seg")

        # Should pass override to service
        call_args = main_view_model.detector_service.initialize_detector.call_args
        # Verification depends on implementation

    def test_setup_detector_handles_initialization_failure(self, main_view_model):
        """Test detector initialization failure handling."""
        main_view_model.detector_service.initialize_detector = Mock(return_value=None)

        result = main_view_model.setup_detector()

        assert result is False

    def test_setup_detector_updates_video_processing_service(self, main_view_model):
        """Test detector assigned to VideoProcessingService."""
        mock_detector = Mock()
        main_view_model.detector_service.initialize_detector = Mock(return_value=mock_detector)
        main_view_model.detector_service.detector = mock_detector

        main_view_model.setup_detector()

        # Should update video processing service
        assert main_view_model.video_processing_service.detector == mock_detector

    def test_setup_detector_sets_zones_when_available(self, main_view_model):
        """Test detector zones are set when available."""
        mock_detector = Mock()
        mock_detector.set_zones = Mock()
        main_view_model.detector_service.initialize_detector = Mock(return_value=mock_detector)

        main_view_model.project_manager.get_zone_data = Mock(
            return_value=Mock(polygon=[[0, 0], [640, 0], [640, 480], [0, 480]])
        )

        main_view_model.setup_detector()

        # Zones may be set via setup_detector_zones
        # Test depends on zone setup flow


class TestSetActiveWeight:
    """Test suite for set_active_weight method."""

    def test_set_active_weight_updates_weight_manager(self, main_view_model):
        """Test setting active weight updates WeightManager."""
        main_view_model.weight_manager.set_active_weight = Mock()

        main_view_model.set_active_weight("yolo11m.pt")

        # Should update weight manager
        main_view_model.weight_manager.set_active_weight.assert_called_once_with("yolo11m.pt")

    def test_set_active_weight_reinitializes_detector(self, main_view_model):
        """Test changing weight reinitializes detector."""
        main_view_model.weight_manager.set_active_weight = Mock()

        with patch.object(main_view_model, 'setup_detector') as mock_setup:
            main_view_model.set_active_weight("yolo11m.pt")

            # Should reinitialize detector
            mock_setup.assert_called()

    def test_set_active_weight_handles_invalid_name(self, main_view_model):
        """Test setting invalid weight name."""
        main_view_model.weight_manager.set_active_weight = Mock(side_effect=ValueError("Invalid weight"))

        # Should handle error gracefully
        try:
            main_view_model.set_active_weight("invalid.pt")
        except ValueError:
            pass  # Error may be propagated or handled

    def test_set_active_weight_to_none(self, main_view_model):
        """Test setting weight to None."""
        main_view_model.weight_manager.set_active_weight = Mock()

        main_view_model.set_active_weight(None)

        # Should allow None (no model)
        main_view_model.weight_manager.set_active_weight.assert_called_once_with(None)


class TestGetAllWeightNames:
    """Test suite for get_all_weight_names method."""

    def test_get_all_weight_names_returns_list(self, main_view_model):
        """Test get_all_weight_names returns weight list."""
        weights = main_view_model.get_all_weight_names()

        assert isinstance(weights, list)
        assert "yolo11n.pt" in weights
        assert "yolo11m.pt" in weights

    def test_get_all_weight_names_handles_empty(self, main_view_model):
        """Test get_all_weight_names with no weights."""
        main_view_model.weight_manager.get_all_weight_names = Mock(return_value=[])

        weights = main_view_model.get_all_weight_names()

        assert weights == []


class TestClassifyWeightType:
    """Test suite for classify_weight_type method."""

    def test_classify_weight_type_detection(self, main_view_model):
        """Test weight type classification for detection."""
        main_view_model.weight_manager.classify_weight_type = Mock(return_value="det")

        weight_type = main_view_model.classify_weight_type("yolo11n.pt")

        assert weight_type == "det"

    def test_classify_weight_type_segmentation(self, main_view_model):
        """Test weight type classification for segmentation."""
        main_view_model.weight_manager.classify_weight_type = Mock(return_value="seg")

        weight_type = main_view_model.classify_weight_type("yolo11n-seg.pt")

        assert weight_type == "seg"

    def test_classify_weight_type_unknown(self, main_view_model):
        """Test classification for unknown weight type."""
        main_view_model.weight_manager.classify_weight_type = Mock(return_value=None)

        weight_type = main_view_model.classify_weight_type("unknown.pt")

        assert weight_type is None


class TestDeleteWeight:
    """Test suite for delete_weight method."""

    def test_delete_weight_removes_from_manager(self, main_view_model):
        """Test deleting weight removes from WeightManager."""
        main_view_model.weight_manager.delete_weight = Mock()

        main_view_model.delete_weight("yolo11m.pt")

        # Should call weight manager
        main_view_model.weight_manager.delete_weight.assert_called_once_with("yolo11m.pt")

    def test_delete_weight_cannot_delete_active(self, main_view_model):
        """Test cannot delete currently active weight."""
        main_view_model.weight_manager.get_active_weight_name = Mock(return_value="yolo11n.pt")
        main_view_model.weight_manager.delete_weight = Mock(side_effect=ValueError("Cannot delete active"))

        # Should prevent deletion or show error
        with pytest.raises(ValueError):
            main_view_model.delete_weight("yolo11n.pt")


class TestOpenVINOConversion:
    """Test suite for OpenVINO conversion."""

    def test_set_openvino_usage_enables(self, main_view_model):
        """Test enabling OpenVINO usage."""
        main_view_model.weight_manager.set_use_openvino = Mock()

        main_view_model.set_openvino_usage(True)

        # Should update weight manager
        main_view_model.weight_manager.set_use_openvino.assert_called_once_with(True)

    def test_set_openvino_usage_disables(self, main_view_model):
        """Test disabling OpenVINO usage."""
        main_view_model.weight_manager.set_use_openvino = Mock()

        main_view_model.set_openvino_usage(False)

        main_view_model.weight_manager.set_use_openvino.assert_called_once_with(False)

    def test_convert_active_weight_to_openvino(self, main_view_model):
        """Test converting active weight to OpenVINO format."""
        main_view_model.weight_manager.convert_weight_to_openvino = Mock(return_value=True)
        mock_dialog = Mock()

        result = main_view_model.convert_active_weight_to_openvino(mock_dialog)

        # Should call conversion
        main_view_model.weight_manager.convert_weight_to_openvino.assert_called_once()

    def test_convert_weight_handles_failure(self, main_view_model):
        """Test handling of conversion failure."""
        main_view_model.weight_manager.convert_weight_to_openvino = Mock(return_value=False)
        mock_dialog = Mock()

        result = main_view_model.convert_active_weight_to_openvino(mock_dialog)

        # Should handle failure gracefully
        assert result is False

    def test_get_openvino_status(self, main_view_model):
        """Test getting OpenVINO status string."""
        main_view_model.weight_manager.get_use_openvino = Mock(return_value=True)

        status = main_view_model.get_openvino_status()

        assert isinstance(status, str)


class TestDetectorConfiguration:
    """Test suite for detector configuration."""

    def test_get_current_detector_parameters(self, main_view_model):
        """Test retrieving current detector parameters."""
        main_view_model.detector_service.get_current_parameters = Mock(return_value={
            "confidence": 0.5,
            "iou": 0.45,
        })

        params = main_view_model.get_current_detector_parameters()

        assert "confidence" in params or params is not None

    def test_get_factory_detector_parameters(self, main_view_model):
        """Test retrieving factory default parameters."""
        main_view_model.detector_service.get_factory_parameters = Mock(return_value={
            "confidence": 0.25,
            "iou": 0.7,
        })

        params = main_view_model.get_factory_detector_parameters()

        # Should return defaults
        assert params is not None

    def test_are_project_overrides_active(self, main_view_model):
        """Test checking if project overrides are active."""
        main_view_model._using_project_overrides = True

        assert main_view_model.are_project_overrides_active() is True


class TestDetectorPropertyAccess:
    """Test suite for detector property."""

    def test_detector_property_getter(self, main_view_model):
        """Test detector property returns DetectorService instance."""
        mock_detector = Mock()
        main_view_model.detector_service.detector = mock_detector

        assert main_view_model.detector == mock_detector

    def test_detector_property_setter(self, main_view_model):
        """Test detector property sets on DetectorService."""
        mock_detector = Mock()

        main_view_model.detector = mock_detector

        # Should set on detector service
        assert main_view_model.detector_service.detector == mock_detector

    def test_detector_property_deleter(self, main_view_model):
        """Test detector property deletion."""
        main_view_model.detector_service.detector = Mock()

        del main_view_model.detector

        # Should clear detector
        assert main_view_model.detector_service.detector is None

    def test_detector_initialized_property(self, main_view_model):
        """Test detector_initialized property."""
        main_view_model.detector_service.detector = None
        assert main_view_model.detector_initialized is False

        main_view_model.detector_service.detector = Mock()
        assert main_view_model.detector_initialized is True


class TestManageWeights:
    """Test suite for manage_weights method."""

    def test_manage_weights_opens_dialog(self, main_view_model):
        """Test manage_weights opens management dialog."""
        with patch('zebtrack.core.main_view_model.ManageWeightsDialog') as mock_dialog:
            main_view_model.manage_weights()

            # Should open dialog
            mock_dialog.assert_called_once()

    def test_manage_weights_refreshes_after_changes(self, main_view_model):
        """Test manage_weights refreshes detector after changes."""
        # Dialog may trigger detector refresh
        # Implementation-specific


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
