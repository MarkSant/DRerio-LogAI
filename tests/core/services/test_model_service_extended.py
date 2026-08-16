"""
Extended unit tests for ModelService.

Tests conversion exceptions, OpenVINO status resolution, metadata inspection,
and weight validation branches.
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from zebtrack.core.services.model_service import ModelService


class TestModelServiceExtended:
    """Test extended ModelService behaviors."""

    def setup_method(self):
        self.mock_weight_manager = MagicMock()
        self.service = ModelService(self.mock_weight_manager)

    def test_convert_to_openvino_empty_name_raises_value_error(self):
        with pytest.raises(ValueError, match="weight_name cannot be empty"):
            self.service.convert_to_openvino("")

    def test_convert_to_openvino_success_and_failure(self):
        # Success
        self.mock_weight_manager.convert_to_openvino.return_value = True
        assert self.service.convert_to_openvino("best.pt") is True

        # Exception caught and returns False
        self.mock_weight_manager.convert_to_openvino.side_effect = RuntimeError(
            "OpenVINO compile failed"
        )
        assert self.service.convert_to_openvino("best.pt") is False

    def test_get_weight_details(self):
        self.mock_weight_manager.get_weight_details.return_value = {"path": "/models/best.pt"}
        details = self.service.get_weight_details("best.pt")
        assert details == {"path": "/models/best.pt"}

    def test_get_openvino_status_branches(self):
        # Empty name
        assert "No weight selected" in self.service.get_openvino_status("", use_openvino=True)

        # Not found
        self.mock_weight_manager.get_weight_details.return_value = None
        assert (
            "not found" in self.service.get_openvino_status("unknown.pt", use_openvino=True).lower()
        )

        # Disabled
        self.mock_weight_manager.get_weight_details.return_value = {"path": "/models/best.pt"}
        assert "disabled" in self.service.get_openvino_status("best.pt", use_openvino=False).lower()

        # Enabled and ready
        with patch("pathlib.Path.exists", return_value=True):
            self.mock_weight_manager.get_weight_details.return_value = {
                "openvino_path": "/models/best_openvino_model"
            }
            assert "ready" in self.service.get_openvino_status("best.pt", use_openvino=True).lower()

        # Enabled but required conversion
        with patch("pathlib.Path.exists", return_value=False):
            self.mock_weight_manager.get_weight_details.return_value = {
                "openvino_path": "/models/best_openvino_model"
            }
            assert (
                "required" in self.service.get_openvino_status("best.pt", use_openvino=True).lower()
            )

    def test_list_available_weights(self):
        self.mock_weight_manager.weights = {"weight1.pt": {}, "weight2.pt": {}}
        weights = self.service.list_available_weights()
        assert weights == ["weight1.pt", "weight2.pt"]

        # Empty weights
        self.mock_weight_manager.weights = None
        assert self.service.list_available_weights() == []

    def test_validate_weight(self):
        # Not found
        self.mock_weight_manager.get_weight_details.return_value = None
        assert self.service.validate_weight("missing.pt") is False

        # Found and exists on disk
        with patch("pathlib.Path.exists", return_value=True):
            self.mock_weight_manager.get_weight_details.return_value = {"path": "/models/best.pt"}
            assert self.service.validate_weight("best.pt") is True

        # Found but missing on disk
        with patch("pathlib.Path.exists", return_value=False):
            self.mock_weight_manager.get_weight_details.return_value = {"path": "/models/best.pt"}
            assert self.service.validate_weight("best.pt") is False

    def test_inspect_model_weight_not_found(self):
        self.mock_weight_manager.get_weight_details.return_value = None
        with pytest.raises(ValueError, match="not found in the configuration"):
            self.service.inspect_model("unknown.pt")

    def test_inspect_model_file_not_found_on_disk(self):
        with patch("pathlib.Path.exists", return_value=False):
            self.mock_weight_manager.get_weight_details.return_value = {
                "path": "/models/missing.pt",
                "type": "seg",
            }
            res = self.service.inspect_model("missing.pt")
            assert res["is_available"] is False
            assert "Model file not found" in res["error"]

    def test_inspect_model_ultralytics_missing(self):
        with patch("pathlib.Path.exists", return_value=True):
            self.mock_weight_manager.get_weight_details.return_value = {
                "path": "/models/best.pt",
                "type": "seg",
            }
            with patch.dict(sys.modules, {"ultralytics": None}):
                with pytest.raises(ImportError, match="Ultralytics package is required"):
                    self.service.inspect_model("best.pt")

    def test_inspect_model_success_and_exception(self):
        mock_yolo_instance = MagicMock()
        mock_yolo_instance.names = {0: "zebrafish"}
        mock_yolo_instance.task = "segment"
        mock_yolo_instance.model.args = {"imgsz": 640}

        mock_ultralytics = ModuleType("ultralytics")
        mock_ultralytics.YOLO = MagicMock(return_value=mock_yolo_instance)  # type: ignore[attr-defined]

        with patch("pathlib.Path.exists", return_value=True):
            self.mock_weight_manager.get_weight_details.return_value = {
                "path": "/models/best.pt",
                "type": "seg",
            }
            with patch.dict(sys.modules, {"ultralytics": mock_ultralytics}):
                res = self.service.inspect_model("best.pt")
                assert res["is_available"] is True
                assert res["model_task"] == "segment"
                assert res["class_names"] == {0: "zebrafish"}
                assert res["num_classes"] == 1
                assert res["input_shape"] == 640

                # YOLO constructor throws exception
                mock_ultralytics.YOLO.side_effect = RuntimeError("Corrupted checkpoint header")
                res_err = self.service.inspect_model("best.pt")
                assert res_err["model_task"] == "unknown"
                assert "Corrupted checkpoint" in res_err["error"]
