"""Phase 2 tests for DetectorService hyperparameter override application.

Verifies the new ``_apply_project_detector_hyperparams`` helper that
mutates a freshly-instantiated detector plugin's ``conf_threshold`` /
``nms_threshold`` based on the project's ``model_overrides`` block.
"""

from __future__ import annotations

from unittest.mock import MagicMock, Mock

import pytest

from zebtrack.core.services.detector_service import DetectorService


class FakePlugin:
    """Plain attribute holder mimicking the real plugin surface."""

    def __init__(self, conf: float = 0.25, nms: float = 0.45) -> None:
        self.conf_threshold = conf
        self.nms_threshold = nms


@pytest.fixture
def detector_service() -> DetectorService:
    return DetectorService(
        state_manager=MagicMock(),
        project_manager=Mock(),
        weight_manager=MagicMock(),
        model_service=MagicMock(),
        settings_obj=MagicMock(),
    )


def test_apply_hyperparams_writes_conf_and_nms(detector_service: DetectorService) -> None:
    detector_service.project_manager.project_data = {
        "model_overrides": {
            "confidence_threshold": 0.4,
            "nms_threshold": 0.6,
        }
    }
    plugin = FakePlugin()

    detector_service._apply_project_detector_hyperparams(plugin)

    assert plugin.conf_threshold == 0.4
    assert plugin.nms_threshold == 0.6


def test_apply_hyperparams_skips_none_values(detector_service: DetectorService) -> None:
    detector_service.project_manager.project_data = {
        "model_overrides": {"confidence_threshold": None, "nms_threshold": 0.55},
    }
    plugin = FakePlugin(conf=0.25, nms=0.45)

    detector_service._apply_project_detector_hyperparams(plugin)

    assert plugin.conf_threshold == 0.25  # untouched
    assert plugin.nms_threshold == 0.55


def test_apply_hyperparams_rejects_out_of_range(detector_service: DetectorService) -> None:
    detector_service.project_manager.project_data = {
        "model_overrides": {"confidence_threshold": 2.0, "nms_threshold": -1.0},
    }
    plugin = FakePlugin(conf=0.25, nms=0.45)

    detector_service._apply_project_detector_hyperparams(plugin)

    # Both values out of [0, 1] → plugin attributes left at defaults.
    assert plugin.conf_threshold == 0.25
    assert plugin.nms_threshold == 0.45


def test_apply_hyperparams_handles_invalid_type(detector_service: DetectorService) -> None:
    detector_service.project_manager.project_data = {
        "model_overrides": {"confidence_threshold": "not-a-float"},
    }
    plugin = FakePlugin(conf=0.25)

    detector_service._apply_project_detector_hyperparams(plugin)

    assert plugin.conf_threshold == 0.25


def test_apply_hyperparams_no_project_data(detector_service: DetectorService) -> None:
    """When no project loaded, helper must be a no-op (no AttributeError)."""
    detector_service.project_manager.project_data = None
    plugin = FakePlugin()

    detector_service._apply_project_detector_hyperparams(plugin)  # should not raise

    assert plugin.conf_threshold == 0.25
    assert plugin.nms_threshold == 0.45


def test_apply_hyperparams_no_overrides_block(detector_service: DetectorService) -> None:
    detector_service.project_manager.project_data = {}
    plugin = FakePlugin()

    detector_service._apply_project_detector_hyperparams(plugin)

    assert plugin.conf_threshold == 0.25
    assert plugin.nms_threshold == 0.45


def test_apply_hyperparams_skips_unknown_attr_on_plugin(
    detector_service: DetectorService,
) -> None:
    """A plugin lacking conf_threshold attr must not raise — just be skipped."""
    detector_service.project_manager.project_data = {
        "model_overrides": {"confidence_threshold": 0.4},
    }

    class BarePlugin:
        pass

    plugin = BarePlugin()

    detector_service._apply_project_detector_hyperparams(plugin)  # no AttributeError

    assert not hasattr(plugin, "conf_threshold")
