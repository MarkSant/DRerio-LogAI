"""Extended unit tests for core/recording/frame_processing_pipeline.py (Part 6)."""

from __future__ import annotations

import numpy as np
import pytest

from zebtrack.core.recording.frame_processing_pipeline import FrameProcessingMixin


class DummyPipelineIsolated(FrameProcessingMixin):
    pass


class TestFrameProcessingPipelineExtended6:
    """Test FrameProcessingMixin super-method fallback errors."""

    def test_define_arena_from_detections_raises_not_implemented(self):
        pipe = DummyPipelineIsolated()
        with pytest.raises(NotImplementedError, match="_define_arena_from_detections"):
            pipe._define_arena_from_detections()

    def test_start_recording_after_arena_raises_not_implemented(self):
        pipe = DummyPipelineIsolated()
        with pytest.raises(NotImplementedError, match="_start_recording_after_arena"):
            pipe._start_recording_after_arena()

    def test_run_multi_aquarium_detection_raises_not_implemented(self):
        pipe = DummyPipelineIsolated()
        dummy_frame = np.zeros((10, 10, 3), dtype=np.uint8)
        with pytest.raises(NotImplementedError, match="_run_multi_aquarium_detection"):
            pipe._run_multi_aquarium_detection(dummy_frame, 1, None)
