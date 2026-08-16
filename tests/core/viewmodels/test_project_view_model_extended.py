"""
Extended unit tests for ProjectViewModel.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from zebtrack.core.viewmodels.project_view_model import ProjectViewModel


def _make_vm() -> ProjectViewModel:
    deps = MagicMock()
    boot = MagicMock()
    boot.batch_configuration_service = MagicMock()
    return ProjectViewModel(
        dependencies=deps,
        bootstrap_result=boot,
        event_bus=MagicMock(),
    )


class TestProjectViewModelExtended:
    """Test ProjectViewModel lifecycle delegation."""

    def test_create_project_workflow(self):
        vm = _make_vm()
        vm.project_lifecycle_coordinator.create_project.return_value = True  # type: ignore[union-attr]
        assert vm.create_project_workflow(name="TestProj") is True
        vm.project_lifecycle_coordinator.create_project.assert_called_once_with(  # type: ignore[union-attr]
            name="TestProj"
        )
        vm.project_lifecycle_coordinator = None
        assert vm.create_project_workflow(name="TestProj") is None

    def test_open_and_close_project_workflow(self):
        vm = _make_vm()
        vm.project_lifecycle_coordinator.open_project.return_value = True  # type: ignore[union-attr]
        assert vm.open_project_workflow("/path/to/proj") is True

        vm.project_lifecycle_coordinator.close_project.return_value = True  # type: ignore[union-attr]
        assert vm.close_project() is True

    def test_on_video_selected(self):
        vm = _make_vm()
        vm.on_video_selected("/path/to/video.mp4")
        vm.project_manager.set_active_zone_video.assert_called_once_with(  # type: ignore[union-attr,attr-defined]
            "/path/to/video.mp4"
        )

    def test_handle_delete_hierarchy_node(self):
        vm = _make_vm()
        vm.project_lifecycle_coordinator.delete_hierarchy_node.return_value = (2, 5)  # type: ignore[union-attr]
        res = vm.handle_delete_hierarchy_node("group", group_id="g1")
        assert res == (2, 5)

        vm.project_lifecycle_coordinator = None
        assert vm.handle_delete_hierarchy_node("group", group_id="g1") == (0, 0)

    def test_handle_delete_aquarium(self):
        vm = _make_vm()
        vm.project_lifecycle_coordinator.delete_aquarium_scope.return_value = True  # type: ignore[union-attr]
        res = vm.handle_delete_aquarium("/video.mp4", aquarium_id=1)
        assert res is True
