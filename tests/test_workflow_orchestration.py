from unittest.mock import MagicMock

import pytest

pytest.skip("Obsolete workflow tests", allow_module_level=True)

# --- Types and Constants ---
from zebtrack.ui.event_bus import EventBus
from zebtrack.ui.events import Events

# --- Paths for Patching ---
STATE_MANAGER_PATH = "zebtrack.core.main_view_model.StateManager"
PROJECT_SERVICE_PATH = "zebtrack.core.main_view_model.ProjectService"
ANALYSIS_SERVICE_PATH = "zebtrack.core.main_view_model.AnalysisService"
PROJECT_MANAGER_PATH = "zebtrack.core.main_view_model.ProjectManager"
WEIGHT_MANAGER_PATH = "zebtrack.core.main_view_model.WeightManager"
DETECTOR_SERVICE_PATH = "zebtrack.core.main_view_model.DetectorService"
RECORDER_PATH = "zebtrack.core.main_view_model.Recorder"
ARDUINO_MANAGER_PATH = "zebtrack.core.main_view_model.ArduinoManager"
RECORDING_SERVICE_PATH = "zebtrack.core.main_view_model.RecordingService"
UI_COORDINATOR_PATH = "zebtrack.core.main_view_model.UICoordinator"
GUI_PATH = "zebtrack.core.main_view_model.ApplicationGUI"
VIDEO_PROCESSING_SERVICE_PATH = "zebtrack.core.main_view_model.VideoProcessingService"
SETTINGS_PATH = "zebtrack.core.main_view_model.settings"
MODEL_SERVICE_PATH = "zebtrack.core.main_view_model.ModelService"
PROJECT_WORKFLOW_SERVICE_PATH = "zebtrack.core.main_view_model.ProjectWorkflowService"


@pytest.fixture(scope="function")
def patched_vm_setup():
    """Mocks all dependencies except for the EventBus."""
    from tests.helpers import create_mock_settings, create_test_controller

    # Create real event bus to test event flow
    real_event_bus = EventBus()

    # Create mock settings with event queue enabled
    mock_settings = create_mock_settings()
    mock_settings.ui_features.enable_event_queue = True

    # Create mock project workflow service
    mock_project_workflow_service = MagicMock()
    mock_project_workflow_service.create_project.return_value = {
        "success": True,
        "animal_method": "seg",
        "wizard_metadata": {},
    }

    # Create mock weight manager
    mock_weight_manager = MagicMock()
    mock_weight_manager.get_default_weight.return_value = ("default.pt", {})

    # Create controller using factory with mocked services
    mock_root = MagicMock()
    view_model = create_test_controller(
        mock_root,
        event_bus=real_event_bus,
        settings_obj=mock_settings,
        weight_manager=mock_weight_manager,
        project_workflow_service=mock_project_workflow_service,
    )

    view_model.bind_events()

    yield {
        "view_model": view_model,
        "event_bus": real_event_bus,
        "mocks": {
            "project_workflow_service": mock_project_workflow_service,
        },
    }


class TestWorkflowOrchestration:
    def test_create_project_workflow_event(self, patched_vm_setup):
        event_bus = patched_vm_setup["event_bus"]
        mock_pws = patched_vm_setup["mocks"]["project_workflow_service"]

        payload = {"project_name": "test", "animal_method": "seg"}
        event_bus.publish_event(Events.PROJECT_CREATE, payload)

        # Process the event queue manually (EventBus doesn't have auto-dispatch)
        events = event_bus.drain()
        for event in events:
            if event.type.name == "NAMED":
                event_bus.dispatch_named_event(event.payload)

        mock_pws.create_project.assert_called_once()
        call_args, call_kwargs = mock_pws.create_project.call_args
        assert call_kwargs["project_name"] == "test"
        assert call_kwargs["animal_method"] == "seg"
