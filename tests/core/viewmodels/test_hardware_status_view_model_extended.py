"""
Extended unit tests for HardwareStatusViewModel.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.core.viewmodels.hardware_status_view_model import HardwareStatusViewModel


class TestHardwareStatusViewModelExtended:
    """Test HardwareStatusViewModel detector, coordinator, and hardware delegators."""

    @pytest.fixture
    def mock_vm(self):
        deps = MagicMock()
        boot = MagicMock()
        boot.hardware.arduino_manager = MagicMock()
        boot.hardware.active_weight_name = "best.pt"
        boot.hardware.use_openvino = False
        boot.ui_state_controller = MagicMock()
        event_bus = MagicMock()
        return HardwareStatusViewModel(
            dependencies=deps,
            bootstrap_result=boot,
            event_bus=event_bus,
        )

    def test_detector_property_getter_setter(self, mock_vm: HardwareStatusViewModel):
        dummy_detector = MagicMock()
        mock_vm.detector = dummy_detector
        assert mock_vm.detector == dummy_detector

    def test_detector_initialized_property(self, mock_vm: HardwareStatusViewModel):
        det_state = MagicMock()
        det_state.detector_initialized = True
        mock_vm.state_manager.get_detector_state.return_value = det_state
        assert mock_vm.detector_initialized is True

    def test_setup_detector_success_and_fallback(self, mock_vm: HardwareStatusViewModel):
        mock_vm.detector_setup_coordinator.setup_detector.return_value = (True, "Ready")
        assert mock_vm.setup_detector(temp_animal_method="seg", perspective="top") is True
        mock_vm.detector_setup_coordinator.setup_detector.assert_called_once_with(
            animal_method="seg",
            use_openvino=False,
            active_weight_name="best.pt",
            perspective="top",
        )

        mock_vm.detector_setup_coordinator = None
        assert mock_vm.setup_detector() is False

    def test_update_detector_parameters(self, mock_vm: HardwareStatusViewModel):
        mock_vm.detector_setup_coordinator.update_detector_parameters.return_value = True
        assert mock_vm.update_detector_parameters({"conf": 0.5}) is True
        mock_vm.detector_setup_coordinator.update_detector_parameters.assert_called_once_with(
            {"conf": 0.5}
        )

        mock_vm.detector_setup_coordinator = None
        assert mock_vm.update_detector_parameters({"conf": 0.5}) is False

    def test_get_current_detector_parameters(self, mock_vm: HardwareStatusViewModel):
        mock_vm.detector_setup_coordinator.get_detector_parameters.return_value = {"conf": 0.5}
        assert mock_vm.get_current_detector_parameters() == {"conf": 0.5}

        mock_vm.detector_setup_coordinator = None
        assert mock_vm.get_current_detector_parameters() == {}

    def test_restore_detector_defaults(self, mock_vm: HardwareStatusViewModel):
        mock_vm.detector_setup_coordinator.get_factory_detector_parameters.return_value = {}
        mock_vm.detector_setup_coordinator.update_detector_parameters.return_value = True
        assert mock_vm.restore_detector_defaults() is True

        mock_vm.detector_setup_coordinator = None
        assert mock_vm.restore_detector_defaults() is False
