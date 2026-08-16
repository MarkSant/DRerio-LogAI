"""
Extended unit tests for HardwareStatusViewModel.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.viewmodels.hardware_status_view_model import HardwareStatusViewModel


def _make_vm() -> HardwareStatusViewModel:
    """Build a HardwareStatusViewModel with fully-mocked dependencies."""
    deps = MagicMock()
    boot = MagicMock()
    boot.hardware.arduino_manager = MagicMock()
    boot.hardware.active_weight_name = "best.pt"
    boot.hardware.use_openvino = False
    boot.ui_state_controller = MagicMock()
    vm = HardwareStatusViewModel(
        dependencies=deps,
        bootstrap_result=boot,
        event_bus=MagicMock(),
    )
    return vm


class TestHardwareStatusViewModelExtended:
    """Test HardwareStatusViewModel detector, coordinator, and hardware delegators."""

    def test_detector_property_getter_setter(self):
        vm = _make_vm()
        dummy_detector = MagicMock()
        vm.detector = dummy_detector
        assert vm.detector == dummy_detector

    def test_detector_initialized_property(self):
        vm = _make_vm()
        det_state = MagicMock()
        det_state.detector_initialized = True
        vm.state_manager.get_detector_state.return_value = det_state  # type: ignore[union-attr,attr-defined]
        assert vm.detector_initialized is True

    def test_setup_detector_success_and_fallback(self):
        vm = _make_vm()
        vm.detector_setup_coordinator.setup_detector.return_value = (True, "Ready")  # type: ignore[union-attr]
        assert vm.setup_detector(temp_animal_method="seg", perspective="top") is True
        vm.detector_setup_coordinator.setup_detector.assert_called_once_with(  # type: ignore[union-attr]
            animal_method="seg",
            use_openvino=False,
            active_weight_name="best.pt",
            perspective="top",
        )
        vm.detector_setup_coordinator = None
        assert vm.setup_detector() is False

    def test_update_detector_parameters(self):
        vm = _make_vm()
        vm.detector_setup_coordinator.update_detector_parameters.return_value = True  # type: ignore[union-attr]
        assert vm.update_detector_parameters({"conf": 0.5}) is True
        vm.detector_setup_coordinator.update_detector_parameters.assert_called_once_with(  # type: ignore[union-attr]
            {"conf": 0.5}
        )
        vm.detector_setup_coordinator = None
        assert vm.update_detector_parameters({"conf": 0.5}) is False

    def test_get_current_detector_parameters(self):
        vm = _make_vm()
        vm.detector_setup_coordinator.get_detector_parameters.return_value = {"conf": 0.5}  # type: ignore[union-attr]
        assert vm.get_current_detector_parameters() == {"conf": 0.5}
        vm.detector_setup_coordinator = None
        assert vm.get_current_detector_parameters() == {}

    def test_restore_detector_defaults(self):
        vm = _make_vm()
        vm.detector_setup_coordinator.get_factory_detector_parameters.return_value = {}  # type: ignore[union-attr]
        vm.detector_setup_coordinator.update_detector_parameters.return_value = True  # type: ignore[union-attr]
        assert vm.restore_detector_defaults() is True
        vm.detector_setup_coordinator = None
        assert vm.restore_detector_defaults() is False
