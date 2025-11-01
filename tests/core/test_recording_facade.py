"""
Unit tests for RecordingFacade.

Tests the facade pattern for recording operations, ensuring proper
coordination between Recorder, StateManager, and EventBus.
"""

from unittest.mock import Mock

import pytest

from zebtrack.core.recording_facade import RecordingFacade


@pytest.fixture
def mock_recorder():
    """Create mock Recorder."""
    recorder = Mock()
    recorder.start_recording = Mock()
    recorder.stop_recording = Mock()
    return recorder


@pytest.fixture
def mock_state_manager():
    """Create mock StateManager."""
    state_manager = Mock()
    # Default to not recording
    recording_state = Mock()
    recording_state.is_recording = False
    recording_state.output_path = None
    state_manager.get_recording_state = Mock(return_value=recording_state)
    state_manager.update_recording_state = Mock()
    return state_manager


@pytest.fixture
def mock_event_bus():
    """Create mock EventBus."""
    event_bus = Mock()
    event_bus.publish_event = Mock(return_value=True)
    return event_bus


@pytest.fixture
def recording_facade(mock_recorder, mock_state_manager, mock_event_bus):
    """Create RecordingFacade with mocked dependencies."""
    return RecordingFacade(
        recorder=mock_recorder,
        state_manager=mock_state_manager,
        event_bus=mock_event_bus,
    )


class TestRecordingFacadeInitialization:
    """Test suite for RecordingFacade initialization."""

    def test_init_with_all_dependencies(self, mock_recorder, mock_state_manager, mock_event_bus):
        """Test initialization with all dependencies."""
        facade = RecordingFacade(
            recorder=mock_recorder,
            state_manager=mock_state_manager,
            event_bus=mock_event_bus,
        )

        assert facade.recorder == mock_recorder
        assert facade.state_manager == mock_state_manager
        assert facade.event_bus == mock_event_bus


class TestRecordingFacadeStartRecording:
    """Test suite for start_recording method."""

    def test_start_recording_success(self, recording_facade, mock_recorder, tmp_path):
        """Test successful start of recording."""
        video_path = tmp_path / "test_video.mp4"
        video_path.touch()
        output_dir = tmp_path / "output"
        mock_zones = Mock()

        result = recording_facade.start_recording(
            video_path=video_path,
            output_dir=output_dir,
            frame_width=1920,
            frame_height=1080,
            zones=mock_zones,
            fps=30.0,
            record_video=True,
        )

        assert result is True
        assert output_dir.exists()
        mock_recorder.start_recording.assert_called_once()

    def test_start_recording_video_not_found(self, recording_facade, tmp_path):
        """Test start_recording when video file doesn't exist."""
        video_path = tmp_path / "nonexistent.mp4"
        output_dir = tmp_path / "output"
        mock_zones = Mock()

        result = recording_facade.start_recording(
            video_path=video_path,
            output_dir=output_dir,
            frame_width=1920,
            frame_height=1080,
            zones=mock_zones,
        )

        assert result is False

    def test_start_recording_updates_state(self, recording_facade, mock_state_manager, tmp_path):
        """Test that start_recording updates StateManager."""
        video_path = tmp_path / "test_video.mp4"
        video_path.touch()
        output_dir = tmp_path / "output"
        mock_zones = Mock()

        recording_facade.start_recording(
            video_path=video_path,
            output_dir=output_dir,
            frame_width=1920,
            frame_height=1080,
            zones=mock_zones,
        )

        mock_state_manager.update_recording_state.assert_called_once()
        call_kwargs = mock_state_manager.update_recording_state.call_args[1]
        assert call_kwargs["is_recording"] is True
        assert call_kwargs["output_path"] == output_dir

    def test_start_recording_publishes_event(self, recording_facade, mock_event_bus, tmp_path):
        """Test that start_recording publishes event via EventBus."""
        video_path = tmp_path / "test_video.mp4"
        video_path.touch()
        output_dir = tmp_path / "output"
        mock_zones = Mock()

        recording_facade.start_recording(
            video_path=video_path,
            output_dir=output_dir,
            frame_width=1920,
            frame_height=1080,
            zones=mock_zones,
        )

        mock_event_bus.publish_event.assert_called_once()
        call_args = mock_event_bus.publish_event.call_args
        assert call_args[0][0] == "recording.started"
        assert "video_path" in call_args[1]["data"]
        assert "output_dir" in call_args[1]["data"]

    def test_start_recording_handles_exception(self, recording_facade, mock_recorder, tmp_path):
        """Test start_recording handles exceptions gracefully."""
        video_path = tmp_path / "test_video.mp4"
        video_path.touch()
        output_dir = tmp_path / "output"
        mock_zones = Mock()

        # Make recorder raise an exception
        mock_recorder.start_recording.side_effect = RuntimeError("Test error")

        result = recording_facade.start_recording(
            video_path=video_path,
            output_dir=output_dir,
            frame_width=1920,
            frame_height=1080,
            zones=mock_zones,
        )

        assert result is False


