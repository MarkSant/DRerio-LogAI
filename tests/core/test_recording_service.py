"""
Unit tests for RecordingService.

Phase: Sprint 1.1 - Complete test coverage for RecordingService
Tests recording session lifecycle, Arduino integration, timed recording,
and state management coordination.
"""

from unittest.mock import Mock, patch

import pytest

from zebtrack.core.recording_service import RecordingService


@pytest.fixture
def mock_controller():
    """Create mock MainViewModel controller."""
    controller = Mock()
    controller.recorder = Mock()
    controller.arduino_manager = Mock()
    return controller


@pytest.fixture
def mock_state_manager():
    """Create mock StateManager."""
    sm = Mock()
    sm.get_recording_state = Mock(return_value=Mock(is_recording=False))
    sm.update_recording_state = Mock()
    return sm


@pytest.fixture
def mock_project_manager():
    """Create mock ProjectManager."""
    pm = Mock()
    pm.project_data = {}
    pm.get_zone_data = Mock(return_value=Mock(polygon=[[0, 0], [100, 0], [100, 100], [0, 100]]))
    return pm


@pytest.fixture
def mock_root():
    """Create mock Tkinter root."""
    root = Mock()
    root.after = Mock(return_value="job_id_123")
    root.after_cancel = Mock()
    return root


@pytest.fixture
def recording_service(mock_controller, mock_state_manager, mock_project_manager, mock_root):
    """Create RecordingService with mocked dependencies."""
    service = RecordingService(
        controller=mock_controller,
        state_manager=mock_state_manager,
        project_manager=mock_project_manager,
        root=mock_root,
    )
    # Setup UI callbacks
    service.set_ui_callbacks(
        {
            "show_error": Mock(),
            "update_button_state": Mock(),
            "set_status": Mock(),
            "stop_recording_callback": Mock(),
        }
    )
    return service


class TestRecordingServiceInitialization:
    """Test suite for RecordingService initialization."""

    def test_init_with_all_dependencies(
        self, mock_controller, mock_state_manager, mock_project_manager, mock_root
    ):
        """Test initialization with all dependencies."""
        service = RecordingService(
            controller=mock_controller,
            state_manager=mock_state_manager,
            project_manager=mock_project_manager,
            root=mock_root,
        )

        assert service.controller == mock_controller
        assert service.state_manager == mock_state_manager
        assert service.project_manager == mock_project_manager
        assert service.root == mock_root
        assert service.timed_recording_job is None

    def test_init_without_root(self, mock_controller, mock_state_manager, mock_project_manager):
        """Test initialization without Tkinter root."""
        service = RecordingService(
            controller=mock_controller,
            state_manager=mock_state_manager,
            project_manager=mock_project_manager,
            root=None,
        )

        assert service.root is None

    def test_recorder_property_accesses_controller(self, recording_service, mock_controller):
        """Test recorder property delegates to controller."""
        assert recording_service.recorder == mock_controller.recorder

    def test_arduino_manager_property_accesses_controller(self, recording_service, mock_controller):
        """Test arduino_manager property delegates to controller."""
        assert recording_service.arduino_manager == mock_controller.arduino_manager

    def test_set_ui_callbacks(self, recording_service):
        """Test UI callbacks can be set."""
        callbacks = {
            "show_error": Mock(),
            "update_button_state": Mock(),
        }
        recording_service.set_ui_callbacks(callbacks)

        assert recording_service._ui_callbacks == callbacks


class TestScheduleRecording:
    """Test suite for schedule_recording method."""

    def test_schedule_recording_immediate_without_countdown(self, recording_service):
        """Test recording starts immediately when countdown disabled."""
        context = {
            "folder_name": "test_session",
            "output_folder": "/fake/output",
            "camera_width": 640,
            "camera_height": 480,
            "day": 1,
            "group": "G1",
            "cobaia": "1",
            "arduino_enabled": False,
        }
        project_data = {
            "use_countdown": False,
            "countdown_duration_s": 0,
        }

        # Mock start_session to avoid full execution
        recording_service.start_session = Mock()

        recording_service.schedule_recording(context, project_data, trigger_source="manual")

        # Should call start_session immediately
        recording_service.start_session.assert_called_once_with(context, project_data, "manual")

    def test_schedule_recording_with_countdown_enabled(self, recording_service):
        """Test recording calls countdown when enabled."""
        context = {
            "folder_name": "test_session",
            "output_folder": "/fake/output",
            "camera_width": 640,
            "camera_height": 480,
        }
        project_data = {
            "use_countdown": True,
            "countdown_duration_s": 3,
        }

        recording_service._run_countdown = Mock()

        recording_service.schedule_recording(context, project_data, trigger_source="manual")

        # Should call countdown
        recording_service._run_countdown.assert_called_once()
        args = recording_service._run_countdown.call_args
        assert args[0][0] == 3  # duration_s

    def test_schedule_recording_countdown_zero_duration(self, recording_service):
        """Test countdown with zero duration starts immediately."""
        context = {
            "folder_name": "test_session",
            "output_folder": "/fake/output",
            "camera_width": 640,
            "camera_height": 480,
        }
        project_data = {
            "use_countdown": True,
            "countdown_duration_s": 0,  # Zero duration = immediate start
        }

        recording_service.start_session = Mock()

        recording_service.schedule_recording(context, project_data, trigger_source="manual")

        # Should NOT use countdown
        recording_service.start_session.assert_called_once()


