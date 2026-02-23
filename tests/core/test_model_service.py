"""
Unit tests for ModelService.

Phase 2.4: Configuration Management tests for weight management,
OpenVINO conversion status, and configuration validation.
"""

import unittest
from unittest.mock import Mock, patch

from zebtrack.core.services.model_service import ModelService


class TestModelServiceConfiguration(unittest.TestCase):
    """Test suite for ModelService configuration management."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_weight_manager = Mock()
        self.service = ModelService(self.mock_weight_manager)

    def test_get_all_weight_names(self):
        """Test retrieving all weight names."""
        self.mock_weight_manager.get_all_weights.return_value = [
            "weight1.pt",
            "weight2_seg.pt",
            "weight3_det.pt",
        ]

        result = self.service.get_all_weight_names()

        assert len(result) == 3
        assert "weight1.pt" in result
        self.mock_weight_manager.get_all_weights.assert_called_once()

    def test_get_weight_type_seg(self):
        """Test getting weight type for segmentation model."""
        self.mock_weight_manager.get_weight_details.return_value = {
            "path": "/path/to/weight_seg.pt",
            "type": "seg",
        }

        result = self.service.get_weight_type("weight_seg.pt")

        assert result == "seg"

    def test_get_weight_type_det(self):
        """Test getting weight type for detection model."""
        self.mock_weight_manager.get_weight_details.return_value = {
            "path": "/path/to/weight_det.pt",
            "type": "det",
        }

        result = self.service.get_weight_type("weight_det.pt")

        assert result == "det"

    def test_get_weight_type_not_found(self):
        """Test getting weight type for non-existent weight."""
        self.mock_weight_manager.get_weight_details.return_value = None

        result = self.service.get_weight_type("nonexistent.pt")

        assert result is None


class TestModelServiceOpenVINO(unittest.TestCase):
    """Test suite for OpenVINO-related functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_weight_manager = Mock()
        self.service = ModelService(self.mock_weight_manager)

    def test_is_openvino_ready_true(self):
        """Test checking if OpenVINO is ready when it exists."""
        with patch("pathlib.Path.exists", return_value=True):
            self.mock_weight_manager.get_weight_details.return_value = {
                "openvino_path": "/path/to/openvino_model",
            }

            result = self.service.is_openvino_ready("weight.pt")

            assert result is True

    def test_is_openvino_ready_false_no_path(self):
        """Test checking if OpenVINO is ready when path is missing."""
        self.mock_weight_manager.get_weight_details.return_value = {
            "openvino_path": "",
        }

        result = self.service.is_openvino_ready("weight.pt")

        assert result is False

    def test_is_openvino_ready_false_path_not_exists(self):
        """Test checking if OpenVINO is ready when path doesn't exist."""
        with patch("pathlib.Path.exists", return_value=False):
            self.mock_weight_manager.get_weight_details.return_value = {
                "openvino_path": "/path/to/nonexistent",
            }

            result = self.service.is_openvino_ready("weight.pt")

            assert result is False

    def test_check_openvino_conversion_status_ready(self):
        """Test checking conversion status when ready."""
        with patch("pathlib.Path.exists", return_value=True):
            self.mock_weight_manager.get_weight_details.return_value = {
                "openvino_status": "ready",
                "openvino_path": "/path/to/openvino",
                "last_conversion_error": None,
            }

            result = self.service.check_openvino_conversion_status("weight.pt")

            assert result["status"] == "ready"
            assert result["ready"] is True
            assert result["path"] == "/path/to/openvino"
            assert result["error"] is None

    def test_check_openvino_conversion_status_not_converted(self):
        """Test checking conversion status when not converted."""
        self.mock_weight_manager.get_weight_details.return_value = {
            "openvino_status": "not_converted",
            "openvino_path": "",
            "last_conversion_error": None,
        }

        result = self.service.check_openvino_conversion_status("weight.pt")

        assert result["status"] == "not_converted"
        assert result["ready"] is False

    def test_check_openvino_conversion_status_failed(self):
        """Test checking conversion status when conversion failed."""
        self.mock_weight_manager.get_weight_details.return_value = {
            "openvino_status": "failed",
            "openvino_path": "",
            "last_conversion_error": "Conversion error message",
        }

        result = self.service.check_openvino_conversion_status("weight.pt")

        assert result["status"] == "failed"
        assert result["ready"] is False
        assert result["error"] == "Conversion error message"

    def test_check_openvino_conversion_status_weight_not_found(self):
        """Test checking conversion status for non-existent weight."""
        self.mock_weight_manager.get_weight_details.return_value = None

        result = self.service.check_openvino_conversion_status("nonexistent.pt")

        assert result["status"] == "unknown"
        assert result["ready"] is False
        assert result["error"] == "Weight not found"


