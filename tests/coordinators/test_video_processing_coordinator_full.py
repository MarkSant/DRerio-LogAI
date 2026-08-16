"""Unit tests targeting remaining uncovered logic in VideoProcessingCoordinator."""

from __future__ import annotations

from threading import Event as ThreadingEvent
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from zebtrack.coordinators.video_processing_coordinator import (
    VideoProcessingCoordinator,
    _ask_open_filenames_from_view,
    _payload_get,
)
from zebtrack.ui import payloads
from zebtrack.ui.event_bus_v2 import UIEvents


@pytest.fixture
def mock_deps():
    state_manager = MagicMock()
    project_manager = MagicMock()
    detector_service = MagicMock()
    weight_manager = MagicMock()
    settings_obj = MagicMock()
    ui_coordinator = MagicMock()
    ui_state_controller = MagicMock()
    cancel_event = ThreadingEvent()
    video_selection_service = MagicMock()
    video_validation_service = MagicMock()
    video_classification_service = MagicMock()
    event_bus = MagicMock()
    dialog_coordinator = MagicMock()
    video_metadata_service = MagicMock()
    view = MagicMock()

    coordinator = VideoProcessingCoordinator(
        state_manager=state_manager,
        project_manager=project_manager,
        detector_service=detector_service,
        weight_manager=weight_manager,
        settings_obj=settings_obj,
        ui_coordinator=ui_coordinator,
        ui_state_controller=ui_state_controller,
        cancel_event=cancel_event,
        video_selection_service=video_selection_service,
        video_validation_service=video_validation_service,
        video_classification_service=video_classification_service,
        event_bus=event_bus,
        dialog_coordinator=dialog_coordinator,
        video_metadata_service=video_metadata_service,
        view=view,
    )
    return coordinator, {
        "state_manager": state_manager,
        "project_manager": project_manager,
        "detector_service": detector_service,
        "weight_manager": weight_manager,
        "settings_obj": settings_obj,
        "ui_coordinator": ui_coordinator,
        "ui_state_controller": ui_state_controller,
        "cancel_event": cancel_event,
        "video_selection_service": video_selection_service,
        "video_validation_service": video_validation_service,
        "video_classification_service": video_classification_service,
        "event_bus": event_bus,
        "dialog_coordinator": dialog_coordinator,
        "video_metadata_service": video_metadata_service,
        "view": view,
    }


class TestPayloadGetHelper:
    def test_payload_get_from_dict(self):
        d = {"video_path": "test.mp4", "count": 2}
        assert _payload_get(d, "video_path") == "test.mp4"
        assert _payload_get(d, "missing", "default") == "default"

    def test_payload_get_from_payload_object(self):
        p = payloads.VideoPathPayload(video_path="test.mp4")
        assert _payload_get(p, "video_path") == "test.mp4"
        assert _payload_get(p, "missing", "default") == "default"


class TestAskOpenFilenamesFromView:
    def test_direct_view_method(self):
        view = SimpleNamespace(ask_open_filenames=lambda t, f: ["v1.mp4", "v2.mp4"])
        res = _ask_open_filenames_from_view(view, "Select", [])
        assert res == ["v1.mp4", "v2.mp4"]

    def test_via_dialog_manager(self):
        view = SimpleNamespace(
            dialog_manager=SimpleNamespace(ask_open_filenames=lambda t, f: ["v3.mp4"])
        )
        res = _ask_open_filenames_from_view(view, "Select", [])
        assert res == ["v3.mp4"]

    def test_no_dialog_methods(self):
        view = SimpleNamespace()
        res = _ask_open_filenames_from_view(view, "Select", [])
        assert res == []

    def test_none_view(self):
        res = _ask_open_filenames_from_view(None, "Select", [])
        assert res == []


class TestGetVideoDimensions:
    def test_with_metadata_service_success(self, mock_deps):
        coord, deps = mock_deps
        deps["video_metadata_service"].get_video_dimensions.return_value = (1920, 1080)
        assert coord._get_video_dimensions("video.mp4") == (1920, 1080)

    def test_with_metadata_service_exception(self, mock_deps):
        coord, deps = mock_deps
        deps["video_metadata_service"].get_video_dimensions.side_effect = OSError("Corrupted")
        assert coord._get_video_dimensions("video.mp4") is None