class TestStartSession:
    """Test suite for start_session method."""

    def test_start_session_validates_camera_dimensions(self, recording_service):
        """Test start_session validates camera dimensions."""
        context = {
            "folder_name": "test_session",
            "output_folder": "/fake/output",
            "camera_width": None,  # Missing dimension
            "camera_height": 480,
        }
        project_data = {}

        recording_service.start_session(context, project_data, "manual")

        # Should show error
        recording_service._ui_callbacks["show_error"].assert_called_once()
        error_call = recording_service._ui_callbacks["show_error"].call_args
        assert "câmera" in error_call[0][1].lower() or "camera" in error_call[0][1].lower()

    def test_start_session_starts_recorder(self, recording_service, mock_controller):
        """Test start_session calls recorder.start_recording."""
        context = {
            "folder_name": "test_session",
            "output_folder": "/fake/output",
            "camera_width": 640,
            "camera_height": 480,
            "arduino_enabled": False,
        }
        project_data = {}

        mock_controller.recorder.start_recording = Mock(return_value=True)

        recording_service.start_session(context, project_data, "manual")

        # Should call recorder
        mock_controller.recorder.start_recording.assert_called_once()
        call_args = mock_controller.recorder.start_recording.call_args
        assert call_args[0][0] == "/fake/output"
        assert call_args[0][1] == 640
        assert call_args[0][2] == 480

    def test_start_session_updates_state_manager(
        self, recording_service, mock_state_manager, mock_controller
    ):
        """Test start_session updates StateManager with recording state."""
        context = {
            "folder_name": "test_session",
            "output_folder": "/fake/output",
            "camera_width": 640,
            "camera_height": 480,
            "arduino_enabled": False,
        }
        project_data = {}

        mock_controller.recorder.start_recording = Mock(return_value=True)

        recording_service.start_session(context, project_data, "manual")

        # Should update state manager
        mock_state_manager.update_recording_state.assert_called_once()
        call_args = mock_state_manager.update_recording_state.call_args
        assert call_args[1]["is_recording"] is True
        assert call_args[1]["source"] == "recording_service.start_session.manual"

    def test_start_session_handles_recorder_failure(self, recording_service, mock_controller):
        """Test start_session handles recorder start failure."""
        context = {
            "folder_name": "test_session",
            "output_folder": "/fake/output",
            "camera_width": 640,
            "camera_height": 480,
        }
        project_data = {}

        mock_controller.recorder.start_recording = Mock(return_value=False)

        recording_service.start_session(context, project_data, "manual")

        # Should show error
        recording_service._ui_callbacks["show_error"].assert_called()
        error_msg = recording_service._ui_callbacks["show_error"].call_args[0][1]
        assert "gravação" in error_msg.lower() or "recording" in error_msg.lower()

    def test_start_session_sends_arduino_command(self, recording_service, mock_controller):
        """Test start_session sends Arduino command when enabled."""
        context = {
            "folder_name": "test_session",
            "output_folder": "/fake/output",
            "camera_width": 640,
            "camera_height": 480,
            "arduino_enabled": True,
            "day": 1,
            "group": "G1",
            "cobaia": "3",  # Box number 3
        }
        project_data = {}

        mock_controller.recorder.start_recording = Mock(return_value=True)
        mock_controller.arduino_manager.send_command = Mock()

        recording_service.start_session(context, project_data, "manual")

        # Should send Arduino command
        mock_controller.arduino_manager.send_command.assert_called_once()
        call_args = mock_controller.arduino_manager.send_command.call_args
        assert call_args[0][0] == 3  # Box number

    def test_start_session_schedules_timed_recording(self, recording_service, mock_root):
        """Test start_session schedules timed recording when enabled."""
        context = {
            "folder_name": "test_session",
            "output_folder": "/fake/output",
            "camera_width": 640,
            "camera_height": 480,
            "arduino_enabled": False,
        }
        project_data = {
            "use_timed_recording": True,
            "recording_duration_s": 60,  # 60 seconds
        }

        recording_service.controller.recorder.start_recording = Mock(return_value=True)

        recording_service.start_session(context, project_data, "manual")

        # Should schedule timed job
        mock_root.after.assert_called_once()
        call_args = mock_root.after.call_args
        assert call_args[0][0] == 60000  # 60 seconds = 60000 ms
        assert recording_service.timed_recording_job == "job_id_123"

    def test_start_session_updates_ui_buttons(self, recording_service, mock_controller):
        """Test start_session updates UI button states."""
        context = {
            "folder_name": "test_session",
            "output_folder": "/fake/output",
            "camera_width": 640,
            "camera_height": 480,
            "arduino_enabled": False,
        }
        project_data = {}

        mock_controller.recorder.start_recording = Mock(return_value=True)

        recording_service.start_session(context, project_data, "manual")

        # Should update buttons
        update_calls = recording_service._ui_callbacks["update_button_state"].call_args_list
        assert any("start_rec" in str(call) and "disabled" in str(call) for call in update_calls)
        assert any("stop_rec" in str(call) and "normal" in str(call) for call in update_calls)