class TestModelServiceValidation(unittest.TestCase):
    """Test suite for model configuration validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_weight_manager = Mock()
        self.service = ModelService(self.mock_weight_manager)

    def test_validate_model_configuration_valid(self):
        """Test validating a valid configuration."""
        with patch("pathlib.Path.exists", return_value=True):
            self.mock_weight_manager.get_weight_details.return_value = {
                "path": "/path/to/weight.pt",
                "openvino_status": "ready",
                "openvino_path": "/path/to/openvino",
                "last_conversion_error": None,
            }

            result = self.service.validate_model_configuration("weight.pt", use_openvino=True)

            assert result["valid"] is True
            assert result["weight_exists"] is True
            assert result["weight_valid"] is True
            assert result["openvino_ready"] is True
            assert len(result["errors"]) == 0

    def test_validate_model_configuration_no_weight(self):
        """Test validation fails when no weight specified."""
        result = self.service.validate_model_configuration(None, use_openvino=False)

        assert result["valid"] is False
        assert "No weight specified" in result["errors"]

    def test_validate_model_configuration_weight_not_found(self):
        """Test validation fails when weight not found."""
        self.mock_weight_manager.get_weight_details.return_value = None

        result = self.service.validate_model_configuration("nonexistent.pt", use_openvino=False)

        assert result["valid"] is False
        assert any("not found" in err for err in result["errors"])

    def test_validate_model_configuration_weight_file_missing(self):
        """Test validation fails when weight file doesn't exist."""
        with patch("pathlib.Path.exists", return_value=False):
            self.mock_weight_manager.get_weight_details.return_value = {
                "path": "/path/to/nonexistent.pt",
            }

            result = self.service.validate_model_configuration("weight.pt", use_openvino=False)

            assert result["valid"] is False
            assert any("not found" in err for err in result["errors"])

    def test_validate_model_configuration_openvino_not_ready(self):
        """Test validation with OpenVINO not ready."""
        with patch("pathlib.Path.exists", return_value=True):
            self.mock_weight_manager.get_weight_details.return_value = {
                "path": "/path/to/weight.pt",
                "openvino_status": "not_converted",
                "openvino_path": "",
                "last_conversion_error": None,
            }

            result = self.service.validate_model_configuration("weight.pt", use_openvino=True)

            assert result["valid"] is True  # Still valid, just needs conversion
            assert result["openvino_ready"] is False
            assert any("not converted" in warn for warn in result["warnings"])

    def test_validate_model_configuration_openvino_failed(self):
        """Test validation fails when OpenVINO conversion failed."""
        with patch("pathlib.Path.exists", return_value=True):
            self.mock_weight_manager.get_weight_details.return_value = {
                "path": "/path/to/weight.pt",
                "openvino_status": "failed",
                "openvino_path": "",
                "last_conversion_error": "Conversion failed",
            }

            result = self.service.validate_model_configuration("weight.pt", use_openvino=True)

            assert result["valid"] is False
            assert any("failed" in err for err in result["errors"])