class TestRecordingFacadeStopRecording:
    """Test suite for stop_recording method."""

    def test_stop_recording_success(self, recording_facade, mock_state_manager, mock_recorder):
        """Test successful stop of recording."""
        # Set state to recording
        recording_state = Mock()
        recording_state.is_recording = True
        mock_state_manager.get_recording_state.return_value = recording_state

        result = recording_facade.stop_recording()

        assert result is True
        mock_recorder.stop_recording.assert_called_once()

    def test_stop_recording_not_recording(
        self, recording_facade, mock_state_manager, mock_recorder
    ):
        """Test stop_recording when not currently recording."""
        # State is already not recording (from fixture)
        result = recording_facade.stop_recording()

        assert result is False
        mock_recorder.stop_recording.assert_not_called()

    def test_stop_recording_updates_state(self, recording_facade, mock_state_manager):
        """Test that stop_recording updates StateManager."""
        # Set state to recording
        recording_state = Mock()
        recording_state.is_recording = True
        mock_state_manager.get_recording_state.return_value = recording_state

        recording_facade.stop_recording()

        mock_state_manager.update_recording_state.assert_called_once()
        call_kwargs = mock_state_manager.update_recording_state.call_args[1]
        assert call_kwargs["is_recording"] is False

    def test_stop_recording_publishes_event(
        self, recording_facade, mock_event_bus, mock_state_manager
    ):
        """Test that stop_recording publishes event via EventBus."""
        # Set state to recording
        recording_state = Mock()
        recording_state.is_recording = True
        mock_state_manager.get_recording_state.return_value = recording_state

        recording_facade.stop_recording()

        mock_event_bus.publish_event.assert_called_once_with("recording.stopped")

    def test_stop_recording_handles_exception(
        self, recording_facade, mock_state_manager, mock_recorder
    ):
        """Test stop_recording handles exceptions gracefully."""
        # Set state to recording
        recording_state = Mock()
        recording_state.is_recording = True
        mock_state_manager.get_recording_state.return_value = recording_state

        # Make recorder raise an exception
        mock_recorder.stop_recording.side_effect = RuntimeError("Test error")

        result = recording_facade.stop_recording()

        assert result is False


class TestRecordingFacadeIsRecording:
    """Test suite for is_recording method."""

    def test_is_recording_true(self, recording_facade, mock_state_manager):
        """Test is_recording returns True when recording."""
        recording_state = Mock()
        recording_state.is_recording = True
        mock_state_manager.get_recording_state.return_value = recording_state

        assert recording_facade.is_recording() is True

    def test_is_recording_false(self, recording_facade, mock_state_manager):
        """Test is_recording returns False when not recording."""
        # State is already not recording (from fixture)
        assert recording_facade.is_recording() is False


class TestRecordingFacadeGetOutputFiles:
    """Test suite for get_output_files method."""

    def test_get_output_files_with_all_files(self, recording_facade, mock_state_manager, tmp_path):
        """Test get_output_files with all expected files present."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Create expected files
        parquet_file = output_dir / "test_trajectory.parquet"
        video_file = output_dir / "test_tracked.mp4"
        metadata_file = output_dir / "metadata.csv"
        parquet_file.touch()
        video_file.touch()
        metadata_file.touch()

        # Set state to have output_path
        recording_state = Mock()
        recording_state.is_recording = False
        recording_state.output_path = output_dir
        mock_state_manager.get_recording_state.return_value = recording_state

        files = recording_facade.get_output_files()

        assert "parquet" in files
        assert "video" in files
        assert "metadata" in files
        assert files["parquet"] == parquet_file
        assert files["video"] == video_file
        assert files["metadata"] == metadata_file

    def test_get_output_files_no_output_path(self, recording_facade, mock_state_manager):
        """Test get_output_files when no output path is set."""
        # State has no output_path (from fixture)
        files = recording_facade.get_output_files()

        assert files == {}

    def test_get_output_files_output_dir_not_exists(
        self, recording_facade, mock_state_manager, tmp_path
    ):
        """Test get_output_files when output directory doesn't exist."""
        output_dir = tmp_path / "nonexistent_output"

        # Set state with non-existent path
        recording_state = Mock()
        recording_state.is_recording = False
        recording_state.output_path = output_dir
        mock_state_manager.get_recording_state.return_value = recording_state

        files = recording_facade.get_output_files()

        assert files == {}

    def test_get_output_files_partial_files(self, recording_facade, mock_state_manager, tmp_path):
        """Test get_output_files with only some files present."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Create only parquet file
        parquet_file = output_dir / "test_trajectory.parquet"
        parquet_file.touch()

        # Set state
        recording_state = Mock()
        recording_state.is_recording = False
        recording_state.output_path = output_dir
        mock_state_manager.get_recording_state.return_value = recording_state

        files = recording_facade.get_output_files()

        assert "parquet" in files
        assert "video" not in files
        assert "metadata" not in files