class TestStopSession:
    """Test suite for stop_session method."""

    def test_stop_session_cancels_timed_job(self, recording_service, mock_root):
        """Test stop_session cancels timed recording job."""
        recording_service.timed_recording_job = "job_id_123"

        recording_service.stop_session()

        # Should cancel job
        mock_root.after_cancel.assert_called_once_with("job_id_123")
        assert recording_service.timed_recording_job is None

    def test_stop_session_stops_recorder(
        self, recording_service, mock_controller, mock_state_manager
    ):
        """Test stop_session stops recorder."""
        mock_state_manager.get_recording_state = Mock(return_value=Mock(is_recording=True))

        recording_service.stop_session()

        # Should stop recorder
        mock_controller.recorder.stop_recording.assert_called_once()

    def test_stop_session_updates_state_manager(self, recording_service, mock_state_manager):
        """Test stop_session updates StateManager."""
        mock_state_manager.get_recording_state = Mock(return_value=Mock(is_recording=True))

        recording_service.stop_session()

        # Should update state
        mock_state_manager.update_recording_state.assert_called_once()
        call_args = mock_state_manager.update_recording_state.call_args
        assert call_args[1]["is_recording"] is False

    def test_stop_session_sends_arduino_stop_command(
        self, recording_service, mock_controller, mock_project_manager
    ):
        """Test stop_session sends Arduino stop command."""
        mock_project_manager.project_data = {"use_arduino": True}
        mock_controller.arduino_manager.is_connected = Mock(return_value=True)
        mock_controller.arduino_manager.send_command = Mock(return_value=True)

        recording_service.stop_session()

        # Should send stop command (box 0)
        mock_controller.arduino_manager.send_command.assert_called_once_with(
            0, source="manual-stop"
        )

    def test_stop_session_handles_arduino_not_connected(
        self, recording_service, mock_controller, mock_project_manager
    ):
        """Test stop_session handles Arduino not connected gracefully."""
        mock_project_manager.project_data = {"use_arduino": True}
        mock_controller.arduino_manager.is_connected = Mock(return_value=False)

        # Should not raise exception
        recording_service.stop_session()

    def test_stop_session_updates_ui_buttons(self, recording_service, mock_state_manager):
        """Test stop_session updates UI button states."""
        mock_state_manager.get_recording_state = Mock(return_value=Mock(is_recording=True))

        recording_service.stop_session()

        # Should update buttons
        update_calls = recording_service._ui_callbacks["update_button_state"].call_args_list
        assert any("start_rec" in str(call) and "normal" in str(call) for call in update_calls)
        assert any("stop_rec" in str(call) and "disabled" in str(call) for call in update_calls)


class TestResolveBoxNumber:
    """Test suite for _resolve_box_number method."""

    def test_resolve_box_number_valid_integer_string(self, recording_service):
        """Test box number resolution with valid integer string."""
        box_num = recording_service._resolve_box_number(1, "G1", "3")
        assert box_num == 3

    def test_resolve_box_number_valid_integer(self, recording_service):
        """Test box number resolution with integer."""
        box_num = recording_service._resolve_box_number(1, "G1", 5)
        assert box_num == 5

    def test_resolve_box_number_invalid_string(self, recording_service):
        """Test box number resolution with invalid string."""
        box_num = recording_service._resolve_box_number(1, "G1", "invalid")
        assert box_num is None

    def test_resolve_box_number_none(self, recording_service):
        """Test box number resolution with None."""
        box_num = recording_service._resolve_box_number(1, "G1", None)
        assert box_num is None


