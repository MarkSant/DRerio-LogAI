"""Extended unit tests for core/project/project_workflow_service.py (Part 8)."""

from __future__ import annotations

from zebtrack.core.project.project_workflow_service import ProjectWorkflowService


class TestProjectWorkflowServiceExtended8:
    """Test slot key helper and slot pairs generation."""

    def test_slot_key_formatting(self):
        key = ProjectWorkflowService._slot_key("det", "zebrafish")
        assert key == "det:zebrafish"

        key2 = ProjectWorkflowService._slot_key("seg", "aquarium")
        assert key2 == "seg:aquarium"

    def test_slot_separator_constant(self):
        assert ProjectWorkflowService._SLOT_SEPARATOR == ":"

    def test_slot_key_empty_inputs(self):
        assert ProjectWorkflowService._slot_key("", "") == ":"
        assert ProjectWorkflowService._slot_key("det", "") == "det:"

    def test_slot_key_custom_labels(self):
        res = ProjectWorkflowService._slot_key("segmentation", "subject_01")
        assert res == "segmentation:subject_01"
