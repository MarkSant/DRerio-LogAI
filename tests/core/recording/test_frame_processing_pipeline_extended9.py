"""Extended unit tests for core/recording/frame_processing_pipeline.py (Part 9)."""

from __future__ import annotations

from zebtrack.core.recording.frame_processing_pipeline import VideoFrameMeta


class TestFrameProcessingPipelineExtended9:
    """Test VideoFrameMeta default flags and queued status checks."""

    def test_video_frame_meta_default_flags(self):
        meta = VideoFrameMeta(
            pipeline_frame=0,
            t_capture_perf=0.0,
            t_capture_wall=0.0,
            is_analysis_frame=False,
            queued_for_analysis=False,
        )
        assert meta.pipeline_frame == 0
        assert meta.is_analysis_frame is False
        assert meta.queued_for_analysis is False

    def test_video_frame_meta_perf_timestamp(self):
        meta = VideoFrameMeta(
            pipeline_frame=42,
            t_capture_perf=100.5,
            t_capture_wall=1700000000.0,
            is_analysis_frame=True,
            queued_for_analysis=True,
        )
        assert meta.pipeline_frame == 42
        assert meta.t_capture_perf == 100.5
        assert meta.t_capture_wall == 1700000000.0

    def test_video_frame_meta_analysis_flag(self):
        meta = VideoFrameMeta(
            pipeline_frame=1,
            t_capture_perf=0.0,
            t_capture_wall=0.0,
            is_analysis_frame=True,
            queued_for_analysis=False,
        )
        assert meta.is_analysis_frame is True
        assert meta.queued_for_analysis is False
