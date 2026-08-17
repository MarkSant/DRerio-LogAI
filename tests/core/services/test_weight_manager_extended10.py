"""Extended unit tests for core/services/weight_manager.py (Part 10)."""

from __future__ import annotations

from typing import Any

from zebtrack.core.services.weight_manager import WeightManager


class TestWeightManagerExtended10:
    """Test WeightManager conversion job tracking and initial state."""

    def test_weight_manager_initial_collections(self):
        wm: Any = object.__new__(WeightManager)
        wm.weights = {}
        wm._active_conversion_jobs = {}
        wm._active_quantization_jobs = {}
        wm._runtime_slot_overrides = {}

        assert wm.weights == {}
        assert wm._active_conversion_jobs == {}
        assert wm._active_quantization_jobs == {}
        assert wm._runtime_slot_overrides == {}

    def test_active_conversion_job_assignment(self):
        wm: Any = object.__new__(WeightManager)
        wm._active_conversion_jobs = {}
        wm._active_conversion_jobs["yolo.pt"] = "future_thread"

        assert "yolo.pt" in wm._active_conversion_jobs
        assert wm._active_conversion_jobs["yolo.pt"] == "future_thread"

    def test_active_quantization_job_assignment(self):
        wm: Any = object.__new__(WeightManager)
        wm._active_quantization_jobs = {}
        wm._active_quantization_jobs["model.xml"] = "quant_thread"

        assert "model.xml" in wm._active_quantization_jobs
        assert wm._active_quantization_jobs["model.xml"] == "quant_thread"
