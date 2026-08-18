"""Extended unit tests for core/project/project_workflow_service.py (Part 9)."""

from __future__ import annotations

from zebtrack.core.project.project_workflow_service import (
    _VALID_OPENVINO_DEVICES,
    ProjectWorkflowService,
)


class TestProjectWorkflowServiceExtended9:
    """Test ProjectWorkflowService constants and device configurations."""

    def test_slot_separator_constant(self):
        assert ProjectWorkflowService._SLOT_SEPARATOR == ":"

    def test_valid_openvino_devices_tuple(self):
        assert "AUTO" in _VALID_OPENVINO_DEVICES
        assert "CPU" in _VALID_OPENVINO_DEVICES
        assert "GPU" in _VALID_OPENVINO_DEVICES
        assert "NPU" in _VALID_OPENVINO_DEVICES
