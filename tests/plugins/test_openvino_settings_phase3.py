"""Phase 3 / M1 + M2 schema tests.

Validate the new optional knobs we just added to ``OpenVINOSettings``
(``num_streams``, ``num_threads``) and ``YOLOModelSettings`` (``device``)
default to ``None`` and reject out-of-range values.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from zebtrack.settings import OpenVINOSettings, YOLOModelSettings


def test_openvino_num_streams_defaults_to_none() -> None:
    settings = OpenVINOSettings()
    assert settings.num_streams is None
    assert settings.num_threads is None


def test_openvino_num_streams_accepts_valid_range() -> None:
    settings = OpenVINOSettings(num_streams=4, num_threads=8)
    assert settings.num_streams == 4
    assert settings.num_threads == 8


@pytest.mark.parametrize("invalid", [0, -1, 999])
def test_openvino_num_streams_rejects_out_of_range(invalid: int) -> None:
    with pytest.raises(ValidationError):
        OpenVINOSettings(num_streams=invalid)


@pytest.mark.parametrize("invalid", [0, -1, 999])
def test_openvino_num_threads_rejects_out_of_range(invalid: int) -> None:
    with pytest.raises(ValidationError):
        OpenVINOSettings(num_threads=invalid)


def test_yolo_device_defaults_to_none() -> None:
    settings = YOLOModelSettings(
        path="best.pt",
        confidence_threshold=0.4,
        nms_threshold=0.5,
    )
    assert settings.device is None


@pytest.mark.parametrize("device", ["cpu", "cuda", "cuda:0", "mps"])
def test_yolo_device_accepts_arbitrary_strings(device: str) -> None:
    """device is intentionally typed as ``str | None`` so users can pass
    any string Ultralytics accepts (cpu, cuda, cuda:0, mps, …)."""
    settings = YOLOModelSettings(
        path="best.pt",
        confidence_threshold=0.4,
        nms_threshold=0.5,
        device=device,
    )
    assert settings.device == device