class TestEventRegistrationAndRouting:
    def test_register_event_handlers_subscribes_all(self, mock_deps):
        coord, deps = mock_deps
        coord.register_event_handlers()

        bus = deps["event_bus"]
        subscribed_events = [call[0][0] for call in bus.subscribe.call_args_list]

        assert UIEvents.VIDEO_START_SINGLE_PROCESSING in subscribed_events
        assert UIEvents.PROJECT_IMPORT_VIDEOS in subscribed_events
        assert UIEvents.PROJECT_PROCESS_VIDEOS in subscribed_events
        assert UIEvents.ZONE_AUTO_DETECT in subscribed_events
        assert UIEvents.PROJECT_GENERATE_SUMMARIES in subscribed_events
        assert UIEvents.PROCESSING_GENERATE_TRAJECTORIES in subscribed_events
        assert UIEvents.ZONE_MULTI_AUTO_DETECT in subscribed_events
        assert UIEvents.ZONE_AQUARIUM_ASSIGNMENT_COMPLETED in subscribed_events
        assert UIEvents.ZONE_PROCESSING_MODE_CHANGED in subscribed_events
        assert UIEvents.REPORT_GENERATE in subscribed_events
        assert UIEvents.PROJECT_OPENED in subscribed_events

    def test_register_event_handlers_none_event_bus(self, mock_deps):
        coord, deps = mock_deps
        coord.event_bus = None
        coord.register_event_handlers()  # Should not raise

    def test_handle_zone_auto_detect_empty_or_dot(self, mock_deps):
        coord, deps = mock_deps
        mock_mac = MagicMock()
        coord._multi_aquarium_coordinator = mock_mac
        coord.register_event_handlers()

        # Find handler
        bus = deps["event_bus"]
        for call in bus.subscribe.call_args_list:
            if call[0][0] == UIEvents.ZONE_AUTO_DETECT:
                handler = call[0][1]
                handler({"video_path": ""})
                handler({"video_path": "."})
                mock_mac.run_aquarium_detection.assert_not_called()

    def test_handle_zone_auto_detect_with_settings_fallback(self, mock_deps):
        coord, deps = mock_deps
        mock_mac = MagicMock()
        coord._multi_aquarium_coordinator = mock_mac
        coord.settings.analysis_config.num_aquariums = 4
        coord.register_event_handlers()

        bus = deps["event_bus"]
        for call in bus.subscribe.call_args_list:
            if call[0][0] == UIEvents.ZONE_AUTO_DETECT:
                handler = call[0][1]
                handler({"video_path": "video.mp4", "stabilization_frames": 5})
                mock_mac.run_aquarium_detection.assert_called_once_with(
                    video_path="video.mp4",
                    count=4,
                    multi_aquarium=True,
                    stabilization_frames=5,
                )

    def test_handle_generate_trajectories_filters_sub_and_invalid_extensions(self, mock_deps):
        coord, deps = mock_deps
        coord.process_pending_project_videos = MagicMock()
        coord.register_event_handlers()

        bus = deps["event_bus"]
        for call in bus.subscribe.call_args_list:
            if call[0][0] == UIEvents.PROCESSING_GENERATE_TRAJECTORIES:
                handler = call[0][1]
                # With _sub_ tree node
                handler({"selection": ["video_sub_0", "valid.mp4"]})
                coord.process_pending_project_videos.assert_not_called()

                # With valid files only
                handler({"selection": ["v1.mp4", "v2.avi"]})
                coord.process_pending_project_videos.assert_called_once_with(["v1.mp4", "v2.avi"])

    def test_handle_report_generate_unified_and_standard(self, mock_deps):
        coord, deps = mock_deps
        mock_rc = MagicMock()
        coord._report_coordinator = mock_rc
        coord.register_event_handlers()

        bus = deps["event_bus"]
        for call in bus.subscribe.call_args_list:
            if call[0][0] == UIEvents.REPORT_GENERATE:
                handler = call[0][1]
                handler(
                    {
                        "report_type": "unified",
                        "videos": [{"path": "1.mp4"}, {"path": "2.mp4"}],
                        "replace_existing": True,
                        "report_scope": "selected",
                    }
                )
                mock_rc.generate_unified_report.assert_called_once_with(
                    ["1.mp4", "2.mp4"], replace_existing=True, report_scope="selected"
                )

                handler(
                    {
                        "report_type": "standard",
                        "videos": [{"path": "1.mp4"}],
                    }
                )
                mock_rc.generate_project_reports.assert_called_once_with(["1.mp4"])


