"""
Tests for ProjectWorkflowAdapter.

Phase 2, Task P2-T2: Test extraction of project workflow orchestration.
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from zebtrack.ui.project_workflow_adapter import ProjectWorkflowAdapter


@pytest.fixture
def mock_dependencies():
    """Create mock dependencies for ProjectWorkflowAdapter."""
    return {
        "project_workflow_service": Mock(),
        "project_manager": Mock(),
        "detector_service": Mock(),
        "state_manager": Mock(),
        "ui_event_bus": Mock(),
    }


@pytest.fixture
def adapter(mock_dependencies):
    """Create ProjectWorkflowAdapter instance with mocked dependencies."""
    return ProjectWorkflowAdapter(**mock_dependencies)


class TestProjectWorkflowAdapter:
    """Test suite for ProjectWorkflowAdapter."""

    def test_initialization(self, adapter, mock_dependencies):
        """Test that adapter initializes with correct dependencies."""
        assert adapter.project_workflow_service is mock_dependencies["project_workflow_service"]
        assert adapter.project_manager is mock_dependencies["project_manager"]
        assert adapter.detector_service is mock_dependencies["detector_service"]
        assert adapter.state_manager is mock_dependencies["state_manager"]
        assert adapter.ui_event_bus is mock_dependencies["ui_event_bus"]

    def test_close_project_success(self, adapter, mock_dependencies):
        """Test successful project close workflow."""
        # Setup
        restore_callback = Mock()
        settings_obj = Mock()

        # Execute
        result = adapter.close_project(
            restore_global_defaults_callback=restore_callback,
            settings_obj=settings_obj,
        )

        # Verify
        restore_callback.assert_called_once()
        mock_dependencies["state_manager"].update_project_state.assert_called_once()
        mock_dependencies["ui_event_bus"].publish_event.assert_called_once()
        assert result is not None  # Returns new ProjectManager instance

    def test_create_project_workflow_success(self, adapter, mock_dependencies):
        """Test successful project creation workflow."""
        # Setup
        mock_dependencies["project_workflow_service"].create_project.return_value = {
            "success": True,
            "animal_method": "det",
            "wizard_metadata": {"detector_parameters": {}},
        }

        setup_detector_mock = Mock(return_value=True)
        apply_overrides_mock = Mock()
        callbacks = {
            "setup_detector_callback": setup_detector_mock,
            "set_active_weight_callback": Mock(),
            "set_openvino_usage_callback": Mock(),
            "update_openvino_status_callback": Mock(),
            "get_active_weight_name": lambda: "test_weight",
            "get_use_openvino": lambda: False,
            "apply_wizard_overrides_callback": apply_overrides_mock,
        }

        # Execute
        result = adapter.create_project_workflow(**callbacks, project_name="test")

        # Verify
        assert result is True
        setup_detector_mock.assert_called_once_with("det")
        apply_overrides_mock.assert_called_once()
        assert mock_dependencies["ui_event_bus"].publish_event.call_count >= 3

    def test_create_project_workflow_service_failure(self, adapter, mock_dependencies):
        """Test project creation workflow when service fails."""
        # Setup
        mock_dependencies["project_workflow_service"].create_project.return_value = {
            "success": False,
            "error_message": "Test error",
        }

        callbacks = {
            "setup_detector_callback": Mock(),
            "set_active_weight_callback": Mock(),
            "set_openvino_usage_callback": Mock(),
            "update_openvino_status_callback": Mock(),
            "get_active_weight_name": lambda: "test_weight",
            "get_use_openvino": lambda: False,
            "apply_wizard_overrides_callback": Mock(),
        }

        # Execute
        result = adapter.create_project_workflow(**callbacks)

        # Verify
        assert result is False
        # Should publish error event
        error_calls = [
            call_
            for call_ in mock_dependencies["ui_event_bus"].publish_event.call_args_list
            if "UI_SHOW_ERROR" in str(call_)
        ]
        assert len(error_calls) >= 1

    def test_create_project_workflow_detector_setup_failure(self, adapter, mock_dependencies):
        """Test project creation workflow when detector setup fails."""
        # Setup
        mock_dependencies["project_workflow_service"].create_project.return_value = {
            "success": True,
            "animal_method": "det",
            "wizard_metadata": None,
        }

        setup_detector_mock = Mock(return_value=False)  # Detector setup fails
        callbacks = {
            "setup_detector_callback": setup_detector_mock,
            "set_active_weight_callback": Mock(),
            "set_openvino_usage_callback": Mock(),
            "update_openvino_status_callback": Mock(),
            "get_active_weight_name": lambda: "test_weight",
            "get_use_openvino": lambda: False,
            "apply_wizard_overrides_callback": Mock(),
        }

        # Execute
        result = adapter.create_project_workflow(**callbacks)

        # Verify
        assert result is False
        setup_detector_mock.assert_called_once_with("det")

    def test_open_project_workflow_success(self, adapter, mock_dependencies):
        """Test successful project open workflow."""
        # Setup
        mock_dependencies["project_workflow_service"].open_project.return_value = {
            "success": True,
            "project_info": {
                "name": "Test Project",
                "videos_count": 5,
                "zone_status": "configured",
                "roi_count": 3,
                "active_weight": "test_weight",
                "use_openvino": False,
            },
        }

        setup_detector_mock = Mock(return_value=True)
        callbacks = {
            "setup_detector_callback": setup_detector_mock,
            "set_active_weight_callback": Mock(),
            "set_openvino_usage_callback": Mock(),
            "update_openvino_status_callback": Mock(),
            "setup_zones_callback": Mock(),
            "restore_detector_callback": Mock(),
            "get_active_weight_name": lambda: "test_weight",
            "get_use_openvino": lambda: False,
        }

        # Execute
        result = adapter.open_project_workflow(
            project_path=Path("/test/project.json"),
            **callbacks,
        )

        # Verify
        assert result is True
        setup_detector_mock.assert_called_once()
        # Should publish success info event
        info_calls = [
            call_
            for call_ in mock_dependencies["ui_event_bus"].publish_event.call_args_list
            if "UI_SHOW_INFO" in str(call_)
        ]
        assert len(info_calls) >= 1

    def test_open_project_workflow_service_failure(self, adapter, mock_dependencies):
        """Test project open workflow when service fails."""
        # Setup
        mock_dependencies["project_workflow_service"].open_project.return_value = {
            "success": False,
            "error_message": "Project not found",
        }

        callbacks = {
            "setup_detector_callback": Mock(),
            "set_active_weight_callback": Mock(),
            "set_openvino_usage_callback": Mock(),
            "update_openvino_status_callback": Mock(),
            "setup_zones_callback": Mock(),
            "restore_detector_callback": Mock(),
            "get_active_weight_name": lambda: "test_weight",
            "get_use_openvino": lambda: False,
        }

        # Execute
        result = adapter.open_project_workflow(
            project_path=Path("/test/project.json"),
            **callbacks,
        )

        # Verify
        assert result is False

    def test_open_project_workflow_detector_setup_failure(self, adapter, mock_dependencies):
        """Test project open workflow when detector setup fails."""
        # Setup
        mock_dependencies["project_workflow_service"].open_project.return_value = {
            "success": True,
            "project_info": {
                "name": "Test Project",
                "videos_count": 5,
                "zone_status": "configured",
                "roi_count": 3,
                "active_weight": "test_weight",
                "use_openvino": False,
            },
        }

        setup_detector_mock = Mock(return_value=False)  # Detector setup fails
        callbacks = {
            "setup_detector_callback": setup_detector_mock,
            "set_active_weight_callback": Mock(),
            "set_openvino_usage_callback": Mock(),
            "update_openvino_status_callback": Mock(),
            "setup_zones_callback": Mock(),
            "restore_detector_callback": Mock(),
            "get_active_weight_name": lambda: "test_weight",
            "get_use_openvino": lambda: False,
        }

        # Execute
        result = adapter.open_project_workflow(
            project_path=Path("/test/project.json"),
            **callbacks,
        )

        # Verify
        assert result is False
        setup_detector_mock.assert_called_once()

    def test_setup_zones_from_project(self, adapter, mock_dependencies):
        """Test setup zones from project."""
        # Setup
        setup_zones_callback = Mock()

        # Execute
        adapter.setup_zones_from_project(
            setup_detector_zones_callback=setup_zones_callback,
        )

        # Verify
        setup_zones_callback.assert_called_once()
        # Should publish zone update events
        assert mock_dependencies["ui_event_bus"].publish_event.call_count == 2

    def test_show_post_creation_guide(self, adapter, mock_dependencies):
        """Test showing post-creation guide."""
        # Setup
        mock_dependencies["project_workflow_service"].generate_post_creation_guide.return_value = {
            "title": "Welcome",
            "message": "Project created successfully",
        }

        wizard_metadata = {"experiment_id": "test_exp"}

        # Execute
        adapter._show_post_creation_guide(wizard_metadata)

        # Verify
        mock_dependencies[
            "project_workflow_service"
        ].generate_post_creation_guide.assert_called_once()
        mock_dependencies["ui_event_bus"].publish_event.assert_called_once()

    def test_show_post_creation_guide_suppressed(self, adapter, mock_dependencies):
        """Test showing post-creation guide when suppressed."""
        # Setup
        suppress_check = Mock(return_value=True)
        wizard_metadata = {"experiment_id": "test_exp"}

        # Execute
        adapter._show_post_creation_guide(wizard_metadata, suppress_check)

        # Verify - should not call service or publish events
        mock_dependencies[
            "project_workflow_service"
        ].generate_post_creation_guide.assert_not_called()
        mock_dependencies["ui_event_bus"].publish_event.assert_not_called()

    def test_show_post_creation_guide_no_guide_generated(self, adapter, mock_dependencies):
        """Test showing post-creation guide when no guide is generated."""
        # Setup
        mock_dependencies["project_workflow_service"].generate_post_creation_guide.return_value = (
            None
        )

        wizard_metadata = {"experiment_id": "test_exp"}

        # Execute
        adapter._show_post_creation_guide(wizard_metadata)

        # Verify - should not publish event if no guide generated
        mock_dependencies["ui_event_bus"].publish_event.assert_not_called()
