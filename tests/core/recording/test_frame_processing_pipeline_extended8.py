"""Extended unit tests for core/recording/frame_processing_pipeline.py (Part 8)."""

from __future__ import annotations

from zebtrack.core.recording.frame_processing_pipeline import VideoFrameMeta


class TestFrameProcessingPipelineExtended8:
    """Test VideoFrameMeta properties and equality checks."""

    def test_video_frame_meta_equality(self):
        meta1 = VideoFrameMeta(
            pipeline_frame=5,
            t_capture_perf=10.0,
            t_capture_wall=20.0,
            is_analysis_frame=True,
            queued_for_analysis=False,
        )
        meta2 = VideoFrameMeta(
            pipeline_frame=5,
            t_capture_perf=10.0,
            t_capture_wall=20.0,
            is_analysis_frame=True,
            queued_for_analysis=False,
        )
        assert meta1 == meta2

    def test_video_frame_meta_immutability(self):
        meta = VideoFrameMeta(
            pipeline_frame=1,
            t_capture_perf=None,
            t_capture_wall=None,
            is_analysis_frame=False,
            queued_for_analysis=False,
        )
        assert meta.pipeline_frame == 1
        assert meta.t_capture_perf is None
        assert meta.t_capture_wall is None

    def test_video_frame_meta_attributes_retrieval(self):
        meta = VideoFrameMeta(
            pipeline_frame=100,
            t_capture_perf=1.23,
            t_capture_wall=4.56,
            is_analysis_frame=True,
            queued_for_analysis=True,
        )
        assert meta.pipeline_frame == 100
        assert meta.is_analysis_frame is True
        assert meta.queued_for_analysis is True