class TestProxyMethods:
    def test_cancel_processing(self, mock_deps):
        coord, deps = mock_deps
        mock_ptc = MagicMock()
        coord._progress_coordinator = mock_ptc
        coord.cancel_processing()
        mock_ptc.cancel_processing.assert_called_once()

    def test_multi_aquarium_proxies(self, mock_deps):
        coord, deps = mock_deps
        mock_mac = MagicMock()
        coord._multi_aquarium_coordinator = mock_mac

        coord.set_main_arena_polygon([(0, 0), (1, 1)])
        mock_mac.set_main_arena_polygon.assert_called_once_with([(0, 0), (1, 1)])

        coord.save_manual_arena([(0, 0), (1, 1)])
        mock_mac.save_manual_arena.assert_called_once_with([(0, 0), (1, 1)])

        coord.add_roi_polygon([(0, 0), (1, 1)], "ROI1", (255, 0, 0))
        mock_mac.add_roi_polygon.assert_called_once_with([(0, 0), (1, 1)], "ROI1", (255, 0, 0))

        coord._publish_processing_mode(key="val")
        mock_mac._publish_processing_mode.assert_called_once_with(key="val")


class TestProcessPendingProjectVideos:
    def test_validation_fails(self, mock_deps):
        coord, deps = mock_deps
        coord.validate_can_start_processing = MagicMock(
            return_value=SimpleNamespace(is_valid=False, error_message="Cannot start")
        )
        coord.process_pending_project_videos(["v1.mp4"])
        deps["event_bus"].publish.assert_called_once()

    def test_no_eligible_videos_shows_info(self, mock_deps):
        coord, deps = mock_deps
        coord.validate_can_start_processing = MagicMock(return_value=SimpleNamespace(is_valid=True))
        deps["project_manager"].get_all_videos.return_value = [{"path": "v1.mp4"}]
        deps["video_selection_service"].select_candidates.return_value = SimpleNamespace(
            selection_mode="targeted", candidate_entries=[{"path": "v1.mp4"}]
        )
        coord._handle_targeted_selection_errors = MagicMock(return_value=True)
        coord._extract_and_validate_candidate_paths = MagicMock(return_value=["v1.mp4"])
        deps["video_validation_service"].scan_and_validate_paths.return_value = SimpleNamespace(
            info_by_norm={}, has_missing=False
        )
        deps["video_classification_service"].classify_videos.return_value = SimpleNamespace(
            ready_with_trajectory=[],
            ready_with_zones=[],
            arena_only=[],
            without_arena=[],
            data_changed=False,
        )

        coord.process_pending_project_videos(["v1.mp4"])
        # Should publish UI_SHOW_INFO
        deps["event_bus"].publish.assert_called()
        call_type = deps["event_bus"].publish.call_args[0][0].type
        assert call_type == UIEvents.UI_SHOW_INFO

    def test_multi_aquarium_missing_subjects_error(self, mock_deps):
        coord, deps = mock_deps
        coord.validate_can_start_processing = MagicMock(return_value=SimpleNamespace(is_valid=True))
        deps["project_manager"].get_all_videos.return_value = [{"path": "v1.mp4"}]
        deps["video_selection_service"].select_candidates.return_value = SimpleNamespace(
            selection_mode="targeted", candidate_entries=[{"path": "v1.mp4"}]
        )
        coord._handle_targeted_selection_errors = MagicMock(return_value=True)
        coord._extract_and_validate_candidate_paths = MagicMock(return_value=["v1.mp4"])
        deps["video_validation_service"].scan_and_validate_paths.return_value = SimpleNamespace(
            info_by_norm={}, has_missing=False
        )
        deps["video_classification_service"].classify_videos.return_value = SimpleNamespace(
            ready_with_trajectory=[],
            ready_with_zones=[{"path": "v1.mp4"}],
            arena_only=[],
            without_arena=[],
            data_changed=False,
        )
        coord.select_eligible_videos = MagicMock(return_value=[{"path": "v1.mp4"}])

        # Mock multi aquarium data with missing subject_id
        aq_missing = SimpleNamespace(id=0, subject_id="")
        deps["project_manager"].get_multi_aquarium_zone_data.return_value = SimpleNamespace(
            aquariums=[aq_missing]
        )

        coord.process_pending_project_videos(["v1.mp4"])
        # Should publish UI_SHOW_ERROR
        deps["event_bus"].publish.assert_called()
        call_type = deps["event_bus"].publish.call_args[0][0].type
        assert call_type == UIEvents.UI_SHOW_ERROR