class TestUICallbacks:
    """Test suite for UI callback wrappers."""

    def test_show_error_calls_callback(self, recording_service):
        """Test _show_error calls registered callback."""
        recording_service._show_error("Test Title", "Test Message")

        recording_service._ui_callbacks["show_error"].assert_called_once_with(
            "Test Title", "Test Message"
        )

    def test_update_button_state_calls_callback(self, recording_service):
        """Test _update_button_state calls registered callback."""
        recording_service._update_button_state("start_rec", "disabled")

        recording_service._ui_callbacks["update_button_state"].assert_called_once_with(
            "start_rec", "disabled"
        )

    def test_set_status_calls_callback(self, recording_service):
        """Test _set_status calls registered callback."""
        recording_service._set_status("Test status")

        recording_service._ui_callbacks["set_status"].assert_called_once_with("Test status")

    def test_callbacks_handle_missing_gracefully(self, recording_service):
        """Test UI callbacks handle missing callbacks gracefully."""
        recording_service._ui_callbacks = {}

        # Should not raise exception
        recording_service._show_error("Title", "Message")
        recording_service._update_button_state("button", "state")
        recording_service._set_status("status")


class TestCountdown:
    """Test suite for countdown functionality."""

    @patch("zebtrack.core.recording_service.Toplevel")
    @patch("zebtrack.core.recording_service.Label")
    def test_run_countdown_creates_window(
        self, mock_label, mock_toplevel, recording_service, mock_root
    ):
        """Test countdown creates Toplevel window."""
        # Mock screen dimensions for division
        mock_root.winfo_screenwidth.return_value = 1920
        mock_root.winfo_screenheight.return_value = 1080

        callback = Mock()

        recording_service._run_countdown(3, callback)

        # Should create Toplevel
        mock_toplevel.assert_called_once_with(mock_root)

    def test_run_countdown_without_root_executes_callback_immediately(
        self, mock_controller, mock_state_manager, mock_project_manager
    ):
        """Test countdown without root executes callback immediately."""
        service = RecordingService(
            controller=mock_controller,
            state_manager=mock_state_manager,
            project_manager=mock_project_manager,
            root=None,
        )

        callback = Mock()
        service._run_countdown(3, callback)

        # Should execute callback immediately
        callback.assert_called_once()


class TestIntegrationScenarios:
    """Integration test scenarios for RecordingService."""

    def test_full_recording_cycle_with_timed_recording(
        self, recording_service, mock_controller, mock_root, mock_state_manager
    ):
        """Test complete recording cycle with timed recording."""
        # Setup
        context = {
            "folder_name": "integration_test",
            "output_folder": "/fake/output",
            "camera_width": 640,
            "camera_height": 480,
            "arduino_enabled": False,
        }
        project_data = {
            "use_countdown": False,
            "use_timed_recording": True,
            "recording_duration_s": 30,
        }

        mock_controller.recorder.start_recording = Mock(return_value=True)

        # Start recording
        recording_service.schedule_recording(context, project_data, trigger_source="manual")

        # Verify recording started
        mock_controller.recorder.start_recording.assert_called_once()
        assert recording_service.timed_recording_job == "job_id_123"

        # Simulate recording state being active
        mock_state_manager.get_recording_state.return_value = Mock(is_recording=True)

        # Stop recording
        recording_service.stop_session()

        # Verify job cancelled and recorder stopped
        mock_root.after_cancel.assert_called_once_with("job_id_123")
        mock_controller.recorder.stop_recording.assert_called_once()

    def test_external_trigger_with_arduino(self, recording_service, mock_controller):
        """Test external trigger scenario with Arduino."""
        context = {
            "folder_name": "external_trigger_test",
            "output_folder": "/fake/output",
            "camera_width": 640,
            "camera_height": 480,
            "arduino_enabled": True,
            "day": 1,
            "group": "G1",
            "cobaia": "2",
        }
        project_data = {"use_countdown": False}

        mock_controller.recorder.start_recording = Mock(return_value=True)
        mock_controller.arduino_manager.send_command = Mock()

        # Trigger recording
        recording_service.schedule_recording(context, project_data, trigger_source="external")

        # Verify Arduino command sent
        mock_controller.arduino_manager.send_command.assert_called_once()
        call_args = mock_controller.arduino_manager.send_command.call_args
        assert call_args[0][0] == 2  # Box number from cobaia


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
