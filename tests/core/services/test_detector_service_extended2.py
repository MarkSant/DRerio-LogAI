"""Extended unit tests for core/services/detector_service.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zebtrack.core.services.detector_service import (
    DEFAULT_MATCH_THRESHOLD,
    DEFAULT_TRACK_THRESHOLD,
    DetectorService,
)


class TestDetectorServiceThresholdsAndValidation:
    """Test DetectorService parameter validations, thresholds, and bounds checking."""

    def test_default_threshold_constants(self):
        assert DEFAULT_TRACK_THRESHOLD == 0.25
        assert DEFAULT_MATCH_THRESHOLD == 0.80

    def test_update_tracking_parameters_validates_conf_threshold_range(self):
        svc = DetectorService(
            state_manager=MagicMock(),
            project_manager=MagicMock(),
            weight_manager=MagicMock(),
            model_service=MagicMock(),
            settings_obj=MagicMock(),
        )

        with pytest.raises(ValueError, match="conf_threshold must be between 0.0 and 1.0"):
            svc.update_tracking_parameters(conf_threshold=1.5)

        with pytest.raises(ValueError, match="conf_threshold must be between 0.0 and 1.0"):
            svc.update_tracking_parameters(conf_threshold=-0.1)

    def test_update_tracking_parameters_validates_nms_threshold_range(self):
        svc = DetectorService(
            state_manager=MagicMock(),
            project_manager=MagicMock(),
            weight_manager=MagicMock(),
            model_service=MagicMock(),
            settings_obj=MagicMock(),
        )

        with pytest.raises(ValueError, match="nms_threshold must be between 0.0 and 1.0"):
            svc.update_tracking_parameters(nms_threshold=1.2)

    def test_update_tracking_parameters_validates_track_buffer(self):
        svc = DetectorService(
            state_manager=MagicMock(),
            project_manager=MagicMock(),
            weight_manager=MagicMock(),
            model_service=MagicMock(),
            settings_obj=MagicMock(),
        )

        with pytest.raises(ValueError, match="track_buffer must be at least 1"):
            svc.update_tracking_parameters(track_buffer=0)

        with pytest.raises(ValueError, match="track_buffer must be an integer"):
            svc.update_tracking_parameters(track_buffer="not_an_int")  # type: ignore[arg-type]

    def test_update_tracking_parameters_with_plugin(self):
        svc = DetectorService(
            state_manager=MagicMock(),
            project_manager=MagicMock(),
            weight_manager=MagicMock(),
            model_service=MagicMock(),
            settings_obj=MagicMock(),
        )
        mock_plugin = MagicMock()
        mock_plugin.conf_threshold = 0.25
        mock_plugin.nms_threshold = 0.45

        mock_detector = MagicMock()
        mock_detector.plugin = mock_plugin
        svc.detector = mock_detector

        result = svc.update_tracking_parameters(
            conf_threshold=0.6,
            nms_threshold=0.5,
            scope="global",
        )
        assert result is True
        assert mock_plugin.conf_threshold == 0.6
        assert mock_plugin.nms_threshold == 0.5
