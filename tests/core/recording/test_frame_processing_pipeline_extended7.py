"""Extended unit tests for core/recording/frame_processing_pipeline.py (Part 7)."""

from __future__ import annotations

from zebtrack.core.recording.frame_processing_pipeline import (
    DEFAULT_ARDUINO_EXIT_GRACE_FRAMES,
    VideoFrameMeta,
    _unpack_video_item,
)


class TestFrameProcessingPipelineExtended7:
    """Test frame processing pipeline metadata unpacking and defaults."""

    def test_default_arduino_exit_grace_frames(self):
        assert DEFAULT_ARDUINO_EXIT_GRACE_FRAMES == 2

    def test_video_frame_meta_named_tuple(self):
        meta = VideoFrameMeta(
            pipeline_frame=10,
            t_capture_perf=123.456,
            t_capture_wall=789.012,
            is_analysis_frame=True,
            queued_for_analysis=True,
        )
        assert meta.pipeline_frame == 10
        assert meta.t_capture_perf == 123.456
        assert meta.t_capture_wall == 789.012
        assert meta.is_analysis_frame is True
        assert meta.queued_for_analysis is True

    def test_unpack_video_item_legacy_frame_only(self):
        frame_data = "raw_frame"
        frame, meta = _unpack_video_item(frame_data)
        assert frame == "raw_frame"
        assert meta is None

    def test_unpack_video_item_with_meta(self):
        item = (1, 10.0, 20.0, True, False, "raw_frame_data")
        frame, extracted_meta = _unpack_video_item(item)
        assert frame == "raw_frame_data"
        assert extracted_meta is not None
        assert extracted_meta.pipeline_frame == 1
        assert extracted_meta.t_capture_perf == 10.0
        assert extracted_meta.t_capture_wall == 20.0
        assert extracted_meta.is_analysis_frame is True
        assert extracted_meta.queued_for_analysis is False

    def test_unpack_video_item_short_tuple_fallback(self):
        short_item = ("item1", "item2", "item3")
        frame, meta = _unpack_video_item(short_item)
        assert frame == short_item
        assert meta is None
