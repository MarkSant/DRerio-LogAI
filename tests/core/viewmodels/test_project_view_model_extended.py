"""
Extended unit tests for ProjectViewModel.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.core.viewmodels.project_view_model import ProjectViewModel


class TestProjectViewModelExtended:
    """Test ProjectViewModel lifecycle delegation."""

    @pytest.fixture
    def mock_vm(self):
        deps = MagicMock()
        boot = MagicMock()
        boot.batch_configuration_service = MagicMock()
        event_bus = MagicMock()
        return ProjectViewModel(
            dependencies=deps,
            bootstrap_result=boot,
            event_bus=event_bus,
        )

    def test_create_project_workflow(self, mock_vm: ProjectViewModel):
        mock_vm.project_lifecycle_coordinator.create_project.return_value = True
        assert mock_vm.create_project_workflow(name="TestProj") is True
        mock_vm.project_lifecycle_coordinator.create_project.assert_called_once_with(
            name="TestProj"
        )

        mock_vm.project_lifecycle_coordinator = None
        assert mock_vm.create_project_workflow(name="TestProj") is None

    def test_open_and_close_project_workflow(self, mock_vm: ProjectViewModel):
        mock_vm.project_lifecycle_coordinator.open_project.return_value = True
        assert mock_vm.open_project_workflow("/path/to/proj") is True

        mock_vm.project_lifecycle_coordinator.close_project.return_value = True
        assert mock_vm.close_project() is True

    def test_on_video_selected(self, mock_vm: ProjectViewModel):
        mock_vm.on_video_selected("/path/to/video.mp4")
        mock_vm.project_manager.set_active_zone_video.assert_called_once_with("/path/to/video.mp4")

    def test_handle_delete_hierarchy_node(self, mock_vm: ProjectViewModel):
        mock_vm.project_lifecycle_coordinator.delete_hierarchy_node.return_value = (2, 5)
        res = mock_vm.handle_delete_hierarchy_node("group", group_id="g1")
        assert res == (2, 5)

        mock_vm.project_lifecycle_coordinator = None
        assert mock_vm.handle_delete_hierarchy_node("group", group_id="g1") == (0, 0)

    def test_handle_delete_aquarium(self, mock_vm: ProjectViewModel):
        mock_vm.project_lifecycle_coordinator.delete_aquarium_scope.return_value = True
        res = mock_vm.handle_delete_aquarium("/video.mp4", aquarium_id=1)
        assert res is True
