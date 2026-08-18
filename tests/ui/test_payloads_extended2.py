"""Extended unit tests for ui/payloads.py (Part 2)."""

from __future__ import annotations

from zebtrack.ui.payloads import (
    DetectionOverlayPayload,
    EmptyPayload,
    FrameDisplayPayload,
    FramePayload,
    ItemIdPayload,
    MessagePayload,
    ProcessingCountPayload,
    ProjectContextMenuClickPayload,
    SelectionPayload,
    StatusPayload,
    TrackIdPayload,
    VideoPathPayload,
    VideoPathsPayload,
)


class TestPayloadsExtended2:
    """Test EventBusV2 typed event payload dataclasses."""

    def test_empty_payload(self):
        p = EmptyPayload()
        assert repr(p) == "EmptyPayload()"

    def test_message_payload(self):
        p = MessagePayload(title="Alert", message="Operation complete")
        assert p.title == "Alert"
        assert p.message == "Operation complete"

    def test_status_payload(self):
        p = StatusPayload(message="Ready", status_type="info", level="DEBUG")
        assert p.message == "Ready"
        assert p.status_type == "info"
        assert p.level == "DEBUG"

    def test_video_path_payload(self):
        p = VideoPathPayload(video_path="/path/vid.mp4")
        assert p.video_path == "/path/vid.mp4"

    def test_video_paths_payload(self):
        p = VideoPathsPayload(video_paths=["/path/v1.mp4", "/path/v2.mp4"])
        assert len(p.video_paths) == 2

    def test_selection_payload(self):
        p = SelectionPayload(selection=["item1", "item2"])
        assert p.selection == ["item1", "item2"]

    def test_item_id_payload(self):
        p = ItemIdPayload(item_id="node_42")
        assert p.item_id == "node_42"

    def test_project_context_menu_click_payload(self):
        p = ProjectContextMenuClickPayload(item_id="row_1", x=100, y=200, column_id="name")
        assert p.item_id == "row_1"
        assert p.x == 100
        assert p.y == 200
        assert p.column_id == "name"

    def test_track_id_payload(self):
        p = TrackIdPayload(track_id=1001)
        assert p.track_id == 1001

    def test_frame_payload(self):
        p = FramePayload(frame="frame_data", frame_number=42)
        assert p.frame == "frame_data"
        assert p.frame_number == 42

    def test_frame_display_payload(self):
        p = FrameDisplayPayload(frame="frame_arr", detections=[1, 2], frame_number=10)
        assert p.frame == "frame_arr"
        assert p.frame_number == 10

    def test_processing_count_payload(self):
        p = ProcessingCountPayload(count=3)
        assert p.count == 3

    def test_detection_overlay_payload(self):
        p = DetectionOverlayPayload(detections=[{"box": [0, 0, 10, 10]}], report={"score": 0.95})
        assert len(p.detections) == 1
        assert p.report is not None
        assert p.report["score"] == 0.95
