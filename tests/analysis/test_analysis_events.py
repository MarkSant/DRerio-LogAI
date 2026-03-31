from unittest.mock import Mock, patch

import pytest

from zebtrack.analysis.analysis_service import AnalysisService
from zebtrack.ui.event_bus_v2 import UIEvents


@pytest.fixture
def mock_controller():
    controller = Mock()
    controller.ui_event_bus = Mock()
    controller.ui_event_bus.publish = Mock(
        side_effect=lambda *args, **kwargs: print(f"DEBUG: publish called with {args} {kwargs}")
    )
    return controller


@pytest.fixture
def analysis_service():
    settings = Mock()
    return AnalysisService(settings_obj=settings)


def test_process_videos_batch_publishes_social_summary_event(analysis_service, mock_controller):
    """Test that process_videos_batch publishes UI_UPDATE_SOCIAL_SUMMARY event."""

    mock_root = Mock()
    mock_root.after = Mock(side_effect=lambda delay, func: func())

    videos = [{"path": "test.mp4"}]

    # Mock dependencies
    mock_controller.project_manager = Mock()
    mock_controller.project_manager.get_project_data.return_value = {}
    mock_controller.project_manager.project_data = {}  # Ensure this is a dict, not a Mock

    mock_controller.batch_configuration_service = Mock()
    mock_controller.batch_configuration_service.apply_settings = Mock()

    mock_controller._process_single_video = Mock(return_value=(True, "/tmp"))

    # Mock ROIAnalyzer and BehavioralAnalyzer
    with patch("zebtrack.analysis.analysis_service.ROIAnalyzer") as MockROIAnalyzer:
        mock_analyzer = MockROIAnalyzer.return_value
        mock_analyzer.get_social_summary.return_value = {"social_time_percentage": {}}
        mock_analyzer.get_event_log.return_value = Mock(to_dict=lambda x: [])

        with patch("zebtrack.analysis.analysis_service.ConcreteBehavioralAnalyzer"):
            # Mock file system and pandas
            with patch("os.path.exists", return_value=True):
                with patch("pandas.read_parquet", return_value=Mock(empty=False)):
                    analysis_service.process_videos_batch(
                        videos_to_process=videos,
                        output_base_dir="/tmp",
                        single_video_config=None,
                        controller=mock_controller,
                        cancel_event=Mock(is_set=Mock(return_value=False)),
                        project_manager=mock_controller.project_manager,
                        root_tk=mock_root,
                    )

    # Check calls
    calls = mock_controller.ui_event_bus.publish.call_args_list
    social_summary_calls = [
        call for call in calls if call[0][0].type == UIEvents.UI_UPDATE_SOCIAL_SUMMARY
    ]

    assert len(social_summary_calls) > 0, "UI_UPDATE_SOCIAL_SUMMARY event was not published"

    # Verify payload
    event = social_summary_calls[0][0][0]
    assert event.type == UIEvents.UI_UPDATE_SOCIAL_SUMMARY
    assert hasattr(event.data, "profile")
    assert hasattr(event.data, "stats")
    assert hasattr(event.data, "tracks")
