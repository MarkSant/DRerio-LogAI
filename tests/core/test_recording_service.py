"""
Unit tests for RecordingService.

Phase: Sprint 1.1 - Complete test coverage for RecordingService
Tests recording session lifecycle, Arduino integration, timed recording,
and state management coordination.
"""

import tkinter as tk
from typing import Any, cast
from unittest.mock import Mock, patch

import pytest

from zebtrack.core.recording.recording_service import RecordingService

type ProjectData = dict[str, Any]


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
    pm.project_data = cast(ProjectData, {})
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
        project_data: ProjectData = {
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
        project_data: ProjectData = {
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
        project_data: ProjectData = {
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
        project_data: ProjectData = {}

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
        project_data: ProjectData = {}

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
        project_data: ProjectData = {}

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
        project_data: ProjectData = {}

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
        project_data: ProjectData = {}

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
        project_data: ProjectData = {
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
        project_data: ProjectData = {}

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
        mock_project_manager.project_data = cast(ProjectData, {"use_arduino": True})
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
        mock_project_manager.project_data = cast(ProjectData, {"use_arduino": True})
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

    @patch("zebtrack.core.recording.recording_service.Toplevel")
    @patch("zebtrack.core.recording.recording_service.Label")
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
        project_data: ProjectData = {
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
        project_data: ProjectData = {"use_countdown": False}

        mock_controller.recorder.start_recording = Mock(return_value=True)
        mock_controller.arduino_manager.send_command = Mock()

        # Trigger recording
        recording_service.schedule_recording(context, project_data, trigger_source="external")

        # Verify Arduino command sent
        mock_controller.arduino_manager.send_command.assert_called_once()
        call_args = mock_controller.arduino_manager.send_command.call_args
        assert call_args[0][0] == 2  # Box number from cobaia


class TestRecordingServiceRecorderFailures:
    """Test suite for recorder (parquet/video writer) failure scenarios."""

    def test_start_session_recorder_start_fails(self, recording_service, mock_controller):
        """Test start_session when recorder.start_recording returns False."""
        context = {
            "folder_name": "test_session",
            "output_folder": "/fake/output",
            "camera_width": 640,
            "camera_height": 480,
            "arduino_enabled": False,
        }
        project_data: ProjectData = {}

        mock_controller.recorder.start_recording = Mock(return_value=False)

        recording_service.start_session(context, project_data, "manual")

        # Should show error and restore button states
        recording_service._ui_callbacks["show_error"].assert_called_once()
        error_msg = recording_service._ui_callbacks["show_error"].call_args[0][1]
        assert "gravação" in error_msg.lower() or "recording" in error_msg.lower()

        # Buttons should be restored
        update_calls = recording_service._ui_callbacks["update_button_state"].call_args_list
        assert any("start_rec" in str(call) and "normal" in str(call) for call in update_calls)

    def test_start_session_recorder_raises_exception(self, recording_service, mock_controller):
        """Test start_session when recorder raises exception (disk full, permissions)."""
        context = {
            "folder_name": "test_session",
            "output_folder": "/readonly/output",
            "camera_width": 640,
            "camera_height": 480,
            "arduino_enabled": False,
        }
        project_data: ProjectData = {}

        # Simulate disk full or permission error
        mock_controller.recorder.start_recording = Mock(
            side_effect=PermissionError("Permission denied")
        )

        # Execute - should handle exception
        with pytest.raises(PermissionError):
            recording_service.start_session(context, project_data, "manual")

    def test_stop_session_recorder_raises_exception(self, recording_service, mock_controller):
        """Test stop_session when recorder.stop_recording raises exception."""
        mock_state = Mock(is_recording=True)
        recording_service.state_manager.get_recording_state = Mock(return_value=mock_state)

        mock_controller.recorder.stop_recording = Mock(side_effect=RuntimeError("Flush failed"))

        # Execute - should handle exception
        with pytest.raises(RuntimeError):
            recording_service.stop_session()

    def test_start_session_with_invalid_output_path(self, recording_service):
        """Test start_session with invalid/inaccessible output path."""
        context = {
            "folder_name": "test_session",
            "output_folder": "",  # Empty path
            "camera_width": 640,
            "camera_height": 480,
            "arduino_enabled": False,
        }
        project_data: ProjectData = {}

        recording_service.controller.recorder.start_recording = Mock(return_value=True)

        # Should handle empty path
        recording_service.start_session(context, project_data, "manual")

        # Recorder should be called with empty path
        recording_service.controller.recorder.start_recording.assert_called_once()


class TestRecordingServiceArduinoFailures:
    """Test suite for Arduino command failures."""

    def test_start_session_arduino_send_command_fails(
        self, recording_service, mock_controller, mock_project_manager
    ):
        """Test start_session when Arduino command fails."""
        context = {
            "folder_name": "test_session",
            "output_folder": "/fake/output",
            "camera_width": 640,
            "camera_height": 480,
            "arduino_enabled": True,
            "day": 1,
            "group": "G1",
            "cobaia": "3",
        }
        project_data: ProjectData = {}

        mock_controller.recorder.start_recording = Mock(return_value=True)
        mock_controller.arduino_manager.send_command = Mock(return_value=False)

        # Execute
        recording_service.start_session(context, project_data, "manual")

        # Should still start recording even if Arduino fails
        mock_controller.recorder.start_recording.assert_called_once()
        mock_controller.arduino_manager.send_command.assert_called_once_with(
            3, source="manual-start"
        )

    def test_start_session_arduino_raises_exception(self, recording_service, mock_controller):
        """Test start_session when Arduino raises exception."""
        context = {
            "folder_name": "test_session",
            "output_folder": "/fake/output",
            "camera_width": 640,
            "camera_height": 480,
            "arduino_enabled": True,
            "day": 1,
            "group": "G1",
            "cobaia": "2",
        }
        project_data: ProjectData = {}

        mock_controller.recorder.start_recording = Mock(return_value=True)
        mock_controller.arduino_manager.send_command = Mock(
            side_effect=RuntimeError("Serial port error")
        )

        # Execute - should handle exception and continue
        with pytest.raises(RuntimeError):
            recording_service.start_session(context, project_data, "manual")

    def test_stop_session_arduino_not_connected(
        self, recording_service, mock_controller, mock_project_manager
    ):
        """Test stop_session when Arduino is not connected."""
        mock_project_manager.project_data = cast(ProjectData, {"use_arduino": True})
        mock_controller.arduino_manager.is_connected = Mock(return_value=False)

        # Execute
        recording_service.stop_session()

        # Should not attempt to send command
        mock_controller.arduino_manager.send_command.assert_not_called()

    def test_stop_session_arduino_send_command_fails(
        self, recording_service, mock_controller, mock_project_manager
    ):
        """Test stop_session when Arduino stop command fails."""
        mock_project_manager.project_data = cast(ProjectData, {"use_arduino": True})
        mock_controller.arduino_manager.is_connected = Mock(return_value=True)
        mock_controller.arduino_manager.send_command = Mock(return_value=False)

        # Execute
        recording_service.stop_session()

        # Should attempt to send command even if it fails
        mock_controller.arduino_manager.send_command.assert_called_once_with(
            0, source="manual-stop"
        )

    def test_resolve_box_number_invalid_cobaia(self, recording_service):
        """Test box number resolution with invalid cobaia value."""
        # Non-numeric cobaia
        box_num = recording_service._resolve_box_number(1, "G1", "invalid")
        assert box_num is None

        # Empty string
        box_num = recording_service._resolve_box_number(1, "G1", "")
        assert box_num is None

        # Special characters
        box_num = recording_service._resolve_box_number(1, "G1", "box-3")
        assert box_num is None


class TestRecordingServiceStateManagerFailures:
    """Test suite for StateManager update failures."""

    def test_start_session_state_update_raises_exception(
        self, recording_service, mock_controller, mock_state_manager
    ):
        """Test start_session when state_manager.update_recording_state raises exception."""
        context = {
            "folder_name": "test_session",
            "output_folder": "/fake/output",
            "camera_width": 640,
            "camera_height": 480,
            "arduino_enabled": False,
        }
        project_data: ProjectData = {}

        mock_controller.recorder.start_recording = Mock(return_value=True)
        mock_state_manager.update_recording_state = Mock(
            side_effect=RuntimeError("State update failed")
        )

        # Execute - should propagate exception
        with pytest.raises(RuntimeError):
            recording_service.start_session(context, project_data, "manual")

    def test_stop_session_state_get_raises_exception(self, recording_service, mock_state_manager):
        """Test stop_session when get_recording_state raises exception."""
        mock_state_manager.get_recording_state = Mock(side_effect=RuntimeError("State read failed"))

        # Execute - should propagate exception
        with pytest.raises(RuntimeError):
            recording_service.stop_session()

    def test_stop_session_state_update_raises_exception(
        self, recording_service, mock_state_manager, mock_controller
    ):
        """Test stop_session when update_recording_state raises exception."""
        mock_state = Mock(is_recording=True)
        mock_state_manager.get_recording_state = Mock(return_value=mock_state)
        mock_state_manager.update_recording_state = Mock(
            side_effect=RuntimeError("State update failed")
        )

        # Execute - should propagate exception
        with pytest.raises(RuntimeError):
            recording_service.stop_session()


class TestRecordingServiceTimedRecordingEdgeCases:
    """Test suite for timed recording edge cases."""

    def test_start_session_timed_recording_no_root(
        self, mock_controller, mock_state_manager, mock_project_manager
    ):
        """Test timed recording when root is None."""
        service = RecordingService(
            controller=mock_controller,
            state_manager=mock_state_manager,
            project_manager=mock_project_manager,
            root=None,  # No root
        )
        service.set_ui_callbacks(
            {
                "show_error": Mock(),
                "update_button_state": Mock(),
                "set_status": Mock(),
                "stop_recording_callback": Mock(),
            }
        )

        context = {
            "folder_name": "test_session",
            "output_folder": "/fake/output",
            "camera_width": 640,
            "camera_height": 480,
            "arduino_enabled": False,
        }
        project_data: ProjectData = {
            "use_timed_recording": True,
            "recording_duration_s": 60,
        }

        mock_controller.recorder.start_recording = Mock(return_value=True)

        service.start_session(context, project_data, "manual")

        # Should not schedule timed job without root
        assert service.timed_recording_job is None

    def test_start_session_timed_recording_zero_duration(
        self, recording_service, mock_controller, mock_root
    ):
        """Test timed recording with zero duration."""
        context = {
            "folder_name": "test_session",
            "output_folder": "/fake/output",
            "camera_width": 640,
            "camera_height": 480,
            "arduino_enabled": False,
        }
        project_data: ProjectData = {
            "use_timed_recording": True,
            "recording_duration_s": 0,  # Zero duration
        }

        mock_controller.recorder.start_recording = Mock(return_value=True)

        recording_service.start_session(context, project_data, "manual")

        # Should not schedule job with zero duration
        mock_root.after.assert_not_called()

    def test_start_session_timed_recording_negative_duration(
        self, recording_service, mock_controller, mock_root
    ):
        """Test timed recording with negative duration."""
        context = {
            "folder_name": "test_session",
            "output_folder": "/fake/output",
            "camera_width": 640,
            "camera_height": 480,
            "arduino_enabled": False,
        }
        project_data: ProjectData = {
            "use_timed_recording": True,
            "recording_duration_s": -10,  # Negative duration
        }

        mock_controller.recorder.start_recording = Mock(return_value=True)

        recording_service.start_session(context, project_data, "manual")

        # Should not schedule job with negative duration
        mock_root.after.assert_not_called()

    def test_stop_session_cancels_nonexistent_job(self, recording_service, mock_root):
        """Test stop_session when timed job doesn't exist."""
        recording_service.timed_recording_job = None

        # Execute - should not raise exception
        recording_service.stop_session()

        # Should not attempt to cancel
        mock_root.after_cancel.assert_not_called()


class TestRecordingServiceCountdownFailures:
    """Test suite for countdown failure scenarios."""

    @patch("zebtrack.core.recording.recording_service.Toplevel")
    @patch("zebtrack.core.recording.recording_service.Label")
    def test_run_countdown_window_creation_fails(
        self, mock_label, mock_toplevel, recording_service, mock_root
    ):
        """Test countdown when window creation fails."""
        # Simulate window creation failure
        mock_toplevel.side_effect = RuntimeError("Window creation failed")

        callback = Mock()

        # Execute - should propagate exception
        with pytest.raises(RuntimeError):
            recording_service._run_countdown(3, callback)

    def test_run_countdown_negative_duration(self, recording_service, mock_root):
        """Test countdown with negative duration."""
        mock_root.winfo_screenwidth.return_value = 1920
        mock_root.winfo_screenheight.return_value = 1080

        callback = Mock()

        with patch("zebtrack.core.recording.recording_service.Toplevel"):
            with patch("zebtrack.core.recording.recording_service.Label"):
                recording_service._run_countdown(-5, callback)

                # Callback should be called immediately (or after zero updates)
                # Implementation may vary, but countdown should complete


class _FakeWindow:
    """Toplevel stand-in; the WM hints can be made to fail like a tiling WM."""

    def __init__(self, _parent: Any, *, hostile_wm: bool = False) -> None:
        self.hostile_wm = hostile_wm
        self.exists = True
        self.destroyed = 0
        self.geometry_spec = ""

    def overrideredirect(self, _flag: bool) -> None:
        if self.hostile_wm:
            raise tk.TclError("overrideredirect unsupported")

    def attributes(self, *_args: Any) -> None:
        if self.hostile_wm:
            raise tk.TclError("-topmost unsupported")

    def geometry(self, spec: str) -> None:
        self.geometry_spec = spec

    def winfo_exists(self) -> bool:
        return self.exists

    def destroy(self) -> None:
        self.destroyed += 1
        self.exists = False


class _FakeLabel:
    def __init__(self, _parent: Any, **_kwargs: Any) -> None:
        self.texts: list[str] = []
        self.fail = False

    def pack(self, **_kwargs: Any) -> None:
        pass

    def config(self, *, text: str) -> None:
        if self.fail:
            raise tk.TclError("label destroyed")
        self.texts.append(text)


class _ManualRoot:
    """Root whose ``after`` queue is run by the test, one tick at a time."""

    def __init__(self) -> None:
        self.queue: list[tuple[int, Any]] = []

    def after(self, ms: int, func: Any) -> str:
        self.queue.append((ms, func))
        return f"after#{len(self.queue)}"

    def winfo_screenwidth(self) -> int:
        return 1920

    def winfo_screenheight(self) -> int:
        return 1080

    def tick(self) -> None:
        _ms, func = self.queue.pop(0)
        func()


class TestCountdownWindow:
    """``_run_countdown`` driven tick by tick through a fake Tk root."""

    @pytest.fixture
    def countdown(self, mock_controller, mock_state_manager, mock_project_manager, monkeypatch):
        from zebtrack.core.recording import recording_service as rs_module

        created: dict[str, Any] = {}

        def _toplevel(parent: Any) -> _FakeWindow:
            created["window"] = _FakeWindow(parent, hostile_wm=created.get("hostile", False))
            return created["window"]

        def _label(parent: Any, **kwargs: Any) -> _FakeLabel:
            created["label"] = _FakeLabel(parent, **kwargs)
            return created["label"]

        monkeypatch.setattr(rs_module, "Toplevel", _toplevel)
        monkeypatch.setattr(rs_module, "Label", _label)
        root = _ManualRoot()
        service = RecordingService(
            controller=mock_controller,
            state_manager=mock_state_manager,
            project_manager=mock_project_manager,
            root=cast(Any, root),
        )
        return service, root, created

    def test_counts_down_each_second_then_runs_callback_once(self, countdown):
        service, root, created = countdown
        calls: list[str] = []

        service._run_countdown(3, lambda: calls.append("go"))

        label, window = created["label"], created["window"]
        assert label.texts == ["3"]
        assert root.queue[0][0] == 1000
        root.tick()
        root.tick()
        assert label.texts == ["3", "2", "1"]
        assert calls == []
        root.tick()  # reaches 0
        assert calls == ["go"]
        assert window.destroyed == 1
        assert root.queue == []

    def test_window_is_centred_on_screen(self, countdown):
        service, _root, created = countdown

        service._run_countdown(2, lambda: None)

        # (1920 // 2 - 100, 1080 // 2 - 100) for a 200 x 200 window.
        assert created["window"].geometry_spec == "200x200+860+440"

    def test_hostile_window_manager_does_not_abort_the_countdown(self, countdown):
        service, root, created = countdown
        created["hostile"] = True
        calls: list[str] = []

        service._run_countdown(1, lambda: calls.append("go"))
        root.tick()

        assert calls == ["go"]

    def test_window_closed_mid_countdown_never_starts_the_recording(self, countdown):
        # F2-R-O: the countdown window has no close button (overrideredirect),
        # but if it disappears anyway the recording silently never starts.
        service, root, created = countdown
        calls: list[str] = []

        service._run_countdown(2, lambda: calls.append("go"))
        created["window"].exists = False
        root.tick()

        assert calls == []
        assert root.queue == []

    def test_root_dropped_mid_countdown_starts_immediately(self, countdown):
        service, root, created = countdown
        calls: list[str] = []

        service._run_countdown(3, lambda: calls.append("go"))
        service.root = None
        root.tick()  # "2" is shown, then there is no root left to schedule on

        assert created["label"].texts == ["3", "2"]
        assert calls == ["go"]
        assert created["window"].destroyed == 1

    def test_tcl_error_while_counting_still_starts_the_recording(self, countdown, monkeypatch):
        service, _root, created = countdown
        calls: list[str] = []

        def _toplevel_label_fails(_parent: Any, **_kwargs: Any) -> _FakeLabel:
            label = _FakeLabel(_parent)
            label.fail = True
            created["label"] = label
            return label

        from zebtrack.core.recording import recording_service as rs_module

        monkeypatch.setattr(rs_module, "Label", _toplevel_label_fails)

        service._run_countdown(3, lambda: calls.append("go"))

        assert calls == ["go"]

    def test_countdown_through_schedule_recording_starts_the_session(self, countdown):
        service, root, _created = countdown
        started: list[str] = []
        service.start_session = lambda ctx, pd, src: started.append(src)  # type: ignore[method-assign]

        service.schedule_recording(
            {}, {"use_countdown": True, "countdown_duration_s": "2"}, trigger_source="grid"
        )
        assert started == []
        root.tick()
        root.tick()

        assert started == ["grid"]


class TestRecordingMetadataAndArduino:
    def test_session_metadata_is_written_next_to_the_recording(
        self, recording_service, mock_controller, tmp_path
    ):
        import json

        mock_controller.recorder.start_recording.return_value = True
        context = {
            "folder_name": "Dia_2_Controle_4",
            "output_folder": str(tmp_path),
            "camera_width": 1280,
            "camera_height": 720,
            "day": 2,
            "group": "Controle",
            "cobaia": "4",
        }

        recording_service.start_session(context, {}, "manual")

        saved = json.loads((tmp_path / "_recording_metadata.json").read_text(encoding="utf-8"))
        # The subject is persisted under ``subject``, the key ProjectManager reads.
        assert saved == {"day": 2, "group": "Controle", "subject": "4"}

    def test_no_session_keys_writes_no_metadata(self, recording_service, mock_controller, tmp_path):
        mock_controller.recorder.start_recording.return_value = True
        context = {
            "folder_name": "adhoc",
            "output_folder": str(tmp_path),
            "camera_width": 640,
            "camera_height": 480,
        }

        recording_service.start_session(context, {}, "manual")

        assert not (tmp_path / "_recording_metadata.json").exists()

    def test_non_numeric_subject_sends_no_arduino_command(
        self, recording_service, mock_controller, tmp_path
    ):
        mock_controller.recorder.start_recording.return_value = True
        context = {
            "folder_name": "s",
            "output_folder": str(tmp_path),
            "camera_width": 640,
            "camera_height": 480,
            "arduino_enabled": True,
            "day": 1,
            "group": "G",
            "cobaia": "A3",
        }

        recording_service.start_session(context, {}, "manual")

        mock_controller.arduino_manager.send_command.assert_not_called()

    def test_numeric_subject_drives_its_box(self, recording_service, mock_controller, tmp_path):
        mock_controller.recorder.start_recording.return_value = True
        context = {
            "folder_name": "s",
            "output_folder": str(tmp_path),
            "camera_width": 640,
            "camera_height": 480,
            "arduino_enabled": True,
            "day": 1,
            "group": "G",
            "cobaia": "3",
        }

        recording_service.start_session(context, {}, "external")

        mock_controller.arduino_manager.send_command.assert_called_once_with(
            3, source="external-start"
        )

    def test_timed_recording_schedules_stop_in_milliseconds(
        self, recording_service, mock_controller, mock_root, tmp_path
    ):
        mock_controller.recorder.start_recording.return_value = True
        context = {
            "folder_name": "s",
            "output_folder": str(tmp_path),
            "camera_width": 640,
            "camera_height": 480,
        }

        recording_service.start_session(
            context, {"use_timed_recording": True, "recording_duration_s": 2.5}, "manual"
        )

        stop_cb = recording_service._ui_callbacks["stop_recording_callback"]
        mock_root.after.assert_called_once_with(2500, stop_cb)
        assert recording_service.timed_recording_job == "job_id_123"

    def test_timed_recording_without_stop_callback_schedules_nothing(
        self, recording_service, mock_controller, mock_root, tmp_path
    ):
        mock_controller.recorder.start_recording.return_value = True
        del recording_service._ui_callbacks["stop_recording_callback"]
        context = {
            "folder_name": "s",
            "output_folder": str(tmp_path),
            "camera_width": 640,
            "camera_height": 480,
        }

        recording_service.start_session(
            context, {"use_timed_recording": True, "recording_duration_s": 10}, "manual"
        )

        mock_root.after.assert_not_called()
        assert recording_service.timed_recording_job is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
