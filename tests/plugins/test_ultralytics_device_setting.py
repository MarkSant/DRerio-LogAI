"""Phase 3 / M2 tests for Ultralytics ``device`` setting plumbing.

We mock the ultralytics YOLO class so the test doesn't need real
weights or torch. The goal is to verify:

1. ``UltralyticsDetectorPlugin`` reads ``settings.yolo_model.device``.
2. ``device=None`` (default) is NOT passed to ``model.predict`` so we
   keep the legacy auto-select behavior intact.
3. Explicit ``device="cpu"`` propagates to predict and disables FP16.
4. Explicit ``device="cuda:0"`` propagates and enables FP16 only when
   CUDA is actually available.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import zebtrack.plugins.ultralytics_detector as ul_module


@pytest.fixture
def fake_ultralytics(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace YOLO so __init__ does not load weights from disk."""
    fake_model = MagicMock()
    fake_model.names = {0: "aquarium", 1: "zebrafish"}
    fake_model.predict.return_value = [SimpleNamespace(boxes=None)]
    fake_yolo = MagicMock(return_value=fake_model)
    monkeypatch.setattr(ul_module, "YOLO", fake_yolo)
    monkeypatch.setattr(ul_module, "ULTRALYTICS_AVAILABLE", True)
    return fake_model


def _settings(device: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        yolo_model=SimpleNamespace(
            confidence_threshold=0.4,
            nms_threshold=0.5,
            use_half_precision=True,
            inference_size=640,
            device=device,
        ),
        bytetrack=SimpleNamespace(track_threshold=0.3, match_threshold=0.9),
    )


def test_device_none_is_not_passed_to_predict(fake_ultralytics: MagicMock) -> None:
    """Default behavior: do not pass device kwarg so Ultralytics auto-selects."""
    plugin = ul_module.UltralyticsDetectorPlugin(
        model_path="dummy.pt", settings_obj=_settings(None)
    )
    fake_ultralytics.predict.reset_mock()

    plugin.detect(np.zeros((640, 640, 3), dtype=np.uint8))

    args, kwargs = fake_ultralytics.predict.call_args
    assert "device" not in kwargs


def test_device_cpu_propagates_and_disables_half(fake_ultralytics: MagicMock) -> None:
    """device='cpu' → kwarg flows through; FP16 forced off (CPU does not benefit)."""
    plugin = ul_module.UltralyticsDetectorPlugin(
        model_path="dummy.pt", settings_obj=_settings("cpu")
    )
    assert plugin._half_enabled is False
    fake_ultralytics.predict.reset_mock()

    plugin.detect(np.zeros((640, 640, 3), dtype=np.uint8))

    _args, kwargs = fake_ultralytics.predict.call_args
    assert kwargs["device"] == "cpu"
    assert kwargs["half"] is False


def test_device_cuda_enables_half_only_when_cuda_available(
    fake_ultralytics: MagicMock,
) -> None:
    """device='cuda:0' propagates; FP16 reflects real CUDA availability."""
    with patch.object(ul_module, "is_cuda_available", return_value=True):
        plugin = ul_module.UltralyticsDetectorPlugin(
            model_path="dummy.pt", settings_obj=_settings("cuda:0")
        )

    assert plugin._half_enabled is True
    fake_ultralytics.predict.reset_mock()

    plugin.detect(np.zeros((640, 640, 3), dtype=np.uint8))

    _args, kwargs = fake_ultralytics.predict.call_args
    assert kwargs["device"] == "cuda:0"
    assert kwargs["half"] is True


def test_device_cuda_with_no_runtime_cuda_disables_half(
    fake_ultralytics: MagicMock,
) -> None:
    """User asked for CUDA but runtime cannot provide it → FP16 must stay off."""
    with patch.object(ul_module, "is_cuda_available", return_value=False):
        plugin = ul_module.UltralyticsDetectorPlugin(
            model_path="dummy.pt", settings_obj=_settings("cuda:0")
        )

    assert plugin._half_enabled is False