class TestModelServicePathHelpers(unittest.TestCase):
    """Test suite for path helper methods."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_weight_manager = Mock()
        self.mock_weight_manager.weights = {
            "weight1.pt": {"path": "/path/to/weight1.pt"},
            "weight2.pt": {"path": "/path/to/weight2.pt"},
        }
        self.service = ModelService(self.mock_weight_manager)

    def test_find_weight_by_path_found(self):
        """Test finding weight by path when it exists."""
        name, details = self.service.find_weight_by_path("/path/to/weight1.pt")

        assert name == "weight1.pt"
        assert details is not None
        assert details["path"] == "/path/to/weight1.pt"

    def test_find_weight_by_path_not_found(self):
        """Test finding weight by path when it doesn't exist."""
        name, details = self.service.find_weight_by_path("/path/to/nonexistent.pt")

        assert name is None
        assert details is None

    def test_find_weight_by_path_empty(self):
        """Test finding weight with empty path."""
        name, details = self.service.find_weight_by_path("")

        assert name is None
        assert details is None

    def test_get_model_path_for_inference_without_openvino(self):
        """Test getting model path for regular inference."""
        with patch("pathlib.Path.exists", return_value=True):
            self.mock_weight_manager.get_weight_details.return_value = {
                "path": "/path/to/weight.pt",
            }

            path, details = self.service.get_model_path_for_inference(
                "weight.pt", use_openvino=False
            )

            assert path == "/path/to/weight.pt"
            assert details is not None

    def test_get_model_path_for_inference_with_openvino(self):
        """Test getting model path for OpenVINO inference."""
        with patch("pathlib.Path.exists", return_value=True):
            self.mock_weight_manager.get_weight_details.return_value = {
                "path": "/path/to/weight.pt",
                "openvino_status": "ready",
                "openvino_path": "/path/to/openvino",
                "last_conversion_error": None,
            }

            path, details = self.service.get_model_path_for_inference(
                "weight.pt", use_openvino=True
            )

            assert path == "/path/to/openvino"
            assert details is not None

    def test_get_model_path_for_inference_openvino_not_ready(self):
        """Test getting model path when OpenVINO is not ready."""
        self.mock_weight_manager.get_weight_details.return_value = {
            "path": "/path/to/weight.pt",
            "openvino_status": "not_converted",
            "openvino_path": "",
            "last_conversion_error": None,
        }

        path, details = self.service.get_model_path_for_inference("weight.pt", use_openvino=True)

        assert path is None
        assert details is None


class TestModelServiceConfigurationSummary(unittest.TestCase):
    """Test suite for configuration summary methods."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_weight_manager = Mock()
        self.service = ModelService(self.mock_weight_manager)

    def test_get_weight_configuration_summary_complete(self):
        """Test getting complete weight configuration summary."""
        with patch("pathlib.Path.exists", return_value=True):
            self.mock_weight_manager.get_weight_details.return_value = {
                "path": "/path/to/weight.pt",
                "type": "seg",
                "openvino_status": "ready",
                "openvino_path": "/path/to/openvino",
                "last_conversion_error": None,
            }

            result = self.service.get_weight_configuration_summary("weight.pt")

            assert result["name"] == "weight.pt"
            assert result["type"] == "seg"
            assert result["path"] == "/path/to/weight.pt"
            assert result["exists"] is True
            assert result["openvino_available"] is True
            assert result["openvino_status"] == "ready"

    def test_get_weight_configuration_summary_none(self):
        """Test getting summary for None weight."""
        result = self.service.get_weight_configuration_summary(None)

        assert result["name"] is None
        assert result["type"] is None
        assert result["exists"] is False

    def test_get_weight_configuration_summary_not_found(self):
        """Test getting summary for non-existent weight."""
        self.mock_weight_manager.get_weight_details.return_value = None

        result = self.service.get_weight_configuration_summary("nonexistent.pt")

        assert result["name"] == "nonexistent.pt"
        assert result["type"] is None
        assert result["exists"] is False


if __name__ == "__main__":
    unittest.main()
